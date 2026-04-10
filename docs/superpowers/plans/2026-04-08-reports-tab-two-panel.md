# Reports Tab Two-Panel Layout Implementation Plan

**Goal:** Replace the hub-to-detail swap in the Reports tab with a persistent two-panel layout — compact card rail on the left, content on the right — so analysts can switch between reports without navigating back.

**Architecture:** All changes are in `static/app.js`. The `#tab-reports` shell in `index.html` stays untouched — `renderReports()` builds the two-panel DOM inside it. Selected card state is tracked in `state.selectedAudienceId`. Existing content renderers (`renderSingleDocView`, `renderRegionListView`) are unchanged — they still write to `#audience-detail-body`.

**Tech Stack:** Vanilla JS / inline styles, GitHub dark palette — no new dependencies.

---

## File Map

| File | Action | Lines |
|------|--------|-------|
| `static/app.js` | Add `selectedAudienceId` to state | ~34 |
| `static/app.js` | Rewrite `renderReports()` | ~617–619 |
| `static/app.js` | Rewrite `renderReportsHub()` → `renderReportsRail()` | ~621–667 |
| `static/app.js` | Replace `openAudienceDetail()` with `selectAudience()` | ~673–713 |
| `static/app.js` | Remove `closeAudienceDetail()` | ~715–724 |
| `static/app.js` | Update `_hubGenerate` call inside rail HTML | same block |

`static/index.html` — no changes.

---

## Task 1: Add `selectedAudienceId` to state

**Files:**
- Modify: `static/app.js` — state object (~line 34)

The state object needs to track which card is active so the rail and content stay in sync.

- [ ] **Step 1: Find the state object and add the field**

Current block (around line 34):
```javascript
  selectedRsmRegion: 'APAC',
  rsmStatus: {},
```

Add `selectedAudienceId` on the line before `selectedRsmRegion`:
```javascript
  selectedAudienceId: 'ciso',
  selectedRsmRegion: 'APAC',
  rsmStatus: {},
```

- [ ] **Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): add selectedAudienceId to state for Reports two-panel"
```

---

## Task 2: Rewrite `renderReports()` — two-panel shell

**Files:**
- Modify: `static/app.js:617–619`

`renderReports()` now builds the two-panel layout and kicks off both the rail and the content render.

- [ ] **Step 1: Find and replace `renderReports()`**

Current:
```javascript
async function renderReports() {
  renderReportsHub();
}
```

Replace with:
```javascript
async function renderReports() {
  const tab = $('tab-reports');
  if (!tab) return;

  // Build two-panel shell (idempotent — only if not already built)
  if (!$('reports-rail')) {
    tab.innerHTML = `
      <div style="display:grid;grid-template-columns:180px 1fr;height:calc(100vh - 60px);overflow:hidden">
        <div id="reports-rail"
             style="border-right:1px solid #21262d;overflow-y:auto;background:#080c10"></div>
        <div id="reports-content"
             style="display:flex;flex-direction:column;overflow:hidden"></div>
      </div>`;
  }

  renderReportsRail();
  renderAudienceContent(state.selectedAudienceId);
}
```

- [ ] **Step 2: Verify structure**

Open the Reports tab. You should see a left rail (blank, 180px wide) and a right panel. No content yet — that comes in the next tasks.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): Reports tab — two-panel shell"
```

---

## Task 3: Replace `renderReportsHub()` with `renderReportsRail()`

**Files:**
- Modify: `static/app.js:621–667`

Replace the grid-of-cards hub with a compact vertical card list in the left rail. Each item shows name + format + phase badge. The active item gets a blue left border. Cards marked `phase: 'future'` are dimmed but still clickable (they show a "coming soon" panel).

- [ ] **Step 1: Find `renderReportsHub()` and replace it entirely**

