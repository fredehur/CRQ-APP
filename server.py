"""CRQ Command Center — FastAPI backend."""

import asyncio
import datetime
import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

BASE = Path(__file__).resolve().parent
OUTPUT        = BASE / "output"
DELIVERABLES  = OUTPUT / "deliverables"
PIPELINE      = OUTPUT / "pipeline"
VALIDATION    = OUTPUT / "validation"
LOGS          = OUTPUT / "logs"
REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]
REGISTERS_DIR    = BASE / "data" / "registers"
ACTIVE_REGISTER  = BASE / "data" / "active_register.json"
SOURCES_DB = "data/sources.db"
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
threat_landscape_state = {
    "running": False,
    "started_at": None,
}
research_state = {
    "running": False,
    "progress": [],   # list of {incident_type, status: "running"|"done"|"error"}
    "started_at": None,
}
event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_run_log: dict = {"status": "no_run", "timestamp": None, "duration_seconds": None, "regions": {}}


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _active_register_id() -> str:
    data = _read_json(ACTIVE_REGISTER)
    return data.get("register_id", "aerogrid_enterprise") if data else "aerogrid_enterprise"


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
    data = _read_json(PIPELINE / "run_manifest.json")
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


# ── API: Registers ──────────────────────────────────────────────────────
@app.get("/api/registers")
async def list_registers():
    REGISTERS_DIR.mkdir(parents=True, exist_ok=True)
    active_id = _active_register_id()
    registers = []
    for f in sorted(REGISTERS_DIR.glob("*.json")):
        data = _read_json(f)
        if data:
            data["is_active"] = data.get("register_id") == active_id
            registers.append(data)
    return registers


@app.post("/api/registers")
async def create_register(payload: dict):
    register_id = payload.get("register_id", "").strip()
    if not register_id:
        return JSONResponse({"error": "register_id required"}, status_code=400)
    path = REGISTERS_DIR / f"{register_id}.json"
    if path.exists():
        return JSONResponse({"error": f"Register '{register_id}' already exists"}, status_code=409)
    REGISTERS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


@app.put("/api/registers/{register_id}")
async def update_register(register_id: str, payload: dict):
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    payload["register_id"] = register_id
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


@app.delete("/api/registers/{register_id}")
async def delete_register(register_id: str):
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    if _active_register_id() == register_id:
        return JSONResponse({"error": "Cannot delete the active register"}, status_code=409)
    path.unlink()
    return {"deleted": register_id}


@app.patch("/api/registers/{register_id}/scenarios/{scenario_id}")
async def patch_scenario(register_id: str, scenario_id: str, payload: dict):
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    data = _read_json(path)
    if not data:
        return JSONResponse({"error": "Register file corrupt"}, status_code=500)
    scenarios = data.get("scenarios", [])
    for i, s in enumerate(scenarios):
        if s.get("scenario_id") == scenario_id:
            if "value_at_cyber_risk_usd" in payload:
                scenarios[i]["value_at_cyber_risk_usd"] = int(payload["value_at_cyber_risk_usd"])
            if "probability_pct" in payload:
                scenarios[i]["probability_pct"] = float(payload["probability_pct"])
            if "description" in payload:
                scenarios[i]["description"] = str(payload["description"]).strip()
            data["scenarios"] = scenarios
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return scenarios[i]
    return JSONResponse({"error": f"Scenario '{scenario_id}' not found"}, status_code=404)


@app.get("/api/registers/active")
async def get_active_register():
    active_id = _active_register_id()
    path = REGISTERS_DIR / f"{active_id}.json"
    data = _read_json(path)
    return data or {"error": "active register file not found", "register_id": active_id}


@app.post("/api/registers/active")
async def set_active_register(payload: dict):
    register_id = payload.get("register_id", "").strip()
    if not register_id:
        return JSONResponse({"error": "register_id required"}, status_code=400)
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    ACTIVE_REGISTER.write_text(json.dumps({"register_id": register_id}), encoding="utf-8")
    return {"active": register_id}


@app.post("/api/registers/suggest-tags")
async def suggest_register_tags(payload: dict):
    name = payload.get("name", "").strip()
    description = payload.get("description", "").strip()
    if not name or not description:
        return JSONResponse({"error": "name and description required"}, status_code=400)
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "suggest_tags.py"),
        "--name", name, "--description", description,
        cwd=str(BASE),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return JSONResponse({"error": stderr.decode(errors="replace")[:200]}, status_code=500)
    try:
        tags = json.loads(stdout.decode().strip())
        return {"tags": tags}
    except json.JSONDecodeError:
        return JSONResponse({"error": "tag suggestion returned invalid JSON"}, status_code=500)


