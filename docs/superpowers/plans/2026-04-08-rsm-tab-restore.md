# RSM Tab Restore Implementation Plan

**Goal:** Make the RSM Briefs card in the Reports hub clickable and replace the current split-pane viewer with a Flash / INTSUM tabbed interface, showing proper placeholder content when no API data is available.

**Architecture:** Two edits to `static/app.js` only — enable the RSM card in `AUDIENCE_REGISTRY` and rewrite `renderRsmContent` to use the already-existing `rsmActiveTab` state for a tabbed UI. No server changes needed; the API endpoints already exist and the UI handles empty responses gracefully.

**Tech Stack:** Vanilla JS / HTML (inline styles, GitHub dark palette) — no new dependencies.

---

## File Map

| File | Action | Change |
|------|--------|--------|
| `static/app.js` | Modify line ~599 | Change RSM card `phase: 'phase-2'` → `phase: 'live'` |
| `static/app.js` | Modify lines ~1873–1931 | Rewrite `renderRsmContent` — tabs instead of split panes |
| `static/app.js` | Add after `selectRsmRegion` (~line 1871) | New `selectRsmBriefTab(region, type)` function |

No changes to `static/index.html` or `server.py`.

---

## Task 1: Enable RSM card in Reports hub

**Files:**
- Modify: `static/app.js:596-603`

The `AUDIENCE_REGISTRY` has the RSM entry marked `phase: 'phase-2'`. This makes the card dimmed and non-clickable. The "Phase 2" notice should live inside the detail view (as an empty state message), not as a gate on the card.

- [ ] **Step 1: Find and update the RSM registry entry**

Current block (lines ~596–603):

```javascript
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
```

Replace with:

```javascript
  {
    id: 'rsm',
    name: 'RSM Briefs',
    format: 'Markdown + PDF · 5 regions',
    phase: 'live',
    generate: null,
    downloads: [],
    renderer: 'region-list',
  },
```

- [ ] **Step 2: Verify in browser**

Open the Reports tab. The RSM Briefs card should now be full opacity and clickable. Clicking it opens the region-list detail view with the region sidebar.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): enable RSM Briefs card in Reports hub"
```

---

## Task 2: Add `selectRsmBriefTab` function

**Files:**
- Modify: `static/app.js` — insert after `selectRsmRegion` (~line 1871)

The `rsmActiveTab` state (`keyed by region: 'flash' | 'intsum'`) already exists but is never written or read. This function sets it and triggers a re-render.

- [ ] **Step 1: Find `selectRsmRegion` and add the new function immediately after it**

Current block ending at ~line 1871:

```javascript
function selectRsmRegion(r) {
  state.selectedRsmRegion = r;
  renderRsmSidebar();
  renderRsmContent(r);
}
```

Add immediately after (do not modify `selectRsmRegion`):

```javascript
function selectRsmBriefTab(region, type) {
  state.rsmActiveTab[region] = type;
  renderRsmContent(region);
}
```

- [ ] **Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): add selectRsmBriefTab for Flash/INTSUM tab switching"
```

---

## Task 3: Rewrite `renderRsmContent` with tabbed UI

**Files:**
- Modify: `static/app.js:1873-1931`

Replace the split-pane renderer with a tabbed interface. The tab bar shows Flash Alert and INTSUM buttons. The active tab state (`rsmActiveTab[region]`) persists across region switches. When no data is available, each tab shows a placeholder notice referencing Phase 2 instead of a generic "No brief available" line.

Key behaviour changes:
- Loading spinner only shows on first fetch (cache hit = instant re-render, no flash)
- API failure is handled: `state.rsmBriefs[region]` is set to `{ flash: null, intsum: null }` so render still runs
- Default active tab: Flash if flash data exists, otherwise INTSUM
- PDF download link targets the active tab type

- [ ] **Step 1: Find and replace `renderRsmContent` (lines ~1873–1931)**

Replace the entire function (from `async function renderRsmContent(region) {` to the closing `}`) with:

```javascript
async function renderRsmContent(region) {
  const header = $('rsm-region-label');
  const body   = $('rsm-panel-body');
  if (!header || !body) return;

  header.textContent = REGION_LABELS[region] || region;

  // Only show loading spinner on first fetch — cache hit renders immediately
  if (!state.rsmBriefs[region]) {
    body.innerHTML = `<p style="color:#6e7681;font-size:11px;padding:12px 16px">Loading...</p>`;
    const data = await fetchJSON(`/api/rsm/${region.toLowerCase()}`);
    state.rsmBriefs[region] = data || { flash: null, intsum: null };
  }

  const brief     = state.rsmBriefs[region];
  const hasFlash  = !!brief?.flash;
  const hasIntsum = !!brief?.intsum;
  const r         = region.toLowerCase();

  // Default active tab: prefer flash, fall back to intsum
  if (!state.rsmActiveTab[region]) {
    state.rsmActiveTab[region] = hasFlash ? 'flash' : 'intsum';
  }
  const activeTab = state.rsmActiveTab[region];

  function _tabBtn(type, label) {
    const isActive = type === activeTab;
    return `<button onclick="selectRsmBriefTab('${region}', '${type}')"
      style="font-size:10px;font-family:inherit;padding:5px 14px;border:none;
             border-bottom:2px solid ${isActive ? '#58a6ff' : 'transparent'};
             background:transparent;color:${isActive ? '#e6edf3' : '#6e7681'};cursor:pointer;
             transition:color 0.1s">
      ${label}
    </button>`;
  }

  const tabBar = `
    <div style="border-bottom:1px solid #21262d;display:flex;align-items:center;padding:0 8px;flex-shrink:0">
      ${_tabBtn('flash', '⚡ Flash Alert')}
      ${_tabBtn('intsum', 'INTSUM')}
      <a href="/api/rsm/${r}/pdf?type=${activeTab}" download
         style="margin-left:auto;font-size:9px;padding:2px 8px;border-radius:3px;
                background:transparent;border:1px solid #30363d;color:#6e7681;text-decoration:none">
         &#8659; PDF</a>
    </div>`;

  function _tabContent(type) {
    const content = brief?.[type];
    if (!content) {
      const typeLabel = type === 'flash' ? 'flash alert' : 'INTSUM brief';
      return `
        <div style="padding:20px 16px">
          <div style="font-size:10px;letter-spacing:0.06em;text-transform:uppercase;color:#484f58;margin-bottom:8px">
            ${type === 'flash' ? '⚡ Flash Alert' : 'Weekly INTSUM'}
          </div>
          <div style="font-size:11px;color:#6e7681">No ${typeLabel} available for ${region}.</div>
          <div style="margin-top:6px;font-size:10px;color:#484f58">
            RSM briefs are generated in Phase 2 (Seerist integration).
            Run <code style="font-size:9px;color:#8b949e">/run-crq</code> after Seerist is configured.
          </div>
        </div>`;
    }
    return `<pre style="font-size:10px;color:#e6edf3;white-space:pre-wrap;word-break:break-word;
                         line-height:1.6;margin:0;padding:12px 14px">${esc(content)}</pre>`;
  }

  body.innerHTML = `
    <div style="display:flex;flex-direction:column;flex:1;overflow:hidden;width:100%">
      ${tabBar}
      <div style="flex:1;overflow-y:auto">${_tabContent(activeTab)}</div>
    </div>`;
}
```

- [ ] **Step 2: Verify in browser — empty state**

Open Reports → RSM Briefs → select any region. Should see:
- Tab bar with "⚡ Flash Alert" and "INTSUM" buttons
- Active tab (Flash) shows the Phase 2 placeholder message
- Clicking INTSUM tab switches content without page reload
- PDF link is present in the tab bar

- [ ] **Step 3: Verify tab persistence**

Switch to a different region in the sidebar. Default tab resets for the new region (flash → intsum fallback logic). Switch back to previous region — tab state may reset (that's fine, `rsmActiveTab` only persists while the detail view is open).

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): RSM briefs — tabbed Flash/INTSUM UI with Phase 2 placeholder"
```

---

## Self-Review

**Spec coverage:**
- ✅ RSM card enabled (clickable) — Task 1
- ✅ Flash / INTSUM tabs — Task 3
- ✅ Works without API data — Task 3 (`data || { flash: null, intsum: null }`)
- ✅ `rsmActiveTab` state used — Task 2 + 3
- ✅ No server changes needed — confirmed (API endpoints exist, UI handles null gracefully)

**Placeholder scan:** No TBDs. All code blocks complete. Empty state message is explicit.

**Type consistency:** `selectRsmBriefTab(region, type)` used in Task 2 onclick matches `_tabBtn` in Task 3. `state.rsmActiveTab[region]` written in Task 2 function, read in Task 3 render — consistent.
