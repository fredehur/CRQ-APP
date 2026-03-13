"""CRQ Command Center — FastAPI backend."""

import asyncio
import json
import logging
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
TOOL_TIMEOUT = 60  # seconds per subprocess
FULL_MODE_TIMEOUT = 600  # 10 min for claude CLI

log = logging.getLogger("crq")
app = FastAPI(title="CRQ Command Center")

# ── State ────────────────────────────────────────────────────────────────
pipeline_state = {
    "running": False,
    "phase": None,
    "regions_pending": [],
    "regions_done": [],
    "started_at": None,
}
event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ── Subprocess Helper ────────────────────────────────────────────────────
async def _run(tool: str, *args, timeout: int = TOOL_TIMEOUT) -> int:
    """Run a Python tool script with timeout. Returns exit code."""
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / tool), *args,
        cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        log.error("Tool %s timed out after %ds", tool, timeout)
        await _emit("error", {"tool": tool, "message": f"Timed out after {timeout}s"})
        return -1
    if proc.returncode != 0:
        stderr = (await proc.stderr.read()).decode(errors="replace").strip()
        log.warning("Tool %s exited %d: %s", tool, proc.returncode, stderr)
        await _emit("error", {"tool": tool, "exit_code": proc.returncode, "message": stderr[:200]})
    return proc.returncode


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


@app.get("/api/region/{region}/signals")
async def get_region_signals(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    base = OUTPUT / "regional" / r.lower()
    return {
        "geo": _read_json(base / "geo_signals.json"),
        "cyber": _read_json(base / "cyber_signals.json"),
    }


@app.get("/api/outputs/global-md")
async def get_global_md():
    path = OUTPUT / "global_report.md"
    return {"markdown": path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""}


@app.get("/api/outputs/pdf")
async def get_pdf():
    path = OUTPUT / "board_report.pdf"
    if not path.exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    return FileResponse(str(path), media_type="application/pdf",
                        filename="board_report.pdf")


@app.get("/api/outputs/pptx")
async def get_pptx():
    path = OUTPUT / "board_report.pptx"
    if not path.exists():
        return JSONResponse({"error": "PPTX not found"}, status_code=404)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="board_report.pptx",
    )


# ── API: Run Pipeline ────────────────────────────────────────────────────
async def _emit(event: str, data: dict):
    """Push a structured SSE event. Drops oldest if queue is full."""
    if event_queue.full():
        try:
            event_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    await event_queue.put({"event": event, "data": json.dumps(data)})


async def _run_tools_mode(regions: list[str]):
    """Drive layer: tools-only mode — runs Python scripts directly."""
    pipeline_state.update(running=True, phase="gatekeeper", regions_pending=list(regions), regions_done=[], started_at=time.time())
    await _emit("pipeline", {"status": "started", "regions": regions})

    try:
        # Phase 1-2: Gatekeeper + regional analysis
        for r in regions:
            await _emit("phase", {"phase": "gatekeeper", "region": r})
            await _run("regional_search.py", r, "--mock")
            await _run("threat_scorer.py", r)

            # Read the feed to determine gatekeeper decision
            TOP_4_SCENARIOS = {"Ransomware", "Accidental disclosure", "System intrusion", "Insider misuse"}
            feed = _read_json(BASE / "data" / "mock_threat_feeds" / f"{r.lower()}_feed.json")
            active = feed.get("active_threats", False) if feed else False
            severity = feed.get("severity", "LOW") if feed else "LOW"
            scenario = feed.get("primary_scenario", "None") if feed else "None"

            if not active:
                status = "clear"
                decision = "CLEAR"
            elif scenario in TOP_4_SCENARIOS:
                status = "escalated"
                decision = "ESCALATE"
            else:
                status = "monitor"
                decision = "MONITOR"

            await _emit("gatekeeper", {"region": r, "decision": decision, "severity": severity})

            # Write data.json
            await _run("write_region_data.py", r, status)

            # Log gatekeeper event
            event_type = "GATEKEEPER_YES" if status == "escalated" else "GATEKEEPER_NO"
            msg = f"{r} — {decision.lower()}: {scenario}"
            await _run("audit_logger.py", event_type, msg)

            pipeline_state["regions_done"].append(r)
            pipeline_state["regions_pending"] = [x for x in pipeline_state["regions_pending"] if x != r]

        await _emit("phase", {"phase": "gatekeeper", "status": "complete"})

        # Phase 2: Velocity analysis
        pipeline_state["phase"] = "trend"
        await _emit("phase", {"phase": "trend", "status": "running"})
        await _run("trend_analyzer.py")
        await _emit("phase", {"phase": "trend", "status": "complete"})

        # Phase 3: Cross-regional diff
        pipeline_state["phase"] = "diff"
        await _emit("phase", {"phase": "diff", "status": "running"})
        await _run("report_differ.py")
        await _emit("phase", {"phase": "diff", "status": "complete"})

        # Phase 4: Write manifest
        pipeline_state["phase"] = "manifest"
        await _run("write_manifest.py")

        # Phase 5: Build dashboard
        pipeline_state["phase"] = "dashboard"
        await _emit("phase", {"phase": "dashboard", "status": "running"})
        await _run("build_dashboard.py")
        await _emit("phase", {"phase": "dashboard", "status": "complete"})

        pipeline_state["phase"] = "complete"
        await _emit("pipeline", {"status": "complete"})

    except Exception as exc:
        log.exception("Pipeline failed")
        await _emit("pipeline", {"status": "error", "message": str(exc)})
    finally:
        pipeline_state.update(running=False)


async def _run_full_mode(regions: list[str]):
    """Drive layer: full mode — shells out to claude CLI for real LLM analysis."""
    pipeline_state.update(running=True, phase="running", regions_pending=list(regions), regions_done=[], started_at=time.time())
    await _emit("pipeline", {"status": "started", "mode": "full", "regions": regions})

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "/run-crq",
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

        # Stream stdout lines as log events
        async def stream_with_timeout():
            async for line in proc.stdout:
                text = line.decode(errors="replace").strip()
                if text:
                    await _emit("log", {"message": text})
            await proc.wait()

        try:
            await asyncio.wait_for(stream_with_timeout(), timeout=FULL_MODE_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            await _emit("pipeline", {"status": "error", "message": f"Claude CLI timed out after {FULL_MODE_TIMEOUT}s"})
            return

        pipeline_state["phase"] = "complete"
        await _emit("pipeline", {"status": "complete"})

    except Exception as exc:
        log.exception("Full-mode pipeline failed")
        await _emit("pipeline", {"status": "error", "message": str(exc)})
    finally:
        pipeline_state.update(running=False)


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