@app.get("/api/global-report")
async def get_global_report():
    data = _read_json(PIPELINE / "global_report.json")
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
    path = PIPELINE / "history.json"
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
    path = PIPELINE / "trend_analysis.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "no_data"}


@app.get("/api/threat-landscape")
async def get_threat_landscape():
    path = PIPELINE / "threat_landscape.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "no_data"}


@app.post("/api/run-threat-landscape")
async def run_threat_landscape():
    if threat_landscape_state["running"]:
        return {"status": "already_running"}
    threat_landscape_state["running"] = True
    threat_landscape_state["started_at"] = time.time()
    asyncio.create_task(_run_threat_landscape())
    return {"status": "running"}


async def _run_threat_landscape():
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--agent", ".claude/agents/threat-landscape-agent.md",
            "--message", (
                "Read all output/runs/*/regional/*/data.json and sections.json files. "
                "Synthesize longitudinal patterns. Write output/pipeline/threat_landscape.json "
                "per your instructions."
            ),
            "--allowedTools", "Bash,Write,Read",
            "--model", "sonnet",
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=FULL_MODE_TIMEOUT)
    except Exception as e:
        log.error("threat-landscape-agent failed: %s", e)
    finally:
        threat_landscape_state["running"] = False


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
    path = LOGS / "system_trace.log"
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


@app.get("/api/region/{region}/sections")
async def get_region_sections(region: str):
    path = OUTPUT / "regional" / region.lower() / "sections.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@app.get("/api/region/{region}/sources")
async def get_region_sources(region: str):
    """Aggregate sources from geo_signals.json and cyber_signals.json for a region."""
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    base = OUTPUT / "regional" / r.lower()
    sources = []
    for fname in ("geo_signals.json", "cyber_signals.json"):
        data = _read_json(base / fname)
        if data and isinstance(data.get("sources"), list):
            for s in data["sources"]:
                if isinstance(s, dict) and s.get("name"):
                    sources.append({"name": s["name"], "url": s.get("url", "")})
    return {"region": r, "sources": sources}


@app.get("/api/outputs/global-md")
async def get_global_md():
    path = PIPELINE / "global_report.md"
    return {"markdown": path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""}


@app.get("/api/outputs/pdf")
async def get_pdf():
    path = DELIVERABLES / "board_report.pdf"
    if not path.exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    return FileResponse(str(path), media_type="application/pdf",
                        filename="board_report.pdf")


@app.get("/api/outputs/pptx")
async def get_pptx():
    path = DELIVERABLES / "board_report.pptx"
    if not path.exists():
        return JSONResponse({"error": "PPTX not found"}, status_code=404)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="board_report.pptx",
    )


