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
| Architecture | Rebuild in-place — same Tailwind CDN + vanilla JS stack, no new dependencies |

---

## Architecture

**Approach:** Rebuild `static/index.html` and `static/app.js` in-place. No new infrastructure, no build tooling, no new dependencies beyond `marked.js` (CDN) for markdown rendering.

**Files changed:**
- `static/index.html` — full rewrite
- `static/app.js` — full rewrite

**Files unchanged:**
- `server.py` — no backend changes needed
- All pipeline tools — no changes

**Audience extensibility pattern:** Depth-2 intelligence fields (Admiralty, Signal type, Dominant pillar) carry `data-audience="board"` attributes. A future audience tab switcher shows/hides by audience via one JS function. Single-view for now, expandable without a rewrite.

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

The mode selector ("Tools / Full LLM") is moved to a settings icon in the header — developer concern, not stakeholder concern.

---

## Region Cards

### Escalated cards (large, CRITICAL → HIGH → MEDIUM order)

Each escalated card surfaces all available intelligence fields:

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

- Admiralty badge has a tooltip explaining the rating (e.g. B = usually reliable, 2 = probably true)
- Velocity: ↑ accelerating · → stable · ↓ improving
- `data-audience="board"` on Admiralty, Signal, Pillar fields — audience-switchable without rewrite
- "Read Full Brief" opens regional panel on Brief tab
- "View Outputs" opens regional panel on Sources tab

### Clear/Monitor chips (compact row)

```
[✓ LATAM — Clear  A1]   [✓ NCE — Clear]   [⚠ XXX — Monitor  B3]
```

- Shows region name, status badge, Admiralty rating
- Clicking a chip opens a small popover with the gatekeeper's one-sentence rationale — confirms the region was actively assessed, not skipped

---

## Output Viewer Panels

A single reusable slide-over panel component, slides in from the right, overlays without layout shift.

### Regional panel (triggered by card buttons)

Two tabs: **Brief** and **Sources**

- **Brief tab:** Rendered markdown of `output/regional/{region}/report.md` via `marked.js`. Styled with proper headers, paragraph spacing, bold text.
- **Sources tab:** List of geo + cyber signal sources — title, snippet, URL, date. Read from `output/regional/{region}/geo_signals.json` and `cyber_signals.json`.

### Global panel (triggered by "Global Outputs" button)

Three tabs: **Report**, **PDF**, **PowerPoint**

- **Report tab:** Rendered `output/global_report.md` via `marked.js`
- **PDF tab:** `<iframe>` embedding `output/board_report.pdf` + Download button
- **PowerPoint tab:** Download button only (`.pptx` cannot be previewed in browser)

**Extensibility:** Adding a NotebookLM audio tab later is a new tab entry + `<audio>` element. No structural changes needed.

**Implementation:** One DOM element (`#output-panel`), `loadPanel(type, region)` function swaps content. `type` is `"regional"` or `"global"`.

---

## Pipeline Progress

### Progress bar

Appears at top of page when pipeline starts, disappears on completion. Driven by existing SSE events from `server.py` — no backend changes.

```
● Running Phase 1 — Regional Analysis (APAC, AME...)
████████████░░░░░░░░░░░░░░░░░░░  3 of 6 phases
```

- On completion: bar fills, shows "Pipeline complete — Mar 13, 12:04" for 3 seconds, then fades out
- On error: bar turns red, shows failed phase

Phase labels mapped from existing SSE event types:
- `PIPELINE_START` → Phase 0
- `GATEKEEPER_YES/NO` × 5 → Phase 1 progress
- `PHASE_COMPLETE "Velocity"` → Phase 2
- `PHASE_COMPLETE "Cross-regional"` → Phase 3
- `PHASE_COMPLETE "Global"` → Phase 4
- `PIPELINE_COMPLETE` → Phase 5+6 done

### History tab

Second nav tab. Reads from `output/runs/` directory.

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

- Each row reads `run_manifest.json` from the archived run
- "View" loads that run's data into the Overview tab in read-only mode with a banner: "Viewing archived run — Mar 12, 09:17"
- Audit trace: collapsible, raw `system_trace.log` lines, monospace font — for compliance/debug

---

## Data Sources (read-only, no new endpoints)

All data already exists — no new `server.py` endpoints needed for the core rework.

| UI Element | Data source |
|------------|-------------|
| KPI strip | `GET /api/manifest` → `run_manifest.json` |
| Executive summary | `GET /api/manifest` → `global_report.json` (served via existing manifest or new `/api/global` endpoint) |
| Region cards | `GET /api/region/{region}` → `data.json` per region |
| Regional brief | `GET /output/regional/{region}/report.md` (static file) |
| Regional sources | `GET /output/regional/{region}/geo_signals.json` + `cyber_signals.json` |
| Global report tab | `GET /output/global_report.md` (static file) |
| PDF tab | `GET /output/board_report.pdf` (static file, iframe) |
| PPTX tab | `GET /output/board_report.pptx` (static download) |
| History list | `GET /api/runs` → list of archived run manifests |
| Audit trace | `GET /output/system_trace.log` (static file) |

One addition to `server.py` may be needed: a `/api/global` endpoint serving `output/global_report.json` for the executive summary. All output files may also need to be served as static assets (currently only `static/` is served).

---

## New Dependencies

| Dependency | Purpose | How loaded |
|------------|---------|------------|
| `marked.js` | Markdown → HTML rendering | CDN script tag |

No npm, no build step.

---

## Out of Scope (F-2)

- Audience tabs (Board / CISO / Ops / Sales) — parked F-5
- Historical trend charts (VaCR sparklines over time) — parked F-5
- Analyst chat — parked F-5
- Scheduled runs — parked F-5
- NotebookLM audio tab — parked until API available
- Live OSINT (remove --mock) — F-4

---

## Build Sequence

1. `static/index.html` — full structure: header, nav tabs, progress bar slot, KPI strip, executive summary, escalated cards section, clear chips row, global outputs button, output panel component, settings modal
2. `static/app.js` — rewrite in sections: state, KPI render, card render, chip render, panel system (`loadPanel`), SSE/progress bar, history tab, settings
3. Verify: `server.py` static file serving covers `output/` directory for brief/PDF/PPTX access — add route if needed
4. Test full pipeline run end-to-end in browser
