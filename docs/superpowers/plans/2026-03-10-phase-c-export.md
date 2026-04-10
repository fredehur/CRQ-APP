# Phase C — Board Export Polish Implementation Plan


**Goal:** Replace flat markdown exporters with production-quality board PDF and PPTX using Playwright + Jinja2 + python-pptx, sharing a single typed data layer.

**Architecture:** `report_builder.py` reads all pipeline output files and assembles a `ReportData` dataclass. `export_pdf.py` renders a Jinja2 HTML template via Playwright to PDF. `export_pptx.py` builds slides from a `base.pptx` template using python-pptx. Both exporters are thin renderers — all data logic lives in the builder.

**Tech Stack:** Python 3.14, `jinja2`, `playwright` (Chromium), `python-pptx`, `pytest`, `uv`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tools/report_builder.py` | Create | Data model + file reading + pillar parsing |
| `tools/templates/report.html.j2` | Create | Full multi-page HTML for Playwright → PDF |
| `tools/export_pdf.py` | Rewrite | Jinja2 render → Playwright → PDF |
| `tools/export_pptx.py` | Rewrite | python-pptx slide builder |
| `.claude/agents/regional-analyst-agent.md` | Edit | Add mandatory section headers for pillar parsing |
| `run-crq.md` | Edit | Update Phase 6 CLI calls |
| `pyproject.toml` | Edit | Add jinja2 + playwright deps |
| `tests/conftest.py` | Create | Shared pytest fixtures (mock output files) |
| `tests/test_report_builder.py` | Create | Unit tests for data layer |
| `tests/test_export_pdf.py` | Create | Template render smoke test |
| `tests/test_export_pptx.py` | Create | PPTX structure tests |

---

## Chunk 1: Setup & Data Layer

### Task 1: Add dependencies and test scaffold

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_report_builder.py` (stub)

- [ ] **Step 1: Add jinja2 and playwright to project**

```bash
cd C:/Users/frede/crq-agent-workspace
uv add jinja2 playwright
uv run playwright install chromium
```

Expected: no errors, `pyproject.toml` gains `jinja2` and `playwright` entries.

- [ ] **Step 2: Verify both imports work**

```bash
uv run python -c "import jinja2; import playwright; print('deps ok')"
```

Expected: `deps ok`

- [ ] **Step 3: Create tests/ directory and conftest.py**

Create `tests/__init__.py` (empty) and `tests/conftest.py`:

```python
# tests/conftest.py
"""Shared pytest fixtures — creates a minimal mock output tree in a temp dir."""
import json
import os
import pytest


REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

MOCK_MANIFEST = {
    "pipeline_id": "crq-test-001",
    "client": "AeroGrid Wind Solutions",
    "run_timestamp": "2026-03-10T08:00:00Z",
    "status": "complete",
    "total_vacr_exposure_usd": 44700000,
    "regions": {
        "APAC": {"status": "escalated", "severity": "HIGH", "vacr_usd": 18500000,
                 "admiralty": "B2", "velocity": "stable", "dominant_pillar": "Geopolitical"},
        "AME":  {"status": "escalated", "severity": "CRITICAL", "vacr_usd": 22000000,
                 "admiralty": "A1", "velocity": "accelerating", "dominant_pillar": "Cyber"},
        "LATAM":{"status": "clear",    "severity": "LOW",      "vacr_usd": 0,
                 "admiralty": "A1", "velocity": "unknown", "dominant_pillar": None},
        "MED":  {"status": "monitor",  "severity": "MEDIUM",   "vacr_usd": 4200000,
                 "admiralty": "C3", "velocity": "stable", "dominant_pillar": "Geopolitical"},
        "NCE":  {"status": "clear",    "severity": "LOW",      "vacr_usd": 0,
                 "admiralty": "A1", "velocity": "unknown", "dominant_pillar": None},
    }
}

MOCK_GLOBAL_REPORT = {
    "total_vacr_exposure": 44700000,
    "executive_summary": "Two regions are at elevated risk. Total exposure is $44.7M.",
    "regional_threats": [
        {"region": "APAC", "scenario": "System intrusion", "vacr_usd": 18500000,
         "admiralty_rating": "B2", "velocity": "stable"},
        {"region": "AME", "scenario": "Ransomware", "vacr_usd": 22000000,
         "admiralty_rating": "A1", "velocity": "accelerating"},
    ],
    "monitor_regions": ["MED"],
}

MOCK_DATA_JSONS = {
    "APAC":  {"region": "APAC",  "status": "escalated", "severity": "HIGH",
              "vacr_exposure_usd": 18500000, "admiralty": "B2", "velocity": "stable",
              "primary_scenario": "System intrusion", "dominant_pillar": "Geopolitical"},
    "AME":   {"region": "AME",   "status": "escalated", "severity": "CRITICAL",
              "vacr_exposure_usd": 22000000, "admiralty": "A1", "velocity": "accelerating",
              "primary_scenario": "Ransomware", "dominant_pillar": "Cyber"},
    "LATAM": {"region": "LATAM", "status": "clear",     "severity": "LOW",
              "vacr_exposure_usd": 0, "admiralty": "A1", "velocity": "unknown",
              "primary_scenario": None, "dominant_pillar": None},
    "MED":   {"region": "MED",   "status": "monitor",   "severity": "MEDIUM",
              "vacr_exposure_usd": 4200000, "admiralty": "C3", "velocity": "stable",
              "primary_scenario": "Insider misuse", "dominant_pillar": "Geopolitical"},
    "NCE":   {"region": "NCE",   "status": "clear",     "severity": "LOW",
              "vacr_exposure_usd": 0, "admiralty": "A1", "velocity": "unknown",
              "primary_scenario": None, "dominant_pillar": None},
}

APAC_REPORT_MD = """# APAC Regional Executive Brief

## Why — Geopolitical Driver
State-sponsored groups in the South China Sea corridor are targeting supply chain access.

## How — Cyber Vector
System intrusion attempts targeting OT networks at blade manufacturing plants.

## So What — Business Impact
$18,500,000 at risk. Disruption threatens 75% of AeroGrid's manufacturing revenue.
"""

AME_REPORT_MD = """# AME Regional Executive Brief

## Why — Geopolitical Driver
Ransomware groups exploiting North American energy sector during regulatory transition.

## How — Cyber Vector
Double-extortion ransomware targeting backup systems and operational databases.

## So What — Business Impact
$22,000,000 at risk. Service delivery continuity for 25% of global operations at stake.
"""


@pytest.fixture
def mock_output(tmp_path):
    """Create a minimal mock output/ tree under tmp_path. Returns the root path."""
    # run_manifest.json
    (tmp_path / "run_manifest.json").write_text(
        json.dumps(MOCK_MANIFEST), encoding="utf-8"
    )
    # global_report.json
    (tmp_path / "global_report.json").write_text(
        json.dumps(MOCK_GLOBAL_REPORT), encoding="utf-8"
    )
    # regional data
    for region, data in MOCK_DATA_JSONS.items():
        region_dir = tmp_path / "regional" / region.lower()
        region_dir.mkdir(parents=True)
        (region_dir / "data.json").write_text(json.dumps(data), encoding="utf-8")

    # escalated report.md files
    (tmp_path / "regional" / "apac" / "report.md").write_text(
        APAC_REPORT_MD, encoding="utf-8"
    )
    (tmp_path / "regional" / "ame" / "report.md").write_text(
        AME_REPORT_MD, encoding="utf-8"
    )
    return tmp_path
```