@app.get("/api/outputs/ciso-docx")
async def get_ciso_docx():
    """Generate (or serve cached) CISO weekly brief as a Word document."""
    import subprocess
    out_path = DELIVERABLES / "ciso_brief.docx"
    result = subprocess.run(
        ["uv", "run", "python", "tools/export_ciso_docx.py", str(out_path)],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0 or not out_path.exists():
        return JSONResponse({"error": result.stderr or "Export failed"}, status_code=500)
    return FileResponse(
        str(out_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="ciso_brief.docx",
    )


@app.get("/api/outputs/status")
async def get_outputs_status():
    """Return existence + mtime for each deliverable."""
    import datetime
    files = {
        "ciso_docx":    DELIVERABLES / "ciso_brief.docx",
        "board_pdf":    DELIVERABLES / "board_report.pdf",
        "board_pptx":   DELIVERABLES / "board_report.pptx",
    }
    result = {}
    for key, path in files.items():
        if path.exists():
            ts = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            result[key] = {"ready": True, "generated": ts}
        else:
            result[key] = {"ready": False, "generated": None}
    return result


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
def _update_run_log(event: str, data: dict) -> None:
    """Incrementally update in-memory run log and persist to disk."""
    global _run_log

    if event == "pipeline":
        status = data.get("status")
        if status == "started":
            _run_log = {
                "status": "running",
                "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                "started_at": time.time(),
                "duration_seconds": None,
                "regions": {},
            }
        elif status == "complete":
            _run_log["status"] = "done"
            started = _run_log.pop("started_at", None)
            if started:
                _run_log["duration_seconds"] = int(time.time() - started)
        elif status == "error":
            _run_log["status"] = "error"
            _run_log["error"] = data.get("message", "Unknown error")
            started = _run_log.pop("started_at", None)
            if started:
                _run_log["duration_seconds"] = int(time.time() - started)

    elif event == "gatekeeper":
        region = data.get("region", "")
        if region:
            if region not in _run_log.get("regions", {}):
                _run_log.setdefault("regions", {})[region] = {
                    "decision": data.get("decision"),
                    "admiralty": data.get("admiralty", ""),
                    "rationale": data.get("rationale", ""),
                    "scenario_match": data.get("scenario_match", ""),
                    "dominant_pillar": data.get("dominant_pillar", ""),
                    "signal_count": None,
                    "summary": None,
                    "events": [],
                    "error": None,
                }
            else:
                _run_log["regions"][region].update({
                    "decision": data.get("decision"),
                    "admiralty": data.get("admiralty", ""),
                    "rationale": data.get("rationale", ""),
                    "scenario_match": data.get("scenario_match", ""),
                    "dominant_pillar": data.get("dominant_pillar", ""),
                })

    elif event == "phase":
        region = data.get("region", "")
        message = data.get("message", "")
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {"time": ts, "type": "phase", "message": message}
        if region and region in _run_log.get("regions", {}):
            _run_log["regions"][region]["events"].append(entry)
        else:
            _run_log.setdefault("global_events", []).append(entry)

    elif event == "deep_research":
        region = data.get("region", "")
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        msg = f"Deep research — {data.get('type', '')} — {data.get('message', '')}"
        entry = {"time": ts, "type": "deep_research", "message": msg}
        if region and region in _run_log.get("regions", {}):
            _run_log["regions"][region]["events"].append(entry)

    elif event == "error":
        region = data.get("region", "")
        message = data.get("message", "Unknown error")
        if region and region in _run_log.get("regions", {}):
            _run_log["regions"][region]["error"] = message
        else:
            _run_log["error"] = message

    # Persist to disk
    log_path = BASE / "output" / "pipeline" / "last_run_log.json"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(_run_log, indent=2), encoding="utf-8")
    except Exception:
        pass


async def _emit(event: str, data: dict):
    """Push a structured SSE event. Drops oldest if queue is full."""
    global _run_log
    if event_queue.full():
        try:
            event_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    await event_queue.put({"event": event, "data": json.dumps(data)})
    # Write run log incrementally
    _update_run_log(event, data)


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
                gk = re.search(r'`?([A-Z]{2,5})\s*[—-]+\s*(ESCALATE|MONITOR|CLEAR)', text)
                if gk:
                    region, decision = gk.group(1), gk.group(2)
                    gk_payload: dict = {"region": region, "decision": decision}
                    gk_file = BASE / "output" / "regional" / region / "gatekeeper_decision.json"
                    if gk_file.exists():
                        try:
                            gk_data = json.loads(gk_file.read_text(encoding="utf-8"))
                            gk_payload["rationale"] = gk_data.get("rationale", "")
                            gk_payload["admiralty"] = gk_data.get("admiralty", "")
                            gk_payload["scenario_match"] = gk_data.get("scenario_match", "")
                            gk_payload["dominant_pillar"] = gk_data.get("dominant_pillar", "")
                        except Exception:
                            pass
                    await _emit("gatekeeper", gk_payload)
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


@app.get("/api/run/log")
async def get_run_log():
    """Return the last run log from disk, or no_run sentinel."""
    log_path = BASE / "output" / "pipeline" / "last_run_log.json"
    if log_path.exists():
        return json.loads(log_path.read_text(encoding="utf-8"))
    return {"status": "no_run"}


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
    data = _read_json(VALIDATION / "flags.json")
    if not data:
        return {"status": "no_data", "scenarios": [], "summary": {}}

    # Build scenario → [escalated regions] from regional data.json files
    regions = ["apac", "ame", "latam", "med", "nce"]
    scenario_regions: dict[str, list[str]] = {}
    for region in regions:
        rd = _read_json(OUTPUT / "regional" / region / "data.json")
        if rd and rd.get("gatekeeper_decision") == "ESCALATED" and rd.get("primary_scenario"):
            scenario_regions.setdefault(rd["primary_scenario"], []).append(region.upper())

    # Build scenario → velocity string from trend_analysis.json
    trend = _read_json(PIPELINE / "trend_analysis.json")
    scenario_velocity: dict[str, str] = {}
    if trend and trend.get("run_count", 0) > 0:
        run_count = trend["run_count"]
        for _region_key, rdata in trend.get("regions", {}).items():
            for sc_name, freq in rdata.get("scenario_frequency", {}).items():
                if sc_name not in scenario_velocity:
                    scenario_velocity[sc_name] = f"\u2191 {freq}/{run_count} runs" if freq > 0 else f"\u2014 0/{run_count} runs"
                else:
                    # Aggregate: pick highest frequency across regions
                    existing_freq = int(scenario_velocity[sc_name].split()[1].split("/")[0])
                    if freq > existing_freq:
                        scenario_velocity[sc_name] = f"\u2191 {freq}/{run_count} runs"

    # Enrich each scenario row
    for row in data.get("scenarios", []):
        name = row.get("scenario", "")
        row["osint_signal"] = scenario_regions.get(name, [])
        row["velocity"] = scenario_velocity.get(name, None)

    return data


@app.get("/api/validation/sources")
async def get_validation_sources():
    path = BASE / "data" / "validation_sources.json"
    data = _read_json(path)
    return data or {"sources": []}


@app.get("/api/validation/candidates")
async def get_validation_candidates():
    data = _read_json(VALIDATION / "candidates.json")
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
    cands_path = VALIDATION / "candidates.json"
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
        # Count sources with non-empty raw_text
        import glob as _glob, json as _json
        _cache_files = _glob.glob("output/validation/cache/**/*.json", recursive=True)
        _fetched = sum(1 for f in _cache_files if _json.load(open(f, encoding="utf-8")).get("raw_text", ""))
        await _emit("validation", {"status": "step", "step": "source_harvester", "message": f"Fetched content for {_fetched}/{len(_cache_files)} sources"})

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
        _bm_total = sum(len(_json.load(open(f, encoding="utf-8")).get("benchmarks", [])) for f in _cache_files)
        await _emit("validation", {"status": "step", "step": "benchmark_extractor", "message": f"Extracted {_bm_total} benchmark figures"})

        await _emit("validation", {"status": "step", "step": "crq_comparator", "message": "Comparing VaCR figures..."})
        rc = await _run("crq_comparator.py", timeout=60)
        if rc != 0:
            await _emit("validation", {"status": "error", "step": "crq_comparator"})
            return
        try:
            _flags = _json.load(open("output/validation/flags.json", encoding="utf-8"))
            _sm = _flags.get("summary", {})
            await _emit("validation", {"status": "step", "step": "crq_comparator", "message": f"Results: {_sm.get('supported', 0)} supported · {_sm.get('challenged', 0)} challenged · {_sm.get('no_data', 0)} no data"})
        except Exception:
            pass

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


@app.get("/api/validation/register-results")
@app.get("/api/register-validation/results")
async def get_register_validation():
    path = VALIDATION / "register_validation.json"
    data = _read_json(path)
    return data or {"status": "no_data"}


@app.post("/api/validation/run-register")
async def run_register_validation():
    import asyncio
    VALIDATION.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "register_validator.py"),
        cwd=str(BASE),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return JSONResponse(
            {"error": stderr.decode(errors="replace")[:500]}, status_code=500
        )
    data = _read_json(VALIDATION / "register_validation.json")
    return data or {"status": "no_data"}


