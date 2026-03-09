"""CRQ Command Center — FastAPI backend."""

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

app = FastAPI(title="CRQ Command Center")

# ── State ────────────────────────────────────────────────────────────────
pipeline_state = {
    "running": False,
    "phase": None,
    "regions_pending": [],
    "regions_done": [],
    "started_at": None,
}
event_queue: asyncio.Queue = asyncio.Queue()


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ── API: Data ────────────────────────────────────────────────────────────
@app.get("/api/manifest")
async def get_manifest():
    data = _read_json(OUTPUT / "run_manifest.json")
    return data or {"status": "no_data"}


@app.get("/api/region/{region}")
async def get_region(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    data = _read_json(OUTPUT / "regional" / r.lower() / "data.json")
    return data or {"region": r, "status": "no_data"}


@app.get("/api/region/{region}/report")
async def get_region_report(region: str):
    r = region.upper()
    path = OUTPUT / "regional" / r.lower() / "report.md"
    if path.exists():
        return {"region": r, "report": path.read_text(encoding="utf-8")}
    return {"region": r, "report": None}


@app.get("/api/global-report")
async def get_global_report():
    data = _read_json(OUTPUT / "global_report.json")
    return data or {"status": "no_data"}


@app.get("/api/status")
async def get_status():
    return pipeline_state


@app.get("/api/runs")
async def list_runs():
    runs_dir = OUTPUT / "runs"
    if not runs_dir.exists():
        return []
    runs = []
    for d in sorted(runs_dir.iterdir(), reverse=True):
        if d.is_dir():
            manifest = _read_json(d / "run_manifest.json")
            runs.append({
                "name": d.name,
                "manifest": manifest,
            })
    return runs


@app.get("/api/trace")
async def get_trace():
    path = OUTPUT / "system_trace.log"
    if path.exists():
        return {"log": path.read_text(encoding="utf-8", errors="replace")}
    return {"log": ""}


# ── API: Run Pipeline ────────────────────────────────────────────────────
async def _emit(event: str, data: dict):
    """Push a structured SSE event."""
    await event_queue.put({"event": event, "data": json.dumps(data)})


async def _run_tools_mode(regions: list[str]):
    """Drive layer: tools-only mode — runs Python scripts directly."""
    pipeline_state.update(running=True, phase="gatekeeper", regions_pending=list(regions), regions_done=[], started_at=time.time())
    await _emit("pipeline", {"status": "started", "regions": regions})

    # Phase 1-2: Gatekeeper + regional analysis
    for r in regions:
        await _emit("phase", {"phase": "gatekeeper", "region": r})
        proc = await asyncio.create_subprocess_exec(
            "uv", "run", "python", str(BASE / "tools" / "regional_search.py"), r, "--mock",
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        proc = await asyncio.create_subprocess_exec(
            "uv", "run", "python", str(BASE / "tools" / "threat_scorer.py"), r,
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        score_output = stdout.decode().strip()

        # Read the feed to determine gatekeeper decision
        feed = _read_json(BASE / "data" / "mock_threat_feeds" / f"{r.lower()}_feed.json")
        severity = feed.get("severity", "LOW") if feed else "LOW"
        decision = "YES" if severity in ("HIGH", "CRITICAL", "MEDIUM") else "NO"

        await _emit("gatekeeper", {"region": r, "decision": decision, "severity": severity})

        # Write data.json
        status = "escalated" if decision == "YES" else "clear"
        proc = await asyncio.create_subprocess_exec(
            "uv", "run", "python", str(BASE / "tools" / "write_region_data.py"), r, status,
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        # Log gatekeeper event
        event_type = "GATEKEEPER_YES" if decision == "YES" else "GATEKEEPER_NO"
        msg = f"{r} — {'threat confirmed, escalating' if decision == 'YES' else 'no active threat, skipped'}"
        await asyncio.create_subprocess_exec(
            "uv", "run", "python", str(BASE / "tools" / "audit_logger.py"), event_type, msg,
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

        pipeline_state["regions_done"].append(r)
        pipeline_state["regions_pending"] = [x for x in pipeline_state["regions_pending"] if x != r]

    await _emit("phase", {"phase": "gatekeeper", "status": "complete"})

    # Phase 3: Cross-regional diff
    pipeline_state["phase"] = "diff"
    await _emit("phase", {"phase": "diff", "status": "running"})
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "report_differ.py"),
        cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    await _emit("phase", {"phase": "diff", "status": "complete"})

    # Phase 4: Write manifest
    pipeline_state["phase"] = "manifest"
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "write_manifest.py"),
        cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()

    # Phase 5: Build dashboard
    pipeline_state["phase"] = "dashboard"
    await _emit("phase", {"phase": "dashboard", "status": "running"})
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "build_dashboard.py"),
        cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.wait()
    await _emit("phase", {"phase": "dashboard", "status": "complete"})

    pipeline_state.update(running=False, phase="complete")
    await _emit("pipeline", {"status": "complete"})


async def _run_full_mode(regions: list[str]):
    """Drive layer: full mode — shells out to claude CLI for real LLM analysis."""
    pipeline_state.update(running=True, phase="running", regions_pending=list(regions), regions_done=[], started_at=time.time())
    await _emit("pipeline", {"status": "started", "mode": "full", "regions": regions})

    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "/run-crq",
        cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )

    # Stream stdout lines as log events
    async for line in proc.stdout:
        text = line.decode(errors="replace").strip()
        if text:
            await _emit("log", {"message": text})

    await proc.wait()
    pipeline_state.update(running=False, phase="complete")
    await _emit("pipeline", {"status": "complete"})


@app.post("/api/run/all")
async def run_all(mode: str = Query(default="tools")):
    if pipeline_state["running"]:
        return JSONResponse({"error": "Pipeline already running"}, status_code=409)
    driver = _run_full_mode if mode == "full" else _run_tools_mode
    asyncio.create_task(driver(REGIONS))
    return {"started": True, "mode": mode, "regions": REGIONS}


@app.post("/api/run/region/{region}")
async def run_region(region: str, mode: str = Query(default="tools")):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    if pipeline_state["running"]:
        return JSONResponse({"error": "Pipeline already running"}, status_code=409)
    driver = _run_full_mode if mode == "full" else _run_tools_mode
    asyncio.create_task(driver([r]))
    return {"started": True, "mode": mode, "regions": [r]}


# ── SSE Stream ───────────────────────────────────────────────────────────
@app.get("/api/logs/stream")
async def logs_stream():
    async def generate():
        while True:
            try:
                msg = await asyncio.wait_for(event_queue.get(), timeout=30)
                yield msg
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}

    return EventSourceResponse(generate())


# ── Static Files ─────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(BASE / "static" / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
