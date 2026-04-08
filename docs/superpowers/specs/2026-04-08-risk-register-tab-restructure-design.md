# Risk Register Tab Restructure — Design Spec

**Date:** 2026-04-08
**Status:** Approved

---

## Problem

The current Risk Register tab (`tab-validate`) has four structural failures:

1. **Wrong priority order** — VaCR INTELLIGENCE (validation output, priority 4) sits at the top. The register scenarios with current numbers are buried below it.
2. **Single vertical scroll** — 8 stacked sections with equal visual weight. No hierarchy. No way to see scenario numbers and validation results simultaneously.
3. **No scenario–validation link** — Scenario Library and validation results are disconnected sections. Nothing links a scenario's VaCR figure to its benchmark verdict.
4. **Orphaned register switcher** — Switch Register lives in the global header bar, visually disconnected from the register content in the tab.

---

## What Is Removed

These sections are deleted from the tab — HTML elements removed, JS functions deleted:

| Section | HTML element | JS functions deleted |
|---|---|---|
| Scenario Library (master scenarios) | `rr-master-table` | `loadValScenarios()`, `addMasterScenario()`, `editMasterScenario()`, `deleteMasterScenario()`, `saveMasterScenarioEdit()` |
| Regional Risk Register | `rr-regional-table` | `loadRegionalScenarios()`, `addRegionalScenario()`, `editRegionalScenario()`, `deleteRegionalScenario()` |
| Old benchmark validation divider + stacked results | inline divs | The top-level `_renderRegisterValidationResults()` wrapper is rewritten — inner render helpers (`_renderRegValDimension`, `_ctxBadge`, `_renderSourceRow`, `_renderSourcesBox`) are kept and reused |

The `val-last-run`, `btn-run-research`, `btn-run-validate`, and old benchmark results container are also removed.

---

## Switch Register — Single Owner

The global `register-bar` (always visible above all tabs) remains the single owner of Switch Register. The tab-local header strip does **not** duplicate a switch button. When the Risk Register tab is active, the register-bar above provides switch access. No duplication.

---

## Layout

### Tab-local header strip

A compact info bar at the top of `tab-validate` content — read-only context + run action:

```
▣  AeroGrid Enterprise — Wind Power Plant  ·  9 scenarios     Validated 2h ago  [▶ RUN]
```

- Register name + count: read-only, pulls from `state.activeRegister`
- `▶ RUN`: triggers `runRegisterValidation()`
- Timestamp: `relTime(state.validationData?.validated_at)` — hidden if no data

### Two-column body

The two columns fill the remaining viewport height. Each column scrolls independently (`overflow-y: auto`).

```
┌─────────────────────┬────────────────────────────────────────────┐
│  Scenario List      │  Scenario Detail (right panel)             │
│  40%  │ scroll      │  60%  │ scroll independently               │
│                     │                                            │
│  Name   VaCR  Prob  │  [Name]  [ID]              [✎ Edit]        │
│  $  %  verdict      │                                            │
│                     │  1. Numbers zone                           │
│  [selected row      │     VaCR · Probability (editable)          │
│   blue left border] │                                            │
│                     │  2. Validation zone                        │
│  + Add Scenario     │     Financial verdict + sources            │
│                     │     Probability verdict + sources          │
│                     │     Recommendation                         │
│                     │                                            │
│                     │  ▸ AUDIT TRACE (collapsed)                 │
│                     │                                            │
└─────────────────────┴────────────────────────────────────────────┘

── SOURCE REGISTRY ─────────────────────────────────────────── ▾ ──
   Registered Sources (global list)  |  New Sources (pending)
   [full width, collapsed by default, spans below two columns]
```

---

## Left Panel — Scenario List

**Content per row:**
- Scenario name
- VaCR figure (`$22.0M`) — green
- Probability (`31.7%`) — muted
- Two verdict badges side by side: `$ supports` / `$ challenges` / `$ insufficient` and `% supports` / `% challenges` / `% insufficient`
- **If no validation data exists for a scenario:** show grey `—` in both badge slots consistently

**Interaction:**
- Click row → loads scenario into right panel, highlights row with 2px blue left border and `#111820` background
- First scenario auto-selected on load (even if no validation data — right panel will show "No validation data yet" in the validation zone)
- `+ Add Scenario` button at the bottom of the list → opens the add-scenario form in the right panel (see below)