# ── API: Risk Register — Regional Scenarios ──────────────────────────────
_REGIONAL_DB = BASE / "data" / "mock_crq_database.json"
_MASTER_DB   = BASE / "data" / "master_scenarios.json"


@app.get("/api/risk-register/regional")
async def get_regional_scenarios():
    data = _read_json(_REGIONAL_DB)
    return data or {}


@app.put("/api/risk-register/regional/{scenario_id}")
async def update_regional_scenario(scenario_id: str, body: dict):
    data = _read_json(_REGIONAL_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    for region, scenarios in data.items():
        for i, s in enumerate(scenarios):
            if s.get("scenario_id") == scenario_id:
                # Merge update fields; preserve scenario_id and region structure
                data[region][i].update({k: v for k, v in body.items() if k != "scenario_id"})
                _REGIONAL_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
                return {"ok": True, "scenario_id": scenario_id}
    return JSONResponse({"error": f"Scenario {scenario_id} not found"}, status_code=404)


@app.post("/api/risk-register/regional")
async def add_regional_scenario(body: dict):
    data = _read_json(_REGIONAL_DB) or {}
    region = body.get("region", "").upper()
    if not region:
        return JSONResponse({"error": "region required"}, status_code=400)
    # Auto-generate scenario_id: REGION-NNN
    existing = [s for scenarios in data.values() for s in scenarios if s.get("scenario_id", "").startswith(region)]
    new_id = f"{region}-{len(existing) + 1:03d}"
    scenario = {
        "scenario_id": new_id,
        "department": body.get("department", ""),
        "scenario_name": body.get("scenario_name", "New Scenario"),
        "critical_assets": body.get("critical_assets", []),
        "value_at_cyber_risk_usd": body.get("value_at_cyber_risk_usd", 0),
    }
    data.setdefault(region, []).append(scenario)
    _REGIONAL_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "scenario_id": new_id}