- [ ] **Step 4: Create stub test file**

Create `tests/test_report_builder.py`:

```python
# tests/test_report_builder.py
"""Tests for report_builder.py — data layer."""
```

- [ ] **Step 5: Install pytest and run (should pass — no tests yet)**

```bash
uv add --dev pytest
uv run pytest tests/ -v
```

Expected: `no tests ran` or `0 passed`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: add jinja2/playwright deps and test scaffold"
```

---

### Task 2: Build report_builder.py — data model

**Files:**
- Create: `tools/report_builder.py`
- Modify: `tests/test_report_builder.py`

- [ ] **Step 1: Write failing tests for data model**

Add to `tests/test_report_builder.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from report_builder import RegionStatus, RegionEntry, ReportData


def test_region_status_values():
    assert RegionStatus.ESCALATED == "escalated"
    assert RegionStatus.MONITOR == "monitor"
    assert RegionStatus.CLEAR == "clear"


def test_region_entry_is_dataclass():
    entry = RegionEntry(
        name="APAC", status=RegionStatus.ESCALATED,
        vacr=18_500_000.0, admiralty="B2", velocity="stable",
        severity="HIGH", scenario_match="System intrusion",
        why_text="geo text", how_text="cyber text", so_what_text="biz text",
    )
    assert entry.name == "APAC"
    assert entry.status == RegionStatus.ESCALATED
    assert entry.vacr == 18_500_000.0


def test_report_data_derived_counts():
    regions = [
        RegionEntry("APAC", RegionStatus.ESCALATED, 18_500_000, "B2", "stable", "HIGH", "Sys", "w", "h", "s"),
        RegionEntry("AME",  RegionStatus.ESCALATED, 22_000_000, "A1", "accelerating", "CRITICAL", "Ransomware", "w", "h", "s"),
        RegionEntry("MED",  RegionStatus.MONITOR,    4_200_000, "C3", "stable", "MEDIUM", "Insider", None, None, None),
        RegionEntry("LATAM",RegionStatus.CLEAR,      0,         "A1", "unknown", "LOW", None, None, None, None),
        RegionEntry("NCE",  RegionStatus.CLEAR,      0,         "A1", "unknown", "LOW", None, None, None, None),
    ]
    data = ReportData(
        run_id="crq-test-001", timestamp="2026-03-10T08:00:00Z",
        total_vacr=44_700_000.0,
        exec_summary="Two regions at risk.",
        escalated_count=2, monitor_count=1, clear_count=2,
        regions=regions, monitor_regions=["MED"],
    )
    assert data.escalated_count == 2
    assert data.monitor_count == 1
    assert data.clear_count == 2
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_report_builder.py -v
```

Expected: `ModuleNotFoundError: No module named 'report_builder'`

- [ ] **Step 3: Create tools/report_builder.py with data model**

```python
# tools/report_builder.py
"""
Reads all pipeline output files and assembles a ReportData object.
No rendering logic — consumed by export_pdf.py and export_pptx.py.
"""
from __future__ import annotations

import json
import logging
import os
import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = "output"
REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]


class RegionStatus(StrEnum):
    ESCALATED = "escalated"
    MONITOR = "monitor"
    CLEAR = "clear"


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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_report_builder.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add tools/report_builder.py tests/test_report_builder.py
git commit -m "feat: report_builder data model (RegionStatus, RegionEntry, ReportData)"
```

---

### Task 3: Implement pillar parser and file readers

**Files:**
- Modify: `tools/report_builder.py`
- Modify: `tests/test_report_builder.py`

- [ ] **Step 1: Write failing tests for pillar parser**

Add to `tests/test_report_builder.py`:

```python
from report_builder import _parse_pillars


def test_parse_pillars_designed_headers():
    md = """# APAC Brief

## Why — Geopolitical Driver
State actors targeting supply chain.

## How — Cyber Vector
OT network intrusion attempts.

## So What — Business Impact
$18.5M at risk.
"""
    why, how, so_what = _parse_pillars(md)
    assert "State actors" in why
    assert "OT network" in how
    assert "$18.5M" in so_what


def test_parse_pillars_legacy_headers():
    """Backward compat with old agent output that uses different headers."""
    md = """# APAC Brief

## Situation Overview
State actors targeting supply chain.

## Risk Context and Empirical Baseline
OT network intrusion attempts.

## Board-Level Implication
$18.5M at risk.
"""
    why, how, so_what = _parse_pillars(md)
    assert "State actors" in why
    assert "OT network" in how
    assert "$18.5M" in so_what


def test_parse_pillars_unrecognised_returns_full_text():
    md = "Just a plain report with no headers."
    why, how, so_what = _parse_pillars(md)
    assert "plain report" in why
    assert how is None
    assert so_what is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_report_builder.py::test_parse_pillars_designed_headers -v
```

Expected: `ImportError` or `AttributeError`

- [ ] **Step 3: Implement _parse_pillars and build() in report_builder.py**

Add below the dataclasses:

```python
# ── Header sets for pillar parsing (prefix match) ─────────────────────────────
_PILLAR_HEADERS = [
    # Designed headers (Phase C+)
    ("## Why", "## How", "## So What"),
    # Legacy headers (pre-Phase C agent output)
    ("## Situation Overview", "## Risk Context", "## Board-Level"),
]


def _parse_pillars(text: str) -> tuple[str | None, str | None, str | None]:
    """Split report.md text into (why, how, so_what) by section header prefix.

    Tries designed headers first, then legacy headers.
    Falls back to (full_text, None, None) if no headers matched.
    """
    lines = text.splitlines(keepends=True)

    for h1, h2, h3 in _PILLAR_HEADERS:
        indices = {}
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped.startswith(h1) and 1 not in indices:
                indices[1] = i
            elif stripped.startswith(h2) and 2 not in indices:
                indices[2] = i
            elif stripped.startswith(h3) and 3 not in indices:
                indices[3] = i

        if len(indices) == 3:
            i1, i2, i3 = indices[1], indices[2], indices[3]
            why     = "".join(lines[i1 + 1 : i2]).strip()
            how     = "".join(lines[i2 + 1 : i3]).strip()
            so_what = "".join(lines[i3 + 1 :]).strip()
            return why, how, so_what

    # No recognised headers — return full text as why, rest None
    return text.strip(), None, None


# ── Public API ─────────────────────────────────────────────────────────────────

