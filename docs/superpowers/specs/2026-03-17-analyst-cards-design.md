# Phase K — Analyst-First Dashboard Cards

**Date:** 2026-03-17
**Status:** Approved — ready for planning

---

## Problem

The current dashboard surfaces pipeline mechanics (signal counts, convergence scores) rather than analyst conclusions. The highest-quality outputs the agents produce — scenario judgment, gatekeeper rationale, signal type classification, analyst brief — are either invisible or buried. An analyst opening the dashboard cannot answer "what is happening and should I act?" without clicking through multiple layers.

**Specific gaps:**

- `primary_scenario` and `signal_type` (Event/Trend/Mixed) are never shown anywhere in the UI
- `velocity` is computed every run but never displayed
- `dominant_pillar` (Geo vs Cyber) is absent from escalated cards
- Gatekeeper `rationale` only appears on CLEAR regions — not on the ESCALATED ones that need it most
- `report.md` (the 3-pillar analyst brief) is completely absent from the UI despite being the richest output
- `strategic_assessment` per region from `global_report.json` is never surfaced
- Signal count and convergence dot (developer metrics) are the primary visual on region rows

---

## Design

### Left panel — Region index rows

**Current:** `[REGION NAME]` + `[convergence dot] [N signals]`

**New:** Two-line row layout

```
[REGION]  [SCENARIO]              [EVENT] →
          Ransomware · Cyber
```

Line 1: Region name (severity-coloured) + scenario name + signal type badge + velocity arrow (right-aligned)
Line 2 (escalated only): Primary scenario · Dominant pillar — in muted colour

**Signal type badges:**
- `EVENT` — amber, solid
- `TREND` — blue, solid
- `MIXED` — purple, solid
- CLEAR rows: no badge, just `clear` in muted green

**Velocity arrows (escalated only):**
- `accelerating` → `↑` red
- `stable` → `→` grey
- `improving` → `↓` green
- `unknown` → omit

**Remove:** convergence dot, signal count number

**Data source:** `data.json` fields: `primary_scenario`, `signal_type`, `velocity`, `dominant_pillar`, `severity`

---

### Right panel — Escalated region header

**Current:** `[SEVERITY] Region Name   [B2]   timestamp`

**New:** Add a context strip directly below the header bar:

```
[SCENARIO] [EVENT] [Cyber] [→ stable]
Gatekeeper: Active ransomware campaign confirmed targeting North American energy sector...
```

- Row 1: `primary_scenario` pill + `signal_type` badge + `dominant_pillar` pill + velocity arrow
- Row 2: Gatekeeper rationale (full `d.rationale` text, muted colour, 11px)

**Data source:** `data.json` fields: `primary_scenario`, `signal_type`, `dominant_pillar`, `velocity`, `rationale`

---

### Right panel — Escalated region body

**Current:** Signal cluster cards only (no framing context).

**New:** Add a collapsible "Analyst Brief" section **above** the cluster cards.

```
▶ ANALYST BRIEF                                          [expand]
```

When expanded: fetches `GET /api/region/{region}/report` (already exists in server.py) and renders the markdown inline as plain text (pre-wrap, 11px, muted). No markdown parsing needed — raw text is readable.

Label the section with the signal type classification: `EVENT BRIEF` or `TREND BRIEF` or `MIXED BRIEF`.

Cluster cards remain below the brief section, unchanged.

**UX:** Brief is collapsed by default. State persists in `state.expandedBriefs` (Set, same pattern as `expandedClusters`).

---

### Right panel — CLEAR region

**Current:** Rationale + Admiralty + Window + Sources queried.

**Keep as-is.** CLEAR cards are already analyst-friendly. No changes needed.

---

### Left panel — Global synthesis block

**Current:** `synthesis_brief` text + status badge counts + run timestamp.

**New:** Add a **priority region callout** and a **velocity summary line** below the synthesis brief:

```
synthesis_brief text here...

Priority: AME (CRITICAL · Ransomware · Event · ↑)
Velocity: 3 stable, 0 accelerating, 0 improving
```

- Priority region: highest-severity escalated region, formatted as `REGION (SEVERITY · scenario · signal_type · velocity_arrow)`
- Velocity summary: count of escalated regions by velocity bucket
- If no escalated regions: omit both lines

**Data source:** `state.regionData` (already loaded) + `state.manifest`

---

## Data availability summary

All fields are already written by the pipeline — no agent changes required.

| New UI element | Source field | Location |
|---|---|---|
| Scenario name | `primary_scenario` | `data.json` |
| Signal type badge | `signal_type` | `data.json` |
| Velocity arrow | `velocity` | `data.json` |
| Dominant pillar pill | `dominant_pillar` | `data.json` |
| Gatekeeper rationale | `rationale` | `data.json` |
| Analyst brief | `report.md` | `GET /api/region/{region}/report` |
| Strategic assessment | `strategic_assessment` | `global_report.json` → `regional_threats[]` |
| Priority region | derived | `state.regionData` |
| Velocity summary | derived | `state.regionData` |

---

## Files changed

| File | Change |
|---|---|
| `static/app.js` | Render functions: `renderLeftPanel`, `renderRightPanel`, `renderClusterCard` + new `renderClearPanel` stays |
| `static/index.html` | Minor: CSS additions for new pills/badges, no structural changes |
| `server.py` | No changes needed — `GET /api/region/{region}/report` already exists |

---

## What is NOT changing

- Signal cluster cards — kept, unchanged. Good for drill-down.
- Admiralty badge in header — kept.
- CLEAR region panel — kept as-is.
- Reports tab — unchanged.
- History tab — unchanged.
- All backend / pipeline code — zero changes.

---

## Build order

```
K-1  CSS: add pills for signal_type, dominant_pillar, velocity arrows     ~30 min
K-2  Region index rows: replace signal count / convDot with new layout    ~45 min
K-3  Escalated right panel: context strip (scenario/type/pillar/vel/rat)  ~45 min
K-4  Analyst brief section: collapsible report.md fetch + render          ~45 min
K-5  Global synthesis: priority callout + velocity summary                ~30 min
```

Total estimate: ~3 hours. Pure frontend — `static/app.js` + minor `static/index.html` CSS.
