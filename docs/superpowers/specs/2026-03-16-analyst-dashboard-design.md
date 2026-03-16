# CRQ Analyst Dashboard — Design Spec

**Date:** 2026-03-16
**Status:** Approved for implementation planning
**Replaces:** Phase F-2 dashboard rework (roadmap-design.md lines 213–292)

---

## Reframe: Analyst Workstation, Not Executive Dashboard

The current dashboard was built as an executive-facing view. This spec reframes it as an **analyst workstation** — the tool the analyst uses to run the pipeline, explore signal output, and produce reports. Executives receive the reports (PDF, PPTX, markdown). They do not use this dashboard.

Consequences of this reframe:

- VaCR monetary values removed from the dashboard entirely (appear in reports only)
- Signal convergence replaces severity score as the primary regional metric
- The pipeline run trigger becomes a first-class UI element with time window control
- Data freshness is surfaced prominently
- Mode selector removed from main UI (settings gear only)

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Layout | Split-pane workstation | Analyst keeps full overview while exploring signals — no context loss |
| Aesthetic | SIGINT Terminal | IBM Plex Mono, green-on-near-black — authoritative, intelligence-native |
| Primary metric | Signal convergence | "4 sources pointing at the same theme" is more actionable than a severity label |
| Signal display | Themed clusters, raw sources on expand | Fast scan at cluster level, verification at source level |
| Global view | Cross-regional synthesis, always visible | Left panel pinned — never buried |
| Reports | Rendered markdown preview + export buttons | Analyst reviews before sending to board |
| Time window | Preset selector on run trigger | Controls OSINT search recency per run |
| Agent Console | Floating panel, unchanged | Stays — fits analyst context well |

---

## Navigation

Three tabs, no page reload — section switching only:

| Tab | Content |
|---|---|
| **Overview** | Split-pane workstation (default) |
| **Reports** | Rendered `global_report.md` + PDF/PPTX download buttons |
| **History** | Run history list + collapsible audit trace (unchanged) |

---

## Overview — Split-Pane Layout

### Left Panel (≈280px, fixed)

**Top section — Global Synthesis:**
- `synthesis_brief` (2-sentence cross-regional summary from `global_report.json`)
- Region status counts: `N ESCALATED | N MONITOR | N CLEAR`
- Run timestamp + relative age (e.g. "Last run 2h ago — 7-day window")

**Region list (5 rows):**
Each row shows:
- Region name (colored by signal intensity: red → orange → yellow → green)
- Signal count badge (e.g. "4 signals")
- Convergence indicator (dot color + filled bar segments)
- Click → right panel updates to that region's signal explorer

Default selection on load: region with the highest `total_signals` in `signal_clusters.json`. Tie-break: highest severity score from `data.json`. If no run exists: first region in canonical order (APAC, AME, LATAM, MED, NCE).

### Right Panel (flex)

**Header:**
- Region name + severity badge (CRITICAL / HIGH / MEDIUM / MONITOR / CLEAR)
- Run timestamp
- Admiralty rating badge with tooltip — tooltip content: decoded label, e.g. `B2 → Usually reliable / Probably true`. Full Admiralty scale decoded in tooltip.

**Signal Explorer — Escalated/Monitor regions:**

Signal clusters sourced from `signal_clusters.json` (see Pipeline section). Each cluster:
- Cluster name (theme label from analyst agent)
- Signal type pills: GEO / CYBER
- Convergence count ("×3 sources")
- Expand → inline list of raw source headlines with source name

**Signal Explorer — Clear regions:**

Confirmation screen:
- "Signal check confirmed — no active threats detected"
- Gatekeeper rationale (from `data.json`)
- Admiralty rating + window used
- Source count checked (e.g. "7 sources queried, 0 signals above threshold")

---

## Reports Tab

- Download buttons: **Export PDF** / **Export PPTX** (trigger existing export scripts via API)
- Rendered markdown preview of `global_report.md` below buttons (using `marked.js`)
- "Last generated" timestamp — read from `run_manifest.json` → `timestamp` field (not filesystem mtime)

---

## Run Trigger

**Location:** Top-right of header, always visible.

**Controls:**
- Time window selector (dropdown): `Last 24h | Last 7 days | Last 30 days | Last quarter`
- **▶ RUN ALL** button

The selected window is passed to the orchestrator, which forwards it to `geo_collector.py` and `cyber_collector.py` as a `--window` argument. The window is recorded in `run_manifest.json` alongside the run timestamp.

---

## Aesthetic

**Typography:** IBM Plex Mono throughout — headings, labels, data values, source names.
**Background:** `#070a0e` (near-black)
**Surface:** `#0d1117` (slightly lighter for panels)
**Border:** `#21262d`
**Accent:** `#3fb950` (green — active state, clear regions, run button)
**Severity palette:**

| Level | Color | Background |
|---|---|---|
| CRITICAL | `#ff7b72` | `#2d0000` |
| HIGH | `#ffa657` | `#2d1800` |
| MEDIUM | `#e3b341` | `#2d2200` |
| MONITOR | `#79c0ff` | `#1a1a2d` |
| CLEAR | `#3fb950` | `#0a1a0a` |

**Signal type pills:**
- GEO: `#79c0ff` on `#0d1f36`
- CYBER: `#d2a8ff` on `#1a0d36`

---

## Pipeline Data Contract (prerequisites for UI)

The UI depends on structured data that the current pipeline does not yet produce. These pipeline changes must be built before the UI.

### 1. `signal_clusters.json` per region — NEW (medium effort)

