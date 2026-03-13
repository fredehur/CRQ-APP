# F-2 Dashboard Rework — Design Spec
**Date:** 2026-03-13
**Status:** Approved
**Phase:** F-2

---

## Context

The current dashboard (`static/index.html` + `static/app.js`) is functional but not fit for its audience. It surfaces a flat card grid with a permanent log panel consuming 1/3 of screen space, buries the executive summary below region cards, and exposes developer controls (mode selector) in the main UI. Rich intelligence fields produced by the pipeline — Admiralty ratings, signal type, rationale, financial rank, velocity — never appear in the live app.

This rework imposes a board-readable information hierarchy, surfaces all pipeline intelligence in the UI, and introduces a unified output viewer panel for regional and global deliverables.

---

## Decisions Made

| Question | Decision |
|----------|----------|
| Pipeline log treatment | Progress bar while running, full log on History tab — not a permanent panel |
| Brief viewer | Slide-over panel from right, overlays dashboard without layout shift |
| Output viewer scope | Regional panel (per-card) + Global panel (board deliverables). Separated. |
| Audience tabs | Parked (F-5). Build for Board/CISO now, structure for easy expansion via `data-audience` attributes |
| Architecture | Rebuild in-place — same Tailwind CDN + vanilla JS stack, `marked.js` added via CDN |

---

## Architecture

**Approach:** Rebuild `static/index.html` and `static/app.js` in-place. No new build tooling.

**Files changed:**
- `static/index.html` — full rewrite
- `static/app.js` — full rewrite
- `server.py` — two new endpoints: `GET /api/outputs/pdf` and `GET /api/outputs/pptx` (FileResponse)

**Files unchanged:** All pipeline tools, agents, hooks.

**Audience extensibility pattern:** Depth-2 intelligence fields (Admiralty, Signal type, Dominant pillar) carry `data-audience="board"` attributes. A future audience tab switcher shows/hides by audience via one JS function. Single Board/CISO view for now, expandable without a rewrite.

---

## Layout & Information Hierarchy

Single scrolling page with a fixed header. Reading order follows board consumption — headline first, evidence last.

```
┌─────────────────────────────────────────────────────────┐
│ Header: Logo · "AeroGrid Wind Solutions" · [Run button] │
│         Nav tabs: Overview | History    [⚙ settings]   │
├─────────────────────────────────────────────────────────┤
│ Progress bar (visible only while pipeline is running)   │
├─────────────────────────────────────────────────────────┤
│ KPI strip: Total VaCR · Escalated · Monitor · Clear     │
│            Last Run timestamp · Global Trend arrow      │
├─────────────────────────────────────────────────────────┤
│ Executive Summary (full width, prominent, above fold)   │
├─────────────────────────────────────────────────────────┤
│ ESCALATED REGIONS — large cards, ordered by severity    │
│ [AME CRITICAL]   [APAC HIGH]   [MED MEDIUM]             │
├─────────────────────────────────────────────────────────┤
│ CLEAR / MONITOR REGIONS — compact status chips row      │
│ [✓ LATAM Clear A1]   [✓ NCE Clear]                      │
├─────────────────────────────────────────────────────────┤
│ [Global Outputs] button → opens global output panel     │
└─────────────────────────────────────────────────────────┘
```

The mode selector ("Tools / Full LLM") moves to a settings modal (⚙ icon in header) — developer concern, not stakeholder concern.

### Empty states

**No run yet** (`GET /api/manifest` returns `{"status": "no_data"}`):
- KPI strip shows all `—` placeholders
- Executive summary section shows: "No intelligence run yet. Click Run All Regions to generate the first report."
- Region cards section shows five placeholder chips labelled with region names, all grey

**Pipeline currently running:**
- Progress bar visible at top
- Region cards from the previous run remain visible (stale data banner: "Run in progress — data from [last run timestamp]")
- Run button disabled and labelled "Running..."

**Error state:**
- Progress bar turns red, shows "Pipeline failed at Phase X"
- Previous run data remains visible
- Run button re-enabled

---

## Region Cards

### Escalated cards (large, CRITICAL → HIGH → MEDIUM order)

Each escalated card surfaces all available intelligence fields from `data.json`:

```
┌─────────────────────────────────────────────────────┐
│ [CRITICAL]  AME — Americas          $22.0M VaCR      │
│ ─────────────────────────────────────────────────── │
│ Scenario: Ransomware          Financial Rank: #1     │
│ Admiralty: B2 ⓘ               Signal: Trend          │
│ Pillar: Geopolitical          Velocity: → stable     │
│                                                     │
│ Rationale: "Ransomware signals corroborated across  │
│ two independent sources with recent sector          │
│ precedent."                                         │
│                                                     │
│ [Read Full Brief]             [View Outputs]        │
└─────────────────────────────────────────────────────┘
```