@app.delete("/api/risk-register/regional/{scenario_id}")
async def delete_regional_scenario(scenario_id: str):
    data = _read_json(_REGIONAL_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    for region, scenarios in data.items():
        for i, s in enumerate(scenarios):
            if s.get("scenario_id") == scenario_id:
                data[region].pop(i)
                if not data[region]:
                    del data[region]
                _REGIONAL_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
                return {"ok": True}
    return JSONResponse({"error": f"Scenario {scenario_id} not found"}, status_code=404)


# ── API: Risk Register — Master Scenarios ────────────────────────────────

@app.get("/api/risk-register/master")
async def get_master_scenarios():
    data = _read_json(_MASTER_DB)
    return {"scenarios": data.get("scenarios", [])} if data else {"scenarios": []}


@app.put("/api/risk-register/master/{incident_type}")
async def update_master_scenario(incident_type: str, body: dict):
    data = _read_json(_MASTER_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    for i, s in enumerate(data.get("scenarios", [])):
        if s.get("incident_type") == incident_type:
            data["scenarios"][i].update({k: v for k, v in body.items() if k != "incident_type"})
            _MASTER_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            return {"ok": True}
    return JSONResponse({"error": f"Scenario '{incident_type}' not found"}, status_code=404)


@app.post("/api/risk-register/master")
async def add_master_scenario(body: dict):
    data = _read_json(_MASTER_DB) or {"meta": {}, "scenarios": []}
    incident_type = body.get("incident_type", "").strip()
    if not incident_type:
        return JSONResponse({"error": "incident_type required"}, status_code=400)
    if any(s.get("incident_type") == incident_type for s in data.get("scenarios", [])):
        return JSONResponse({"error": f"'{incident_type}' already exists"}, status_code=409)
    scenario = {
        "incident_type": incident_type,
        "event_frequency_pct": body.get("event_frequency_pct", 0.0),
        "frequency_rank": body.get("frequency_rank", 99),
        "financial_impact_pct": body.get("financial_impact_pct", 0.0),
        "financial_rank": body.get("financial_rank", 99),
        "records_affected_pct": body.get("records_affected_pct", 0.0),
        "records_rank": body.get("records_rank", 99),
    }
    data["scenarios"].append(scenario)
    _MASTER_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "incident_type": incident_type}


@app.delete("/api/risk-register/master/{incident_type}")
async def delete_master_scenario(incident_type: str):
    # URL-encode spaces — FastAPI path param decodes automatically
    data = _read_json(_MASTER_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    original_len = len(data.get("scenarios", []))
    data["scenarios"] = [s for s in data.get("scenarios", []) if s.get("incident_type") != incident_type]
    if len(data["scenarios"]) == original_len:
        return JSONResponse({"error": f"Scenario '{incident_type}' not found"}, status_code=404)
    _MASTER_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


# ── API: Risk Register — VaCR Research Pipeline ──────────────────────────

@app.get("/api/risk-register/research")
async def get_research_results():
    data = _read_json(PIPELINE / "vacr_research.json")
    return data or {"generated_at": None, "results": []}


@app.post("/api/risk-register/research")
async def trigger_research():
    if research_state["running"]:
        return JSONResponse({"error": "Research already running"}, status_code=409)
    asyncio.create_task(_run_research())
    return {"started": True}


@app.get("/api/risk-register/research/status")
async def get_research_status():
    return research_state


async def _run_research():
    """Run vacr_researcher.py for all master scenarios in parallel. Emits SSE events."""
    import importlib.util, sys as _sys
    research_state.update(running=True, progress=[], started_at=time.time())
    await _emit("research", {"status": "started"})

    # Load master scenarios to get incident types + find matching regional VaCR
    master_data = _read_json(BASE / "data" / "master_scenarios.json") or {}
    scenarios = master_data.get("scenarios", [])
    regional_data = _read_json(BASE / "data" / "mock_crq_database.json") or {}

    # Build a map of incident_type -> best VaCR (highest across regions for that scenario)
    # Since regional scenarios use different names, we use the highest regional VaCR as proxy
    all_regional_vacr = [
        s.get("value_at_cyber_risk_usd", 0)
        for region_list in regional_data.values()
        for s in region_list
        if s.get("value_at_cyber_risk_usd", 0) > 0
    ]
    default_vacr = max(all_regional_vacr) if all_regional_vacr else 0

    research_state["progress"] = [{"incident_type": s["incident_type"], "status": "pending"} for s in scenarios]

    async def _research_one(scenario: dict) -> None:
        incident_type = scenario["incident_type"]
        # Update progress
        for p in research_state["progress"]:
            if p["incident_type"] == incident_type:
                p["status"] = "running"
        done_count = sum(1 for p in research_state["progress"] if p["status"] == "done")
        await _emit("research", {"status": "step", "incident_type": incident_type,
                                  "message": f"Researching: {incident_type}... [{done_count}/{len(scenarios)} complete]"})
        try:
            # Run in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            spec = importlib.util.spec_from_file_location("vacr_researcher", BASE / "tools" / "vacr_researcher.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            result = await loop.run_in_executor(
                None,
                lambda: mod.research_scenario(incident_type, default_vacr, "energy")
            )
            mod._update_output(result)

            for p in research_state["progress"]:
                if p["incident_type"] == incident_type:
                    p["status"] = "done"
            done_count = sum(1 for p in research_state["progress"] if p["status"] == "done")
            await _emit("research", {"status": "step", "incident_type": incident_type,
                                      "message": f"Done: {incident_type} [{done_count}/{len(scenarios)} complete]"})
        except Exception as exc:
            for p in research_state["progress"]:
                if p["incident_type"] == incident_type:
                    p["status"] = "error"
            await _emit("research", {"status": "error", "incident_type": incident_type, "message": str(exc)})

    try:
        await asyncio.gather(*[_research_one(s) for s in scenarios])
        await _emit("research", {"status": "complete"})
    except Exception as exc:
        await _emit("research", {"status": "error", "message": str(exc)})
    finally:
        research_state.update(running=False)


# ── API: Source Registry ─────────────────────────────────────────────────
@app.get("/api/sources")
async def get_source_registry(
    region: Optional[str] = None,
    type: Optional[str] = None,
    tier: Optional[str] = None,
    cited_only: bool = False,
    hide_junk: bool = True,
    limit: int = 100,
):
    """Return sources from the registry with optional filters."""
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            conn.row_factory = sqlite3.Row
            clauses = []
            params: list = []
            if region:
                # Join with appearances to filter by region
                base_sql = (
                    "SELECT DISTINCT s.* FROM sources_registry s "
                    "JOIN source_appearances a ON a.source_id = s.id "
                    "WHERE a.region = ?"
                )
                params.append(region.upper())
            else:
                base_sql = "SELECT * FROM sources_registry s WHERE 1=1"
            if type:
                clauses.append("s.source_type = ?")
                params.append(type)
            if tier:
                clauses.append("s.credibility_tier = ?")
                params.append(tier.upper())
            if cited_only:
                clauses.append("s.cited_count > 0")
            if hide_junk:
                clauses.append("s.junk = 0")
            where = (" AND " + " AND ".join(clauses)) if clauses else ""
            sql = f"{base_sql}{where} ORDER BY s.last_seen DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "url": r["url"],
                    "name": r["name"],
                    "domain": r["domain"],
                    "published_at": r["published_at"] if "published_at" in r.keys() else None,
                    "first_seen": r["first_seen"] if "first_seen" in r.keys() else None,
                    "source_type": r["source_type"],
                    "credibility_tier": r["credibility_tier"],
                    "collection_type": r["collection_type"] if "collection_type" in r.keys() else "osint",
                    "appearance_count": r["appearance_count"],
                    "cited_count": r["cited_count"],
                    "last_seen": r["last_seen"],
                    "junk": r["junk"],
                }
                for r in rows
            ]
    except Exception:
        return []