def build(output_dir: str = OUTPUT_DIR) -> ReportData:
    """Assemble ReportData from pipeline output files.

    Args:
        output_dir: path to the output/ directory (override in tests).

    Raises:
        FileNotFoundError: if global_report.json or run_manifest.json are absent.
    """
    base = Path(output_dir)

    # --- run_manifest.json ---
    manifest = json.loads((base / "run_manifest.json").read_text(encoding="utf-8"))
    run_id    = manifest.get("pipeline_id", "unknown")
    timestamp = manifest.get("run_timestamp", "unknown")

    # --- global_report.json ---
    global_report = json.loads(
        (base / "global_report.json").read_text(encoding="utf-8")
    )
    total_vacr    = float(global_report.get("total_vacr_exposure", 0))
    exec_summary  = global_report.get("executive_summary", "")
    monitor_regions = global_report.get("monitor_regions", [])

    # --- Regional entries ---
    regions: list[RegionEntry] = []
    for region_name in REGIONS:
        data_path = base / "regional" / region_name.lower() / "data.json"
        if not data_path.exists():
            logger.warning("Missing data.json for %s — skipping", region_name)
            continue

        d = json.loads(data_path.read_text(encoding="utf-8"))
        raw_status = d.get("status", "clear")
        try:
            status = RegionStatus(raw_status)
        except ValueError:
            logger.warning("Unknown status %r for %s — defaulting to clear", raw_status, region_name)
            status = RegionStatus.CLEAR

        why_text = how_text = so_what_text = None
        if status == RegionStatus.ESCALATED:
            report_path = base / "regional" / region_name.lower() / "report.md"
            if report_path.exists():
                why_text, how_text, so_what_text = _parse_pillars(
                    report_path.read_text(encoding="utf-8")
                )
            else:
                logger.warning(
                    "report.md missing for escalated region %s — body will be empty",
                    region_name,
                )

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
        ))

    escalated = [r for r in regions if r.status == RegionStatus.ESCALATED]
    monitor   = [r for r in regions if r.status == RegionStatus.MONITOR]
    clear     = [r for r in regions if r.status == RegionStatus.CLEAR]

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
    )
```

- [ ] **Step 4: Write failing integration test for build()**

Add to `tests/test_report_builder.py`:

```python
from report_builder import build, RegionStatus


def test_build_from_mock_output(mock_output):
    data = build(output_dir=str(mock_output))

    assert data.run_id == "crq-test-001"
    assert data.total_vacr == 44_700_000.0
    assert data.escalated_count == 2
    assert data.monitor_count == 1
    assert data.clear_count == 2
    assert len(data.regions) == 5


def test_build_escalated_regions_have_pillar_text(mock_output):
    data = build(output_dir=str(mock_output))
    apac = next(r for r in data.regions if r.name == "APAC")
    assert apac.status == RegionStatus.ESCALATED
    assert apac.why_text is not None
    assert "State-sponsored" in apac.why_text
    assert apac.how_text is not None
    assert apac.so_what_text is not None


def test_build_clear_regions_have_no_pillar_text(mock_output):
    data = build(output_dir=str(mock_output))
    latam = next(r for r in data.regions if r.name == "LATAM")
    assert latam.status == RegionStatus.CLEAR
    assert latam.why_text is None
    assert latam.how_text is None


def test_build_graceful_when_report_md_missing(mock_output):
    """build() should not raise if report.md is absent for an escalated region."""
    (mock_output / "regional" / "ame" / "report.md").unlink()
    data = build(output_dir=str(mock_output))
    ame = next(r for r in data.regions if r.name == "AME")
    assert ame.status == RegionStatus.ESCALATED
    assert ame.why_text is None  # graceful — no crash
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest tests/test_report_builder.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 6: Commit**

```bash
git add tools/report_builder.py tests/test_report_builder.py
git commit -m "feat: report_builder — file readers, pillar parser, build()"
```

---

### Task 4: Update agent section headers for clean pillar parsing

**Files:**
- Modify: `.claude/agents/regional-analyst-agent.md`

- [ ] **Step 1: Verify the section exists**

```bash
grep -n "THREE-PILLAR\|Paragraph 1\|Paragraph 2\|Paragraph 3" .claude/agents/regional-analyst-agent.md
```

Expected output (line numbers may differ):
```
30:## THREE-PILLAR BRIEF STRUCTURE — MANDATORY
34:**Paragraph 1 — The Why (Geopolitical)**
37:**Paragraph 2 — The How (Cyber)**
40:**Paragraph 3 — The So What (Business)**
```

- [ ] **Step 2: Apply the exact edit — replace the three paragraph blocks**

In `.claude/agents/regional-analyst-agent.md`, replace:

```markdown
**Paragraph 1 — The Why (Geopolitical)**
What geopolitical or macro-economic condition is creating this threat environment? Reference the `geo_signals.lead_indicators`. Frame in terms of state actor intent, economic conditions, or structural pressure — not technical activity.

**Paragraph 2 — The How (Cyber)**
How is that condition manifesting as a threat to AeroGrid's operations? Reference the `cyber_signals.threat_vector` and `target_assets`. Frame in terms of business assets at risk — not technical attack mechanics.

**Paragraph 3 — The So What (Business)**
What is the financial and operational consequence for AeroGrid? State the VaCR figure, cite the scenario's financial impact rank from the master scenarios, connect to manufacturing capacity or service delivery continuity.
```

With:

```markdown
**Paragraph 1 — The Why (Geopolitical)**
Open your paragraph with the heading: `## Why — Geopolitical Driver`
What geopolitical or macro-economic condition is creating this threat environment? Reference the `geo_signals.lead_indicators`. Frame in terms of state actor intent, economic conditions, or structural pressure — not technical activity.

**Paragraph 2 — The How (Cyber)**
Open your paragraph with the heading: `## How — Cyber Vector`
How is that condition manifesting as a threat to AeroGrid's operations? Reference the `cyber_signals.threat_vector` and `target_assets`. Frame in terms of business assets at risk — not technical attack mechanics.

**Paragraph 3 — The So What (Business)**
Open your paragraph with the heading: `## So What — Business Impact`
What is the financial and operational consequence for AeroGrid? State the VaCR figure, cite the scenario's financial impact rank from the master scenarios, connect to manufacturing capacity or service delivery continuity.
```

- [ ] **Step 3: Verify headers appear in the file**

```bash
grep -n "## Why\|## How\|## So What" .claude/agents/regional-analyst-agent.md
```

Expected:
```
35:Open your paragraph with the heading: `## Why — Geopolitical Driver`
39:Open your paragraph with the heading: `## How — Cyber Vector`
43:Open your paragraph with the heading: `## So What — Business Impact`
```

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat: regional-analyst agent uses mandatory ## Why/How/So What headers"
```

---

## Chunk 2: HTML Template & PDF Export

### Task 5: Create the Jinja2 HTML template

**Files:**
- Create: `tools/templates/report.html.j2`
- Create: `tests/test_export_pdf.py`

- [ ] **Step 1: Create tools/templates/ directory**

```bash
mkdir -p tools/templates
```

