# Agent Activity Console — Design Spec

**Date:** 2026-03-14
**Status:** Approved
**Scope:** `static/index.html`, `static/app.js` — no backend changes

---

## Overview

A floating agent activity console panel fixed to the bottom-right corner of the CRQ dashboard. Shows live agent events and raw Claude CLI output during pipeline runs. Appears automatically when a run starts; user can close and reopen it at will. Log appends across runs.

---

## Layout & Structure

- **Container:** `<div id="agent-console">` — `fixed bottom-4 right-4`, `w-80` (320px), `max-h-72` (288px), `bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-40` — `z-40` keeps it below `panel-overlay` (`z-50`) so the slide-over panel backdrop correctly covers the console when open.
- **Header bar:** Full-width strip at top. Left: `"Agent Activity"` label (`text-xs font-semibold text-gray-300`). Right: close `✕` button (`text-gray-500 hover:text-white`). Fixed height, does not scroll.
- **Log body:** `overflow-y-auto` area below the header, fills remaining height. Monospace small text. Auto-scrolls to bottom on new entries unless user has scrolled up.
- **Toggle button:** `<button id="agent-console-toggle">` — `fixed bottom-4 right-4`, `hidden` by default. Shown only after the first run has started AND the console is closed. Small pill: `"⬛ Agent Activity"` (`bg-gray-800 text-gray-300 text-xs px-3 py-1 rounded-full border border-gray-700`). Clicking it reopens the console. Note: the current `index.html` has no other elements fixed to `bottom-4 right-4` — this corner is free.

**Visibility rules:**
- On fresh page load: console hidden, toggle button hidden.
- On `pipeline started` SSE event: show console, hide toggle button.
- On user clicking `✕`: hide console, show toggle button (only if a run has ever started).
- On user clicking toggle button: show console, hide toggle button.

---

## Log Entry Types

Entries are appended to the log body in arrival order. Three visual types:

### 1. Run Separator
Shown at the start of every run **after the first** (i.e., when `runCount > 1`).

```
--- 2026-03-14 14:32 ---
```

Style: `text-gray-600 text-xs text-center py-1`

### 2. Structured Event
One line per event. Colored pill prefix + message.

| SSE Event | Condition | Pill | Color | Message |
|---|---|---|---|---|
| `pipeline` | `status: started` | `[PIPELINE]` | gray | `Started` |
| `pipeline` | `status: complete` | `[PIPELINE]` | green | `Complete` |
| `pipeline` | `status: error` | `[PIPELINE]` | red | `Error: {message}` |
| `phase` | `status: running` | `[PHASE]` | blue | phase label |
| `phase` | `status: complete` | `[PHASE]` | blue | phase label + ` ✓` |
| `phase` | no `status` key (per-region gatekeeper emit) | `[PHASE]` | blue | phase label (treat as running) |
| `gatekeeper` | `decision: ESCALATE` | `[{REGION} → ESCALATE]` | red | `{severity}` (only meaningful field for ESCALATE) |
| `gatekeeper` | `decision: MONITOR` | `[{REGION} → MONITOR]` | yellow | `elevated` |
| `gatekeeper` | `decision: CLEAR` | `[{REGION} → CLEAR]` | green | `clear` |

**Mode note:** `phase` and `gatekeeper` events are emitted by the tools-mode pipeline only. In LLM mode, agent activity arrives exclusively as `log` events (raw Claude CLI stdout).

Pill style: `text-xs font-mono font-semibold px-1.5 py-0.5 rounded mr-1` with color variant. Message: `text-gray-300 text-xs`.

### 3. Raw Log Line
Source: `log` SSE events (LLM mode only — Claude CLI stdout).

Style: `text-gray-500 text-xs font-mono leading-tight` — dimmed monospace, no prefix. Truncated to 120 chars to prevent layout overflow.

Event data shape: `{ message: string }` — read `data.message` from the parsed JSON payload.

---

## Auto-Scroll Behaviour

- `_consolePinned = true` (default).
- After appending an entry: if `_consolePinned`, set `scrollTop = scrollHeight`.
- On `scroll` event: if `scrollTop < scrollHeight - clientHeight - 10`, set `_consolePinned = false`.
- On `scroll` event: if at bottom (`scrollTop >= scrollHeight - clientHeight - 5`), set `_consolePinned = true`.

---

## SSE Wiring

All changes extend the existing `initSSE()` function in `static/app.js`. No new server endpoints. No backend changes.

New/extended listeners:

```
pipeline  → on started: (1) show console, (2) insert separator if runCount > 1, (3) increment runCount, (4) append [PIPELINE] Started entry
phase     → append [PHASE] entry (extend existing listener)
gatekeeper → new listener; append colored region→decision entry
log       → new listener; append raw dimmed line (truncated to 120 chars)
```

---

## Files Changed

| File | Change |
|---|---|
| `static/index.html` | Add `#agent-console` div (header + log body) and `#agent-console-toggle` button |
| `static/app.js` | Extend `initSSE()` with gatekeeper + log listeners; add show/hide/scroll logic; add `runCount` state |

No changes to: `server.py`, any Python tool, any agent definition.

---

## Out of Scope

- Persisting log across page refreshes (DOM only — clears on reload)
- Server-side log storage for the console
- Filtering or searching within the console
- Resizing the panel

