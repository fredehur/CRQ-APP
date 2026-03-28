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
validation_state = {
    "running": False,
    "phase": None,
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


@app.get("/api/rsm/{region}/pdf")
async def get_rsm_brief_pdf(region: str, type: str = Query("intsum", pattern="^(flash|intsum)$")):
    """Export an RSM brief (FLASH or INTSUM) as a downloadable PDF."""
    import io
    import tempfile
    import os
    from fpdf import FPDF

    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    r_lower = r.lower()
    base = OUTPUT / "regional" / r_lower

    def _latest_md(pattern: str):
        if not base.exists():
            return None
        files = sorted(base.glob(pattern))
        return files[-1] if files else None

    if type == "flash":
        md_path = _latest_md(f"rsm_flash_{r_lower}_*.md")
        label = "FLASH"
    else:
        md_path = _latest_md(f"rsm_brief_{r_lower}_*.md")
        label = "INTSUM"

    if not md_path:
        return JSONResponse({"error": f"No {label} brief found for {r}"}, status_code=404)

    raw = md_path.read_text(encoding="utf-8", errors="replace")
    # Sanitize to latin-1 (fpdf2 core fonts); replace common symbols, strip rest
    _sym = {"⚡": "[FLASH]", "●": "*", "—": "-", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
    for k, v in _sym.items():
        raw = raw.replace(k, v)
    content = raw.encode("latin-1", errors="replace").decode("latin-1")

    # Render to PDF using fpdf2
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)        # must be set before add_page
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header bar
    pdf.set_fill_color(13, 17, 23)   # GitHub dark
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Courier", "B", 11)
    pdf.cell(0, 10, f"AEROWIND // {r} {label} // RESTRICTED", fill=True, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    # Body — monospaced, dark-on-white
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Courier", size=9)
    w = pdf.epw  # effective page width respects margins
    for line in content.splitlines():
        pdf.multi_cell(w, 4.5, line if line else " ")

    # Write to temp file and serve
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    try:
        pdf.output(tmp.name)
        filename = f"rsm_{label.lower()}_{r_lower}_{md_path.stem.split('_')[-1]}.pdf"
        return FileResponse(
            tmp.name,
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            background=None,
        )
    except Exception as e:
        os.unlink(tmp.name)
        return JSONResponse({"error": str(e)}, status_code=500)


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


@app.get("/api/trends")
async def get_trends():
    path = OUTPUT / "trend_analysis.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "no_data"}


@app.get("/api/review/{region}")
async def get_review(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=400)
    path = OUTPUT / "regional" / region.lower() / "review_status.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "draft"}


@app.put("/api/review/{region}")
async def put_review(region: str, body: dict):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=400)
    if "reviewer" not in body or "status" not in body:
        return JSONResponse({"error": "Body must include 'reviewer' and 'status'"}, status_code=422)
    if body["status"] not in ("published", "draft"):
        return JSONResponse({"error": "status must be 'published' or 'draft'"}, status_code=422)

    review = {
        "reviewer": body["reviewer"],
        "status": body["status"],
        "notes": body.get("notes", ""),
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    region_lower = region.lower()
    out_dir = OUTPUT / "regional" / region_lower
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "review_status.tmp"
    tmp.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_dir / "review_status.json")

    # Trigger audience card generation on publish if report exists
    if body["status"] == "published":
        report_path = out_dir / "report.md"
        if report_path.exists():
            asyncio.create_task(
                asyncio.create_subprocess_exec(
                    "uv", "run", "python", "tools/generate_audience_cards.py", r, "--mock",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            )
    return {"ok": True}


@app.get("/api/audience/{region}")
async def get_audience(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=400)
    path = OUTPUT / "regional" / region.lower() / "audience_cards.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


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


# ── API: Validation ──────────────────────────────────────────────────────
@app.get("/api/validation/flags")
async def get_validation_flags():
    data = _read_json(OUTPUT / "validation_flags.json")
    return data or {"status": "no_data", "scenarios": [], "summary": {}}


@app.get("/api/validation/sources")
async def get_validation_sources():
    path = BASE / "data" / "validation_sources.json"
    data = _read_json(path)
    return data or {"sources": []}


@app.get("/api/validation/candidates")
async def get_validation_candidates():
    data = _read_json(OUTPUT / "validation_candidates.json")
    return data or {"candidates": [], "generated_at": None}


@app.post("/api/validation/sources/add")
async def add_validation_source(body: dict):
    """Manually add a source to the trusted registry."""
    import re
    url = body.get("url", "").strip()
    name = body.get("name", "").strip()
    if not url or not name:
        return JSONResponse({"error": "url and name required"}, status_code=400)

    sources_path = BASE / "data" / "validation_sources.json"
    sources_data = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {"sources": []}
    if any(s["url"] == url for s in sources_data.get("sources", [])):
        return JSONResponse({"error": "Source URL already in registry"}, status_code=409)

    source_id = re.sub(r"[^a-z0-9]+", "-", name[:40].lower()).strip("-")
    new_source = {
        "id": source_id,
        "name": name,
        "url": url,
        "cadence": body.get("cadence", "annual"),
        "admiralty_reliability": "C",
        "sector_tags": body.get("sector_tags", []),
        "scenario_tags": body.get("scenario_tags", []),
        "last_checked": None,
        "last_new_content": None,
    }
    sources_data["sources"].append(new_source)
    _write_json_atomic(sources_path, sources_data)
    return {"ok": True, "source_id": source_id}


@app.delete("/api/validation/sources/{source_id}")
async def delete_validation_source(source_id: str):
    sources_path = BASE / "data" / "validation_sources.json"
    if not sources_path.exists():
        return JSONResponse({"error": "No sources file"}, status_code=404)
    sources_data = json.loads(sources_path.read_text(encoding="utf-8"))
    original = sources_data.get("sources", [])
    filtered = [s for s in original if s["id"] != source_id]
    if len(filtered) == len(original):
        return JSONResponse({"error": f"Source not found: {source_id}"}, status_code=404)
    sources_data["sources"] = filtered
    _write_json_atomic(sources_path, sources_data)
    return {"ok": True, "deleted": source_id}


@app.post("/api/validation/promote")
async def promote_candidate(body: dict):
    """Promote a discovered candidate into the trusted source registry."""
    import os
    url = body.get("url", "").strip()
    if not url:
        return JSONResponse({"error": "url required"}, status_code=400)

    # Load candidates, mark as promoted
    cands_path = OUTPUT / "validation_candidates.json"
    if not cands_path.exists():
        return JSONResponse({"error": "No candidates file"}, status_code=404)
    cands_data = json.loads(cands_path.read_text(encoding="utf-8"))
    candidate = next((c for c in cands_data.get("candidates", []) if c.get("url") == url), None)
    if not candidate:
        return JSONResponse({"error": "Candidate not found"}, status_code=404)

    # Build new source entry
    import re
    source_id = re.sub(r"[^a-z0-9]+", "-", (candidate.get("title", url)[:40]).lower()).strip("-")
    new_source = {
        "id": source_id,
        "name": candidate.get("title", url)[:80],
        "url": url,
        "cadence": "unknown",
        "admiralty_reliability": "C",
        "sector_tags": candidate.get("sector_tags", []),
        "scenario_tags": candidate.get("scenario_tags", []),
        "last_checked": None,
        "last_new_content": None,
    }

    # Append to validation_sources.json
    sources_path = BASE / "data" / "validation_sources.json"
    sources_data = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {"sources": []}
    # Guard against duplicates
    existing_urls = {s["url"] for s in sources_data.get("sources", [])}
    if url in existing_urls:
        return JSONResponse({"error": "Source already in registry"}, status_code=409)
    sources_data["sources"].append(new_source)
    _write_json_atomic(sources_path, sources_data)

    # Mark candidate as promoted
    for c in cands_data.get("candidates", []):
        if c.get("url") == url:
            c["status"] = "promoted"
    _write_json_atomic(cands_path, cands_data)

    return {"ok": True, "source_id": source_id}


async def _run_validation():
    """Run the 4-script validation chain. Emits SSE events."""
    validation_state.update(running=True, phase="harvesting", started_at=time.time())
    await _emit("validation", {"status": "started"})
    try:
        await _emit("validation", {"status": "step", "step": "source_harvester", "message": "Fetching known sources..."})
        rc = await _run("source_harvester.py", timeout=120)
        if rc != 0:
            await _emit("validation", {"status": "error", "step": "source_harvester"})
            return

        await _emit("validation", {"status": "step", "step": "source_discoverer", "message": "Discovering new sources..."})
        rc = await _run("source_discoverer.py", timeout=120)
        if rc != 0:
            await _emit("validation", {"status": "error", "step": "source_discoverer"})
            return

        await _emit("validation", {"status": "step", "step": "benchmark_extractor", "message": "Extracting benchmarks..."})
        rc = await _run("benchmark_extractor.py", timeout=180)
        if rc != 0:
            await _emit("validation", {"status": "error", "step": "benchmark_extractor"})
            return

        await _emit("validation", {"status": "step", "step": "crq_comparator", "message": "Comparing VaCR figures..."})
        rc = await _run("crq_comparator.py", timeout=60)
        if rc != 0:
            await _emit("validation", {"status": "error", "step": "crq_comparator"})
            return

        await _emit("validation", {"status": "complete"})
    except Exception as exc:
        log.exception("Validation run failed")
        await _emit("validation", {"status": "error", "message": str(exc)})
    finally:
        validation_state.update(running=False, phase=None)


@app.post("/api/run/validate")
async def run_validate():
    if validation_state["running"]:
        return JSONResponse({"error": "Validation already running"}, status_code=409)
    if pipeline_state["running"]:
        return JSONResponse({"error": "Main pipeline is running — try again after it completes"}, status_code=409)
    asyncio.create_task(_run_validation())
    return {"started": True}


@app.get("/api/validation/status")
async def get_validation_status():
    return validation_state


# ── Static Files ─────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(BASE / "static" / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