@app.get("/api/sources/stats")
async def get_source_stats():
    """Return aggregate counts across the source registry."""
    zeroed = {
        "total": 0,
        "by_type": {"news": 0, "government": 0, "intelligence": 0, "academic": 0, "industry": 0, "social": 0, "youtube": 0},
        "by_tier": {"A": 0, "B": 0, "C": 0},
        "by_region": {"APAC": 0, "AME": 0, "MED": 0, "NCE": 0, "LATAM": 0},
        "total_junk": 0,
        "total_cited": 0,
    }
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            conn.row_factory = sqlite3.Row
            result = dict(zeroed)
            result["by_type"] = dict(zeroed["by_type"])
            result["by_tier"] = dict(zeroed["by_tier"])
            result["by_region"] = dict(zeroed["by_region"])

            total_row = conn.execute("SELECT COUNT(*) as cnt FROM sources_registry").fetchone()
            result["total"] = total_row["cnt"] if total_row else 0

            for row in conn.execute("SELECT source_type, COUNT(*) as cnt FROM sources_registry GROUP BY source_type").fetchall():
                key = row["source_type"]
                if key in result["by_type"]:
                    result["by_type"][key] = row["cnt"]

            # NOTE: Milestone 4 — exclude collection_type='benchmark' from OSINT quality scoring
            for row in conn.execute("SELECT credibility_tier, COUNT(*) as cnt FROM sources_registry GROUP BY credibility_tier").fetchall():
                key = row["credibility_tier"]
                if key in result["by_tier"]:
                    result["by_tier"][key] = row["cnt"]

            for row in conn.execute("SELECT region, COUNT(DISTINCT source_id) as cnt FROM source_appearances GROUP BY region").fetchall():
                key = row["region"]
                if key in result["by_region"]:
                    result["by_region"][key] = row["cnt"]

            junk_row = conn.execute("SELECT COUNT(*) as cnt FROM sources_registry WHERE junk = 1").fetchone()
            result["total_junk"] = junk_row["cnt"] if junk_row else 0

            cited_row = conn.execute("SELECT COUNT(*) as cnt FROM sources_registry WHERE cited_count > 0").fetchone()
            result["total_cited"] = cited_row["cnt"] if cited_row else 0

            return result
    except Exception:
        return zeroed


