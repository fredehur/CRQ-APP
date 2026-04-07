# Run Log Tab + Persistent Run Bar — Design Spec

**Date:** 2026-04-07
**Status:** Approved

---

## Problem

The current Agent Activity console is a floating overlay that:
- Covers app content while the pipeline runs
- Dumps raw chronological log lines from 5 parallel regions — unreadable
- Is ephemeral: dismissed after a run, lost on page reload
- Conflates developer noise (`[log]` stdout lines) with decision-level intelligence

The user needs a structured, persistent record of what the pipeline decided — not just what it executed.

---

## Solution Overview

Two changes:

1. **Persistent Run Bar** — slim bar always visible at the top of the app, housing the Run button and live run status
2. **Run Log tab** — new nav tab replacing the floating console; structured by region, decision-level, persistent across reloads

Remove: floating `#agent-console`, toggle button, all raw `[log]` SSE lines from display.

---

## Persistent Run Bar

**Location:** Between the nav tabs and tab body content. Always visible regardless of active tab.

**Contents (left to right):**
- `Run Pipeline` button — disabled while a run is in progress
- Status label — one of:
  - `Idle`
  - `Running — 3/5 regions complete`
  - `Done in 4m 32s`
  - `Failed — APAC error`
- Thin progress bar — driven by regions completing (increments 1/5 per region done), not phases
- Window selector (existing control, moved here from Overview tab)

**Behaviour:**
- Button triggers the same `/api/run/all` endpoint as today
- Progress bar resets to 0 on new run start
- Status label persists until next run starts (shows last run outcome at idle)

---

## Run Log Tab

**Nav label:** `Run Log`

### Run Header

Shown at top of tab. Populated when a run completes (or on load from persisted file):
- Timestamp: `Last run: 2026-04-07 14:23`
- Duration: `Completed in 4m 32s`
- Outcome badge: `All Clear` (green) / `Escalations: 3` (amber/red) / `Failed` (red)
- Empty state: `No run yet — click Run Pipeline to start`

### Region Accordions

Five accordions in fixed order: APAC, AME, LATAM, MED, NCE.

**Initial state:** All collapsed. A region expands automatically when its gatekeeper decision arrives via SSE.

**Accordion header (always visible when region has data):**
- Region name
- Decision badge: `ESCALATE` (red) / `MONITOR` (blue) / `CLEAR` (green)
- Signal count: e.g., `7 signals` — populated after analyst phase completes (sourced from `data.json`); omitted from header during live run until available

**Inside each accordion — two sections:**

#### Summary (always open)
Content differs by decision:

**ESCALATED regions** — sourced from `data.json` (written by analyst agent):
- Scenario: e.g., `Supply Chain Disruption`
- Dominant pillar: `GEO-LED` / `CYBER-LED`
- Admiralty rating: e.g., `B2`
- Strategic assessment: `strategic_assessment` field verbatim (1–2 sentences)

**MONITOR / CLEAR regions** — analyst agent does not run; show gatekeeper rationale only:
- Decision: `MONITOR` / `CLEAR`
- Admiralty rating from gatekeeper decision
- Rationale: gatekeeper reason string from SSE `gatekeeper` event

#### Event Timeline (expandable)
- Open by default for ESCALATED regions
- Collapsed by default for MONITOR / CLEAR regions
- Ordered list of events as they arrived, with timestamps:
  - Phase transitions: `[14:23:04] Phase 2 — Gatekeeper`
  - Deep research hits: `[14:23:18] Deep research — Supply Chain Disruption (3 sources)`
  - Sources found: `[14:23:31] 12 sources collected`
  - Gatekeeper rationale: `[14:23:45] Decision: ESCALATE — B2 confidence, geo-led`
  - Analyst phase events (scenario coupling logged via existing `phase` SSE events)
- Raw `[log]` stdout lines are **not shown** — dropped entirely

#### Errors (always visible if present)
- Red highlighted block
- Error message from SSE `pipeline` error event
- Shown regardless of accordion open/closed state

---

## Persistence

**Problem:** SSE events are in-memory. A page reload loses the run log.

**Solution:** Server writes `output/pipeline/last_run_log.json` incrementally as SSE events are emitted. Structure:

```json
{
  "timestamp": "2026-04-07T14:23:00",
  "duration_seconds": 272,
  "status": "done",
  "regions": {
    "APAC": {
      "decision": "ESCALATE",
      "signal_count": 7,
      "summary": { "scenario": "...", "dominant_pillar": "...", "admiralty": "...", "strategic_assessment": "..." },
      "events": [
        { "time": "14:23:04", "type": "phase", "message": "Phase 2 — Gatekeeper" },
        ...
      ],
      "error": null
    }
  }
}
```

On tab load, `GET /api/run/log` returns this file. New run start overwrites the file.

---

## What's Removed

| Removed | Replaced by |
|---|---|
| `#agent-console` floating div | Run Log tab |
| `#agent-console-toggle` button | Persistent run bar status |
| `showConsole()` / `hideConsole()` calls | — |
| Raw `[log]` SSE events in UI | Dropped entirely |
| Run button on Overview tab | Persistent run bar |
| Window selector on Overview tab | Persistent run bar |

---

## Backend Changes

- New endpoint: `GET /api/run/log` — returns `last_run_log.json` or `{"status": "no_run"}`
- SSE handler in `server.py` writes to `last_run_log.json` as events are emitted
- `output/pipeline/` directory must exist before write; server should `mkdir -p` on startup or at run start
- No changes to existing SSE event schema — frontend filters which events to display

---

## Frontend Changes

- Remove `#agent-console` and `#agent-console-toggle` from `index.html`
- Add persistent run bar HTML between nav and tab body
- Add `Run Log` tab to nav
- New `renderRunLog()` function in `app.js`
- SSE handler updated: route events to run log + `last_run_log.json` writer; drop `[log]` events from display
- Remove `showConsole()`, `hideConsole()`, `appendConsoleEntry()` functions
- Move run button + window selector wiring to run bar
