# Phase C — Board Export Polish: Design Spec
**Date:** 2026-03-10
**Status:** Approved
**Scope:** Board-level PDF and PPTX export upgrade (single audience profile)

---

## Goal

Replace the current flat markdown-to-file exporters with production-quality board exports. One PDF, one PPTX, both generated from the same data layer and shared template system.

---

## Decisions Made

| Decision | Choice | Rationale |
|---|---|---|
| Visual style | Clean & Minimal | White background, `#104277` brand blue, thin lines |
| PDF structure | Standard (5–6 pages) | Cover → Exec Summary → Region pages → Appendix |
| PPTX structure | Mirror PDF | Same sections, editable text via python-pptx |
| PDF renderer | Playwright (Chromium) | Already installed; full CSS fidelity; no coordinate math |
| HTML templating | Jinja2 | Clean data injection; `@page` CSS for print layout |
| PPTX approach | `base.pptx` slide master | Pre-configured `#104277` theme; named placeholders |
| Region page layout | Sidebar scorecard | Fixed 90px sidebar (VaCR / Admiralty / Velocity / Severity) + 3-pillar body |
| Audience scope | Board only (Phase C) | Audience-specific profiles deferred to Phase D |

---

## Architecture

### Data Flow

```
global_report.json
regional/{region}/data.json (×5)      →  report_builder.py  →  ReportData
regional/{region}/report.md (escalated)                              │
run_manifest.json                                         ┌──────────┴──────────┐
                                                          │                     │
                                                   export_pdf.py          export_pptx.py
                                                          │                     │
                                              Jinja2 + Playwright       python-pptx + base.pptx
                                                          │                     │
                                                 board_report.pdf     board_report.pptx
```

### File Changes

| File | Action |
|---|---|
| `tools/report_builder.py` | **New** — shared data layer |
| `tools/templates/report.html.j2` | **New** — Jinja2 HTML template for PDF |
| `tools/templates/base.pptx` | **New** — PPTX slide master (~30KB binary) |
| `tools/export_pdf.py` | **Rewrite** |
| `tools/export_pptx.py` | **Rewrite** |

---

## Component Designs

### 1. `tools/report_builder.py`

**Job:** Read all pipeline output files, assemble `ReportData`. No rendering logic.

**Reads:**
- `output/global_report.json` — exec_summary, total_vacr_exposure, monitor_regions
- `output/regional/{region}/data.json` — status, admiralty, velocity, severity, scenario_match (all 5 regions)
- `output/regional/{region}/report.md` — body text for escalated regions only
- `output/run_manifest.json` — pipeline_id, timestamp

**Data model:**
```python
class RegionStatus(StrEnum):
    ESCALATED = "escalated"
    MONITOR = "monitor"
    CLEAR = "clear"

@dataclass
class RegionEntry:
    name: str
    status: RegionStatus
    vacr: float | None
    admiralty: str | None        # e.g. "B2"
    velocity: str | None         # "accelerating" | "stable" | "improving" | "unknown"
    severity: str | None         # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    scenario_match: str | None
    why_text: str | None         # parsed from report.md ## Why section
    how_text: str | None         # parsed from report.md ## How section
    so_what_text: str | None     # parsed from report.md ## So What section

@dataclass
class ReportData:
    run_id: str
    timestamp: str
    total_vacr: float
    exec_summary: str
    escalated_count: int         # derived
    monitor_count: int           # derived
    clear_count: int             # derived
    regions: list[RegionEntry]
    monitor_regions: list[str]
```

**Pillar parsing:** splits `report.md` on section header prefixes `## Why`, `## How`, `## So What` (prefix match, not exact — handles variants like `## Why — Geopolitical Driver`) — no `markdown` library required.

**Graceful degradation:** if `report.md` is missing for an escalated region, `why_text/how_text/so_what_text` are set to `None`. The template renders a "Report unavailable" placeholder. Builder logs a warning, does not raise.

---

### 2. `tools/templates/report.html.j2`

**Job:** Full multi-page HTML document. Playwright prints it to PDF.

**CSS rules:**
- `--brand: #104277` CSS variable used throughout
- `@page { size: A4; margin: 20mm 18mm; }`
- `page-break-before: always` on each section wrapper
- `print-color-adjust: exact` to preserve backgrounds in Chromium

