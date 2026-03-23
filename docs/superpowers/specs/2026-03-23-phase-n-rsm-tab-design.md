# Phase N — RSM Tab Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** UI-only — add a fifth RSM tab to the existing CRQ Analyst dashboard. No new pipeline work. Reads existing output files via a new API endpoint.

---

## 1. Overview

The RSM tab surfaces weekly INTSUM and flash alert content for AeroGrid's Regional Security Managers directly inside the analyst workstation UI. Pipeline already generates these briefs (`tools/rsm_dispatcher.py`, `tools/notifier.py`). This phase makes them visible in the app without leaving the dashboard.

---

## 2. Layout

**Pattern:** Sidebar + Document — identical split to the existing Overview tab. No new navigation paradigm.

```
┌──────────────────────────────────────────────────────┐
│ // CRQ ANALYST   Overview  Reports  History  Config  RSM● │
├────────────┬─────────────────────────────────────────┤
│  REGIONS   │  [⚡ FLASH]  [INTSUM WK12]               │
│            │                                         │
│ ⚡ APAC    │  AEROWIND // APAC FLASH // 2026-03-20  │
│  AME       │  TRIGGER: HotspotsAI 0.87 · ADM: B2   │
│  LATAM     │                                         │
│  MED       │  █ SITUATION                            │
│  NCE       │  Pre-media anomaly confirmed...         │
│            │                                         │
└────────────┴─────────────────────────────────────────┘
```

---

## 3. Components

### 3.1 Tab Bar Entry

- Label: `RSM`
- Red dot indicator (`●`) appended to label when **any** region has an active flash alert
- Driven by `state.rsmHasFlash`; populated on `loadLatestData()` from `GET /api/rsm/status` (see 4.2)

### 3.2 Sidebar

- Five region rows: APAC, AME, LATAM, MED, NCE (fixed order)
- Each row: region name only
- `⚡` prefix on rows where `state.rsmStatus[region].has_flash === true`
- Selected row: blue left border + subtle blue background (matches existing Overview selected style)
- Default selection: first region with a flash alert, or APAC if none

### 3.3 Content Area — Inner Tabs

Two sub-tabs per region:

| Tab | Label | Shown when |
|-----|-------|------------|
| Flash | `⚡ FLASH` (red background) | `flash !== null` |
| INTSUM | `INTSUM WK##` | always |

- Flash tab is selected by default when present
- If no flash, only the INTSUM tab is rendered (no empty tab)
- Week number in INTSUM tab label parsed from the brief header line (`WK12-2026` → `WK12`). If the pattern cannot be found (e.g. mock placeholder files), tab label falls back to `INTSUM` with no week suffix — no error thrown

### 3.4 Brief Content Renderer

- Rendered as `<pre>` monospace block — preserves `█` section headers, `▪` bullets, and `⚡` early warning markers native to the SITREP/INTSUM format
- Scrollable within the content area
- No markdown parsing — raw text only
- Fallback message when no brief available: `No brief available for this region.` (styled as dim subtitle)

---

## 4. Data Flow

### 4.1 Two API Endpoints

**Endpoint A — Status (lightweight, called on every `loadLatestData()`):**
```
GET /api/rsm/status
```
Response:
```json
{
  "APAC": {"has_flash": true,  "has_intsum": true},
  "AME":  {"has_flash": false, "has_intsum": true},
  "LATAM":{"has_flash": false, "has_intsum": true},
  "MED":  {"has_flash": false, "has_intsum": true},
  "NCE":  {"has_flash": false, "has_intsum": true}
}
```
Server logic: for each region, check whether `rsm_flash_*` and `rsm_brief_*` files exist in `output/regional/{region_lower}/`. Return boolean flags only — no file content read.

**Endpoint B — Content (lazy, called only when user selects a region):**
```
GET /api/rsm/{region}
```
Response:
```json
{
  "region": "APAC",
  "intsum": "AEROWIND // APAC INTSUM // WK12-2026\n...",
  "flash": "AEROWIND // APAC FLASH // 2026-03-20 14:00Z\n..." | null
}
```
Server logic:
1. Read `output/regional/{region_lower}/rsm_brief_{region_lower}_*.md` — latest by lexicographic sort (ISO date filenames sort correctly alphabetically) — as `intsum`
2. Read `output/regional/{region_lower}/rsm_flash_{region_lower}_*.md` — latest by lexicographic sort — as `flash`
3. Both fields return `null` if no matching file found

> **Note:** The file prefix (`rsm_brief_` vs `rsm_flash_`) is the discriminator between INTSUM and flash briefs. No content inspection required. Flash tab only appears when a real flash brief file exists. Current mock placeholder files (`[MOCK] RSM WEEKLY_INTSUM...`) will display as-is in the INTSUM panel — this is expected until the dispatcher generates real briefs.

### 4.2 Tab Dot and Sidebar Logic (client)

On `loadLatestData()`, call `GET /api/rsm/status` (one cheap request). Populate `state.rsmStatus`. Set `state.rsmHasFlash = true` if any region has `has_flash === true` → render `RSM●` in tab bar. Drive sidebar ⚡ indicators from `state.rsmStatus[region].has_flash`.

### 4.3 State

Add to existing `state` object:

```js
state.selectedRsmRegion = 'APAC'   // currently selected RSM sidebar region
state.rsmStatus = {}               // from /api/rsm/status: { APAC: {has_flash, has_intsum}, ... }
state.rsmBriefs = {}               // keyed by region, cached full content from /api/rsm/{region}
state.rsmActiveTab = {}            // keyed by region: 'flash' | 'intsum'
state.rsmHasFlash = false          // drives tab dot

// Initialisation: rsmActiveTab[region] is set to 'flash' if API response has flash !== null, otherwise 'intsum'
```

`rsmStatus` is refreshed on every `loadLatestData()`. `rsmBriefs` is fetched lazily on first region selection and cached for the session — not re-fetched on SSE pipeline completion (briefs are weekly cadence, not per-run).

---

## 5. Files Modified

| File | Change |
|------|--------|
| `server.py` | Add `GET /api/rsm/status` and `GET /api/rsm/{region}` endpoints |
| `static/app.js` | Add RSM tab render, sidebar, content area, state fields. **Must also** update `_doSwitchTab` to include `'rsm'` in its tab name array, and add `tab-rsm` / `nav-rsm` element IDs following the existing pattern — omitting this will cause the previously active tab to remain visible when switching to RSM |

No new files required.

---

## 6. Out of Scope

- Delivering or re-running RSM briefs from the UI (pipeline-only)
- Editing RSM audience config from this tab (Config tab owns that)
- Flash alert notifications / push / email from UI
- Rendering markdown (raw monospace only)
- Historical RSM brief archive viewer

---

## 7. Success Criteria

1. Fifth tab appears in nav bar with red dot when flash brief is present
2. Sidebar shows ⚡ on regions with active flash
3. Clicking a region loads its brief from `/api/rsm/{region}`
4. Flash sub-tab shown and selected by default when flash exists; hidden when not
5. INTSUM renders correctly as monospace pre-formatted text
6. Fallback message shown when no brief available
7. No regressions to existing tabs