Current function (lines ~621–667):
```javascript
function renderReportsHub() {
  const hub = $('reports-hub');
  if (!hub) return;
  const cardsHtml = AUDIENCE_REGISTRY.map(a => {
    ...
  }).join('');
  hub.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">${cardsHtml}</div>`;
}
```

Replace the entire function with:
```javascript
function renderReportsRail() {
  const rail = $('reports-rail');
  if (!rail) return;

  rail.innerHTML = AUDIENCE_REGISTRY.map(a => {
    const isActive  = a.id === state.selectedAudienceId;
    const isFuture  = a.phase === 'future';
    const opacity   = isFuture ? '0.4' : '1';
    const phaseBadge = a.phase === 'live'
      ? `<span style="font-size:8px;background:#1a3a1a;border:1px solid #238636;color:#3fb950;
                      padding:1px 5px;border-radius:8px;margin-left:4px">Live</span>`
      : a.phase === 'phase-2'
        ? `<span style="font-size:8px;background:#2d2208;border:1px solid #9e6a03;color:#e3b341;
                        padding:1px 5px;border-radius:8px;margin-left:4px">Phase 2</span>`
        : `<span style="font-size:8px;background:#161b22;border:1px solid #30363d;color:#6e7681;
                        padding:1px 5px;border-radius:8px;margin-left:4px">Planned</span>`;

    return `
<div onclick="selectAudience('${a.id}')"
     style="padding:10px 14px;cursor:pointer;opacity:${opacity};
            border-left:2px solid ${isActive ? '#58a6ff' : 'transparent'};
            background:${isActive ? '#0d1117' : 'transparent'};
            transition:background 0.1s"
     onmouseover="if('${a.id}'!==state.selectedAudienceId)this.style.background='#0d111780'"
     onmouseout="if('${a.id}'!==state.selectedAudienceId)this.style.background='transparent'">
  <div style="display:flex;align-items:center;flex-wrap:wrap">
    <span style="font-size:11px;font-weight:600;color:${isActive ? '#e6edf3' : '#8b949e'}">${a.name}</span>
    ${phaseBadge}
  </div>
  <div style="font-size:9px;color:#484f58;margin-top:2px">${a.format}</div>
</div>`;
  }).join('');
}
```

- [ ] **Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): Reports rail — compact card list with active state"
```

---

## Task 4: Add `selectAudience()` and `renderAudienceContent()`

**Files:**
- Modify: `static/app.js` — replace `openAudienceDetail()` (~line 673) and remove `closeAudienceDetail()` (~line 715)

`selectAudience()` updates the selected ID, re-renders the rail (to move the active highlight), and re-renders the content panel. `renderAudienceContent()` builds the content panel header and calls the appropriate renderer.

- [ ] **Step 1: Find `openAudienceDetail()` and replace it**

Current function starts at ~line 673:
```javascript
function openAudienceDetail(id) {
  const audience = AUDIENCE_REGISTRY.find(a => a.id === id);
  ...
}
```

