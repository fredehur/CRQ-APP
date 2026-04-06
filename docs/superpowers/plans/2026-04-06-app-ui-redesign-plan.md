# App UI Redesign — Implementation Plan
**Date:** 2026-04-06
**Spec:** `docs/superpowers/specs/2026-04-06-app-ui-redesign.md`
**Files changed:** `static/index.html`, `static/app.js` only
**Backend:** No changes to `server.py` or any API endpoint

---

## Execution Order

Steps must be executed sequentially. Each step has a validation gate before proceeding.

---

## Step 1 — Nav: Reorder tabs + add separator

**Files:** `static/index.html`

**What to change:**
1. Reorder the `<div class="nav-tab">` elements to: Overview · Reports · Trends · History · [separator] · Config · Validate · Sources
2. Remove the RSM `<div class="nav-tab" id="nav-rsm">` entirely
3. Add separator after the History tab: a 1px `#21262d` `border-right` on `#nav-history`, plus `margin-right: 4px` on `#nav-config` (CSS, not a DOM element)
4. Remove `id="nav-rsm"` and `id="nav-rsm-label"` from HTML

**CSS additions** (in `<style>` block):
```css
#nav-history { border-right: 1px solid #21262d; margin-right: 4px; }
```

**Validation:** Nav renders in correct order, separator visible between History and Config, no RSM tab.

---

## Step 2 — Nav: Remove RSM tab DOM + JS references

**Files:** `static/app.js`

**What to change:**
1. Remove the `switchTab('rsm')` case from `switchTab()` function
2. Remove any `loadRsm()` call or RSM tab initialisation logic
3. Do NOT delete the RSM render functions yet — they will be reused in Step 6

**Validation:** Clicking through all 7 remaining tabs works without JS errors. No RSM tab reference in nav logic.

---

## Step 3 — Overview: Synthesis bar restructure

**Files:** `static/index.html`, `static/app.js`

### HTML changes (`#global-synthesis`):
Replace the current synthesis bar HTML with a two-row structure:

```html
<div id="global-synthesis">
  <!-- Empty state (shown when no run data) -->
  <div id="synthesis-empty" style="padding:10px 16px;font-size:11px;color:#6e7681">
    No run data — click Run All to start.
  </div>
  <!-- Populated state (hidden until run completes) -->
  <div id="synthesis-populated" class="hidden">
    <!-- Row 1: counts + metadata -->
    <div id="synthesis-row1" style="display:flex;align-items:center;gap:10px;padding:8px 16px;border-bottom:1px solid #21262d">
      <div id="status-counts"></div>
      <div id="run-meta" style="margin-left:auto"></div>
    </div>
    <!-- Row 2: narrative -->
    <div id="synthesis-row2" style="padding:10px 16px">
      <p id="synthesis-brief"></p>
    </div>
  </div>
</div>
```

Remove: `gs-label`, `gs-right`, `gs-cell`, `global-priority`, `global-velocity` elements entirely.

### CSS changes:
- Remove `.gs-label`, `.gs-right`, `.gs-cell`, `#global-priority`, `#global-velocity` rules
- `#global-synthesis`: remove `display:flex; align-items:stretch` — let it be a block element
- `#synthesis-brief`: remove `padding: 22px 24px; flex:1` — new padding is `0` (set by row2 container)

### JS changes (`renderGlobalSynthesis()` or equivalent):
- On no-data: show `#synthesis-empty`, hide `#synthesis-populated`
- On data: hide `#synthesis-empty`, show `#synthesis-populated`
- Populate `#status-counts` with colour-coded badges using existing severity colours: `#ff7b72` (ESCALATED), `#79c0ff` (MONITOR), `#3fb950` (CLEAR)
- Populate `#run-meta` with timestamp + window string
- Populate `#synthesis-brief` with narrative text
- Remove: all priority and velocity render logic from this function

**Validation:** Empty state shows single-line message. After a mock run, row 1 shows correct counts + metadata, row 2 shows narrative. No priority/velocity visible.

---

## Step 4 — Overview: Region list simplification

**Files:** `static/app.js`, `static/index.html`