**Data source:** `state.activeRegister.scenarios` (scenario list) cross-referenced with `state.validationData.scenarios` (verdict badges). Both stored in state.

---

## Right Panel — Scenario Detail

### 1. Numbers zone

Two values displayed side by side:

```
VALUE AT CYBER RISK        PROBABILITY
$22,000,000                31.7%
```

`✎ Edit` button in the panel header toggles edit mode for this zone only:
- VaCR becomes a number input (USD, no formatting)
- Probability becomes a number input (float, 0–100)
- Save and Cancel buttons appear below the inputs
- On **Save**: `PATCH /api/registers/{register_id}/scenarios/{scenario_id}` → on success, update `state.activeRegister` and re-render the left panel row (verdict badges unchanged until next RUN)
- On **Cancel**: revert inputs, return to read-only

Edit mode does not affect the validation zone below.

### 2. Validation zone

Renders existing `_renderRegValDimension()` output for the selected scenario's `financial` and `probability` dimensions from `state.validationData`.

If `state.validationData` is null or the scenario has no entry: show a single placeholder:
```
No validation data — click ▶ RUN to validate this register.
```

If data exists, render in order:
- Financial: verdict badge + benchmark range + Registered Sources box + New Sources box
- Probability: verdict badge + benchmark range + Registered Sources box + New Sources box
- `asset_context_note` if present (italic, muted)
- Recommendation paragraph (Sonnet analyst note, amber left border)

### 3. Add Scenario form (right panel takeover)

When `+ Add Scenario` is clicked, the right panel body is replaced with the new-scenario form (currently `showRegisterForm()` logic, adapted). A `✕ Cancel` button at the top restores the previously selected scenario detail. On save, the new scenario is appended to the register, the left panel re-renders, and the new scenario is auto-selected.

---

## Source Registry section (tab-level, full width)

Sits below the two-column grid, spanning full width. Collapsed by default with a toggle header:

```
── SOURCE REGISTRY ──────────────────────────────── ▸ Show ──
```

When expanded, shows two sub-sections side by side (existing UI reused):
- **Registered Sources** — the full validation source list with Admiralty rating, cadence, scenarios tagged
- **New Sources (pending)** — sources found in Track 1 awaiting Promote / Dismiss

This is global to the validation run, not per-scenario. It is also rendered in the Source Audit tab (future — not in scope for this plan). No API changes needed; reuses existing endpoints.

---

## State Management

Two state fields must be stored (not just rendered inline):

```js
state.activeRegister    // { register_id, display_name, scenarios: [...] }
state.validationData    // { validated_at, version_checks, scenarios: [...] } | null
```

`loadRegisters()` already populates `state.activeRegister`.
`loadRegisterValidationResults()` must be updated to store the result in `state.validationData` before rendering, instead of rendering directly from the fetch response.

---

## API Changes

### New endpoint

`PATCH /api/registers/{register_id}/scenarios/{scenario_id}`

Payload:
```json
{
  "value_at_cyber_risk_usd": 22000000,
  "probability_pct": 31.7
}
```

Implementation: read register JSON → find scenario by `scenario_id` → update the two numeric fields → write back. Returns the updated scenario object. No other fields modified.

### Existing endpoints — unchanged

`GET /api/registers`, `POST /api/registers/active`, `GET /api/register-validation/results`, `POST /api/validation/run-register`, `POST /api/registers` (new register creation)

---

## Files Changed

| File | Change |
|---|---|
| `static/index.html` | Restructure `tab-validate` HTML: add tab header strip, two-column grid, source registry full-width section below; remove Scenario Library, Regional Register, old benchmark divider and results container; add independent scroll CSS for both columns |
| `static/app.js` | New `renderRiskRegisterTab()` replacing old vertical layout; `_renderScenarioList()`, `_selectScenario(id)`, `_renderScenarioDetail(scenario, valScenario)`, `_renderEditZone(scenario)`, `saveScenarioEdit(id)`, `toggleSourceRegistry()`; update `loadRegisterValidationResults()` to store in `state.validationData`; delete removed section functions (see table above) |
| `server.py` | Add `PATCH /api/registers/{register_id}/scenarios/{scenario_id}` |