**Data source:** `GET /api/region/{region}` → `data.json` fields:
- `severity` → severity badge colour
- `vacr_exposure_usd` → VaCR display
- `primary_scenario` → Scenario
- `financial_rank` → Financial Rank
- `admiralty` → Admiralty badge (tooltip text generated from rating: letter = reliability, number = credibility)
- `signal_type` → Signal (Event / Trend / Mixed)
- `dominant_pillar` → Pillar
- `velocity` → arrow: ↑ accelerating · → stable · ↓ improving
- `rationale` → Rationale text

**Admiralty tooltip:** Hovering the ⓘ shows a one-liner, e.g. `B2 = Usually reliable source, information probably true`.

**Audience attributes:** `data-audience="board"` on Admiralty, Signal type, and Dominant pillar rows.

**Buttons:**
- "Read Full Brief" → opens regional panel, Brief tab
- "View Outputs" → opens regional panel, Signal Detail tab

### Clear/Monitor chips (compact row)

```
[✓ LATAM — Clear  A1]   [✓ NCE — Clear]   [⚠ XXX — Monitor  B3]
```

- Clicking a chip opens an inline popover with the `rationale` field from that region's `data.json`
- Monitor status is a real pipeline state (`status: "monitor"` written by `write_region_data.py`) — rendered as a yellow ⚠ chip
- If `admiralty` is null for a clear/monitor region, the rating is omitted from the chip

---

## Output Viewer Panels

A single reusable slide-over panel (`#output-panel`) slides in from the right, overlays without layout shift. Close button or Escape dismisses it. `loadPanel(type, region)` swaps content — `type` is `"regional"` or `"global"`.

### Regional panel (triggered by card buttons)

Two tabs: **Brief** and **Signal Detail**

**Brief tab:**
- Fetches `GET /api/region/{region}/report` (returns markdown string)
- Renders via `marked.js` — styled with proper headers, paragraph spacing, bold text

**Signal Detail tab:**
- Fetches `GET /api/region/{region}` for `data.json`
- Reads `geo_signals.json` and `cyber_signals.json` from the same API call or a new `GET /api/region/{region}/signals` endpoint (see Data Sources)
- Displays two sections:

**Geopolitical signals** (from `geo_signals.json`):
- Summary paragraph
- Lead indicators as a bulleted list

**Cyber signals** (from `cyber_signals.json`):
- Summary paragraph
- Threat vector
- Target assets as a bulleted list

Note: mock fixture files do not contain source URLs. When F-4 (live OSINT) ships, `geo_signals.json` will gain `source_urls[]` — the Signal Detail tab should render these as a "Sources" list if the field is present, and omit the section if it is absent.

### Global panel (triggered by "Global Outputs" button)

Three tabs: **Report**, **PDF**, **PowerPoint**

**Report tab:**
- Fetches `GET /api/global-report` (already exists in server.py, returns `global_report.json`)
- Also fetches `GET /api/region/global/report` or reads `output/global_report.md` — use `GET /api/outputs/global-md` (new endpoint, see below)
- Renders markdown via `marked.js`

**PDF tab:**
- `<iframe src="/api/outputs/pdf">` — browser renders PDF inline
- Download button: `<a href="/api/outputs/pdf" download>`

**PowerPoint tab:**
- Download button only: `<a href="/api/outputs/pptx" download>` — `.pptx` cannot be previewed in browser

**Extensibility:** Adding a NotebookLM audio tab later is a new tab entry + `<audio>` element pointing to `GET /api/outputs/audio`. No structural changes needed.

---

## Pipeline Progress

### Progress bar

Appears at top of page when pipeline starts, disappears on completion. Driven by existing SSE stream (`GET /api/logs/stream`).

```
● Running Phase 1 — Regional Analysis (APAC, AME...)
████████████░░░░░░░░░░░░░░░░░░░  3 of 6 phases
```

**SSE event mapping** (actual event shapes from server.py):

| SSE event | data.phase | data.status | Progress bar action |
|-----------|-----------|-------------|---------------------|
| `phase` | `"gatekeeper"` | `"running"` | Phase 1 — Regional Analysis |
| `phase` | `"gatekeeper"` | `"complete"` | Phase 1 done → advance bar |
| `phase` | `"trend"` | `"running"` | Phase 2 — Velocity Analysis |
| `phase` | `"trend"` | `"complete"` | Phase 2 done |
| `phase` | `"diff"` | `"running"` | Phase 3 — Cross-Regional Diff |
| `phase` | `"diff"` | `"complete"` | Phase 3 done |
| `phase` | `"dashboard"` | `"running"` | Phase 4–5 — Global Report & Exports |
| `phase` | `"dashboard"` | `"complete"` | Phase 4–5 done |
| `phase` | `"complete"` | (none) | Pipeline complete → fill bar, fade after 3s |

