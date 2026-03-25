# Phase M — Regional Footprint Context Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `data/regional_footprint.json` and `tools/build_context.py` so pipeline agents reason against AeroGrid's specific regional presence rather than the thin global company profile.

**Architecture:** A pre-assembled context block (`context_block.txt`) is written per region before agents run. The analyst agent reads it as a named input file; the gatekeeper receives a one-liner summary prepended to its task description (same pattern as `PRIOR_FEEDBACK`). A Config tab Footprint panel + two API endpoints allow operators to update the four editable fields without touching the JSON file directly.

**Tech Stack:** Python 3 (stdlib only — `json`, `pathlib`, `sys`, `argparse`), pytest/monkeypatch, FastAPI (existing server.py), vanilla JS (existing app.js pattern).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `data/regional_footprint.json` | Create | 5-region mock data — all fields from spec |
| `tools/build_context.py` | Create | CLI: reads footprint JSON → writes `context_block.txt`; `--gatekeeper-summary` flag |
| `tests/test_build_context.py` | Create | 8 unit tests (monkeypatch/tmp_path pattern) |
| `.claude/commands/run-crq.md` | Modify | Phase 0: call `build_context.py` per region + capture gatekeeper summaries |
| `.claude/agents/regional-analyst-agent.md` | Modify | STEP 1: add item 9 — `context_block.txt` |
| `.claude/agents/gatekeeper-agent.md` | Modify | TASK: add FOOTPRINT variable + calibration instruction |
| `server.py` | Modify | Add `GET /api/footprint` + `PUT /api/footprint/{region}` after `/api/history` |
| `static/index.html` | Modify | Add Footprint sub-tab nav link + panel HTML |
| `static/app.js` | Modify | Add footprint state, `loadFootprint()`, `renderFootprint()`, save handler |

---

## Task M-1: Create `data/regional_footprint.json`

**Files:**
- Create: `data/regional_footprint.json`

- [ ] **Step 1: Write the file**

Create `data/regional_footprint.json` with the exact schema from the spec. All 5 regions (APAC, AME, LATAM, MED, NCE), fully populated with mock data. Use exactly these values:

```json
{
  "APAC": {
    "summary": "Primary manufacturing region. 60% of global turbine output. Highest operational sensitivity.",
    "headcount": 3200,
    "sites": [
      {"name": "Kaohsiung Manufacturing Hub", "country": "TW", "type": "manufacturing", "criticality": "primary"},
      {"name": "Shanghai Service Hub",         "country": "CN", "type": "service",       "criticality": "high"},
      {"name": "Tokyo Regional Office",        "country": "JP", "type": "service",       "criticality": "medium"}
    ],
    "crown_jewels": ["Series 7 production line", "SCADA network TW-01", "OT predictive maintenance stack"],
    "supply_chain_dependencies": ["Taiwanese semiconductor components", "Korean rare earth supply"],
    "key_contracts": ["TEPCO 5yr turbine supply agreement", "Vestas APAC logistics JV"],
    "notes": "",
    "stakeholders": [
      {"role": "APAC Regional Ops Lead", "email": "apac-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "APAC RSM",               "email": "rsm-apac@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  },
  "AME": {
    "summary": "Primary North American operations. Wind farm service hub and growing manufacturing presence.",
    "headcount": 2100,
    "sites": [
      {"name": "Houston Operations Center", "country": "US", "type": "service", "criticality": "high"},
      {"name": "Toronto Engineering Hub",   "country": "CA", "type": "service", "criticality": "medium"}
    ],
    "crown_jewels": ["Wind farm telemetry network NA-01", "Predictive maintenance IP"],
    "supply_chain_dependencies": ["US steel imports", "Canadian logistics network"],
    "key_contracts": ["NextEra Energy 3yr maintenance contract", "Ontario Wind Power service agreement"],
    "notes": "",
    "stakeholders": [
      {"role": "AME Regional Ops Lead", "email": "ame-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "AME RSM",               "email": "rsm-ame@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  },
  "LATAM": {
    "summary": "Growing service and maintenance presence. No primary manufacturing. Emerging wind market.",
    "headcount": 680,
    "sites": [
      {"name": "São Paulo Regional Office", "country": "BR", "type": "service", "criticality": "medium"},
      {"name": "Santiago Service Centre",   "country": "CL", "type": "service", "criticality": "medium"}
    ],
    "crown_jewels": ["Regional service contracts", "Field technician network"],
    "supply_chain_dependencies": ["Brazilian logistics partners"],
    "key_contracts": ["Enel Chile wind maintenance 2yr", "Neoenergia turbine service Brazil"],
    "notes": "",
    "stakeholders": [
      {"role": "LATAM Regional Ops Lead", "email": "latam-ops@aerowind.com", "notify_on": ["escalated"]},
      {"role": "LATAM RSM",               "email": "rsm-latam@aerowind.com", "notify_on": ["escalated"]}
    ]
  },
  "MED": {
    "summary": "Manufacturing and service hub for Southern Europe and North Africa. Offshore wind growth market.",
    "headcount": 1400,
    "sites": [
      {"name": "Palermo Offshore Ops", "country": "IT", "type": "manufacturing", "criticality": "high"},
      {"name": "Malaga Service Hub",   "country": "ES", "type": "service",       "criticality": "medium"}
    ],
    "crown_jewels": ["Offshore blade assembly process", "Mediterranean service network"],
    "supply_chain_dependencies": ["Spanish steel supply", "North African logistics corridor"],
    "key_contracts": ["Iberdrola offshore maintenance 4yr", "ENEL MED service contract"],
    "notes": "",
    "stakeholders": [
      {"role": "MED Regional Ops Lead", "email": "med-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "MED RSM",               "email": "rsm-med@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  },
  "NCE": {
    "summary": "Largest European presence. Mature wind market. Key R&D and engineering functions.",
    "headcount": 2800,
    "sites": [
      {"name": "Hamburg Manufacturing Hub",  "country": "DE", "type": "manufacturing", "criticality": "high"},
      {"name": "Gdansk Blade Plant",         "country": "PL", "type": "manufacturing", "criticality": "high"},
      {"name": "Copenhagen Engineering Hub", "country": "DK", "type": "service",       "criticality": "high"}
    ],
    "crown_jewels": ["Core turbine aerodynamic IP", "R&D roadmap and prototype designs", "OT/SCADA networks EU-01/EU-02"],
    "supply_chain_dependencies": ["German precision engineering components", "Nordic offshore logistics"],
    "key_contracts": ["Ørsted offshore wind 5yr maintenance", "Vattenfall EU service agreement"],
    "notes": "",
    "stakeholders": [
      {"role": "NCE Regional Ops Lead", "email": "nce-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "NCE RSM",               "email": "rsm-nce@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  }
}
```

- [ ] **Step 2: Verify it's valid JSON**

```bash
uv run python -c "import json; data = json.load(open('data/regional_footprint.json', encoding='utf-8')); print(list(data.keys()))"
```

Expected output: `['APAC', 'AME', 'LATAM', 'MED', 'NCE']`

- [ ] **Step 3: Commit**

```bash
git add data/regional_footprint.json
git commit -m "feat(M-1): add regional_footprint.json with mock data for all 5 regions"
```

---

## Task M-2: Create `tools/build_context.py` + tests

**Files:**
- Create: `tools/build_context.py`
- Create: `tests/test_build_context.py`

### Step 2a — Write the failing tests first

- [ ] **Step 1: Write `tests/test_build_context.py`**

