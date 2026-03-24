"""CRQ Command Center — FastAPI backend."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Literal, Optional

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


@app.get("/api/rsm/status")
async def get_rsm_status():
    """Lightweight check — returns boolean flags for each region. No file content read."""
    result = {}
    for region in REGIONS:
        r = region.lower()
        base = OUTPUT / "regional" / r
        intsum_files = list(base.glob(f"rsm_brief_{r}_*.md")) if base.exists() else []
        flash_files  = list(base.glob(f"rsm_flash_{r}_*.md"))  if base.exists() else []
        result[region] = {
            "has_intsum": len(intsum_files) > 0,
            "has_flash":  len(flash_files)  > 0,
        }
    return result


@app.get("/api/rsm/{region}")
async def get_rsm_brief(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    r_lower = r.lower()
    base = OUTPUT / "regional" / r_lower

    def _latest_md(pattern: str) -> str | None:
        if not base.exists():
            return None
        files = sorted(base.glob(pattern))  # ISO date filenames sort lexicographically
        if not files:
            return None
        return files[-1].read_text(encoding="utf-8", errors="replace")

    return {
        "region": r,
        "intsum": _latest_md(f"rsm_brief_{r_lower}_*.md"),
        "flash":  _latest_md(f"rsm_flash_{r_lower}_*.md"),
    }


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


@app.get("/api/history")
async def get_history():
    """Return history.json for the History tab charts."""
    path = OUTPUT / "history.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"regions": {r: [] for r in REGIONS}, "drift": {}, "generated_at": None}


@app.get("/api/footprint")
async def get_footprint():
    """Return full regional_footprint.json."""
    path = Path("data/regional_footprint.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@app.put("/api/footprint/{region}")
async def update_footprint(region: str, body: dict):
    """Update four editable fields for one region. Atomic write."""
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=400)

    path = Path("data/regional_footprint.json")
    if not path.exists():
        return JSONResponse({"error": "regional_footprint.json not found"}, status_code=500)

    footprint = json.loads(path.read_text(encoding="utf-8"))

    if r not in footprint:
        return JSONResponse({"error": f"Region {r} not in footprint file"}, status_code=404)

    entry = footprint[r]
    if "summary" in body:
        entry["summary"] = body["summary"]
    if "headcount" in body:
        entry["headcount"] = int(body["headcount"])
    if "notes" in body:
        entry["notes"] = body["notes"]
    if "rsm_email" in body:
        rsm_role = f"{r} RSM"
        for stakeholder in entry.get("stakeholders", []):
            if stakeholder.get("role") == rsm_role:
                stakeholder["email"] = body["rsm_email"]
                break

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(footprint, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return {"ok": True}


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


@app.get("/api/region/{region}/clusters")
async def get_region_clusters(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    data = _read_json(OUTPUT / "regional" / r.lower() / "signal_clusters.json")
    if data is None:
        return {"region": r, "clusters": [], "total_signals": 0, "sources_queried": 0, "status": "no_data"}
    return data


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


# ── API: Config ───────────────────────────────────────────────────────
def _write_json_atomic(path: Path, data) -> None:
    """Write JSON atomically via tmp file + os.replace."""
    import os
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


@app.get("/api/config/topics")
async def get_topics():
    path = BASE / "data" / "osint_topics.json"   # inline — do not extract to module constant
    raw = path.read_text(encoding="utf-8") if path.exists() else "[]"
    return json.loads(raw)


@app.post("/api/config/topics")
async def post_topics(body: dict):
    topics = body.get("topics")
    if not isinstance(topics, list):
        return JSONResponse({"error": "topics must be an array"}, status_code=400)
    _write_json_atomic(BASE / "data" / "osint_topics.json", topics)
    return {"ok": True}


@app.get("/api/config/sources")
async def get_sources():
    path = BASE / "data" / "youtube_sources.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/config/sources")
async def post_sources(body: dict):
    sources = body.get("sources")
    if not isinstance(sources, list):
        return JSONResponse({"error": "sources must be an array"}, status_code=400)
    _write_json_atomic(BASE / "data" / "youtube_sources.json", sources)
    return {"ok": True}


def _parse_agent_md(path: Path) -> dict:
    """Split agent .md into frontmatter object + body string."""
    import re
    content = path.read_text(encoding="utf-8")
    # Match --- block at start of file
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not m:
        return {"frontmatter": {}, "body": content, "_frontmatter_raw": ""}
    fm_raw = m.group(1)
    body = m.group(2)
    # Parse YAML frontmatter keys into dict (simple key: value, no nested support needed)
    fm = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return {"frontmatter": fm, "body": body, "_frontmatter_raw": fm_raw}


def _get_agent_allowlist() -> list[str]:
    """Return sorted list of agent stems from .claude/agents/*.md"""
    agents_dir = BASE / ".claude" / "agents"
    if not agents_dir.exists():
        return []
    return sorted(p.stem for p in agents_dir.glob("*.md"))


@app.get("/api/config/prompts")
async def get_prompts():
    agents = []
    for stem in _get_agent_allowlist():
        path = BASE / ".claude" / "agents" / f"{stem}.md"
        parsed = _parse_agent_md(path)
        agents.append({"agent": stem, "frontmatter": parsed["frontmatter"], "body": parsed["body"]})
    return agents


@app.post("/api/config/prompts/{agent}")
async def post_prompt(agent: str, body: dict):
    import os
    allowlist = _get_agent_allowlist()
    if agent not in allowlist:
        return JSONResponse({"error": f"Unknown agent: {agent}"}, status_code=400)
    new_body = body.get("body", "")
    path = BASE / ".claude" / "agents" / f"{agent}.md"
    parsed = _parse_agent_md(path)
    # Reconstruct file: original frontmatter block preserved verbatim
    new_content = f"---\n{parsed['_frontmatter_raw']}\n---\n{new_body}"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(tmp, path)
    return {"ok": True}


# ── API: Discovery ───────────────────────────────────────────────────────
@app.post("/api/discover/topics")
async def discover_topics(body: dict):
    query = body.get("query", "").strip()
    depth = body.get("depth", "quick")
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "discover.py"),
        "topics", query, f"--depth={depth}",
        cwd=str(BASE),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    if proc.returncode != 0:
        return JSONResponse({"error": stderr.decode(errors="replace")[:300]}, status_code=500)
    return JSONResponse(json.loads(stdout.decode(errors="replace")))


@app.post("/api/discover/sources")
async def discover_sources(body: dict):
    query = body.get("query", "").strip()
    depth = body.get("depth", "quick")
    if not query:
        return JSONResponse({"error": "query required"}, status_code=400)
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "discover.py"),
        "sources", query, f"--depth={depth}",
        cwd=str(BASE),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    if proc.returncode != 0:
        return JSONResponse({"error": stderr.decode(errors="replace")[:300]}, status_code=500)
    return JSONResponse(json.loads(stdout.decode(errors="replace")))


@app.get("/api/discover/suggestions")
async def get_suggestions():
    path = OUTPUT / "config_suggestions.json"
    if not path.exists():
        return {"topics": [], "sources": [], "generated_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"topics": [], "sources": [], "generated_at": None}


# ── API: Feedback ────────────────────────────────────────────────────────
@app.get("/api/feedback/{run_id}")
async def get_feedback(run_id: str):
    """Return feedback entries for a pipeline run."""
    runs_dir = BASE / "output" / "runs"
    if not runs_dir.exists():
        return JSONResponse({"error": f"Run not found: {run_id}"}, status_code=404)
    for folder in sorted(runs_dir.iterdir()):
        manifest_path = folder / "run_manifest.json"
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            if m.get("pipeline_id") == run_id:
                fb_path = folder / "feedback.json"
                if fb_path.exists():
                    return json.loads(fb_path.read_text(encoding="utf-8"))
                return []
    return JSONResponse({"error": f"Run not found: {run_id}"}, status_code=404)


@app.post("/api/feedback/{run_id}")
async def post_feedback(run_id: str, body: dict):
    """Append a feedback entry for a pipeline run."""
    VALID_RATINGS = {"accurate", "overstated", "understated", "false_positive"}
    VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE", "global"}

    region = body.get("region", "")
    rating = body.get("rating", "")
    if region not in VALID_REGIONS:
        return JSONResponse({"error": f"Invalid region: {region}"}, status_code=400)
    if rating not in VALID_RATINGS:
        return JSONResponse({"error": f"Invalid rating: {rating}"}, status_code=400)

    from datetime import datetime, timezone
    entry = {
        "region": region,
        "rating": rating,
        "note": body.get("note", ""),
        "analyst": body.get("analyst", "anonymous"),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    runs_dir = BASE / "output" / "runs"
    if runs_dir.exists():
        for folder in sorted(runs_dir.iterdir()):
            manifest_path = folder / "run_manifest.json"
            if manifest_path.exists():
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                if m.get("pipeline_id") == run_id:
                    fb_path = folder / "feedback.json"
                    existing = json.loads(fb_path.read_text(encoding="utf-8")) if fb_path.exists() else []
                    existing.append(entry)
                    _write_json_atomic(fb_path, existing)
                    return {"ok": True, "entry": entry}

    return JSONResponse({"error": f"Run not found: {run_id}"}, status_code=404)


# ── API: Run Pipeline ────────────────────────────────────────────────────
async def _emit(event: str, data: dict):
    """Push a structured SSE event. Drops oldest if queue is full."""
    if event_queue.full():
        try:
            event_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    await event_queue.put({"event": event, "data": json.dumps(data)})


async def _run_full_mode(regions: list[str], window: str = "7d"):
    """Drive layer: full mode — shells out to claude CLI for real LLM analysis."""
    pipeline_state.update(running=True, phase="running", regions_pending=list(regions), regions_done=[], started_at=time.time())
    await _emit("pipeline", {"status": "started", "mode": "full", "regions": regions})

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", f"/run-crq --window {window}",
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

        # Stream stdout lines as log events, parsing structured markers
        async def stream_with_timeout():
            async for line in proc.stdout:
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                # Emit raw log for all lines
                await _emit("log", {"line": text})
                # Parse structured events from known output patterns
                # GATEKEEPER: lines like "APAC — ESCALATE (B2, HIGH, ...)"  or  "`APAC — CLEAR`"
                import re
                gk = re.search(r'`?([A-Z]{2,5})\s*[—-]+\s*(ESCALATE|MONITOR|CLEAR)', text)
                if gk:
                    region, decision = gk.group(1), gk.group(2)
                    await _emit("gatekeeper", {"region": region, "decision": decision})
                    if decision in ("ESCALATE", "MONITOR", "CLEAR"):
                        rd = pipeline_state["regions_done"]
                        if region not in rd:
                            rd.append(region)
                        pending = pipeline_state["regions_pending"]
                        if region in pending:
                            pipeline_state["regions_pending"] = [x for x in pending if x != region]
                    continue
                # PHASE markers: lines like "PIPELINE_START", "PHASE_COMPLETE", "PIPELINE_COMPLETE"
                phase = re.search(r'\[(PIPELINE_START|PIPELINE_COMPLETE|PHASE_COMPLETE|GATEKEEPER_YES|GATEKEEPER_NO|HOOK_PASS|HOOK_FAIL)\]', text)
                if phase:
                    await _emit("phase", {"phase": phase.group(1), "message": text})
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
async def run_all(
    window: Literal["1d", "7d", "30d", "90d"] = Query(default="7d"),
):
    if pipeline_state["running"]:
        return JSONResponse({"error": "Pipeline already running"}, status_code=409)
    asyncio.create_task(_run_full_mode(REGIONS, window=window))
    return {"started": True, "regions": REGIONS, "window": window}


@app.post("/api/run/region/{region}")
async def run_region(
    region: str,
    window: Literal["1d", "7d", "30d", "90d"] = Query(default="7d"),
):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    if pipeline_state["running"]:
        return JSONResponse({"error": "Pipeline already running"}, status_code=409)
    asyncio.create_task(_run_full_mode([r], window=window))
    return {"started": True, "regions": [r], "window": window}


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