- [ ] **Step 2: Write failing template smoke test**

Create `tests/test_export_pdf.py`:

```python
# tests/test_export_pdf.py
"""Smoke tests: template renders without error and contains expected content."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import jinja2
from report_builder import build


TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "tools", "templates", "report.html.j2"
)


def _render(mock_output):
    data = build(output_dir=str(mock_output))
    loader = jinja2.FileSystemLoader(os.path.dirname(TEMPLATE_PATH))
    env = jinja2.Environment(loader=loader, autoescape=True)
    tmpl = env.get_template("report.html.j2")
    return tmpl.render(data=data)


def test_template_renders_without_error(mock_output):
    html = _render(mock_output)
    assert len(html) > 500


def test_template_contains_brand_color(mock_output):
    html = _render(mock_output)
    assert "#104277" in html


def test_template_contains_pipeline_id(mock_output):
    html = _render(mock_output)
    assert "crq-test-001" in html


def test_template_contains_vacr(mock_output):
    html = _render(mock_output)
    assert "44" in html  # $44.7M


def test_template_contains_escalated_regions(mock_output):
    html = _render(mock_output)
    assert "APAC" in html
    assert "AME" in html


def test_template_contains_three_pillar_labels(mock_output):
    html = _render(mock_output)
    assert "Geopolitical Driver" in html
    assert "Cyber Vector" in html
    assert "Business Impact" in html
```

- [ ] **Step 3: Run tests — verify they fail (template missing)**

```bash
uv run pytest tests/test_export_pdf.py -v
```

Expected: `TemplateNotFound: report.html.j2`

