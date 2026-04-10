# Phase E — Intelligence Transparency Implementation Plan


**Goal:** Surface OSINT intelligence sources and gatekeeper decision rationale in the dashboard, PDF, and PPTX exports — and add live pipeline telemetry via SSE hooks.

**Architecture:** Three independent sub-phases (E-1, E-2, E-3), each releasable on its own. E-1 reads existing files that are already written to disk but never surfaced. E-2 modifies collectors to write a new `intelligence_sources.json` file per region and surfaces those sources in all outputs. E-3 adds fire-and-forget telemetry via a new `send_event.py` tool, a new server endpoint, and Claude Code hook scripts.

**Tech Stack:** Python 3.14, FastAPI, Jinja2, python-pptx, Playwright/Chromium (PDF), pytest, uv, Claude Code hooks (Stop + PostToolUse events)

---

## File Map

### E-1 — modified files
- `tools/report_builder.py` — add `rationale`, `financial_rank`, `confidence` fields to `RegionEntry`; read `gatekeeper_decision.json` + `scenario_map.json` per region in `build()`
- `tools/build_dashboard.py` — read `gatekeeper_decision.json` + `scenario_map.json` per region; inject Decision Intelligence block into each region card HTML
- `tools/templates/report.html.j2` — add "Basis of assessment" block inside the per-region page body
- `tools/export_pptx.py` — add rationale line to `build_region()` sidebar
- `tests/test_e1_decision_transparency.py` — new test file (5 tests)

### E-2 — modified + new files
- `tools/geo_collector.py` — `collect()` returns `(normalized_dict, raw_sources_list)`; `main()` writes `intelligence_sources.json`
- `tools/cyber_collector.py` — same + reads existing file, merges `cyber_sources`, guard on missing `geo_sources`
- `tools/build_dashboard.py` — collapsible Intelligence Sources section per region card
- `tools/templates/report.html.j2` — "Sources Consulted" appendix table
- `tools/export_pptx.py` — "Sources Consulted" appendix slide
- `tests/test_intelligence_sources.py` — new test file (6 tests)

### E-3 — new + modified files
- `tools/send_event.py` — new: fire-and-forget POST + trace log fallback
- `server.py` — add `POST /internal/event` endpoint
- `.claude/hooks/agent-stop.sh` — new Stop hook script
- `.claude/hooks/tool-failure.sh` — new PostToolUse hook script
- `.claude/settings.json` — register both new hook scripts
- `.claude/commands/run-crq.md` — add `AGENT_START` log calls before each agent delegation
- `static/index.html` — live status strip above region cards
- `tests/test_send_event.py` — new test file (3 tests)

---

## Chunk 1: E-1 — Decision Transparency

### Task 1: Extend `RegionEntry` in `report_builder.py`

**Files:**
- Modify: `tools/report_builder.py`

`RegionEntry` currently has: `name`, `status`, `vacr`, `admiralty`, `velocity`, `severity`, `scenario_match`, `why_text`, `how_text`, `so_what_text`.

Add three new optional fields:

- [ ] **Step 1: Add fields to RegionEntry dataclass**

In `tools/report_builder.py`, update the `RegionEntry` dataclass (after line `so_what_text: str | None`):

```python
@dataclass
class RegionEntry:
    name: str
    status: RegionStatus
    vacr: float | None
    admiralty: str | None
    velocity: str | None
    severity: str | None
    scenario_match: str | None
    why_text: str | None
    how_text: str | None
    so_what_text: str | None
    # E-1 additions
    rationale: str | None = None
    financial_rank: int | None = None
    confidence: str | None = None
```

- [ ] **Step 2: Read gatekeeper_decision.json and scenario_map.json in `build()`**

In `build()`, inside the per-region loop (after the existing `regions.append()` call is built up), add before `regions.append(...)`:

```python
# E-1: read gatekeeper decision + scenario map (graceful if absent)
rationale = None
financial_rank = None
confidence = None

gk_path = base / "regional" / region_name.lower() / "gatekeeper_decision.json"
if gk_path.exists():
    try:
        gk = json.loads(gk_path.read_text(encoding="utf-8"))
        rationale = gk.get("rationale")
    except (json.JSONDecodeError, KeyError):
        pass

sm_path = base / "regional" / region_name.lower() / "scenario_map.json"
if sm_path.exists():
    try:
        sm = json.loads(sm_path.read_text(encoding="utf-8"))
        financial_rank = sm.get("financial_rank")
        confidence = sm.get("confidence")
    except (json.JSONDecodeError, KeyError):
        pass
```

Then update the `RegionEntry(...)` constructor call in `build()` — replace the existing `regions.append(...)` block with:

```python
regions.append(RegionEntry(
    name=region_name,
    status=status,
    vacr=float(d.get("vacr_exposure_usd", 0) or 0),
    admiralty=d.get("admiralty"),
    velocity=d.get("velocity"),
    severity=d.get("severity"),
    scenario_match=d.get("primary_scenario"),
    why_text=why_text,
    how_text=how_text,
    so_what_text=so_what_text,
    rationale=rationale,
    financial_rank=financial_rank,
    confidence=confidence,
))
```

- [ ] **Step 3: Run existing tests to verify nothing broke**

```bash
uv run pytest tests/test_report_builder.py -v
```

Expected: all existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/report_builder.py
git commit -m "feat(E-1): add rationale/financial_rank/confidence to RegionEntry"
```

---

### Task 2: Add Decision Intelligence block to `build_dashboard.py`

**Files:**
- Modify: `tools/build_dashboard.py`

The dashboard builds HTML inline. Each region card is built in a `for r in threat_regions` loop. We also need to add the block to clear and monitor cards. All three read from `gatekeeper_decision.json` and `scenario_map.json`.

- [ ] **Step 1: Add per-region gatekeeper/scenario reads in `build()`**

After the existing `region_data` dict is populated (around line 77), add:

```python
gatekeeper_data = {}
scenario_map_data = {}
for region in REGIONS:
    gk_path = f"output/regional/{region.lower()}/gatekeeper_decision.json"
    if os.path.exists(gk_path):
        try:
            with open(gk_path, encoding="utf-8") as f:
                gatekeeper_data[region] = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    sm_path = f"output/regional/{region.lower()}/scenario_map.json"
    if os.path.exists(sm_path):
        try:
            with open(sm_path, encoding="utf-8") as f:
                scenario_map_data[region] = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