All SSE events arrive as `event: phase` with JSON `data` field. JS listener: `source.addEventListener('phase', handler)`.

**On completion:** Bar fills green, label shows "Pipeline complete — [timestamp]", fades out after 3 seconds. Dashboard data refreshes via `GET /api/manifest`.

**On error:** Bar turns red, label shows "Pipeline failed". Run button re-enabled.

### History tab

Second nav tab. Reads from `GET /api/runs` which returns list of archived run manifests from `output/runs/`.

```
Run History
────────────────────────────────────────────────
2026-03-13 12:04Z   $44.7M   3 escalated   [View]
2026-03-12 09:17Z   $41.2M   2 escalated   [View]
────────────────────────────────────────────────
Audit Trace (last run)   [▼ expand]
  2026-03-13 12:00Z PIPELINE_START ...
  2026-03-13 12:01Z GATEKEEPER_YES AME ...
```

**"View" scope:** Manifest-level only — loads the archived `run_manifest.json` data (total VaCR, per-region status/severity/VaCR, timestamp) into the Overview KPI strip and region chips. Overview renders in read-only mode with a banner: "Viewing archived run — Mar 12, 09:17. [Return to latest]". No regional drill-down into archived run detail — archived report.md/data.json paths are not served.

**Audit trace:** Fetches `GET /api/trace` (already exists). Collapsible section, monospace font, raw `system_trace.log` lines.

---

## Data Sources & API Endpoints

### Existing endpoints (no changes needed)

| Endpoint | Returns | Used for |
|----------|---------|----------|
| `GET /api/manifest` | `run_manifest.json` | KPI strip, region status, last-run timestamp |
| `GET /api/region/{region}` | `data.json` | Region card fields |
| `GET /api/region/{region}/report` | markdown string | Regional brief (Brief tab) |
| `GET /api/global-report` | `global_report.json` | Executive summary, global JSON |
| `GET /api/runs` | list of run manifests | History tab rows |
| `GET /api/trace` | log text | Audit trace |
| `GET /api/logs/stream` | SSE stream | Progress bar events |

### New endpoints needed in server.py

| Endpoint | Returns | Used for |
|----------|---------|----------|
| `GET /api/outputs/pdf` | FileResponse `output/board_report.pdf` | PDF tab iframe + download |
| `GET /api/outputs/pptx` | FileResponse `output/board_report.pptx` | PPTX download button |
| `GET /api/outputs/global-md` | markdown string from `output/global_report.md` | Report tab in global panel |
| `GET /api/region/{region}/signals` | dict with `geo` and `cyber` keys | Signal Detail tab |

`/api/region/{region}/signals` reads `output/regional/{region}/geo_signals.json` and `output/regional/{region}/cyber_signals.json` and returns both as `{"geo": {...}, "cyber": {...}}`.

---

## New Dependencies

| Dependency | Purpose | How loaded |
|------------|---------|------------|
| `marked.js` | Markdown → HTML rendering | CDN script tag |

No npm, no build step.

---

## Out of Scope (F-2)

- Audience tabs (Board / CISO / Ops / Sales) — parked F-5
- Historical trend charts — parked F-5
- Analyst chat — parked F-5
- Scheduled runs — parked F-5
- NotebookLM audio tab — parked until API available
- Live OSINT (remove --mock) — F-4
- Source URL rendering in Signal Detail tab — deferred to F-4 (mock fixtures have no URLs)
- Regional drill-down from History tab — out of scope, manifest-level only

---

## Build Sequence

1. **`server.py`** — add 4 new endpoints: `GET /api/outputs/pdf`, `GET /api/outputs/pptx`, `GET /api/outputs/global-md`, `GET /api/region/{region}/signals`
2. **`static/index.html`** — full rewrite: header with nav tabs + settings icon, progress bar slot, KPI strip, executive summary, escalated cards section, clear/monitor chips row, global outputs button, slide-over panel component (`#output-panel`), settings modal
3. **`static/app.js`** — full rewrite in sections:
   - State management (`manifest`, `regionData`, `globalReport`)
   - KPI render (including empty/running states)
   - Escalated card render (all fields, buttons, Admiralty tooltip)
   - Clear/monitor chip render (popover with rationale)
   - Panel system: `loadPanel(type, region)`, tab switching, Brief/Signal Detail/Report/PDF/PPTX tabs
   - SSE handler → progress bar phase mapping
   - History tab: run list, "View" archived mode, audit trace
   - Settings modal (mode selector)
4. **Test:** Full pipeline run in browser — verify all card fields populate, panel opens/closes, progress bar tracks phases, history tab lists runs