from pydantic import BaseModel


class SourceFlagBody(BaseModel):
    junk: bool


def _sync_blocked_urls_to_file() -> None:
    """Sync blocked URLs from DB to data/blocked_urls.txt."""
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            rows = conn.execute("SELECT url FROM sources_registry WHERE blocked = 1 AND url IS NOT NULL").fetchall()
        urls = [r[0] for r in rows if r[0]]
        blocked_file = BASE / "data" / "blocked_urls.txt"
        blocked_file.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    except Exception as e:
        print(f"[server] sync_blocked_urls failed: {e}", file=sys.stderr)


@app.post("/api/sources/{source_id}/flag")
async def flag_source(source_id: str, body: SourceFlagBody):
    """Set or clear the junk flag on a source."""
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT id FROM sources_registry WHERE id = ?", (source_id,)).fetchone()
            if row is None:
                return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
            blocked_val = 1 if body.junk else 0
            conn.execute(
                "UPDATE sources_registry SET junk = ?, blocked = ? WHERE id = ?",
                (1 if body.junk else 0, blocked_val, source_id),
            )
            conn.commit()
        # Sync blocked URLs flat file
        _sync_blocked_urls_to_file()
        return {"ok": True}
    except Exception:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)



class SourceTierBody(BaseModel):
    tier: str


@app.post("/api/sources/{source_id}/tier")
async def set_source_tier(source_id: str, body: SourceTierBody):
    """Override the credibility tier for a source."""
    if body.tier not in ("A", "B", "C"):
        return JSONResponse({"ok": False, "error": "tier must be A, B, or C"}, status_code=400)
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            row = conn.execute(
                "SELECT id FROM sources_registry WHERE id = ?", (source_id,)
            ).fetchone()
            if row is None:
                return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
            conn.execute(
                "UPDATE sources_registry SET credibility_tier = ? WHERE id = ?",
                (body.tier, source_id),
            )
            conn.commit()
        return {"ok": True}
    except Exception:
        return JSONResponse({"ok": False, "error": "db error"}, status_code=500)