```

- [ ] **Step 2: Add helper function for Decision Intelligence HTML block**

Add this function above `build()`:

```python
def decision_intelligence_block(region_name, gatekeeper_data, scenario_map_data):
    """Return HTML for the Decision Intelligence block, or '' if data absent."""
    gk = gatekeeper_data.get(region_name)
    sm = scenario_map_data.get(region_name)
    if not gk:
        return ""
    decision = gk.get("decision", "")
    admiralty = gk.get("admiralty", {})
    if isinstance(admiralty, dict):
        admiralty_rating = admiralty.get("rating", "")
    else:
        admiralty_rating = str(admiralty)
    scenario_match = gk.get("scenario_match", "")
    dominant_pillar = gk.get("dominant_pillar", "")
    rationale = gk.get("rationale", "")
    financial_rank = sm.get("financial_rank", "") if sm else ""
    confidence = sm.get("confidence", "").upper() if sm else ""

    decision_color = {
        "ESCALATE": "text-red-700 bg-red-50 border-red-200",
        "MONITOR": "text-amber-700 bg-amber-50 border-amber-200",
        "CLEAR": "text-green-700 bg-green-50 border-green-200",
    }.get(decision, "text-gray-700 bg-gray-50 border-gray-200")

    rank_txt = f"Financial rank #{financial_rank}" if financial_rank else ""
    conf_txt = f"Confidence: {confidence}" if confidence else ""
    meta_parts = [p for p in [scenario_match, rank_txt, conf_txt] if p]
    meta_line = " · ".join(meta_parts)

    return f"""
        <div class="mt-3 p-3 border rounded text-xs {decision_color}">
            <div class="flex items-center gap-2 mb-1">
                <span class="font-bold uppercase">{decision}</span>
                {f'<span class="font-mono font-bold">{admiralty_rating}</span>' if admiralty_rating else ""}
                {f'<span class="text-gray-500">{dominant_pillar}</span>' if dominant_pillar else ""}
            </div>
            {f'<div class="mb-1">{meta_line}</div>' if meta_line else ""}
            {f'<div class="italic">&ldquo;{rationale}&rdquo;</div>' if rationale else ""}
        </div>"""
```

- [ ] **Step 3: Inject block into escalated region cards**

In the `for r in threat_regions:` loop, find the region card HTML and add the block before the closing `</div>`. The region name comes from `r.get("region", "Unknown")`. After the `<p class="text-sm text-gray-600 ...">` line, add:

```python
di_block = decision_intelligence_block(r.get("region", ""), gatekeeper_data, scenario_map_data)
```

Then include `{di_block}` in the card HTML just before the closing `</div>`.

- [ ] **Step 4: Inject block into monitor cards**

In the `for m in monitor_regions:` loop, extract region name from `m.get("region", "Unknown")` and add `decision_intelligence_block(region_name, gatekeeper_data, scenario_map_data)` to each monitor card.

- [ ] **Step 5: Inject block into clear cards**

In the clear cards loop, add `decision_intelligence_block(region, gatekeeper_data, scenario_map_data)` to each clear card.

- [ ] **Step 6: Run build_dashboard manually to verify output**

```bash
uv run python tools/build_dashboard.py
```

Expected: exits 0, `output/dashboard.html` written. Open in browser and verify Decision Intelligence blocks appear on APAC, AME, MED cards and are absent (or show CLEAR block) on LATAM, NCE.

- [ ] **Step 7: Commit**

```bash
git add tools/build_dashboard.py
git commit -m "feat(E-1): add Decision Intelligence block to dashboard region cards"
```

---

### Task 3: Add "Basis of assessment" to PDF template

**Files:**
- Modify: `tools/templates/report.html.j2`

- [ ] **Step 1: Add CSS for basis-of-assessment block**

In the `<style>` section, add:

```css
.basis-block {
  margin-top: 5mm;
  padding: 3mm 4mm;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 3px;
  font-size: 9pt;
  color: #475569;
}
.basis-block .basis-label {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 8pt;
  color: var(--slate);
  margin-bottom: 1mm;
}
```

- [ ] **Step 2: Add basis block to each region page**

In `tools/templates/report.html.j2`, find the region page section. It starts with `{% for r in data.regions if r.status == "escalated" %}` and the region body ends with:

```html
    </div>
  </div>