- [ ] **Step 4: Create tools/templates/report.html.j2**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Global Cyber Risk Intelligence Brief</title>
<style>
  :root { --brand: #104277; --red: #dc2626; --amber: #d97706; --green: #16a34a; --slate: #64748b; }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #1e293b; background: #fff; }

  @page { size: A4; margin: 18mm 16mm; }

  .page { page-break-before: always; min-height: 240mm; }
  .page:first-child { page-break-before: avoid; }

  /* ── Cover ──────────────────────────────────────────────────────────── */
  .cover { display: flex; flex-direction: column; min-height: 257mm; }
  .cover-band {
    background: var(--brand); color: #fff;
    padding: 40mm 16mm 20mm;
    flex: 0 0 40%;
  }
  .cover-band .client { font-size: 13pt; opacity: 0.8; margin-bottom: 8mm; }
  .cover-band .report-title { font-size: 22pt; font-weight: 700; line-height: 1.2; }
  .cover-body { padding: 10mm 16mm; flex: 1; display: flex; flex-direction: column; justify-content: space-between; }
  .cover-vacr { font-size: 36pt; font-weight: 700; color: var(--brand); margin: 6mm 0 2mm; }
  .cover-vacr-label { font-size: 10pt; color: var(--slate); text-transform: uppercase; letter-spacing: 0.5px; }
  .cover-meta { font-size: 9pt; color: var(--slate); }
  .cover-meta span { display: block; margin-bottom: 2mm; }
  .cover-confidential { font-size: 8pt; font-weight: 700; color: var(--red); text-align: right; margin-top: auto; }

  @media print {
    * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  }

  /* ── Section header ──────────────────────────────────────────────────── */
  .section-header {
    background: var(--brand); color: #fff;
    padding: 5mm 6mm 4mm;
    margin: 0 -16mm 6mm;
    display: flex; justify-content: space-between; align-items: center;
  }
  .section-header h2 { font-size: 14pt; font-weight: 700; }
  .section-header .sub { font-size: 9pt; opacity: 0.8; }

  /* ── Executive Summary ───────────────────────────────────────────────── */
  .status-strip { display: flex; gap: 4mm; margin-bottom: 6mm; }
  .status-badge {
    padding: 2mm 4mm; border-radius: 3px;
    font-size: 9pt; font-weight: 700;
    display: flex; flex-direction: column; align-items: center; gap: 1mm;
  }
  .status-badge .count { font-size: 18pt; line-height: 1; }
  .badge-red    { background: #fee2e2; color: var(--red); border: 1px solid #fca5a5; }
  .badge-amber  { background: #fef3c7; color: var(--amber); border: 1px solid #fcd34d; }
  .badge-green  { background: #dcfce7; color: var(--green); border: 1px solid #86efac; }
  .badge-blue   { background: #dbeafe; color: var(--brand); border: 1px solid #93c5fd; }

  .total-vacr { font-size: 28pt; font-weight: 700; color: var(--brand); margin: 4mm 0 2mm; }
  .total-vacr-label { font-size: 9pt; color: var(--slate); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5mm; }

  .exec-summary-text { font-size: 10.5pt; line-height: 1.6; color: #334155; margin-bottom: 6mm; }

  .admiralty-table { width: 100%; border-collapse: collapse; font-size: 9pt; margin-top: 4mm; }
  .admiralty-table th { background: #f1f5f9; color: var(--slate); text-transform: uppercase;
    font-size: 8pt; letter-spacing: 0.5px; padding: 2mm 3mm; text-align: left;
    border-bottom: 2px solid #e2e8f0; }
  .admiralty-table td { padding: 2mm 3mm; border-bottom: 1px solid #f1f5f9; }

  /* ── Region pages ────────────────────────────────────────────────────── */
  .region-layout { display: flex; gap: 5mm; margin-top: 5mm; }
  .region-sidebar {
    width: 32mm; flex-shrink: 0;
    border: 1px solid #e2e8f0; border-radius: 4px; overflow: hidden;
  }
  .kpi-cell {
    padding: 3mm 2mm; text-align: center;
    border-bottom: 1px solid #e2e8f0;
  }
  .kpi-cell:last-child { border-bottom: none; }
  .kpi-label { font-size: 7pt; color: var(--slate); text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 1mm; }
  .kpi-value { font-size: 13pt; font-weight: 700; color: var(--brand); line-height: 1; }
  .kpi-value.red { color: var(--red); }
  .kpi-value.amber { color: var(--amber); }

  .region-body { flex: 1; }
  .pillar { margin-bottom: 5mm; }
  .pillar-label {
    font-size: 8pt; font-weight: 700; color: var(--brand);
    text-transform: uppercase; letter-spacing: 0.5px;
    border-left: 3px solid var(--brand); padding-left: 2mm;
    margin-bottom: 2mm;
  }
  .pillar-text { font-size: 10pt; line-height: 1.6; color: #334155; }

  .unavailable-notice {
    background: #fef3c7; border: 1px solid #fcd34d; border-radius: 4px;
    padding: 4mm; font-size: 9pt; color: var(--amber);
  }

  /* ── Status badge chips ──────────────────────────────────────────────── */
  .chip {
    display: inline-block; padding: 1mm 3mm; border-radius: 3px;
    font-size: 8pt; font-weight: 700;
  }
  .chip-red    { background: #dc2626; color: #fff; }
  .chip-amber  { background: #d97706; color: #fff; }
  .chip-green  { background: #16a34a; color: #fff; }

  /* ── Velocity arrows ─────────────────────────────────────────────────── */
  .vel-up   { color: var(--red); }
  .vel-down { color: var(--green); }
  .vel-flat { color: var(--slate); }

  /* ── Appendix ────────────────────────────────────────────────────────── */
  .monitor-card {
    border-left: 4px solid var(--amber); background: #fefce8;
    padding: 3mm 4mm; border-radius: 0 4px 4px 0; margin-bottom: 3mm;
  }
  .monitor-card h4 { font-size: 10pt; font-weight: 700; color: var(--amber); margin-bottom: 1mm; }
  .clear-row {
    display: flex; align-items: center; gap: 3mm;
    padding: 2mm 3mm; border-bottom: 1px solid #f1f5f9; font-size: 9.5pt;
  }
  .meta-table { width: 100%; border-collapse: collapse; font-size: 9pt; margin-top: 3mm; }
  .meta-table td { padding: 2mm 3mm; border-bottom: 1px solid #f1f5f9; }
  .meta-table td:first-child { color: var(--slate); width: 40%; }
</style>
</head>
<body>

{# ══════════════════════════════════════════════════════════════════ COVER #}
<div class="page cover">
  <div class="cover-band">
    <div class="client">AeroGrid Wind Solutions</div>
    <div class="report-title">Global Cyber Risk<br>Intelligence Brief</div>
  </div>
  <div class="cover-body">
    <div>
      <div class="cover-vacr-label">Total Value at Cyber Risk</div>
      <div class="cover-vacr">${{ "%.1f"|format(data.total_vacr / 1_000_000) }}M</div>
      <div class="cover-meta">
        <span>Pipeline ID: {{ data.run_id }}</span>
        <span>Run Date: {{ data.timestamp }}</span>
        <span>Regions Assessed: {{ data.regions|length }}</span>
      </div>
    </div>
    <div class="cover-confidential">CONFIDENTIAL</div>
  </div>
</div>

{# ══════════════════════════════════════════════════════════════════ EXEC SUMMARY #}
<div class="page">
  <div class="section-header">
    <h2>Executive Summary</h2>
    <span class="sub">Board-Level Intelligence Brief</span>
  </div>

  <div class="status-strip">
    <div class="status-badge badge-red">
      <span class="count">{{ data.escalated_count }}</span>
      <span>ESCALATED</span>
    </div>
    <div class="status-badge badge-amber">
      <span class="count">{{ data.monitor_count }}</span>
      <span>MONITOR</span>
    </div>
    <div class="status-badge badge-green">
      <span class="count">{{ data.clear_count }}</span>
      <span>CLEAR</span>
    </div>
    <div class="status-badge badge-blue" style="margin-left:auto;">
      <span class="count">${{ "%.1f"|format(data.total_vacr / 1_000_000) }}M</span>
      <span>TOTAL VaCR</span>
    </div>
  </div>

  <div class="exec-summary-text">{{ data.exec_summary }}</div>

  {% set escalated_regions = data.regions | selectattr("status", "equalto", "escalated") | list %}
  {% if escalated_regions %}
  <table class="admiralty-table">
    <thead>
      <tr>
        <th>Region</th>
        <th>Scenario</th>
        <th>VaCR Exposure</th>
        <th>Admiralty</th>
        <th>Velocity</th>
        <th>Severity</th>
      </tr>
    </thead>
    <tbody>
      {% for r in escalated_regions %}
      <tr>
        <td><strong>{{ r.name }}</strong></td>
        <td>{{ r.scenario_match or "—" }}</td>
        <td>${{ "%.1f"|format((r.vacr or 0) / 1_000_000) }}M</td>
        <td>{{ r.admiralty or "—" }}</td>
        <td>
          {% if r.velocity == "accelerating" %}<span class="vel-up">↑ Accelerating</span>
          {% elif r.velocity == "improving"   %}<span class="vel-down">↓ Improving</span>
          {% else %}<span class="vel-flat">→ {{ r.velocity | title if r.velocity else "—" }}</span>
          {% endif %}
        </td>
        <td>{{ r.severity or "—" }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>

{# ══════════════════════════════════════════════════════════════ REGION PAGES #}
{% for r in data.regions if r.status == "escalated" %}
<div class="page">
  <div class="section-header">
    <div>
      <h2>{{ r.name }}</h2>
      <span class="sub">{{ r.scenario_match or "" }}</span>
    </div>
    <span class="chip chip-red">ESCALATED</span>
  </div>

  <div class="region-layout">
    <div class="region-sidebar">
      <div class="kpi-cell">
        <div class="kpi-label">VaCR Exposure</div>
        <div class="kpi-value">${{ "%.1f"|format((r.vacr or 0) / 1_000_000) }}M</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Admiralty</div>
        <div class="kpi-value">{{ r.admiralty or "—" }}</div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Velocity</div>
        <div class="kpi-value {% if r.velocity == 'accelerating' %}red{% elif r.velocity == 'improving' %}vel-down{% else %}{% endif %}">
          {% if r.velocity == "accelerating" %}↑ Accel.
          {% elif r.velocity == "improving"  %}↓ Impr.
          {% else %}→ {{ r.velocity | title if r.velocity else "—" }}
          {% endif %}
        </div>
      </div>
      <div class="kpi-cell">
        <div class="kpi-label">Severity</div>
        <div class="kpi-value {% if r.severity in ('CRITICAL','HIGH') %}red{% elif r.severity == 'MEDIUM' %}amber{% endif %}">
          {{ r.severity or "—" }}
        </div>
      </div>
    </div>

    <div class="region-body">
      {% if r.why_text %}
        <div class="pillar">
          <div class="pillar-label">Why — Geopolitical Driver</div>
          <div class="pillar-text">{{ r.why_text }}</div>
        </div>
        <div class="pillar">
          <div class="pillar-label">How — Cyber Vector</div>
          <div class="pillar-text">{{ r.how_text or "—" }}</div>
        </div>
        <div class="pillar">
          <div class="pillar-label">So What — Business Impact</div>
          <div class="pillar-text">{{ r.so_what_text or "—" }}</div>
        </div>
      {% else %}
        <div class="unavailable-notice">
          Regional intelligence report unavailable for this run. Check pipeline logs.
        </div>
      {% endif %}
    </div>
  </div>
</div>
{% endfor %}

{# ══════════════════════════════════════════════════════════════════ APPENDIX #}
<div class="page">
  <div class="section-header">
    <h2>Appendix</h2>
    <span class="sub">Monitor Regions · Clear Regions · Run Metadata</span>
  </div>

  {% set monitor_regions = data.regions | selectattr("status", "equalto", "monitor") | list %}
  {% if monitor_regions %}
  <h3 style="font-size:10pt;color:var(--amber);margin-bottom:3mm;">Watch — Monitor Regions</h3>
  {% for r in monitor_regions %}
  <div class="monitor-card">
    <h4>{{ r.name }} <span style="font-weight:400;font-size:9pt;">· {{ r.scenario_match or "No scenario" }} · Admiralty {{ r.admiralty or "—" }}</span></h4>
    <div style="font-size:9pt;color:#78350f;">Low-level activity detected. No full analysis triggered. Severity: {{ r.severity or "—" }}</div>
  </div>
  {% endfor %}
  {% endif %}

  {% set clear_regions = data.regions | selectattr("status", "equalto", "clear") | list %}
  {% if clear_regions %}
  <h3 style="font-size:10pt;color:var(--green);margin-top:5mm;margin-bottom:2mm;">Clear Regions</h3>
  {% for r in clear_regions %}
  <div class="clear-row">
    <span class="chip chip-green">CLEAR</span>
    <strong>{{ r.name }}</strong>
    <span style="color:var(--slate);">No active threat detected this cycle.</span>
  </div>
  {% endfor %}
  {% endif %}

  <h3 style="font-size:10pt;color:var(--slate);margin-top:6mm;margin-bottom:2mm;">Run Metadata</h3>
  <table class="meta-table">
    <tr><td>Pipeline ID</td><td>{{ data.run_id }}</td></tr>
    <tr><td>Run Timestamp</td><td>{{ data.timestamp }}</td></tr>
    <tr><td>Regions Assessed</td><td>{{ data.regions | map(attribute="name") | join(", ") }}</td></tr>
    <tr><td>Escalated</td><td>{{ data.escalated_count }}</td></tr>
    <tr><td>Monitor</td><td>{{ data.monitor_count }}</td></tr>
    <tr><td>Clear</td><td>{{ data.clear_count }}</td></tr>
  </table>
</div>

</body>
</html>
```

- [ ] **Step 5: Run template tests**

```bash
uv run pytest tests/test_export_pdf.py -v
```

Expected: all 6 pass.

- [ ] **Step 6: Commit**

```bash
git add tools/templates/report.html.j2 tests/test_export_pdf.py
git commit -m "feat: Jinja2 HTML template for board PDF report"
```

---

### Task 6: Rewrite export_pdf.py

**Files:**
- Modify: `tools/export_pdf.py`

- [ ] **Step 1: Rewrite export_pdf.py**

```python
# tools/export_pdf.py
"""
Renders the board PDF report using Playwright + Jinja2.

Usage:
    uv run python tools/export_pdf.py [output.pdf]
    Defaults to output/board_report.pdf if no argument given.
"""
import sys
import tempfile
import os
from pathlib import Path

import jinja2
from playwright.sync_api import sync_playwright

# Allow running from project root or tools/
sys.path.insert(0, os.path.dirname(__file__))
from report_builder import build

TEMPLATE_DIR  = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"
DEFAULT_OUT   = "output/board_report.pdf"


def export(output_path: str = DEFAULT_OUT) -> None:
    data = build()

    # Render HTML
    loader = jinja2.FileSystemLoader(str(TEMPLATE_DIR))
    env    = jinja2.Environment(loader=loader, autoescape=True)
    html   = env.get_template(TEMPLATE_NAME).render(data=data)

    # Write to temp file (NamedTemporaryFile avoids path collisions)
    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()
            page.goto(Path(tmp_path).as_uri())  # cross-platform URI (file:///C:/... on Windows)
            page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
            )
            browser.close()
    finally:
        os.unlink(tmp_path)

    print(f"PDF exported: {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    export(out)
```

- [ ] **Step 2: Smoke-test the PDF export end-to-end**

```bash
uv run python tools/export_pdf.py output/board_report.pdf
```

Expected: `PDF exported: output/board_report.pdf` — file exists, non-zero size.

```bash
uv run python -c "import os; s=os.path.getsize('output/board_report.pdf'); print(f'{s:,} bytes'); assert s > 50_000"
```

Expected: file size printed, > 50,000 bytes.

- [ ] **Step 3: Commit**

```bash
git add tools/export_pdf.py
git commit -m "feat: export_pdf rewrite — Playwright + Jinja2 board PDF"
```

---

## Chunk 3: PPTX Export & Integration

### Task 7: Rewrite export_pptx.py with base.pptx bootstrap

**Files:**
- Modify: `tools/export_pptx.py`
- Create: `tests/test_export_pptx.py`

- [ ] **Step 1: Write failing PPTX tests**

Create `tests/test_export_pptx.py`:

```python
# tests/test_export_pptx.py
"""Tests for export_pptx.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import pytest
from pptx import Presentation
from report_builder import build
import export_pptx as ep


def test_build_pptx_returns_presentation(mock_output, tmp_path):
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    assert isinstance(prs, Presentation)


def test_pptx_slide_count_matches_structure(mock_output, tmp_path):
    """Cover + Exec Summary + 2 escalated regions + Appendix = 5 slides."""
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    assert len(prs.slides) == 5


def test_pptx_saves_to_file(mock_output, tmp_path):
    data = build(output_dir=str(mock_output))
    out = str(tmp_path / "test_report.pptx")
    ep.export(output_path=out, output_dir=str(mock_output))
    assert os.path.exists(out)
    assert os.path.getsize(out) > 10_000  # non-trivial file


def test_pptx_cover_slide_has_title(mock_output):
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    cover = prs.slides[0]
    title_texts = [shape.text for shape in cover.shapes if shape.has_text_frame]
    assert any("Global Cyber Risk" in t for t in title_texts)


def test_pptx_region_slides_contain_admiralty(mock_output):
    data = build(output_dir=str(mock_output))
    prs = ep.build_presentation(data)
    # Slides 2 = exec, 3 = APAC, 4 = AME, 5 = appendix
    apac_slide = prs.slides[2]
    all_text = " ".join(
        shape.text for shape in apac_slide.shapes if shape.has_text_frame
    )
    assert "B2" in all_text  # APAC admiralty
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_export_pptx.py -v
```

Expected: `ImportError` (export_pptx not yet rewritten).

- [ ] **Step 3: Rewrite export_pptx.py**

```python
# tools/export_pptx.py
"""
Builds the board PPTX report using python-pptx.
Bootstraps tools/templates/base.pptx on first run if absent.

Usage:
    uv run python tools/export_pptx.py [output.pptx]
    Defaults to output/board_report.pptx
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN

sys.path.insert(0, os.path.dirname(__file__))
from report_builder import build, ReportData, RegionEntry, RegionStatus

TEMPLATES_DIR = Path(__file__).parent / "templates"
BASE_PPTX     = TEMPLATES_DIR / "base.pptx"
DEFAULT_OUT   = "output/board_report.pptx"

# Brand colours
BRAND   = RGBColor(0x10, 0x42, 0x77)
RED     = RGBColor(0xDC, 0x26, 0x26)
AMBER   = RGBColor(0xD9, 0x77, 0x06)
GREEN   = RGBColor(0x16, 0xA3, 0x4A)
SLATE   = RGBColor(0x64, 0x74, 0x8B)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
DARK    = RGBColor(0x1E, 0x29, 0x3B)

# Slide dimensions (standard 10×7.5in widescreen 16:9)
W = Inches(10)
H = Inches(7.5)


# ── Base PPTX bootstrap ────────────────────────────────────────────────────────

def _ensure_base_pptx() -> None:
    """Generate tools/templates/base.pptx if it does not exist."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    if BASE_PPTX.exists():
        return

    from pptx.util import Inches
    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H
    # Remove all default slide layouts except blank (index 6)
    # python-pptx requires at least one layout — keep blank
    prs.save(str(BASE_PPTX))


# ── Slide helpers ──────────────────────────────────────────────────────────────

def _add_blank_slide(prs: Presentation):
    blank_layout = prs.slide_layouts[6]  # blank layout
    return prs.slides.add_slide(blank_layout)


def _fill_shape(shape, color: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color


def _add_rect(slide, left, top, width, height, color: RGBColor):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height
    )
    shape.line.fill.background()
    _fill_shape(shape, color)
    return shape


def _add_text(slide, text: str, left, top, width, height,
              font_size: int = 14, bold: bool = False,
              color: RGBColor = DARK, align=PP_ALIGN.LEFT,
              wrap: bool = True) -> None:
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf    = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color


def _vacr_fmt(vacr: float | None) -> str:
    if not vacr:
        return "—"
    return f"${vacr / 1_000_000:.1f}M"


def _vel_label(velocity: str | None) -> str:
    mapping = {"accelerating": "↑ Accelerating", "improving": "↓ Improving",
               "stable": "→ Stable", "unknown": "—"}
    return mapping.get(velocity or "unknown", velocity or "—")


# ── Slide builders ─────────────────────────────────────────────────────────────

def build_cover(prs: Presentation, data: ReportData) -> None:
    slide = _add_blank_slide(prs)

    # Brand header band (top 45%)
    band_h = Inches(3.4)
    _add_rect(slide, 0, 0, W, band_h, BRAND)
    _add_text(slide, "AeroGrid Wind Solutions",
              Inches(0.6), Inches(0.5), Inches(8.8), Inches(0.5),
              font_size=13, color=RGBColor(0xBF,0xDB,0xFF))
    _add_text(slide, "Global Cyber Risk\nIntelligence Brief",
              Inches(0.6), Inches(1.1), Inches(8.8), Inches(2.0),
              font_size=28, bold=True, color=WHITE)

    # VaCR
    _add_text(slide, "TOTAL VALUE AT CYBER RISK",
              Inches(0.6), Inches(3.7), Inches(5), Inches(0.35),
              font_size=9, color=SLATE)
    _add_text(slide, _vacr_fmt(data.total_vacr),
              Inches(0.6), Inches(4.0), Inches(5), Inches(0.9),
              font_size=36, bold=True, color=BRAND)

    # Meta
    meta = f"Pipeline ID: {data.run_id}   |   {data.timestamp}"
    _add_text(slide, meta, Inches(0.6), Inches(5.0), Inches(8), Inches(0.4),
              font_size=9, color=SLATE)

    # Confidential
    _add_text(slide, "CONFIDENTIAL",
              Inches(7.5), Inches(6.9), Inches(2.3), Inches(0.4),
              font_size=8, bold=True, color=RED, align=PP_ALIGN.RIGHT)


def build_exec_summary(prs: Presentation, data: ReportData) -> None:
    slide = _add_blank_slide(prs)

    # Header band
    _add_rect(slide, 0, 0, W, Inches(0.65), BRAND)
    _add_text(slide, "Executive Summary", Inches(0.3), Inches(0.1),
              Inches(7), Inches(0.45), font_size=16, bold=True, color=WHITE)

    # Status badges
    badge_data = [
        (str(data.escalated_count), "ESCALATED", RED),
        (str(data.monitor_count),   "MONITOR",   AMBER),
        (str(data.clear_count),     "CLEAR",     GREEN),
    ]
    for i, (count, label, color) in enumerate(badge_data):
        x = Inches(0.4 + i * 1.3)
        _add_rect(slide, x, Inches(0.85), Inches(1.1), Inches(0.75), color)
        _add_text(slide, count,  x, Inches(0.88), Inches(1.1), Inches(0.4),
                  font_size=20, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        _add_text(slide, label, x, Inches(1.25), Inches(1.1), Inches(0.3),
                  font_size=7, color=WHITE, align=PP_ALIGN.CENTER)

    # VaCR badge
    _add_rect(slide, Inches(8.0), Inches(0.85), Inches(1.7), Inches(0.75), BRAND)
    _add_text(slide, _vacr_fmt(data.total_vacr),
              Inches(8.0), Inches(0.88), Inches(1.7), Inches(0.4),
              font_size=16, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    _add_text(slide, "TOTAL VaCR",
              Inches(8.0), Inches(1.25), Inches(1.7), Inches(0.3),
              font_size=7, color=WHITE, align=PP_ALIGN.CENTER)

    # Exec summary text
    _add_text(slide, data.exec_summary,
              Inches(0.4), Inches(1.8), Inches(9.2), Inches(1.0),
              font_size=10, color=DARK, wrap=True)

    # Admiralty table header
    cols = ["Region", "Scenario", "VaCR", "Admiralty", "Velocity", "Severity"]
    col_widths = [Inches(1.2), Inches(2.2), Inches(1.2), Inches(1.1), Inches(1.8), Inches(1.2)]
    y_header = Inches(3.0)
    x = Inches(0.4)
    for col, w in zip(cols, col_widths):
        _add_text(slide, col, x, y_header, w, Inches(0.3),
                  font_size=8, bold=True, color=SLATE)
        x += w

    escalated = [r for r in data.regions if r.status == RegionStatus.ESCALATED]
    for row_i, r in enumerate(escalated):
        y = Inches(3.35 + row_i * 0.45)
        row = [r.name, r.scenario_match or "—", _vacr_fmt(r.vacr),
               r.admiralty or "—", _vel_label(r.velocity), r.severity or "—"]
        x = Inches(0.4)
        for val, w in zip(row, col_widths):
            _add_text(slide, val, x, y, w, Inches(0.35), font_size=9, color=DARK)
            x += w


def build_region(prs: Presentation, region: RegionEntry) -> None:
    slide = _add_blank_slide(prs)

    # Header band
    _add_rect(slide, 0, 0, W, Inches(0.65), BRAND)
    _add_text(slide, region.name, Inches(0.3), Inches(0.1),
              Inches(6), Inches(0.45), font_size=16, bold=True, color=WHITE)
    _add_text(slide, region.scenario_match or "",
              Inches(0.3), Inches(0.38), Inches(6), Inches(0.25),
              font_size=9, color=RGBColor(0xBF,0xDB,0xFF))
    # ESCALATED chip
    _add_rect(slide, Inches(8.4), Inches(0.12), Inches(1.3), Inches(0.38), RED)
    _add_text(slide, "ESCALATED", Inches(8.4), Inches(0.16),
              Inches(1.3), Inches(0.3), font_size=8, bold=True,
              color=WHITE, align=PP_ALIGN.CENTER)

    # Sidebar scorecard (left 1.4in)
    sidebar_x = Inches(0.3)
    kpi_items = [
        ("VaCR Exposure", _vacr_fmt(region.vacr), BRAND),
        ("Admiralty",     region.admiralty or "—", BRAND),
        ("Velocity",      _vel_label(region.velocity),
         RED if region.velocity == "accelerating" else SLATE),
        ("Severity",      region.severity or "—",
         RED if region.severity in ("CRITICAL","HIGH") else
         AMBER if region.severity == "MEDIUM" else GREEN),
    ]
    for i, (label, value, color) in enumerate(kpi_items):
        y = Inches(0.85 + i * 1.55)
        _add_text(slide, label, sidebar_x, y, Inches(1.4), Inches(0.3),
                  font_size=7, color=SLATE)
        _add_text(slide, value, sidebar_x, Inches(0.85 + i*1.55 + 0.32),
                  Inches(1.4), Inches(0.7), font_size=16, bold=True, color=color)

    # Body — three pillars
    body_x = Inches(1.9)
    body_w = Inches(7.8)
    pillars = [
        ("WHY — GEOPOLITICAL DRIVER", region.why_text),
        ("HOW — CYBER VECTOR",        region.how_text),
        ("SO WHAT — BUSINESS IMPACT", region.so_what_text),
    ]
    y = Inches(0.85)
    for label, text in pillars:
        if text:
            _add_text(slide, label, body_x, y, body_w, Inches(0.28),
                      font_size=8, bold=True, color=BRAND)
            _add_text(slide, text[:400], body_x, y + Inches(0.3),
                      body_w, Inches(1.5), font_size=9, color=DARK, wrap=True)
            y += Inches(2.1)

    if not region.why_text:
        _add_text(slide, "Regional intelligence report unavailable for this run.",
                  body_x, Inches(1.0), body_w, Inches(0.5),
                  font_size=10, color=AMBER)


def build_appendix(prs: Presentation, data: ReportData) -> None:
    slide = _add_blank_slide(prs)

    _add_rect(slide, 0, 0, W, Inches(0.65), BRAND)
    _add_text(slide, "Appendix", Inches(0.3), Inches(0.1),
              Inches(7), Inches(0.45), font_size=16, bold=True, color=WHITE)

    y = Inches(0.85)
    monitor = [r for r in data.regions if r.status == RegionStatus.MONITOR]
    clear   = [r for r in data.regions if r.status == RegionStatus.CLEAR]

    if monitor:
        _add_text(slide, "WATCH — MONITOR REGIONS", Inches(0.4), y,
                  Inches(9), Inches(0.3), font_size=9, bold=True, color=AMBER)
        y += Inches(0.35)
        for r in monitor:
            txt = f"{r.name}  ·  {r.scenario_match or 'No scenario'}  ·  Admiralty {r.admiralty or '—'}  ·  {r.severity or '—'}"
            _add_text(slide, txt, Inches(0.6), y, Inches(9), Inches(0.35),
                      font_size=9, color=DARK)
            y += Inches(0.38)
        y += Inches(0.2)

    if clear:
        _add_text(slide, "CLEAR REGIONS", Inches(0.4), y,
                  Inches(9), Inches(0.3), font_size=9, bold=True, color=GREEN)
        y += Inches(0.35)
        for r in clear:
            _add_text(slide, f"{r.name}  —  No active threat detected this cycle.",
                      Inches(0.6), y, Inches(9), Inches(0.35),
                      font_size=9, color=DARK)
            y += Inches(0.38)
        y += Inches(0.2)

    # Run metadata
    _add_text(slide, "RUN METADATA", Inches(0.4), y,
              Inches(9), Inches(0.3), font_size=9, bold=True, color=SLATE)
    y += Inches(0.35)
    meta_rows = [
        ("Pipeline ID",    data.run_id),
        ("Timestamp",      data.timestamp),
        ("Escalated",      str(data.escalated_count)),
        ("Monitor",        str(data.monitor_count)),
        ("Clear",          str(data.clear_count)),
    ]
    for label, value in meta_rows:
        _add_text(slide, f"{label}:  {value}",
                  Inches(0.6), y, Inches(9), Inches(0.3),
                  font_size=9, color=DARK)
        y += Inches(0.3)


# ── Public API ─────────────────────────────────────────────────────────────────

def build_presentation(data: ReportData) -> Presentation:
    _ensure_base_pptx()
    prs = Presentation(str(BASE_PPTX))
    prs.slide_width  = W
    prs.slide_height = H

    build_cover(prs, data)
    build_exec_summary(prs, data)
    for region in (r for r in data.regions if r.status == RegionStatus.ESCALATED):
        build_region(prs, region)
    build_appendix(prs, data)

    return prs


def export(output_path: str = DEFAULT_OUT, output_dir: str = "output") -> None:
    data = build(output_dir=output_dir)
    prs  = build_presentation(data)
    prs.save(output_path)
    print(f"PPTX exported: {output_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    export(out)
```

- [ ] **Step 4: Run PPTX tests**

```bash
uv run pytest tests/test_export_pptx.py -v
```

Expected: all 5 pass.

- [ ] **Step 5: Smoke-test end-to-end**

```bash
uv run python tools/export_pptx.py output/board_report.pptx
```

Expected: `PPTX exported: output/board_report.pptx`

```bash
ls -lh output/board_report.pptx
```

Expected: file > 20KB, opens in PowerPoint/LibreOffice.

- [ ] **Step 6: Commit base.pptx + rewritten exporter + tests**

```bash
git add tools/export_pptx.py tools/templates/base.pptx tests/test_export_pptx.py
git commit -m "feat: export_pptx rewrite — python-pptx board presentation"
```

---

### Task 8: Update run-crq.md Phase 6 and run full pipeline smoke test

**Files:**
- Modify: `.claude/commands/run-crq.md`

- [ ] **Step 1: Find and update the Phase 6 export calls in run-crq.md**

Verify the current call exists:
```bash
grep -n "export_pdf\|export_pptx" .claude/commands/run-crq.md
```
Expected: line containing `tools/export_pdf.py output/global_report.md output/board_report.pdf`

Locate in `.claude/commands/run-crq.md` the lines:
```
uv run python tools/export_pdf.py output/global_report.md output/board_report.pdf
```

Replace with:
```
uv run python tools/export_pdf.py output/board_report.pdf
uv run python tools/export_pptx.py output/board_report.pptx
```

- [ ] **Step 2: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/run-crq.md
git commit -m "feat: update run-crq Phase 6 to use new exporter CLI signatures"
```

- [ ] **Step 4: Update project-plan.md Phase C status to complete**

In `C:/Users/frede/.claude/projects/C--Users-frede-crq-agent-workspace/memory/project-plan.md`, mark Phase C as `✅ COMPLETE`.

- [ ] **Step 5: Final commit**

```bash
git add docs/
git commit -m "docs: Phase C implementation plan complete"
```