@app.get("/api/sources/attribution")
async def get_source_attribution():
    """Per-region source citation rates for the Validate tab."""
    zeroed = {"regions": {r: {"total": 0, "cited": 0, "citation_rate": 0, "tiers": {"A": 0, "B": 0, "C": 0}} for r in ["APAC","AME","LATAM","MED","NCE"]}, "total": 0, "cited": 0, "citation_rate": 0}
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            conn.row_factory = sqlite3.Row
            result = {"regions": {}, "total": 0, "cited": 0, "citation_rate": 0}
            for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
                total = (conn.execute("SELECT COUNT(DISTINCT source_id) as c FROM source_appearances WHERE region = ?", (region,)).fetchone() or {"c": 0})["c"]
                cited = (conn.execute("SELECT COUNT(DISTINCT sa.source_id) as c FROM source_appearances sa JOIN sources_registry sr ON sr.id = sa.source_id WHERE sa.region = ? AND sr.cited_count > 0", (region,)).fetchone() or {"c": 0})["c"]
                tiers = {"A": 0, "B": 0, "C": 0}
                for row in conn.execute("SELECT sr.credibility_tier, COUNT(DISTINCT sa.source_id) as c FROM source_appearances sa JOIN sources_registry sr ON sr.id = sa.source_id WHERE sa.region = ? GROUP BY sr.credibility_tier", (region,)).fetchall():
                    if row["credibility_tier"] in tiers:
                        tiers[row["credibility_tier"]] = row["c"]
                result["regions"][region] = {"total": total, "cited": cited, "citation_rate": round(cited / total, 3) if total else 0, "tiers": tiers}
            result["total"] = (conn.execute("SELECT COUNT(*) as c FROM sources_registry WHERE junk = 0").fetchone() or {"c": 0})["c"]
            result["cited"] = (conn.execute("SELECT COUNT(*) as c FROM sources_registry WHERE cited_count > 0").fetchone() or {"c": 0})["c"]
            result["citation_rate"] = round(result["cited"] / result["total"], 3) if result["total"] else 0
            return result
    except Exception:
        return zeroed


@app.get("/api/sources/velocity")
async def get_source_velocity():
    """Source velocity data (new vs recurring sources) for the Trends tab."""
    zeroed = {"new_this_run": 0, "total": 0, "by_region": {}}
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            conn.row_factory = sqlite3.Row
            new_count = (conn.execute("SELECT COUNT(*) as c FROM sources_registry WHERE appearance_count = 1 AND junk = 0").fetchone() or {"c": 0})["c"]
            total_count = (conn.execute("SELECT COUNT(*) as c FROM sources_registry WHERE junk = 0").fetchone() or {"c": 0})["c"]
            by_region = {}
            for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
                new_r = (conn.execute("SELECT COUNT(DISTINCT sa.source_id) as c FROM source_appearances sa JOIN sources_registry sr ON sr.id = sa.source_id WHERE sa.region = ? AND sr.appearance_count = 1 AND sr.junk = 0", (region,)).fetchone() or {"c": 0})["c"]
                total_r = (conn.execute("SELECT COUNT(DISTINCT source_id) as c FROM source_appearances WHERE region = ?", (region,)).fetchone() or {"c": 0})["c"]
                top_rows = conn.execute("SELECT sr.name, sr.appearance_count, sr.cited_count, sr.credibility_tier FROM sources_registry sr JOIN source_appearances sa ON sa.source_id = sr.id WHERE sa.region = ? AND sr.junk = 0 GROUP BY sr.id ORDER BY sr.appearance_count DESC, sr.cited_count DESC LIMIT 4", (region,)).fetchall()
                by_region[region] = {
                    "new": new_r,
                    "total": total_r,
                    "top_sources": [{"name": r["name"], "appearances": r["appearance_count"], "cited": r["cited_count"] > 0, "tier": r["credibility_tier"]} for r in top_rows]
                }
            return {"new_this_run": new_count, "total": total_count, "by_region": by_region}
    except Exception:
        return zeroed


# ── Startup ──────────────────────────────────────────────────────────────
@app.on_event("startup")
async def _startup():
    global _run_log
    log_path = BASE / "output" / "pipeline" / "last_run_log.json"
    if log_path.exists():
        try:
            _run_log = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass


# ── Static Files ─────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(BASE / "static" / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