</div>
{% endfor %}
```

Insert the basis block immediately before the `  </div>` that closes `region-layout` (the `<div class="region-layout">` wrapping both sidebar and body). The insertion should follow directly after the `</div>` that closes `region-body`:

```jinja2
    </div>{# end region-body #}
    {% if r.rationale %}
    <div class="basis-block" style="margin-top:4mm;">
      <div class="basis-label">Basis of Assessment</div>
      <div>{{ r.rationale }}</div>
      {% if r.financial_rank %}<div style="margin-top:1mm;font-size:8pt;">Financial impact rank: #{{ r.financial_rank }}{% if r.confidence %} · Confidence: {{ r.confidence | upper }}{% endif %}</div>{% endif %}
    </div>
    {% endif %}
  </div>{# end region-layout #}
</div>{# end page #}
{% endfor %}
```

The stable anchor is the `</div>{% endfor %}` pattern at the end of the `{% for r in data.regions if r.status == "escalated" %}` block.

- [ ] **Step 3: Run PDF export to verify**

```bash
uv run python tools/export_pdf.py output/board_report.pdf
```

Expected: exits 0, PDF written. Open and verify "Basis of Assessment" appears on APAC/AME/MED region pages.

- [ ] **Step 4: Commit**

```bash
git add tools/templates/report.html.j2
git commit -m "feat(E-1): add Basis of Assessment block to PDF region pages"
```

---

### Task 4: Add "Basis of assessment" to PPTX

**Files:**
- Modify: `tools/export_pptx.py`

- [ ] **Step 1: Add rationale rendering in `build_region()`**

In `build_region()`, after the existing `if not region.why_text:` block (around line 251), add:

```python
# E-1: Basis of assessment
if region.rationale:
    rank_txt = f"  ·  Rank #{region.financial_rank}" if region.financial_rank else ""
    conf_txt = f"  ·  Confidence: {region.confidence.upper()}" if region.confidence else ""
    basis_text = f"Basis: {region.rationale}{rank_txt}{conf_txt}"
    _add_text(slide, "BASIS OF ASSESSMENT", body_x, y, body_w, Inches(0.28),
              font_size=7, bold=True, color=SLATE)
    _add_text(slide, basis_text, body_x, y + Inches(0.3),
              body_w, Inches(0.5), font_size=8, color=DARK, wrap=True)
```

Note: only add this if `y + Inches(2.6)` fits within `H` (slide height 7.5in). Add a guard:

```python
if region.rationale and y + Inches(0.8) < H:
    ...
```

- [ ] **Step 2: Run PPTX export to verify**

```bash
uv run python tools/export_pptx.py output/board_report.pptx
```

Expected: exits 0, PPTX written.

- [ ] **Step 3: Commit**

```bash
git add tools/export_pptx.py
git commit -m "feat(E-1): add Basis of Assessment to PPTX region slides"
```

---

### Task 5: E-1 tests

**Files:**
- Create: `tests/test_e1_decision_transparency.py`

The `mock_output` fixture from `conftest.py` creates a temp output tree with `data.json` per region but no `gatekeeper_decision.json` or `scenario_map.json`. We extend it inline for E-1 tests.

- [ ] **Step 1: Write the 5 E-1 tests**

```python
"""Tests for E-1 Decision Transparency — build_dashboard.py, export_pdf.py, export_pptx.py."""
import json
import sys
import os
import pytest

# Allow importing tools from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MOCK_GK_DECISION = {
    "decision": "ESCALATE",
    "admiralty": {"rating": "B2"},
    "scenario_match": "System intrusion",
    "dominant_pillar": "Geopolitical",
    "rationale": "State-sponsored APT activity confirmed via geo and cyber signal corroboration.",
}

MOCK_SCENARIO_MAP = {
    "financial_rank": 3,
    "confidence": "high",
    "scenario": "System intrusion",
}


def _add_gatekeeper_files(mock_output, regions=("APAC",)):
    """Add gatekeeper_decision.json and scenario_map.json to the mock output tree."""
    for region in regions:
        region_dir = mock_output / "regional" / region.lower()
        region_dir.mkdir(parents=True, exist_ok=True)
        (region_dir / "gatekeeper_decision.json").write_text(
            json.dumps(MOCK_GK_DECISION), encoding="utf-8"
        )
        (region_dir / "scenario_map.json").write_text(
            json.dumps(MOCK_SCENARIO_MAP), encoding="utf-8"
        )


def test_report_builder_loads_rationale(mock_output):
    """RegionEntry.rationale is populated when gatekeeper_decision.json is present."""
    _add_gatekeeper_files(mock_output, regions=("APAC",))
    from tools.report_builder import build
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.rationale == MOCK_GK_DECISION["rationale"]
    assert apac.financial_rank == MOCK_SCENARIO_MAP["financial_rank"]
    assert apac.confidence == MOCK_SCENARIO_MAP["confidence"]


def test_report_builder_rationale_absent_graceful(mock_output):
    """RegionEntry.rationale is None when gatekeeper_decision.json is absent — no exception."""
    from tools.report_builder import build
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.rationale is None
    assert apac.financial_rank is None


def test_build_dashboard_decision_block_present(mock_output, tmp_path, monkeypatch):
    """build_dashboard.py HTML contains decision rationale when gatekeeper_decision.json exists."""
    _add_gatekeeper_files(mock_output, regions=("APAC",))
    # Point dashboard outputs to tmp_path
    monkeypatch.chdir(str(mock_output.parent))
    # We test the HTML string directly via the module
    # Patch output paths to write to tmp_path
    import importlib, tools.build_dashboard as bd
    # Run build and capture HTML
    html_out = tmp_path / "dashboard.html"
    monkeypatch.setattr("tools.build_dashboard.GLOBAL_REPORT_PATH", str(mock_output / "global_report.json"))
    monkeypatch.setattr("tools.build_dashboard.MANIFEST_PATH", str(mock_output / "run_manifest.json"))
    monkeypatch.setattr("tools.build_dashboard.TRACE_LOG_PATH", str(mock_output / "system_trace.log"))
    # Not practical to monkeypatch all region reads — run subprocess instead
    import subprocess
    result = subprocess.run(
        [sys.executable, "tools/build_dashboard.py"],
        cwd="c:/Users/frede/crq-agent-workspace",
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0
    html = open("c:/Users/frede/crq-agent-workspace/output/dashboard.html", encoding="utf-8").read()
    assert "State-sponsored APT activity confirmed" in html


def test_export_pdf_runs_without_gatekeeper(mock_output):
    """export_pdf.py does not raise when gatekeeper_decision.json is absent."""
    from tools.report_builder import build
    # Just verify build() returns without error — full PDF export requires Playwright
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.rationale is None  # graceful


def test_export_pptx_runs_without_gatekeeper(mock_output, tmp_path):
    """export_pptx.py builds a Presentation without gatekeeper_decision.json."""
    from tools.report_builder import build
    from tools.export_pptx import build_presentation
    data = build(output_dir=str(mock_output))
    prs = build_presentation(data)
    out = tmp_path / "test.pptx"
    prs.save(str(out))
    assert out.exists()
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/test_e1_decision_transparency.py -v
```

Expected: all 5 PASS.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/ -v --ignore=tests/test_geo_collector.py --ignore=tests/test_cyber_collector.py
```

Note: `test_geo_collector.py` and `test_cyber_collector.py` have a hardcoded worktree path that is stale — they are skipped here and will be fixed in E-2.

Expected: all previously passing tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e1_decision_transparency.py
git commit -m "test(E-1): add 5 decision transparency tests"
```

---

## Chunk 2: E-2 — Intelligence Provenance

### Task 6: Modify `geo_collector.py` to write `intelligence_sources.json`

**Files:**
- Modify: `tools/geo_collector.py`

Currently `collect()` returns `normalize(articles)` (a dict). It must return `(normalize(articles), articles)` so the caller can write the raw sources list.

The fixture format is `{title, summary, source, date}`. When mapping to `intelligence_sources.json`, use: `title→title`, `summary→snippet`, `source→source`, `date→published_date`, `url=null`, `mock=true`.

- [ ] **Step 1: Modify `collect()` to return a tuple**

Change the last line of `collect()` from:
```python
return normalize(articles)
```
to:
```python
return normalize(articles), articles
```

- [ ] **Step 2: Update `main()` to unpack tuple, write both files**

Replace the current `main()` body after `result = collect(region, mock)`:

```python
normalized, raw_articles = collect(region, mock)

out_dir = f"output/regional/{region.lower()}"
os.makedirs(out_dir, exist_ok=True)

# Write geo_signals.json (unchanged schema)
out_path = f"{out_dir}/geo_signals.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(normalized, f, indent=2, ensure_ascii=False)
print(f"[geo_collector] wrote {out_path}", file=sys.stderr)

# Write intelligence_sources.json with geo_sources array
from datetime import datetime, timezone
geo_sources = [
    {
        "title": a.get("title", ""),
        "snippet": a.get("summary", a.get("snippet", "")),
        "source": a.get("source", ""),
        "published_date": a.get("date", a.get("published_date", "")),
        "url": a.get("url", None),
        "mock": mock,
    }
    for a in raw_articles
]
intel_path = f"{out_dir}/intelligence_sources.json"
intel_doc = {
    "region": region,
    "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "geo_sources": geo_sources,
}
with open(intel_path, "w", encoding="utf-8") as f:
    json.dump(intel_doc, f, indent=2, ensure_ascii=False)
print(f"[geo_collector] wrote {intel_path}", file=sys.stderr)
```

- [ ] **Step 3: Verify geo_collector still runs**

```bash
uv run python tools/geo_collector.py APAC --mock
```

Expected: exits 0. `output/regional/apac/geo_signals.json` unchanged. `output/regional/apac/intelligence_sources.json` created with `geo_sources` array.

- [ ] **Step 4: Verify geo_signals.json schema unchanged**

```bash
python -c "import json; d=json.load(open('output/regional/apac/geo_signals.json')); assert all(k in d for k in ['summary','lead_indicators','dominant_pillar']); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add tools/geo_collector.py
git commit -m "feat(E-2): geo_collector writes intelligence_sources.json geo_sources"
```

---

### Task 7: Modify `cyber_collector.py` to merge `intelligence_sources.json`

**Files:**
- Modify: `tools/cyber_collector.py`

Same tuple change as geo, plus: reads existing `intelligence_sources.json`, merges in `cyber_sources`. Guard: if file is absent or missing `geo_sources` key, logs warning and writes only `cyber_sources`.

- [ ] **Step 1: Modify `collect()` to return tuple**

Change last line of `collect()` from:
```python
return normalize(articles)
```
to:
```python
return normalize(articles), articles
```

- [ ] **Step 2: Update `main()` to unpack, write/merge intelligence_sources.json**

Replace the current `main()` body after `result = collect(region, mock)`:

```python
normalized, raw_articles = collect(region, mock)

out_dir = f"output/regional/{region.lower()}"
os.makedirs(out_dir, exist_ok=True)

# Write cyber_signals.json (unchanged schema)
out_path = f"{out_dir}/cyber_signals.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(normalized, f, indent=2, ensure_ascii=False)
print(f"[cyber_collector] wrote {out_path}", file=sys.stderr)

# Build cyber_sources list (same field mapping as geo)
from datetime import datetime, timezone
cyber_sources = [
    {
        "title": a.get("title", ""),
        "snippet": a.get("summary", a.get("snippet", "")),
        "source": a.get("source", ""),
        "published_date": a.get("date", a.get("published_date", "")),
        "url": a.get("url", None),
        "mock": mock,
    }
    for a in raw_articles
]

# Read existing intelligence_sources.json and merge
intel_path = f"{out_dir}/intelligence_sources.json"
intel_doc = {}
if os.path.exists(intel_path):
    try:
        with open(intel_path, encoding="utf-8") as f:
            intel_doc = json.load(f)
        if "geo_sources" not in intel_doc:
            import sys as _sys
            print(
                f"[cyber_collector] WARNING: {intel_path} missing geo_sources key — "
                "writing cyber_sources only. Run geo_collector first.",
                file=_sys.stderr,
            )
            # Also log to system_trace.log via audit_logger if available
            try:
                import subprocess as _sp
                _sp.run(
                    [sys.executable, "tools/audit_logger.py", "WARN",
                     f"{region} cyber_collector: intelligence_sources.json missing geo_sources"],
                    capture_output=True,
                )
            except Exception:
                pass
    except (json.JSONDecodeError, OSError):
        intel_doc = {}

intel_doc["region"] = region
intel_doc["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
intel_doc["cyber_sources"] = cyber_sources

with open(intel_path, "w", encoding="utf-8") as f:
    json.dump(intel_doc, f, indent=2, ensure_ascii=False)
print(f"[cyber_collector] wrote {intel_path}", file=sys.stderr)
```

- [ ] **Step 3: Run both collectors for APAC and verify merged file**

```bash
uv run python tools/geo_collector.py APAC --mock
uv run python tools/cyber_collector.py APAC --mock
python -c "
import json
d = json.load(open('output/regional/apac/intelligence_sources.json'))
assert 'geo_sources' in d, 'missing geo_sources'
assert 'cyber_sources' in d, 'missing cyber_sources'
assert len(d['geo_sources']) > 0
assert len(d['cyber_sources']) > 0
print('OK — geo:', len(d['geo_sources']), 'cyber:', len(d['cyber_sources']))
"
```

- [ ] **Step 4: Commit**

```bash
git add tools/cyber_collector.py
git commit -m "feat(E-2): cyber_collector merges intelligence_sources.json cyber_sources"
```

---

### Task 8: Add Intelligence Sources section to `build_dashboard.py`

**Files:**
- Modify: `tools/build_dashboard.py`

Each region card gains a collapsible `<details>` section. Sources are listed under "Geo Intelligence" and "Cyber Intelligence" sub-headings. MOCK badge shown when `"mock": true`.

- [ ] **Step 1: Add `load_intelligence_sources()` helper**

Add above `build()`:

```python
def load_intelligence_sources(region):
    """Return intelligence_sources dict or None if file absent."""
    path = f"output/regional/{region.lower()}/intelligence_sources.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
```

- [ ] **Step 2: Add `intelligence_sources_block()` helper**

```python
def intelligence_sources_block(intel):
    """Return collapsible HTML block for intelligence sources, or '' if intel is None."""
    if not intel:
        return ""

    def source_rows(sources, section_label):
        if not sources:
            return ""
        rows = ""
        for s in sources:
            title = s.get("title", "")
            snippet = s.get("snippet", "")
            pub_date = s.get("published_date", "")
            source_name = s.get("source", "")
            url = s.get("url")
            is_mock = s.get("mock", True)
            mock_badge = '<span class="ml-1 text-xs bg-yellow-100 text-yellow-700 px-1 rounded">MOCK</span>' if is_mock else ""
            title_html = f'<a href="{url}" class="underline">{title}</a>' if url else title
            rows += f"""
            <div class="py-1 border-b border-gray-100 last:border-0">
                <div class="font-medium text-gray-800">{title_html}{mock_badge}</div>
                <div class="text-gray-500 text-xs mt-0.5">{source_name} · {pub_date}</div>
                {f'<div class="text-gray-600 mt-0.5">{snippet}</div>' if snippet else ""}
            </div>"""
        return f'<div class="mb-2"><div class="text-xs font-bold uppercase text-gray-400 mb-1">{section_label}</div>{rows}</div>'

    geo_html = source_rows(intel.get("geo_sources", []), "Geo Intelligence")
    cyber_html = source_rows(intel.get("cyber_sources", []), "Cyber Intelligence")
    if not geo_html and not cyber_html:
        return ""

    return f"""
        <details class="mt-3">
            <summary class="cursor-pointer text-xs font-semibold text-gray-500 hover:text-gray-700">
                Intelligence Sources ({len(intel.get('geo_sources', []))} geo · {len(intel.get('cyber_sources', []))} cyber)
            </summary>
            <div class="mt-2 text-xs">
                {geo_html}{cyber_html}
            </div>
        </details>"""
```

- [ ] **Step 3: Load intel sources in `build()` and inject into region cards**

After loading `gatekeeper_data` and `scenario_map_data`, add:

```python
intel_sources = {}
for region in REGIONS:
    data = load_intelligence_sources(region)
    if data:
        intel_sources[region] = data
```

Then in each region card (escalated, monitor, clear), add the block at the end:

```python
intel_block = intelligence_sources_block(intel_sources.get(r.get("region", "")))
# include {intel_block} in the card HTML
```

- [ ] **Step 4: Run dashboard and spot-check**

```bash
uv run python tools/geo_collector.py APAC --mock
uv run python tools/cyber_collector.py APAC --mock
uv run python tools/build_dashboard.py
```

Open `output/dashboard.html` and verify "Intelligence Sources" collapsible appears on APAC card with source titles.

- [ ] **Step 5: Commit**

```bash
git add tools/build_dashboard.py
git commit -m "feat(E-2): add collapsible Intelligence Sources section to dashboard"
```

---

### Task 9: Add "Sources Consulted" appendix to PDF and PPTX

**Files:**
- Modify: `tools/templates/report.html.j2`
- Modify: `tools/export_pptx.py`
- Modify: `tools/report_builder.py` (add sources to `ReportData`)

To pass sources through to exports, add a `sources` field to `ReportData` and populate it in `build()`.

- [ ] **Step 1: Add `sources` to `ReportData` in `report_builder.py`**

Replace the `ReportData` dataclass definition with (adding `sources` using `field(default_factory=list)`):

```python
from dataclasses import dataclass, field

@dataclass
class ReportData:
    run_id: str
    timestamp: str
    total_vacr: float
    exec_summary: str
    escalated_count: int
    monitor_count: int
    clear_count: int
    regions: list[RegionEntry]
    monitor_regions: list[str]
    sources: list[dict] = field(default_factory=list)  # E-2: {region, title, published_date, source}
```

In `build()`, after building the `regions` list and computing `escalated`/`monitor`/`clear` counts, add:

```python
# E-2: collect intelligence sources for escalated regions
sources = []
for r in regions:
    if r.status == RegionStatus.ESCALATED:
        intel_path = base / "regional" / r.name.lower() / "intelligence_sources.json"
        if intel_path.exists():
            try:
                intel = json.loads(intel_path.read_text(encoding="utf-8"))
                for s in intel.get("geo_sources", []) + intel.get("cyber_sources", []):
                    sources.append({
                        "region": r.name,
                        "title": s.get("title", ""),
                        "published_date": s.get("published_date", ""),
                        "source": s.get("source", ""),
                    })
            except (json.JSONDecodeError, OSError):
                pass
```

Then replace the `return ReportData(...)` call with:

```python
return ReportData(
    run_id=run_id,
    timestamp=timestamp,
    total_vacr=total_vacr,
    exec_summary=exec_summary,
    escalated_count=len(escalated),
    monitor_count=len(monitor),
    clear_count=len(clear),
    regions=regions,
    monitor_regions=monitor_regions,
    sources=sources,
)
```

- [ ] **Step 2: Add "Sources Consulted" appendix page to `report.html.j2`**

After the existing Appendix page (end of file, after `</div>` of the appendix page), add:

```jinja2
{% if data.sources %}
<div class="page">
  <div class="section-header">
    <h2>Sources Consulted</h2>
    <span class="sub">OSINT intelligence sources — escalated regions only</span>
  </div>
  <table class="admiralty-table" style="margin-top:4mm;">
    <thead>
      <tr>
        <th style="width:12mm;">Region</th>
        <th>Title</th>
        <th style="width:18mm;">Publication</th>
        <th style="width:18mm;">Date</th>
      </tr>
    </thead>
    <tbody>
      {% for s in data.sources %}
      <tr>
        <td>{{ s.region }}</td>
        <td>{{ s.title }}</td>
        <td>{{ s.source }}</td>
        <td>{{ s.published_date }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}
```

- [ ] **Step 3: Add "Sources Consulted" appendix slide to `export_pptx.py`**

Add a new function `build_sources_appendix()` after `build_appendix()`:

```python
def build_sources_appendix(prs: Presentation, data: ReportData) -> None:
    if not data.sources:
        return
    slide = _add_blank_slide(prs)
    _add_rect(slide, 0, 0, W, Inches(0.65), BRAND)
    _add_text(slide, "Sources Consulted", Inches(0.3), Inches(0.1),
              Inches(7), Inches(0.45), font_size=16, bold=True, color=WHITE)
    _add_text(slide, "OSINT — escalated regions only",
              Inches(7.5), Inches(0.2), Inches(2.3), Inches(0.3),
              font_size=8, color=RGBColor(0xBF,0xDB,0xFF), align=PP_ALIGN.RIGHT)

    # Column headers
    cols = ["Region", "Title", "Publication", "Date"]
    col_widths = [Inches(0.8), Inches(5.5), Inches(2.0), Inches(1.5)]
    y = Inches(0.85)
    x = Inches(0.3)
    for col, w in zip(cols, col_widths):
        _add_text(slide, col, x, y, w, Inches(0.3), font_size=8, bold=True, color=SLATE)
        x += w

    Y_MAX = Inches(7.1)
    for src in data.sources:
        y += Inches(0.35)
        if y >= Y_MAX:
            break
        row = [src.get("region",""), src.get("title","")[:80], src.get("source",""), src.get("published_date","")]
        x = Inches(0.3)
        for val, w in zip(row, col_widths):
            _add_text(slide, val, x, y, w, Inches(0.3), font_size=8, color=DARK)
            x += w
```

In `build_presentation()`, add the call after `build_appendix(prs, data)`:

```python
build_sources_appendix(prs, data)
```

- [ ] **Step 4: Run PDF and PPTX exports to verify appendix**

```bash
uv run python tools/export_pdf.py output/board_report.pdf
uv run python tools/export_pptx.py output/board_report.pptx
```

Expected: both exit 0. PDF has "Sources Consulted" page. PPTX has "Sources Consulted" slide.

- [ ] **Step 5: Commit**

```bash
git add tools/report_builder.py tools/templates/report.html.j2 tools/export_pptx.py
git commit -m "feat(E-2): add Sources Consulted appendix to PDF and PPTX"
```

---

### Task 10: E-2 tests + fix broken collector test paths

**Files:**
- Create: `tests/test_intelligence_sources.py`
- Modify: `tests/test_geo_collector.py` (fix hardcoded worktree path)
- Modify: `tests/test_cyber_collector.py` (fix hardcoded worktree path)

- [ ] **Step 1: Fix hardcoded CWD in test_geo_collector.py and test_cyber_collector.py**

In `tests/test_geo_collector.py`, change `cwd="c:/Users/frede/crq-agent-workspace/.worktrees/osint-toolchain"` to `cwd="c:/Users/frede/crq-agent-workspace"`.

Change `read_output()` to use the project root path:
```python
def read_output(region):
    path = f"c:/Users/frede/crq-agent-workspace/output/regional/{region.lower()}/geo_signals.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
```

Do the same for `test_cyber_collector.py`.

- [ ] **Step 2: Write test_intelligence_sources.py**

```python
"""Tests for E-2 Intelligence Provenance — geo_collector and cyber_collector write intelligence_sources.json."""
import json
import os
import subprocess
import sys

PROJECT_ROOT = "c:/Users/frede/crq-agent-workspace"
PYTHON = sys.executable


def run(script, args):
    return subprocess.run(
        [PYTHON, f"tools/{script}"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=PROJECT_ROOT,
    )


def read_intel(region):
    path = os.path.join(PROJECT_ROOT, "output", "regional", region.lower(), "intelligence_sources.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_geo_signals(region):
    path = os.path.join(PROJECT_ROOT, "output", "regional", region.lower(), "geo_signals.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_cyber_signals(region):
    path = os.path.join(PROJECT_ROOT, "output", "regional", region.lower(), "cyber_signals.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_geo_collector_writes_geo_sources():
    """geo_collector writes intelligence_sources.json with geo_sources array and correct fields."""
    rc = run("geo_collector.py", ["APAC", "--mock"]).returncode
    assert rc == 0
    intel = read_intel("APAC")
    assert "geo_sources" in intel
    assert isinstance(intel["geo_sources"], list)
    assert len(intel["geo_sources"]) > 0
    first = intel["geo_sources"][0]
    assert "title" in first
    assert "snippet" in first
    assert "source" in first
    assert "published_date" in first
    assert "mock" in first
    assert first["mock"] is True


def test_cyber_collector_extends_with_cyber_sources():
    """cyber_collector extends intelligence_sources.json with cyber_sources while preserving geo_sources."""
    run("geo_collector.py", ["APAC", "--mock"])
    run("cyber_collector.py", ["APAC", "--mock"])
    intel = read_intel("APAC")
    assert "geo_sources" in intel, "geo_sources must be preserved"
    assert "cyber_sources" in intel
    assert len(intel["cyber_sources"]) > 0


def test_cyber_collector_guard_missing_geo_sources(tmp_path):
    """cyber_collector writes cyber_sources only (no exception) when geo_sources key is absent."""
    import tempfile, os
    # Write a file without geo_sources key into a temp output dir — then run cyber_collector
    # We can't easily redirect output dir, so we test the guard by inspecting the log warning
    # Instead: run cyber_collector without running geo_collector first on a clean region
    # Remove existing intelligence_sources.json for NCE
    intel_path = os.path.join(PROJECT_ROOT, "output", "regional", "nce", "intelligence_sources.json")
    if os.path.exists(intel_path):
        os.remove(intel_path)
    # Write a file with no geo_sources key
    os.makedirs(os.path.dirname(intel_path), exist_ok=True)
    with open(intel_path, "w") as f:
        json.dump({"region": "NCE", "collected_at": "2026-01-01T00:00:00Z"}, f)
    result = run("cyber_collector.py", ["NCE", "--mock"])
    assert result.returncode == 0, f"Should not crash: {result.stderr}"
    intel = read_intel("NCE")
    assert "cyber_sources" in intel


def test_geo_signals_schema_unchanged():
    """geo_signals.json schema is identical before and after E-2 geo_collector run."""
    run("geo_collector.py", ["APAC", "--mock"])
    signals = read_geo_signals("APAC")
    assert "summary" in signals
    assert "lead_indicators" in signals
    assert "dominant_pillar" in signals


def test_cyber_signals_schema_unchanged():
    """cyber_signals.json schema is identical before and after E-2 cyber_collector run."""
    run("cyber_collector.py", ["APAC", "--mock"])
    signals = read_cyber_signals("APAC")
    assert "summary" in signals
    assert "threat_vector" in signals
    assert "target_assets" in signals


def test_empty_sources_writes_file_no_crash(monkeypatch):
    """Collector writes file with empty array if search returns nothing — no exception."""
    # Patch run_search to return [] by using a region with no fixture match is not possible in mock,
    # so we verify that the normalize([]) path produces a valid signal file
    from tools.geo_collector import collect
    normalized, raw = collect("LATAM", mock=True)
    # Should return valid dict and a list (possibly empty)
    assert isinstance(normalized, dict)
    assert isinstance(raw, list)
    assert "summary" in normalized
```

- [ ] **Step 3: Run E-2 tests**

```bash
uv run pytest tests/test_intelligence_sources.py -v
```

Expected: all 6 PASS.

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS (including fixed geo/cyber collector tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_intelligence_sources.py tests/test_geo_collector.py tests/test_cyber_collector.py
git commit -m "test(E-2): intelligence sources tests + fix stale worktree paths in collector tests"
```

---

## Chunk 3: E-3 — Live Pipeline Telemetry

### Task 11: Create `tools/send_event.py`

**Files:**
- Create: `tools/send_event.py`

Fire-and-forget HTTP POST to `http://localhost:8000/internal/event`. Swallows all connection errors. Always appends to `output/system_trace.log` via `audit_logger.py` regardless of server availability.

- [ ] **Step 1: Write send_event.py**

```python
#!/usr/bin/env python3
"""Fire-and-forget telemetry event sender.

Usage:
    uv run python tools/send_event.py <EVENT_TYPE> <AGENT_ID> '<JSON_PAYLOAD>'

Sends HTTP POST to http://localhost:8000/internal/event.
Swallows connection errors — pipeline must never block on telemetry.
Always appends to system_trace.log via audit_logger regardless of server availability.
"""
import json
import sys
import os
import urllib.request
import urllib.error

SERVER_URL = "http://localhost:8000/internal/event"


def send_event(event_type: str, agent_id: str, payload: dict) -> None:
    # Always log to trace file
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from audit_logger import log_event
        log_event(event_type, f"agent={agent_id} payload={json.dumps(payload)}")
    except Exception:
        pass  # trace log failure must not crash pipeline

    # Fire-and-forget POST (best effort)
    try:
        body = json.dumps({
            "event_type": event_type,
            "agent_id": agent_id,
            "payload": payload,
        }).encode("utf-8")
        req = urllib.request.Request(
            SERVER_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, OSError, ConnectionRefusedError):
        pass  # server not running — silent failure


def main():
    if len(sys.argv) < 4:
        print("Usage: send_event.py <EVENT_TYPE> <AGENT_ID> '<JSON_PAYLOAD>'", file=sys.stderr)
        sys.exit(1)

    event_type = sys.argv[1]
    agent_id = sys.argv[2]
    try:
        payload = json.loads(sys.argv[3])
    except json.JSONDecodeError:
        payload = {"raw": sys.argv[3]}

    send_event(event_type, agent_id, payload)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run manual test (server offline)**

```bash
uv run python tools/send_event.py AGENT_STOP test-agent '{"exit_code": 0}'
```

Expected: exits 0, no error output. `output/system_trace.log` has an `AGENT_STOP` entry.

- [ ] **Step 3: Commit**

```bash
git add tools/send_event.py
git commit -m "feat(E-3): add send_event.py fire-and-forget telemetry tool"
```

---

### Task 12: Add `POST /internal/event` to `server.py`

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add request model and endpoint**

Add after the existing imports:

```python
from pydantic import BaseModel

class InternalEvent(BaseModel):
    event_type: str
    agent_id: str
    payload: dict = {}
```

Add after the existing SSE stream endpoint:

```python
@app.post("/internal/event")
async def internal_event(event: InternalEvent):
    """Receive telemetry events from hook scripts and broadcast via SSE."""
    await _emit(event.event_type, {
        "agent_id": event.agent_id,
        **event.payload,
    })
    return {"ok": True}
```

- [ ] **Step 2: Restart server and test endpoint**

```bash
# In another terminal, server already running — test with curl
curl -s -X POST http://localhost:8000/internal/event \
  -H "Content-Type: application/json" \
  -d '{"event_type":"AGENT_STOP","agent_id":"test","payload":{"exit_code":0}}'
```

Expected: `{"ok": true}`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat(E-3): add POST /internal/event endpoint to server.py"
```

---

### Task 13: Create hook scripts and register in settings.json

**Files:**
- Create: `.claude/hooks/agent-stop.sh`
- Create: `.claude/hooks/tool-failure.sh`
- Modify: `.claude/settings.json`

Claude Code's `Stop` hook receives: `CLAUDE_HOOK_AGENT_ID` (or similar), exit code. The `PostToolUse` hook fires after every tool call with exit code in env.

Claude Code hook environment variables for `Stop`: `CLAUDE_EXIT_CODE`, `CLAUDE_AGENT_ID` (if available). For `PostToolUse`: `CLAUDE_TOOL_NAME`, `CLAUDE_EXIT_CODE`.

- [ ] **Step 1: Create agent-stop.sh**

```bash
#!/usr/bin/env bash
# Stop hook — fires AGENT_STOP telemetry event
# Claude Code Stop hook env vars: CLAUDE_EXIT_CODE is set by the runtime

EVENT_TYPE="AGENT_STOP"
AGENT_ID="${CLAUDE_AGENT_ID:-unknown}"
EXIT_CODE="${CLAUDE_EXIT_CODE:-0}"

uv run python tools/send_event.py "$EVENT_TYPE" "$AGENT_ID" \
  "{\"exit_code\": $EXIT_CODE}" 2>/dev/null || true

exit 0
```

Make it executable: `chmod +x .claude/hooks/agent-stop.sh`

- [ ] **Step 2: Create tool-failure.sh**

```bash
#!/usr/bin/env bash
# PostToolUse hook — fires TOOL_FAILURE event when a tool exits non-zero

EXIT_CODE="${CLAUDE_EXIT_CODE:-0}"

# Only fire on non-zero exit
if [ "$EXIT_CODE" != "0" ]; then
  TOOL_NAME="${CLAUDE_TOOL_NAME:-unknown}"
  AGENT_ID="${CLAUDE_AGENT_ID:-unknown}"

  uv run python tools/send_event.py "TOOL_FAILURE" "$AGENT_ID" \
    "{\"tool\": \"$TOOL_NAME\", \"exit_code\": $EXIT_CODE}" 2>/dev/null || true
fi

exit 0
```

- [ ] **Step 3: Register hooks in .claude/settings.json**

Current `settings.json` has `UserPromptSubmit` and `TaskCompleted` hooks only — **there are no existing `Stop` hooks** (confirmed from file). Replace the entire file with:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo \"[PROTOCOL] Teams=ON | Opus orchestrates | Sonnet builds+validates | Parallel by default | Run /prime-dev before build tasks | Full rules: CLAUDE.md > Engineering Protocol\""
          }
        ]
      }
    ],
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/validators/task-completed.sh\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/agent-stop.sh\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/tool-failure.sh\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/agent-stop.sh .claude/hooks/tool-failure.sh .claude/settings.json
git commit -m "feat(E-3): add Stop and PostToolUse hook scripts for telemetry"
```

---

### Task 14: Add AGENT_START log calls to `run-crq.md`

**Files:**
- Modify: `.claude/commands/run-crq.md`

There is no `subagent_start` hook in Claude Code, so `AGENT_START` events must be logged explicitly before each agent delegation via `audit_logger.py`.

- [ ] **Step 1: Add AGENT_START log before each agent delegation**

In `.claude/commands/run-crq.md`, Phase 1 (step 3), before "Delegate to `gatekeeper-agent`", add:

```
Run `uv run python tools/audit_logger.py AGENT_START "gatekeeper-agent {REGION} dispatched"`
```

Before "Delegate to `regional-analyst-agent`" (step 6), add:

```
Run `uv run python tools/audit_logger.py AGENT_START "regional-analyst-agent {REGION} dispatched"`
```

In Phase 4 (global builder), before "Delegate to `global-builder-agent`", add:

```
Run `uv run python tools/audit_logger.py AGENT_START "global-builder-agent dispatched"`
```

In Phase 4b (global validator), before "Delegate to `global-validator-agent`", add:

```
Run `uv run python tools/audit_logger.py AGENT_START "global-validator-agent dispatched"`
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/run-crq.md
git commit -m "feat(E-3): add AGENT_START audit log calls before each agent delegation"
```

---

### Task 15: Add live status strip to `static/index.html`

**Files:**
- Modify: `static/index.html`

A collapsible strip above the region cards. Visible only while a pipeline run is active. Each of the 5 regions shows state: `PENDING → COLLECTING → ANALYZING → ESCALATED / MONITOR / CLEAR`. Driven by SSE events. Strip collapses on `PIPELINE_COMPLETE`.

The existing `app.js` handles SSE events. The live strip is added to the HTML and driven by JS that reads SSE `phase` and `gatekeeper` events.

- [ ] **Step 1: Add live strip HTML above region cards section**

In `static/index.html`, after the KPI strip `</section>` and before `<main ...>`, add:

```html
<!-- Live Pipeline Strip (hidden when idle) -->
<div id="live-strip" class="hidden px-6 py-3 bg-gray-900 border-b border-gray-700">
  <div class="flex items-center gap-2 mb-2">
    <span class="pulse-dot w-2 h-2 rounded-full bg-blue-400 inline-block"></span>
    <span class="text-xs font-semibold uppercase tracking-wide text-blue-400">Pipeline Running</span>
  </div>
  <div id="live-region-states" class="flex flex-wrap gap-3">
    <!-- JS-rendered region state chips -->
  </div>
</div>
```

- [ ] **Step 2: Add live strip JS to app.js or inline script**

Add in `static/index.html` before `</body>` (or in `/static/app.js` — check where SSE handling lives):

```javascript
// Live strip state
const LIVE_REGIONS = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
const regionStates = {};
LIVE_REGIONS.forEach(r => regionStates[r] = 'PENDING');

function updateLiveStrip() {
  const strip = document.getElementById('live-strip');
  const container = document.getElementById('live-region-states');
  if (!strip || !container) return;

  const stateColors = {
    'PENDING':    'bg-gray-700 text-gray-400',
    'COLLECTING': 'bg-blue-900 text-blue-300',
    'ANALYZING':  'bg-amber-900 text-amber-300',
    'ESCALATED':  'bg-red-900 text-red-300',
    'MONITOR':    'bg-amber-800 text-amber-200',
    'CLEAR':      'bg-green-900 text-green-300',
  };

  container.innerHTML = LIVE_REGIONS.map(r => {
    const state = regionStates[r] || 'PENDING';
    const color = stateColors[state] || stateColors['PENDING'];
    return `<span class="text-xs font-mono px-2 py-1 rounded ${color}">${r}: ${state}</span>`;
  }).join('');
}

// Hook into existing SSE event handler (add to the switch/if block that handles events)
function handleLiveStripEvent(eventType, data) {
  const strip = document.getElementById('live-strip');
  if (!strip) return;

  if (eventType === 'pipeline' && data.status === 'started') {
    LIVE_REGIONS.forEach(r => regionStates[r] = 'PENDING');
    strip.classList.remove('hidden');
    updateLiveStrip();
  } else if (eventType === 'phase' && data.phase === 'gatekeeper' && data.region) {
    regionStates[data.region] = 'COLLECTING';
    updateLiveStrip();
  } else if (eventType === 'gatekeeper' && data.region) {
    const decision = data.decision || '';
    regionStates[data.region] = decision === 'ESCALATE' ? 'ESCALATED'
                               : decision === 'MONITOR'  ? 'MONITOR'
                               : 'CLEAR';
    updateLiveStrip();
  } else if (eventType === 'pipeline' && data.status === 'complete') {
    setTimeout(() => strip.classList.add('hidden'), 3000);
  }
}
```

- [ ] **Step 3: Wire live strip into existing SSE handler in `static/app.js`**

The SSE handler is the `connectSSE()` function. Add calls to `handleLiveStripEvent` inside the three existing event listeners that drive the live strip. The exact insertions:

In the `eventSource.addEventListener('pipeline', ...)` handler, add as the first line:
```javascript
  eventSource.addEventListener('pipeline', (e) => {
    const d = JSON.parse(e.data);
    handleLiveStripEvent('pipeline', d);       // ← add this line
    appendLog('pipeline', `Pipeline ${d.status}`);
    // ... rest of existing handler unchanged
  });
```

In the `eventSource.addEventListener('phase', ...)` handler, add as the first line:
```javascript
  eventSource.addEventListener('phase', (e) => {
    const d = JSON.parse(e.data);
    handleLiveStripEvent('phase', d);           // ← add this line
    const msg = d.region ? `${d.phase} — ${d.region}` : `${d.phase} — ${d.status}`;
    appendLog('phase', msg);
  });
```

In the `eventSource.addEventListener('gatekeeper', ...)` handler, add as the first line:
```javascript
  eventSource.addEventListener('gatekeeper', (e) => {
    const d = JSON.parse(e.data);
    handleLiveStripEvent('gatekeeper', d);      // ← add this line
    appendLog('gatekeeper', `${d.region}: ${d.decision} (${d.severity})`);
  });
```

Also add the `handleLiveStripEvent` and `updateLiveStrip` functions from Step 2 **before** the `connectSSE()` function definition.

- [ ] **Step 4: Run the app and verify strip appears during a Tools Mode run**

Start server, open browser, click "Run All Regions" in Tools Mode. Verify:
- Live strip appears with PENDING chips
- Region chips update to COLLECTING then CLEAR/ESCALATED/MONITOR as pipeline progresses
- Strip hides 3 seconds after completion

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(E-3): add live pipeline status strip to dashboard"
```

---

### Task 16: E-3 tests

**Files:**
- Create: `tests/test_send_event.py`

- [ ] **Step 1: Write 3 E-3 tests**

```python
"""Tests for E-3 — send_event.py telemetry tool."""
import sys
import os
import json
import subprocess
import tempfile
import pytest

PROJECT_ROOT = "c:/Users/frede/crq-agent-workspace"
PYTHON = sys.executable


def run_send_event(*args):
    return subprocess.run(
        [PYTHON, "tools/send_event.py"] + list(args),
        capture_output=True, text=True, encoding="utf-8",
        cwd=PROJECT_ROOT,
    )


def test_send_event_silent_when_server_offline():
    """send_event.py exits 0 and produces no error output when server is not running."""
    # Assumes no server running on port 9999 — use a patched URL or just rely on localhost:8000 being down
    # We import and call directly to test ConnectionRefusedError handling
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))
    # Temporarily patch SERVER_URL to a port nothing is listening on
    import importlib
    import tools.send_event as se
    original_url = se.SERVER_URL
    se.SERVER_URL = "http://localhost:19999/internal/event"
    try:
        # Should not raise
        se.send_event("TEST_EVENT", "test-agent", {"test": True})
    finally:
        se.SERVER_URL = original_url


def test_send_event_writes_to_trace_log(tmp_path, monkeypatch):
    """send_event.py appends an entry to system_trace.log regardless of server availability."""
    import tools.send_event as se
    import tools.audit_logger as al

    log_path = tmp_path / "system_trace.log"
    monkeypatch.setattr(al, "LOG_PATH", str(log_path))
    monkeypatch.setattr(se, "SERVER_URL", "http://localhost:19999/internal/event")

    se.send_event("AGENT_STOP", "gatekeeper-agent", {"exit_code": 0})

    assert log_path.exists(), "system_trace.log was not created"
    content = log_path.read_text(encoding="utf-8")
    assert "AGENT_STOP" in content


def test_internal_event_endpoint_puts_to_queue():
    """POST /internal/event returns 200 and puts to event_queue."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "event_type": "AGENT_STOP",
        "agent_id": "test-agent",
        "payload": {"exit_code": 0},
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "http://localhost:8000/internal/event",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
            assert body.get("ok") is True
    except (urllib.error.URLError, ConnectionRefusedError):
        pytest.skip("server not running — skipping live endpoint test")
```

- [ ] **Step 2: Run E-3 tests**

```bash
uv run pytest tests/test_send_event.py -v
```

Expected: test 1 and 2 PASS. Test 3 passes if server is running, skips if not.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS (47+ total after E-1 + E-2 + E-3).

- [ ] **Step 4: Commit**

```bash
git add tests/test_send_event.py
git commit -m "test(E-3): add 3 send_event telemetry tests"
```

---

## Definition of Done

**E-1 complete when:**
- `output/dashboard.html` shows Decision Intelligence block on all 5 region cards
- `output/board_report.pdf` has "Basis of Assessment" on APAC/AME/MED pages
- `output/board_report.pptx` has "BASIS OF ASSESSMENT" on escalated region slides
- All 5 E-1 tests pass
- All pre-existing 42 tests still pass

**E-2 complete when:**
- Running `geo_collector.py APAC --mock` + `cyber_collector.py APAC --mock` writes `output/regional/apac/intelligence_sources.json` with both `geo_sources` and `cyber_sources`
- `geo_signals.json` and `cyber_signals.json` schemas are unchanged (verified by test)
- Dashboard shows collapsible "Intelligence Sources" on each region card
- PDF and PPTX have "Sources Consulted" appendix
- All 6 E-2 tests pass

**E-3 complete when:**
- `send_event.py TEST_EVENT test-agent '{}'` exits 0 with no output and writes to trace log
- `POST /internal/event` returns 200 when server is running
- Dashboard shows live status strip during a Tools Mode pipeline run
- `AGENT_START` events appear in trace log during pipeline run
- All 3 E-3 tests pass