```python
"""Tests for tools/build_context.py — Phase M"""

import json
import sys
from pathlib import Path

import pytest

import tools.build_context as bc


# ── Helpers ────────────────────────────────────────────────────────────────

MINIMAL_FOOTPRINT = {
    "APAC": {
        "summary": "Primary manufacturing region.",
        "headcount": 3200,
        "sites": [
            {"name": "Kaohsiung Manufacturing Hub", "country": "TW", "type": "manufacturing", "criticality": "primary"},
            {"name": "Shanghai Service Hub",         "country": "CN", "type": "service",       "criticality": "high"},
        ],
        "crown_jewels": ["Series 7 production line", "SCADA network TW-01"],
        "supply_chain_dependencies": ["Taiwanese semiconductor components"],
        "key_contracts": ["TEPCO 5yr turbine supply agreement"],
        "notes": "",
        "stakeholders": [
            {"role": "APAC RSM", "email": "rsm-apac@aerowind.com", "notify_on": ["escalated"]}
        ],
    }
}


def _write_footprint(tmp_path: Path, data: dict) -> Path:
    fp = tmp_path / "regional_footprint.json"
    fp.write_text(json.dumps(data), encoding="utf-8")
    return fp


def _patch(monkeypatch, tmp_path: Path, data: dict):
    fp = _write_footprint(tmp_path, data)
    output_dir = tmp_path / "output"
    monkeypatch.setattr(bc, "FOOTPRINT_FILE", fp)
    monkeypatch.setattr(bc, "OUTPUT_DIR", output_dir)
    return fp, output_dir


# ── Tests ──────────────────────────────────────────────────────────────────

def test_valid_region_writes_file(monkeypatch, tmp_path):
    """APAC → context_block.txt created at correct path."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("APAC")
    assert (output_dir / "regional" / "apac" / "context_block.txt").exists()


def test_output_contains_site_names(monkeypatch, tmp_path):
    """Block includes site names from footprint."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "Kaohsiung Manufacturing Hub" in text
    assert "Shanghai Service Hub" in text


def test_output_contains_headcount(monkeypatch, tmp_path):
    """Headcount rendered as formatted number (3,200)."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "3,200" in text


def test_gatekeeper_summary_format(monkeypatch, tmp_path):
    """build_gatekeeper_summary() returns one-liner with criticality."""
    _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    summary = bc.build_gatekeeper_summary(MINIMAL_FOOTPRINT["APAC"], "APAC")
    assert "APAC" in summary
    assert "3,200" in summary
    assert "PRIMARY" in summary or "primary" in summary.lower()
    assert "Kaohsiung" in summary


def test_unknown_region_exits_1(monkeypatch, tmp_path, capsys):
    """Unknown region → exit 1 with stderr message."""
    _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    with pytest.raises(SystemExit) as exc:
        bc.build_context("UNKNOWN")
    assert exc.value.code == 1


def test_missing_footprint_file_exits_1(monkeypatch, tmp_path):
    """No regional_footprint.json → exit 1."""
    monkeypatch.setattr(bc, "FOOTPRINT_FILE", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(bc, "OUTPUT_DIR", tmp_path / "output")
    with pytest.raises(SystemExit) as exc:
        bc.build_context("APAC")
    assert exc.value.code == 1


def test_empty_region_writes_empty_block(monkeypatch, tmp_path):
    """Region absent from file → empty context_block.txt, exit 0."""
    # Footprint has APAC but not NCE
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("NCE")  # should not raise
    block = (output_dir / "regional" / "nce" / "context_block.txt").read_text(encoding="utf-8")
    assert block == ""


def test_notes_field_appended_verbatim(monkeypatch, tmp_path):
    """Notes text appears unchanged in output block."""
    data = json.loads(json.dumps(MINIMAL_FOOTPRINT))
    data["APAC"]["notes"] = "Major turbine order Q2 — supply chain under pressure."
    _, output_dir = _patch(monkeypatch, tmp_path, data)
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "Major turbine order Q2 — supply chain under pressure." in text
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_build_context.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'tools.build_context'` or similar. The tests must fail before we write the implementation.

### Step 2b — Write the implementation

- [ ] **Step 3: Write `tools/build_context.py`**