### JS changes (`renderRegionList()` or equivalent):
Each region row renders as:
```html
<div class="region-row" onclick="selectRegion('APAC')">
  <span style="color: [STATUS_COLOUR]; font-size:11px; font-weight:500">APAC</span>
</div>
```

Where `STATUS_COLOUR` maps:
- ESCALATED → `#ff7b72`
- MONITOR → `#79c0ff`
- CLEAR → `#3fb950`
- Unknown/pending → `#6e7681`

Remove from each row: scenario text, velocity arrow, source counts.

### CSS changes (`.region-row.active`):
```css
.region-row.active {
  background: #111820;
  border-left: 2px solid var(--region-status-colour); /* set inline per row */
  padding-left: 8px;
}
```

In JS, when activating a row: set `style="border-left-color: [STATUS_COLOUR]"` on the active row's left border inline.

**Validation:** Region list shows only names with correct colours. Selected row has matching left border colour. No scenario text or source counts visible.

---

## Step 5 — Overview: Compact rate bar

**Files:** `static/app.js`, `static/index.html`

### CSS changes — replace all `.feedback-*` rules:
```css
.feedback-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-top: 1px solid #21262d;
  background: #080c10; flex-shrink: 0;
}
.feedback-pill {
  font-size: 9px; background: #0d1117; border: 1px solid #21262d;
  color: #8b949e; padding: 1px 8px; border-radius: 10px; cursor: pointer;
  transition: background 0.1s, border-color 0.1s;
}
.feedback-pill:hover { border-color: #30363d; color: #c9d1d9; }
.feedback-pill.selected { background: #1a3a1a; border-color: #238636; color: #3fb950; }
.feedback-note-inline {
  flex-grow: 1; max-width: 240px;
  background: #080c10; border: 1px solid #21262d; color: #c9d1d9;
  font-size: 9px; font-family: 'IBM Plex Mono', monospace;
  padding: 1px 6px; border-radius: 2px; display: none;
}
```

Remove: `.feedback-section`, `.feedback-btns`, `.feedback-btn`, `.feedback-note`, `.feedback-submit`, `.feedback-status` CSS rules.

### JS changes (`renderFeedbackSection()` → `renderFeedbackBar()`):
Render a single `<div class="feedback-bar">` containing:
1. Three pills: `Accurate`, `Incomplete`, `Off-target`
2. A hidden `<input class="feedback-note-inline" placeholder="Add note... (Enter to save)">` (initially `display:none`)

**Interaction logic:**
- Pill click → mark selected, call `submitFeedback(region, rating)` immediately, show note input (`display:flex`)
- Note input `keydown Enter` → call `patchFeedbackNote(region, note)` (PATCH to existing rating record), hide input, show subtle "Saved" flash

**Validation:** Rate bar is a single row. Clicking a pill auto-saves and reveals note field. Note submits on Enter without creating a duplicate rating.

---

## Step 6 — Reports: Audience Hub

**Files:** `static/index.html`, `static/app.js`

### 6a — Audience Registry (JS constant in `app.js`)

Add at top of `app.js`:
```js
const AUDIENCE_REGISTRY = [
  {
    id: 'ciso',
    name: 'CISO Weekly Brief',
    format: 'Word (.docx)',
    phase: 'live',
    generate: '/api/outputs/ciso-docx',
    downloads: [{ label: '↓ Download', endpoint: '/api/outputs/ciso-docx' }],
    renderer: 'single-doc',
    sections: ['Scenario','Threat Actor','Intel Findings','Adversary Activity','Impact','Watch For','Actions'],
  },
  {
    id: 'board',
    name: 'Board Report',
    format: 'PDF + PowerPoint',
    phase: 'live',
    generate: null,
    downloads: [
      { label: '↓ PDF', endpoint: '/api/outputs/pdf' },
      { label: '↓ PPTX', endpoint: '/api/outputs/pptx' },
    ],
    renderer: 'single-doc',
  },
  {
    id: 'rsm',
    name: 'RSM Briefs',
    format: 'Markdown + PDF · 5 regions',
    phase: 'phase-2',
    phaseLabel: 'Requires Seerist integration',
    generate: null,
    downloads: [],
    renderer: 'region-list',
  },
  {
    id: 'sales',
    name: 'Regional Sales',
    format: 'TBD',
    phase: 'future',
    phaseLabel: 'Planned',
    generate: null,
    downloads: [],
    renderer: 'single-doc',
  },
];
```