Replace the entire `openAudienceDetail` function with:
```javascript
function selectAudience(id) {
  state.selectedAudienceId = id;
  renderReportsRail();
  renderAudienceContent(id);
}

function renderAudienceContent(id) {
  const content = $('reports-content');
  if (!content) return;

  const audience = AUDIENCE_REGISTRY.find(a => a.id === id);
  if (!audience) return;

  const isFuture = audience.phase === 'future';

  const dlHtml = audience.downloads.map(d =>
    `<a href="${d.endpoint}" target="_blank"
       style="font-size:10px;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;
              padding:3px 10px;border-radius:2px;text-decoration:none">${d.label}</a>`
  ).join('');

  const genHtml = audience.generate
    ? `<button onclick="_hubGenerate('${audience.id}')"
         style="font-size:10px;background:#1a3a1a;border:1px solid #238636;color:#3fb950;
                padding:3px 10px;border-radius:2px;cursor:pointer;font-family:inherit">
         &#8635; Generate</button>`
    : '';

  content.innerHTML = `
    <div style="padding:10px 16px;border-bottom:1px solid #21262d;flex-shrink:0;
                display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <span style="font-size:11px;font-weight:600;color:#e6edf3">${audience.name}</span>
      <span style="font-size:10px;color:#6e7681">${audience.format}</span>
      <div style="margin-left:auto;display:flex;gap:6px">${genHtml}${dlHtml}</div>
    </div>
    <div id="audience-detail-body" style="flex:1;overflow-y:auto;font-size:12px;color:#c9d1d9"></div>`;

  if (isFuture) {
    $('audience-detail-body').innerHTML =
      `<p style="color:#6e7681;font-size:11px">${audience.phaseLabel || 'Coming soon.'}</p>`;
    return;
  }

  if (audience.renderer === 'region-list') {
    renderRegionListView(audience);
  } else {
    renderSingleDocView(audience);
  }
}
```

- [ ] **Step 2: Find and delete `closeAudienceDetail()`**

Current (lines ~715–724):
```javascript
function closeAudienceDetail() {
  const hub    = $('reports-hub');
  const detail = $('reports-detail');
  if (!hub || !detail) return;
  detail.style.opacity = '0';
  setTimeout(() => {
    detail.classList.add('hidden');
    hub.classList.remove('hidden');
  }, 150);
}
```

Delete the entire function.

- [ ] **Step 3: Fix hardcoded height in `renderRegionListView`**

The RSM region-list grid uses `height:calc(100vh - 140px)` — calculated for the old layout. In the new layout `audience-detail-body` is `flex:1`, so the grid just needs `height:100%`.

Find in `static/app.js` (~line 782):
```javascript
<div style="display:grid;grid-template-columns:200px 1fr;height:calc(100vh - 140px);overflow:hidden;border:1px solid #21262d;border-radius:2px">
```

Replace with:
```javascript
<div style="display:grid;grid-template-columns:200px 1fr;height:100%;overflow:hidden;border:1px solid #21262d;border-radius:2px">
```

- [ ] **Step 4: Verify in browser**

Open Reports tab. Left rail shows 4 cards — CISO is active by default (blue left border). Click Board Report — border moves, right panel updates. Click RSM Briefs — region sidebar fills the content panel without clipping. Click back to CISO — works instantly.

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): Reports — selectAudience + renderAudienceContent replace hub/detail swap"
```

---

## Task 5: Clean up dead references

**Files:**
- Modify: `static/app.js` — scan for `reports-hub`, `reports-detail`, `openAudienceDetail`, `closeAudienceDetail`

After the refactor, `#reports-hub`, `#reports-detail`, `openAudienceDetail`, and `closeAudienceDetail` are no longer used.

- [ ] **Step 1: Search for stale references**

Run in terminal:
```bash
grep -n "reports-hub\|reports-detail\|openAudienceDetail\|closeAudienceDetail" static/app.js
```

Expected: zero matches (all were removed in Tasks 3–4). If any remain, delete them.

- [ ] **Step 2: Commit (only if changes were needed)**

```bash
git add static/app.js
git commit -m "chore(ui): remove stale reports-hub/detail references"
```

---

## Self-Review

**Spec coverage:**
- ✅ Cards always visible in left rail — Task 3
- ✅ Click switches content without navigating back — Task 4
- ✅ Active card highlighted (blue left border) — Task 3
- ✅ Downloads/Generate buttons move to content panel header — Task 4
- ✅ RSM region list still works (renderer: 'region-list') — Task 4 calls `renderRegionListView` unchanged
- ✅ Future/planned cards shown dimmed, click shows "Coming soon" — Task 4

**Placeholder scan:** No TBDs. All code blocks complete. `renderRegionListView` and `renderSingleDocView` are unchanged and already work.

**Type consistency:**
- `selectAudience(id)` used in rail `onclick` (Task 3) and defined in Task 4 — match ✅
- `state.selectedAudienceId` set in Task 1, read in Task 3 (`renderReportsRail`) and Task 4 (`selectAudience`) — match ✅
- `$('audience-detail-body')` created in `renderAudienceContent` (Task 4), read by `renderSingleDocView` and `renderRegionListView` — match ✅
- `$('reports-rail')` created in `renderReports` (Task 2), written by `renderReportsRail` (Task 3) — match ✅
- `$('reports-content')` created in `renderReports` (Task 2), written by `renderAudienceContent` (Task 4) — match ✅