**Written by:** `regional-analyst-agent`
**Location:** `output/regional/{region}/signal_clusters.json`
**Written alongside:** `report.md`

Schema:
```json
{
  "region": "AME",
  "timestamp": "2026-03-16T09:14:00Z",
  "window_used": "7d",
  "total_signals": 4,
  "sources_queried": 12,
  "clusters": [
    {
      "name": "Grid disruption — ransomware cluster",
      "pillar": "Cyber",
      "convergence": 3,
      "sources": [
        { "name": "Reuters Energy", "headline": "US grid operators warn of coordinated access attempts" },
        { "name": "CISA AA26-072", "headline": "ICS/SCADA targeting in energy sector" },
        { "name": "OSINT", "headline": "Wind farm SCADA credentials listed on dark web forum" }
      ]
    }
  ]
}
```

**Field notes:**
- `timestamp` — ISO 8601, same value written to `run_manifest.json`; no separate `run_id` concept
- `pillar` — `"Geo"` or `"Cyber"` (distinct from `signal_type` in `data.json` which means Event/Trend/Mixed)
- `convergence` — integer count of sources within this cluster pointing at the same theme. Computed by the analyst agent: group raw signals by dominant keyword/entity overlap (≥2 sources on the same named entity or scenario = converged). Not a formula — the analyst agent reasons over signal content and assigns the count.
- `sources_queried` — total OSINT sources checked for this region regardless of signal yield; used by the CLEAR region confirmation screen
- For CLEAR regions: `clusters: []`, `total_signals: 0`, `sources_queried: N`

**Convergence indicator thresholds (UI rendering):**
- `convergence >= 3` → red/orange dot (strong convergence)
- `convergence == 2` → yellow dot (weak convergence)
- `convergence <= 1` → grey dot (single source, no convergence)

### 2. `synthesis_brief` field in `global_report.json` — NEW (small effort)

**Written by:** `global-builder-agent`
**Field:** `synthesis_brief` — string, max 2 sentences, cross-regional pattern summary.

Example:
```json
"synthesis_brief": "AME and APAC signals converge on state-adjacent pressure targeting renewable grid infrastructure. Two regions clear; no cross-regional indicator of coordinated campaign yet."
```

### 3. `--window` parameter on collectors — NEW (small effort)

**Affected tools:** `geo_collector.py`, `cyber_collector.py`, `osint_search.py`
**Orchestrator:** `run-crq.md` passes `--window` arg from user selection
**Manifest:** `run_manifest.json` records `window_used`

Preset values: `1d`, `7d`, `30d`, `90d`
Passed as a date recency filter to OSINT search queries (Tavily supports `days` param; DDG uses date-limited query strings).

**Mock mode:** In `--mock` mode the collectors read static fixtures regardless of `--window`. The window value is still recorded in `run_manifest.json` and `signal_clusters.json` so the UI renders it correctly. No per-window fixture variants are needed — mock mode ignores the window filter by design.

### 4. No change needed — CLEAR region data

`data.json` already contains `rationale`, `admiralty`, and `timestamp` for CLEAR regions. The UI can render the confirmation screen from existing fields.

---

## History Tab

Unchanged from current implementation. Contains:
- Run history list (previous run entries, click to load archived run)
- Collapsible audit trace (`system_trace.log` rendered in `<pre>`)

No new data requirements.

## Run Trigger — Error States

| Scenario | UI Behaviour |
|---|---|
| Backend unreachable | Button disabled, status label: "Server offline" in header |
| Pipeline mid-run failure | Agent Activity Console shows error event; header status: "Run failed — check console" |
| Region-level error | Region row in left panel shows error indicator; right panel shows last error message from trace |
| No run data on first load | Left panel shows "No run data — click Run All to start"; right panel empty state |

## Implementation Order

1. **Pipeline first:**
   - `--window` parameter on collectors + orchestrator (unblocks date-scoped runs)
   - `signal_clusters.json` output from regional-analyst-agent
   - `synthesis_brief` field in global-builder-agent
   - **`json-auditor.py` updated** to include `synthesis_brief` in required keys list

2. **UI second:**
   - Full rebuild of `static/index.html` + `static/app.js`
   - Split-pane layout with SIGINT aesthetic
   - Signal explorer wired to `signal_clusters.json`
   - Left panel wired to `synthesis_brief` + `data.json` per region
   - Reports tab with markdown preview
   - Run trigger with window selector

3. **Agent improvements (future session):**
   - Evaluate whether regional-analyst-agent and global-builder-agent outputs can be improved in quality, not just structure
   - Consider specialized sub-agents for signal clustering vs. narrative writing

---

## Files Modified / Created

| File | Action |
|---|---|
| `static/index.html` | Full rewrite |
| `static/app.js` | Full rewrite |
| `tools/geo_collector.py` | Add `--window` arg |
| `tools/cyber_collector.py` | Add `--window` arg |
| `tools/osint_search.py` | Add date recency filter |
| `.claude/commands/run-crq.md` | Pass `--window` to collectors |
| `.claude/agents/regional-analyst-agent.md` | Write `signal_clusters.json` |
| `.claude/agents/global-builder-agent.md` | Write `synthesis_brief` field |
| `output/regional/{region}/signal_clusters.json` | New output file |
| `run_manifest.json` | Add `window_used` field |

---

## Out of Scope (this spec)

- Custom date range picker (presets only)
- Audience tabs (board / ops / sales) — parked in roadmap
- Historical trend charts — parked
- Analyst chat — parked
- Scheduler / automated runs — parked
- Agent quality improvements — separate future session