**Pages:**

**Cover**
- Full-page `#104277` header band (top 40% of page)
- White body: report title "Global Cyber Risk Intelligence Brief", run date, pipeline ID
- Total VaCR in large type (e.g. `$44.7M`)
- `CONFIDENTIAL` label bottom-right
- AeroGrid Wind Solutions name + logo placeholder

**Executive Summary**
- Status counts row: escalated (red badge), monitor (amber badge), clear (green badge)
- Total VaCR exposure (large, `#104277`)
- `exec_summary` text block
- Admiralty distribution table (one row per escalated region)

**Region Pages** (escalated regions only, one page each)
- `#104277` header band: region name + `ESCALATED` badge
- Two-column layout: 90px sidebar + flex body
- Sidebar scorecard: VaCR / Admiralty / Velocity / Severity (each in a stacked cell with label)
- Body: three labelled sections — **Why — Geopolitical Driver** / **How — Cyber Vector** / **So What — Business Impact**
- If `report_body` unavailable: single amber "Report unavailable for this region" notice

**Appendix**
- Monitor regions: amber left-border cards with name + scenario_match + admiralty
- Clear regions: compact green status rows (name + "No active threat")
- Run metadata table: pipeline_id, timestamp, regions processed, tool versions

---

### 3. `tools/export_pdf.py` (rewrite)

```
ReportData → Jinja2.render(report.html.j2) → write to temp .html
           → Playwright: browser.new_page() → page.goto(file://{path})
           → page.pdf(format="A4", print_background=True, path=output_path)
           → delete temp file (use tempfile.NamedTemporaryFile with suffix=".html" — avoids path collisions)
           → print "PDF exported: {output_path}"
```

CLI: `uv run python tools/export_pdf.py [output.pdf]`
If no argument, defaults to `output/board_report.pdf`.
Reads data via `report_builder.build()` (no `input.md` argument needed).

---

### 4. `tools/export_pptx.py` (rewrite)

```
ReportData → python-pptx: open tools/templates/base.pptx
           → build_cover(prs, data)
           → build_exec_summary(prs, data)
           → for region in escalated_regions: build_region(prs, region)
           → build_appendix(prs, data)
           → prs.save(output_path)
           → print "PPTX exported: {output_path}"
```

One builder function per slide type. Each appends one slide using named placeholder shapes from `base.pptx`.

CLI: `uv run python tools/export_pptx.py [output.pptx]`
Defaults to `output/board_report.pptx`.

---

### 5. `tools/templates/base.pptx`

Created once as part of build. Contains:
- Slide master with `#104277` theme color
- Title slide layout (cover)
- Content layout with named placeholders: `title`, `body`, `sidebar`, `kpi_vacr`, `kpi_admiralty`, `kpi_velocity`, `kpi_severity`
- AeroGrid brand fonts (fallback: Calibri)

**Creation:** `export_pptx.py` calls `_ensure_base_pptx()` on startup — generates `tools/templates/base.pptx` programmatically if it does not exist. Self-bootstrapping, no manual step required. The generated file is committed to the repo after first run so subsequent calls skip generation.

---

## Integration

`run-crq.md` Phase 6 currently calls:
```
uv run python tools/export_pdf.py output/global_report.md output/board_report.pdf
```
The rewritten exporters drop the `input.md` positional argument (data is read via `report_builder`). **Phase 6 call in `run-crq.md` must be updated** to:
```
uv run python tools/export_pdf.py output/board_report.pdf
uv run python tools/export_pptx.py output/board_report.pptx
```

---

## Dependencies

| Library | Already installed | Action |
|---|---|---|
| `playwright` | Yes (Chromium) | No change |
| `jinja2` | No | `uv add jinja2` |
| `python-pptx` | Yes | No change |
| `markdown` | — | **Not needed** (pillar parsing via string split) |

One new dependency: `jinja2`.

---

## Out of Scope (Phase D)

- Audience-specific profiles (ExM, lower management, sales)
- NotebookLM audio briefing
- TOC page (deferred — Standard structure doesn't need one)