```python
"""tools/build_context.py — Phase M: Regional Footprint Context Builder

CLI:
    uv run python tools/build_context.py APAC
    uv run python tools/build_context.py --gatekeeper-summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Constants (monkeypatched in tests) ─────────────────────────────────────
FOOTPRINT_FILE = Path("data/regional_footprint.json")
OUTPUT_DIR = Path("output")
KNOWN_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}


# ── Public API ──────────────────────────────────────────────────────────────

def build_gatekeeper_summary(region_data: dict, region: str) -> str:
    """Return a single-line footprint summary for gatekeeper context injection."""
    headcount = f"{region_data.get('headcount', 0):,}"
    sites = region_data.get("sites", [])
    site_strs = [
        f"{s['name'].split()[0]} ({s['type']}, {s['criticality'].upper()})"
        for s in sites
    ]
    sites_part = ", ".join(site_strs) if site_strs else "no sites listed"
    return f"{region} footprint: {headcount} staff | Sites: {sites_part}"


def build_context(region: str) -> None:
    """Read regional_footprint.json, write context_block.txt for agent injection.

    Exit codes:
        0 — success (including region absent from file — writes empty block)
        1 — bad region name or missing footprint file
    """
    if region not in KNOWN_REGIONS:
        print(f"ERROR: Unknown region '{region}'. Must be one of {sorted(KNOWN_REGIONS)}", file=sys.stderr)
        sys.exit(1)

    if not FOOTPRINT_FILE.exists():
        print(f"ERROR: Footprint file not found: {FOOTPRINT_FILE}", file=sys.stderr)
        sys.exit(1)

    footprint = json.loads(FOOTPRINT_FILE.read_text(encoding="utf-8"))

    out_dir = OUTPUT_DIR / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "context_block.txt"

    if region not in footprint:
        print(f"WARNING: Region '{region}' not found in {FOOTPRINT_FILE} — writing empty context block.", file=sys.stderr)
        out_path.write_text("", encoding="utf-8")
        print(f"Context block written (empty): {out_path}")
        return

    data = footprint[region]
    block = _format_context_block(data, region)
    out_path.write_text(block, encoding="utf-8")
    print(f"Context block written: {out_path}")


def build_all_gatekeeper_summaries() -> None:
    """Print one gatekeeper summary line per region (all 5). Captured by orchestrator."""
    if not FOOTPRINT_FILE.exists():
        print(f"ERROR: Footprint file not found: {FOOTPRINT_FILE}", file=sys.stderr)
        sys.exit(1)

    footprint = json.loads(FOOTPRINT_FILE.read_text(encoding="utf-8"))
    for region in sorted(KNOWN_REGIONS):
        if region in footprint:
            print(build_gatekeeper_summary(footprint[region], region))
        else:
            print(f"{region} footprint: no data")


# ── Private formatting ──────────────────────────────────────────────────────

def _format_context_block(data: dict, region: str) -> str:
    lines = [f"[REGIONAL FOOTPRINT — {region}]"]
    lines.append(f"Summary: {data.get('summary', '')}")
    lines.append(f"Headcount: {data.get('headcount', 0):,}")
    lines.append("")

    sites = data.get("sites", [])
    if sites:
        lines.append("Sites:")
        for s in sites:
            lines.append(f"  - {s['name']} ({s['country']}) — {s['type']}, {s['criticality'].upper()}")
    lines.append("")

    crown = data.get("crown_jewels", [])
    if crown:
        lines.append(f"Crown Jewels: {' | '.join(crown)}")

    deps = data.get("supply_chain_dependencies", [])
    if deps:
        lines.append(f"Supply Chain Dependencies: {' | '.join(deps)}")

    contracts = data.get("key_contracts", [])
    if contracts:
        lines.append(f"Key Contracts: {' | '.join(contracts)}")

    notes = data.get("notes", "").strip()
    if notes:
        lines.append("")
        lines.append("Notes:")
        lines.append(notes)

    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build regional footprint context blocks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("region", nargs="?", help="Region code (APAC, AME, LATAM, MED, NCE)")
    group.add_argument("--gatekeeper-summary", action="store_true",
                       help="Print one-line summary per region for gatekeeper injection")
    args = parser.parse_args()

    if args.gatekeeper_summary:
        build_all_gatekeeper_summaries()
    else:
        build_context(args.region.upper())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests — all 8 must pass**

```bash
uv run pytest tests/test_build_context.py -v
```

Expected output: 8 passed.

- [ ] **Step 5: Smoke-test the CLI**

```bash
uv run python tools/build_context.py APAC
cat output/regional/apac/context_block.txt
uv run python tools/build_context.py --gatekeeper-summary
```

Expected: `context_block.txt` created; 5 one-liner summaries printed for `--gatekeeper-summary`.

- [ ] **Step 6: Commit**

```bash
git add tools/build_context.py tests/test_build_context.py
git commit -m "feat(M-2): add build_context.py + 8 tests — regional footprint context builder"
```

---

## Task M-3: Pipeline Wiring

**Files:**
- Modify: `.claude/commands/run-crq.md`
- Modify: `.claude/agents/regional-analyst-agent.md`
- Modify: `.claude/agents/gatekeeper-agent.md`

### Step 3a — run-crq.md Phase 0

- [ ] **Step 1: Read the current Phase 0 section**

Open `.claude/commands/run-crq.md` and find the `## PHASE 0 — VALIDATE & INITIALIZE` block. Locate the line:

```
**Load prior run feedback (if any):**
```

- [ ] **Step 2: Add footprint context block generation after the feedback block**

After the entire `PRIOR_FEEDBACK` paragraph (which ends with `"PRIOR RUN ANALYST FEEDBACK: {PRIOR_FEEDBACK}" — if non-empty, prepend this to each agent's task description.`), add:

```markdown
**Build regional footprint context blocks:**
For each region in [APAC, AME, LATAM, MED, NCE]:
  Run: `uv run python tools/build_context.py {REGION}`
  If the command fails (exit non-zero): log a warning to `output/system_trace.log` using `uv run python tools/audit_logger.py FOOTPRINT_WARN "context block missing for {REGION} — agent proceeds without it"` and continue. This is non-fatal.

**Build gatekeeper summaries:**
Run: `uv run python tools/build_context.py --gatekeeper-summary`
Capture the output as `FOOTPRINT_SUMMARIES` — a dict keyed by region. Parse each line as `{REGION} footprint: {rest}`.
If this command fails, set `FOOTPRINT_SUMMARIES` to an empty dict and continue.
```

- [ ] **Step 3: Add footprint prepend to Phase 1 task descriptions**

In the `## PHASE 1 — REGIONAL ANALYSIS (PARALLEL FAN-OUT)` section, find where `PRIOR_FEEDBACK` is prepended to task descriptions. The instruction reads:
```
"PRIOR RUN ANALYST FEEDBACK: {PRIOR_FEEDBACK}" — if non-empty, prepend this to each agent's task description.
```

Below that line (or as part of the same prepend instruction), add:
```markdown
If `FOOTPRINT_SUMMARIES[{REGION}]` is non-empty, also prepend:
"REGIONAL FOOTPRINT SUMMARY: {FOOTPRINT_SUMMARIES[REGION]}"
Pass this to the gatekeeper invocation within the task. The gatekeeper reads it from its task description — no additional file reads required.
```

### Step 3b — regional-analyst-agent.md STEP 1

- [ ] **Step 4: Add context_block.txt as item 9 to STEP 1 input list**

In `.claude/agents/regional-analyst-agent.md`, find the STEP 1 input list which ends at item 8 (`output/regional/{region_lower}/research_scratchpad.json`). Add item 9:

```markdown
9. `output/regional/{region_lower}/context_block.txt` (if present) —
   AeroGrid's physical footprint in this region: sites, headcount,
   crown jewels, supply chain dependencies, key contracts.
   Cite specific assets when describing business impact in the So What section.
   If absent, proceed without it — do not fabricate footprint data.
```

### Step 3c — gatekeeper-agent.md TASK section

- [ ] **Step 5: Add FOOTPRINT variable to the TASK section**

In `.claude/agents/gatekeeper-agent.md`, find the `## TASK` section. After the sentence "You will be given a REGION and a list of CRITICAL ASSETS." and before the numbered read list, add:

```markdown
If provided, you will also receive:
`FOOTPRINT: {FOOTPRINT_SUMMARY}`
Use site criticality to calibrate escalation threshold — a region with a PRIMARY manufacturing site warrants a lower ESCALATE bar than a service-only presence.
```

- [ ] **Step 6: Verify the agent files are valid (no YAML errors)**

```bash
uv run python -c "
import re
for path in ['.claude/commands/run-crq.md', '.claude/agents/regional-analyst-agent.md', '.claude/agents/gatekeeper-agent.md']:
    text = open(path, encoding='utf-8').read()
    print(f'OK: {path} ({len(text)} chars)')
"
```

Expected: all three files print OK.

- [ ] **Step 7: Commit**

```bash
git add .claude/commands/run-crq.md .claude/agents/regional-analyst-agent.md .claude/agents/gatekeeper-agent.md
git commit -m "feat(M-3): wire footprint context blocks into pipeline — Phase 0, analyst, gatekeeper"
```

---