### 6b — Hub view HTML (replace `#tab-reports` content)

Remove: all existing hardcoded card HTML, the report preview section.

New structure:
```html
<div id="tab-reports" class="hidden" style="padding:20px 24px;overflow-y:auto;max-height:calc(100vh - 36px)">
  <div id="reports-hub"></div>
  <div id="reports-detail" class="hidden" style="opacity:0;transition:opacity 150ms ease"></div>
</div>
```

### 6c — Hub render function (`renderReportsHub()`)

Renders `#reports-hub` using `AUDIENCE_REGISTRY`:
- Grid: `display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:12px`
- Each card built from registry entry
- `phase: 'live'` cards: full opacity, clickable (`onclick="openAudienceDetail('id')"`)
- `phase: 'phase-2'` cards: `opacity:0.55`, `cursor:default`, amber badge with `phaseLabel`, buttons disabled, `title` attribute tooltip
- `phase: 'future'` cards: `opacity:0.35`, `cursor:default`, grey "Planned" badge, buttons disabled, `title` attribute tooltip

### 6d — Detail shell (`openAudienceDetail(id)` / `closeAudienceDetail()`)

`openAudienceDetail(id)`:
1. Hide `#reports-hub`
2. Show `#reports-detail`, set `opacity:0`, then requestAnimationFrame → `opacity:1`
3. Render shell header: `← All reports | [name] [format] [Generate?] [Downloads]`
4. Call renderer based on `audience.renderer`:
   - `'single-doc'` → `renderSingleDocView(audience)`
   - `'region-list'` → `renderRegionListView(audience)`
5. Render compact rate bar at bottom (sticky)

`closeAudienceDetail()` (triggered by "← All reports"):
1. Fade `#reports-detail` to `opacity:0`
2. After 150ms: hide `#reports-detail`, show `#reports-hub`

### 6e — Single-doc renderer (`renderSingleDocView(audience)`)

Renders the CISO brief content inline from existing `/api/region/{region}/sections` or `/api/outputs/global-md` data. Sections rendered as labelled blocks matching existing `.brief-section` style.

### 6f — Region-list renderer (`renderRegionListView(audience)`)

**Move** (not rewrite) the existing RSM tab render logic here:
- Left: narrow region list, colour-coded, click to select
- Right: brief for selected region (scrollable)
- Per-region generate + download buttons in right pane header
- Rate bar: `position:sticky; bottom:0; background:#080c10` scoped to selected region

**Validation:** Hub shows 4 cards in auto-fill grid. CISO and Board are clickable. RSM and Sales show tooltips. Clicking CISO fades to detail view. "← All reports" fades back. RSM card (when phase changes to live) loads region-list renderer with existing RSM logic intact.

---

## Step 7 — Commit

Single commit covering all steps. Message:

```
feat(ui): app UI redesign — nav, overview, audience hub

- Nav: reorder tabs, separator between intelligence/ops clusters, RSM tab removed
- Synthesis bar: two-row layout (counts+meta / narrative), empty state, priority/velocity removed
- Region list: name + status colour only, active border matches status colour
- Rate bar: single inline row, auto-submit, optional inline note field
- Reports: config-driven Audience Hub, audience registry, single-doc + region-list renderers, RSM logic moved not rewritten, report preview removed
```

---

## Validation Checklist (post all steps)

- [ ] 7 tabs in nav, correct order, separator visible, no RSM tab
- [ ] Synthesis bar: empty state single-line, populated = two rows, no priority/velocity
- [ ] Status counts use correct colours (red/blue/green, not amber)
- [ ] Region list: name + colour only, active row border matches status colour
- [ ] Rate bar: single row, click saves, note appears inline, Enter patches record
- [ ] Reports hub: 4 cards in auto-fill grid, live cards clickable, non-live show tooltip
- [ ] CISO detail: fade in, brief readable, "← All reports" fades back
- [ ] RSM detail (when live): region list left, brief right, rate bar sticky
- [ ] No JS errors in console across all tabs
- [ ] No regression in Config, Validate, Source Audit tabs