## Task M-4: API Endpoints

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Read the server.py section around the `/api/history` endpoint**

Open `server.py`. The `/api/history` endpoint is at approximately line 116. The `/api/trace` endpoint follows at approximately line 125. We insert the footprint endpoints between those two.

- [ ] **Step 2: Add the two footprint endpoints**

After the `get_history()` function (which ends at approximately line 122 with `return {"regions": ...}`), add before `@app.get("/api/trace")`:

```python
@app.get("/api/footprint")
async def get_footprint():
    """Return full regional_footprint.json."""
    path = Path("data/regional_footprint.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@app.put("/api/footprint/{region}")
async def update_footprint(region: str, payload: dict):
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

    # Update only the four editable fields
    entry = footprint[r]
    if "summary" in payload:
        entry["summary"] = payload["summary"]
    if "headcount" in payload:
        entry["headcount"] = int(payload["headcount"])
    if "notes" in payload:
        entry["notes"] = payload["notes"]
    if "rsm_email" in payload:
        # Update only the RSM entry's email, preserving notify_on
        rsm_role = f"{r} RSM"
        for stakeholder in entry.get("stakeholders", []):
            if stakeholder.get("role") == rsm_role:
                stakeholder["email"] = payload["rsm_email"]
                break

    # Atomic write via tmp file
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(footprint, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

    return {"ok": True}
```

Note: `payload: dict` uses FastAPI's body parsing. The `Path` import is already in server.py (check). `JSONResponse` is already imported.

- [ ] **Step 3: Verify the server starts without errors**

```bash
uv run python -c "import server; print('server.py imports OK')"
```

Expected: `server.py imports OK`

- [ ] **Step 4: Quick manual smoke test**

Start the server in the background and test the endpoints:

```bash
uv run uvicorn server:app --port 8001 &
sleep 2
curl -s http://127.0.0.1:8001/api/footprint | python -c "import sys,json; d=json.load(sys.stdin); print(list(d.keys()))"
curl -s -X PUT http://127.0.0.1:8001/api/footprint/APAC \
  -H "Content-Type: application/json" \
  -d '{"summary":"Updated summary","headcount":3300,"notes":"Test note","rsm_email":"new-rsm@aerowind.com"}' | python -c "import sys,json; print(json.load(sys.stdin))"
kill %1
```

Expected: `['APAC', 'AME', 'LATAM', 'MED', 'NCE']` then `{'ok': True}`.

- [ ] **Step 5: Restore the footprint file to original mock data**

```bash
git checkout data/regional_footprint.json
```

- [ ] **Step 6: Commit**

```bash
git add server.py
git commit -m "feat(M-4): add GET/PUT /api/footprint endpoints with atomic write"
```

---

## Task M-5: Config Tab — Footprint Panel

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`

### Step 5a — HTML: Add Footprint sub-tab nav + panel

- [ ] **Step 1: Read the Config tab section in index.html**

Open `static/index.html`. Find `id="tab-config"` (approximately line 380). The inner nav bar has `cfg-nav-sources` and `cfg-nav-prompts`. We add `cfg-nav-footprint`.

- [ ] **Step 2: Add the Footprint nav tab**

In the Config tab nav bar (the `<div>` that contains `cfg-nav-sources` and `cfg-nav-prompts`), add a third tab:

```html
<div class="nav-tab" id="cfg-nav-footprint" onclick="switchCfgTab('footprint')">Footprint</div>
```

Place it after `cfg-nav-sources` and before `cfg-nav-prompts`.

- [ ] **Step 3: Add the Footprint panel HTML**

After the closing tag of the Prompts sub-tab panel (look for the closing of `<!-- Prompts sub-tab -->`), add:

```html
<!-- Footprint sub-tab -->
<div id="cfg-footprint" class="hidden" style="flex:1;overflow-y:auto;padding:16px 20px">
  <div id="footprint-panels"></div>
</div>
```

- [ ] **Step 4: Add CSS for the footprint panel**

In the `<style>` section of `index.html`, add:

```css
.footprint-region { border:1px solid #21262d; border-radius:4px; margin-bottom:12px; }
.footprint-region-header { display:flex; align-items:center; justify-content:space-between; padding:8px 12px; cursor:pointer; background:#161b22; font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#8b949e; }
.footprint-region-body { padding:12px; display:none; }
.footprint-region-body.open { display:block; }
.footprint-field { margin-bottom:8px; }
.footprint-field label { display:block; font-size:9px; letter-spacing:0.08em; text-transform:uppercase; color:#6e7681; margin-bottom:3px; }
.footprint-field input, .footprint-field textarea { width:100%; background:#0d1117; border:1px solid #21262d; color:#c9d1d9; padding:4px 8px; border-radius:2px; font-size:11px; font-family:'IBM Plex Mono',monospace; box-sizing:border-box; }
.footprint-field textarea { resize:vertical; min-height:60px; }
.footprint-save-btn { font-size:10px; color:#6e7681; background:#0d1117; border:1px solid #21262d; padding:2px 10px; border-radius:2px; cursor:pointer; }
.footprint-save-btn:hover { color:#c9d1d9; border-color:#58a6ff; }
.footprint-dirty .footprint-region-header { color:#e3b341; }
```

### Step 5b — JS: Add footprint state + functions

- [ ] **Step 5: Read the cfgState section in app.js**

Open `static/app.js`. Find `const cfgState = {` (approximately line 623). Find the `switchCfgTab` function. Note the pattern — it shows/hides `cfg-sources`, `cfg-prompts` divs.

- [ ] **Step 6: Add footprint state to cfgState**

In the `cfgState` object, add:

```js
footprintLoaded: false,
footprintData: {},
footprintDirty: {},   // keyed by region
```

- [ ] **Step 7: Update switchCfgTab to handle 'footprint'**

In the `switchCfgTab` function, find where it sets active tabs. Add `footprint` to the list. The function likely has logic like:
```js
['sources', 'prompts'].forEach(p => ...)
```

Update to include `footprint` in all such arrays. Also add: when switching to `footprint`, call `loadFootprint()`.

The key change: wherever `cfg-sources` and `cfg-prompts` panels are shown/hidden, also handle `cfg-footprint`.

- [ ] **Step 8: Add loadFootprint(), renderFootprint(), and saveFootprintRegion() functions**

Add these functions after the existing config tab functions (e.g., after `saveAgentPrompt`):

```js
async function loadFootprint() {
  if (cfgState.footprintLoaded) { renderFootprint(); return; }
  const data = await fetch('/api/footprint').then(r => r.ok ? r.json() : {}).catch(() => ({}));
  cfgState.footprintData = data;
  cfgState.footprintDirty = {};
  cfgState.footprintLoaded = true;
  renderFootprint();
}

function renderFootprint() {
  const container = $('footprint-panels');
  if (!container) return;
  const regions = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
  container.innerHTML = regions.map(region => {
    const d = cfgState.footprintData[region] || {};
    const rsm = (d.stakeholders || []).find(s => s.role === `${region} RSM`) || {};
    const isDirty = cfgState.footprintDirty[region];
    return `
<div class="footprint-region${isDirty ? ' footprint-dirty' : ''}" id="fp-card-${region}">
  <div class="footprint-region-header" onclick="toggleFootprintRegion('${region}')">
    <span>${region}</span>
    <span>${d.summary ? d.summary.slice(0, 60) + (d.summary.length > 60 ? '...' : '') : 'No data'}</span>
    <span>▼</span>
  </div>
  <div class="footprint-region-body" id="fp-body-${region}">
    <div class="footprint-field">
      <label>Summary</label>
      <input type="text" id="fp-summary-${region}" value="${esc(d.summary || '')}" oninput="markFootprintDirty('${region}')">
    </div>
    <div class="footprint-field">
      <label>Headcount</label>
      <input type="number" id="fp-headcount-${region}" value="${d.headcount || ''}" oninput="markFootprintDirty('${region}')">
    </div>
    <div class="footprint-field">
      <label>RSM Email</label>
      <input type="text" id="fp-rsm-${region}" value="${esc(rsm.email || '')}" oninput="markFootprintDirty('${region}')">
    </div>
    <div class="footprint-field">
      <label>Notes (sites, contracts, crown jewels — freetext)</label>
      <textarea id="fp-notes-${region}" oninput="markFootprintDirty('${region}')">${esc(d.notes || '')}</textarea>
    </div>
    <div style="text-align:right;margin-top:8px">
      <button class="footprint-save-btn" onclick="saveFootprintRegion('${region}')">Save</button>
    </div>
  </div>
</div>`;
  }).join('');
}

function toggleFootprintRegion(region) {
  const body = $(`fp-body-${region}`);
  if (!body) return;
  body.classList.toggle('open');
}

function markFootprintDirty(region) {
  cfgState.footprintDirty[region] = true;
  const card = $(`fp-card-${region}`);
  if (card) card.classList.add('footprint-dirty');
}

async function saveFootprintRegion(region) {
  const payload = {
    summary:   $(`fp-summary-${region}`)?.value || '',
    headcount: parseInt($(`fp-headcount-${region}`)?.value || '0', 10),
    rsm_email: $(`fp-rsm-${region}`)?.value || '',
    notes:     $(`fp-notes-${region}`)?.value || '',
  };
  const r = await fetch(`/api/footprint/${region}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (r.ok) {
    // Refresh local state
    cfgState.footprintDirty[region] = false;
    cfgState.footprintLoaded = false;
    await loadFootprint();
  } else {
    alert(`Save failed for ${region}: ${r.status}`);
  }
}
```

- [ ] **Step 9: Add dirty-state guard on tab navigation**

In the existing tab navigation guard (the `isDirty` check before switching tabs — look for `cfgState.dirty.topics || cfgState.dirty.sources`), also check `Object.values(cfgState.footprintDirty).some(Boolean)` and include it in the unsaved warning condition.

- [ ] **Step 10: Verify the page loads without JS errors**

Start the dev server and open the browser:

```bash
uv run uvicorn server:app --port 8000
```

Open http://127.0.0.1:8000/ → Config tab → Footprint sub-tab.

Verify:
- Five collapsible region cards render
- Clicking a card header expands/collapses it
- Editing a field marks the card dirty (amber header color)
- Clicking Save calls PUT /api/footprint/{region} and refreshes the panel without page reload

- [ ] **Step 11: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(M-5): add Footprint panel to Config tab with per-region edit + save"
```

---

## Task M-6: Final Integration Verification

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass (including the 8 new `test_build_context` tests).

- [ ] **Step 2: Smoke-test build_context.py for all 5 regions**

```bash
for region in APAC AME LATAM MED NCE; do
  uv run python tools/build_context.py $region
done
ls output/regional/*/context_block.txt
```

Expected: 5 files created.

- [ ] **Step 3: Verify context_block.txt content for APAC**

```bash
cat output/regional/apac/context_block.txt
```

Expected output (approximate):
```
[REGIONAL FOOTPRINT — APAC]
Summary: Primary manufacturing region. 60% of global turbine output. Highest operational sensitivity.
Headcount: 3,200

Sites:
  - Kaohsiung Manufacturing Hub (TW) — manufacturing, PRIMARY
  - Shanghai Service Hub (CN) — service, HIGH
  - Tokyo Regional Office (JP) — service, MEDIUM

Crown Jewels: Series 7 production line | SCADA network TW-01 | OT predictive maintenance stack
Supply Chain Dependencies: Taiwanese semiconductor components | Korean rare earth supply
Key Contracts: TEPCO 5yr turbine supply agreement | Vestas APAC logistics JV
```

- [ ] **Step 4: Verify gatekeeper summary**

```bash
uv run python tools/build_context.py --gatekeeper-summary
```

Expected: 5 one-liner summaries, one per region.

- [ ] **Step 5: Commit final verification tag**

```bash
git commit --allow-empty -m "chore(M): Phase M complete — footprint context layer end-to-end verified"
```

---

## Summary

| Task | Files | Key output |
|---|---|---|
| M-1 | `data/regional_footprint.json` | 5-region mock data |
| M-2 | `tools/build_context.py`, `tests/test_build_context.py` | 8 tests passing, CLI working |
| M-3 | `run-crq.md`, `regional-analyst-agent.md`, `gatekeeper-agent.md` | Footprint injected into pipeline |
| M-4 | `server.py` | GET + PUT /api/footprint with atomic write |
| M-5 | `static/index.html`, `static/app.js` | Footprint panel in Config tab |
| M-6 | — | Full test suite passes, smoke tests verified |
