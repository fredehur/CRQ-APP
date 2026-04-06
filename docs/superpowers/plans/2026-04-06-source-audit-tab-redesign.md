# Source Audit Tab Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Source Audit tab with keyword search, merged usage column, freshness/citation colour signals, tier override dropdown, prominent links, and bulk flag with select-all.

**Architecture:** Three files change. `server.py` gets one new endpoint. `static/index.html` gets a search input and revised column headers. `static/app.js` gets rewritten render functions and new helpers. All JS helpers are pure functions — no side effects — making them independently testable. DOM state for checkbox selection lives in `state.selectedSourceIds` (a `Set`).

**Tech Stack:** FastAPI (server.py), vanilla JS (app.js), inline CSS, SQLite via `data/sources.db`

---

## File Map

| File | What changes |
|---|---|
| `server.py` | Add `SourceTierBody` Pydantic model + `POST /api/sources/{id}/tier` endpoint (lines after existing `flag_source`) |
| `static/index.html` | Filter bar: add `<input id="src-search">`. Column headers: swap Appearances+Cited for Usage. Add `<div id="src-bulk-bar">`. |
| `static/app.js` | Add `selectedSourceIds` to state. New helpers: `applySourceSearch`, `_freshnessStyle`, `_usageBar`, `copyUrl`, `_childRow`, `showTierDropdown`, `overrideTier`, `_renderBulkBar`, `toggleSourceCheck`, `selectAllSources`, `bulkFlagSelected`, `clearSourceSelection`. Rewrite `renderSourceRegistryTable`. Update `renderSources`. |

---

## Task 1 — Server: POST /api/sources/{id}/tier

**Files:**
- Modify: `server.py` (after line 1153, after `flag_source`)

- [ ] **Step 1: Add Pydantic model and endpoint**

In `server.py`, after the `flag_source` function (after line ~1153), add:

```python
class SourceTierBody(BaseModel):
    tier: str


@app.post("/api/sources/{source_id}/tier")
async def set_source_tier(source_id: str, body: SourceTierBody):
    """Override the credibility tier for a source."""
    if body.tier not in ("A", "B", "C"):
        return JSONResponse({"ok": False, "error": "tier must be A, B, or C"}, status_code=400)
    try:
        with sqlite3.connect(SOURCES_DB) as conn:
            row = conn.execute(
                "SELECT id FROM sources_registry WHERE id = ?", (source_id,)
            ).fetchone()
            if row is None:
                return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
            conn.execute(
                "UPDATE sources_registry SET credibility_tier = ? WHERE id = ?",
                (body.tier, source_id),
            )
            conn.commit()
        return {"ok": True}
    except Exception:
        return JSONResponse({"ok": False, "error": "db error"}, status_code=500)
```

- [ ] **Step 2: Verify server starts without error**

```bash
PYTHONPATH=. uv run python -c "import server; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Smoke test the endpoint**

Start the server (`uv run python server.py`) then in a second terminal:

```bash
# Should 400 — invalid tier
curl -s -X POST http://localhost:8000/api/sources/test/tier \
  -H "Content-Type: application/json" -d '{"tier":"Z"}' | python -c "import sys,json; print(json.load(sys.stdin))"
# Expected: {'ok': False, 'error': 'tier must be A, B, or C'}

# Should 404 — unknown ID
curl -s -X POST http://localhost:8000/api/sources/does-not-exist/tier \
  -H "Content-Type: application/json" -d '{"tier":"A"}' | python -c "import sys,json; print(json.load(sys.stdin))"
# Expected: {'ok': False, 'error': 'not found'}
```

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat(api): POST /api/sources/{id}/tier — override credibility tier"
```

---

## Task 2 — index.html: Search input, column headers, bulk bar placeholder

**Files:**
- Modify: `static/index.html` (lines 604–655)

- [ ] **Step 1: Replace the filter bar**

Find and replace the entire `<!-- Filter bar -->` block (lines 604–642). Replace with:

```html
<!-- Filter bar -->
<div style="display:flex;align-items:center;gap:8px;flex-wrap:nowrap;margin-bottom:10px;padding:8px 12px;background:#0d1117;border:1px solid #21262d;border-radius:2px">
  <input id="src-search" placeholder="Search publications, domains..."
    oninput="applySourceFilters()"
    style="background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 10px;border-radius:4px;width:220px;outline:none;flex-shrink:0"
    onfocus="this.style.borderColor='#388bfd'" onblur="this.style.borderColor='#30363d'" />
  <div style="width:1px;height:16px;background:#30363d;flex-shrink:0"></div>
  <select id="src-filter-region" onchange="applySourceFilters()" style="background:#161b22;border:1px solid #21262d;color:#8b949e;font-size:10px;padding:3px 6px;border-radius:2px">
    <option value="">All regions</option>
    <option value="APAC">APAC</option>
    <option value="AME">AME</option>
    <option value="MED">MED</option>
    <option value="NCE">NCE</option>
    <option value="LATAM">LATAM</option>
  </select>
  <select id="src-filter-type" onchange="applySourceFilters()" style="background:#161b22;border:1px solid #21262d;color:#8b949e;font-size:10px;padding:3px 6px;border-radius:2px">
    <option value="">All types</option>
    <option value="news">news</option>
    <option value="government">government</option>
    <option value="intelligence">intelligence</option>
    <option value="academic">academic</option>
    <option value="industry">industry</option>
    <option value="social">social</option>
    <option value="youtube">youtube</option>
  </select>
  <select id="src-filter-tier" onchange="applySourceFilters()" style="background:#161b22;border:1px solid #21262d;color:#8b949e;font-size:10px;padding:3px 6px;border-radius:2px">
    <option value="">All tiers</option>
    <option value="A">A</option>
    <option value="B">B</option>
    <option value="C">C</option>
  </select>
  <select id="src-filter-collection" onchange="applySourceFilters()" style="background:#161b22;border:1px solid #21262d;color:#8b949e;font-size:10px;padding:3px 6px;border-radius:2px">
    <option value="">All collections</option>
    <option value="osint">OSINT</option>
    <option value="benchmark">Benchmark</option>
  </select>
  <label style="display:inline-flex;align-items:center;gap:4px;font-size:10px;color:#8b949e;cursor:pointer;white-space:nowrap">
    <input type="checkbox" id="src-filter-cited" onchange="applySourceFilters()" style="accent-color:#3fb950"> Cited
  </label>
  <label style="display:inline-flex;align-items:center;gap:4px;font-size:10px;color:#8b949e;cursor:pointer;white-space:nowrap">
    <input type="checkbox" id="src-filter-hidejunk" onchange="applySourceFilters()" checked style="accent-color:#3fb950"> Hide junk
  </label>
  <span id="src-stats-line" style="font-size:9px;color:#484f58;margin-left:auto;white-space:nowrap"></span>
</div>
```

- [ ] **Step 2: Add bulk action bar placeholder (hidden)**

Immediately after the filter bar div and before `<!-- Table -->`, add:

```html
<!-- Bulk action bar — shown when checkboxes selected -->
<div id="src-bulk-bar" style="display:none;align-items:center;gap:8px;padding:6px 12px;margin-bottom:6px;background:#161b22;border-left:2px solid #e3b341;border-radius:2px"></div>
```

- [ ] **Step 3: Replace column headers**

Find and replace the `<!-- Column headers -->` div (lines 647–655):

```html
<!-- Column headers -->
<div style="display:flex;padding:5px 12px;border-bottom:1px solid #21262d;font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#484f58;background:#080c10">
  <span style="width:24px;flex-shrink:0">
    <input type="checkbox" id="src-select-all" onchange="selectAllSources(this.checked)" style="cursor:pointer" />
  </span>
  <span style="flex:2;min-width:180px">Publication</span>
  <span style="width:100px;flex-shrink:0">Type</span>
  <span style="width:55px;flex-shrink:0">Tier</span>
  <span style="width:150px;flex-shrink:0">Usage</span>
  <span style="width:80px;flex-shrink:0">Last Seen</span>
  <span style="width:90px;flex-shrink:0">Actions</span>
</div>
```

- [ ] **Step 4: Open browser, navigate to Source Audit tab**

Verify: filter bar shows search input on the left, bulk bar is hidden, column headers show Usage instead of Appearances/Cited.

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): source audit filter bar — search input, bulk bar placeholder, revised columns"
```

---

## Task 3 — JS: Pure helper functions

**Files:**
- Modify: `static/app.js` (add helpers in the Sources section, near line 2130 after `_collectionBadge`)

- [ ] **Step 1: Add `applySourceSearch` helper**

After `_collectionBadge` function (~line 2143), add:

```javascript
function applySourceSearch(query, sources) {
  if (!query) return sources;
  const q = query.toLowerCase();
  return sources.filter(s =>
    (s.name   || '').toLowerCase().includes(q) ||
    (s.domain || '').toLowerCase().includes(q) ||
    (s.url    || '').toLowerCase().includes(q)
  );
}
```

- [ ] **Step 2: Add `_freshnessStyle` helper**

```javascript
function _freshnessStyle(dateStr) {
  if (!dateStr) return 'color:#484f58';
  const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  if (days <= 14) return 'color:#3fb950';
  if (days <= 42) return 'color:#e3b341';
  return 'color:#f85149;font-weight:600';
}
```

- [ ] **Step 3: Add `_usageBar` helper**

```javascript
function _usageBar(totalApp, totalCite) {
  if (!totalApp) return '<span style="color:#484f58;font-size:10px">—</span>';
  const pct = Math.round((totalCite / totalApp) * 100);
  const color = pct > 60 ? '#3fb950' : pct >= 20 ? '#e3b341' : '#6e7681';
  return `<span style="display:flex;align-items:center;gap:5px">
    <span style="color:#8b949e;min-width:22px;font-size:10px">${totalApp}</span>
    <span style="display:inline-block;width:55px;height:4px;background:#21262d;border-radius:2px;flex-shrink:0">
      <span style="display:block;width:${Math.min(pct,100)}%;height:4px;background:${color};border-radius:2px"></span>
    </span>
    <span style="color:${color};min-width:30px;font-size:10px">${pct}%</span>
  </span>`;
}
```

- [ ] **Step 4: Add `copyUrl` helper**

```javascript
function copyUrl(url, btnEl) {
  navigator.clipboard.writeText(url).then(() => {
    const orig = btnEl.textContent;
    btnEl.textContent = '✓';
    setTimeout(() => { btnEl.textContent = orig; }, 1000);
  });
}
```

- [ ] **Step 5: Add `_childRow` helper**

```javascript
function _childRow(s) {
  const domain = s.domain || '';
  const faviconHtml = domain
    ? `<img src="https://www.google.com/s2/favicons?domain=${esc(domain)}&sz=16" width="12" height="12"
         style="border-radius:2px;opacity:0.55;flex-shrink:0" onerror="this.style.display='none'" />`
    : '';
  const linkHtml = s.url
    ? `<a href="${esc(s.url)}" target="_blank" title="${esc(s.url)}"
         style="color:#79c0ff;text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:280px">${esc(s.domain || s.url)}</a>
       <span onclick="window.open('${esc(s.url)}','_blank')"
         style="border:1px solid #21262d;border-radius:2px;padding:0 4px;font-size:9px;line-height:16px;cursor:pointer;color:#484f58;flex-shrink:0">↗</span>
       <span onclick="copyUrl('${esc(s.url)}', this)"
         style="border:1px solid #21262d;border-radius:2px;padding:0 4px;font-size:9px;line-height:16px;cursor:pointer;color:#484f58;flex-shrink:0">copy</span>`
    : `<span style="color:#484f58;font-size:10px">${esc(domain || '—')}</span>`;

  const isChecked = state.selectedSourceIds.has(s.id);
  const flagLabel = s.junk ? 'Unflag' : 'Flag junk';
  const flagStyle = s.junk
    ? 'font-size:9px;color:#f85149;background:#1a0a0a;border:1px solid #da3633;padding:2px 6px;border-radius:2px;cursor:pointer'
    : 'font-size:9px;color:#6e7681;background:transparent;border:1px solid #30363d;padding:2px 6px;border-radius:2px;cursor:pointer';

  return `<div style="display:flex;align-items:center;padding:5px 12px 5px 36px;border-bottom:1px solid #0d1117;font-size:11px;background:#080c10">
    <span style="width:24px;flex-shrink:0">
      <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleSourceCheck(['${esc(s.id)}'], this.checked)" style="cursor:pointer" />
    </span>
    <span style="flex:2;min-width:180px;display:flex;align-items:center;gap:6px;overflow:hidden">
      ${faviconHtml}${linkHtml}
    </span>
    <span style="width:100px;flex-shrink:0"></span>
    <span style="width:55px;flex-shrink:0">
      <span onclick="showTierDropdown(this, ['${esc(s.id)}'])" style="display:inline-flex;align-items:center;gap:2px;cursor:pointer">
        ${_tierBadge(s.credibility_tier)}<span style="font-size:8px;color:#484f58">▾</span>
      </span>
    </span>
    <span style="width:150px;flex-shrink:0">${_usageBar(s.appearance_count ?? 0, s.cited_count ?? 0)}</span>
    <span style="width:80px;flex-shrink:0;font-size:10px;${_freshnessStyle(s.last_seen)}">${s.last_seen ? s.last_seen.slice(0,10) : '—'}</span>
    <span style="width:90px;flex-shrink:0">
      <button onclick="flagSource('${esc(s.id)}', ${!s.junk})" style="${flagStyle}">${flagLabel}</button>
      ${s.junk ? '<span style="color:#6e7681;font-size:9px;margin-left:4px">blocked</span>' : ''}
    </span>
  </div>`;
}
```

- [ ] **Step 6: Verify no console errors**

Open browser console on Source Audit tab. Confirm no `ReferenceError` for the new functions.

- [ ] **Step 7: Commit**

```bash
git add static/app.js
git commit -m "feat(sources): add pure JS helpers — search, freshness, usageBar, copyUrl, childRow"
```

---

## Task 4 — JS: Checkbox state + bulk operations

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add `selectedSourceIds` to state object**

Find the `const state = {` initializer near the top of app.js. Add `selectedSourceIds: new Set(),` to it:

```javascript
// Find the existing state object and add this line:
selectedSourceIds: new Set(),
```

Also add a module-level variable just before the Sources section (~line 2087):

```javascript
let _visibleSourceIds = []; // populated by renderSourceRegistryTable
```

- [ ] **Step 2: Add `_renderBulkBar`**

```javascript
function _renderBulkBar() {
  const bar = $('src-bulk-bar');
  if (!bar) return;
  const n = state.selectedSourceIds.size;
  if (n === 0) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  bar.innerHTML = `
    <span style="font-size:10px;color:#e3b341;font-weight:600">${n} selected</span>
    <button onclick="bulkFlagSelected()"
      style="font-size:10px;color:#f85149;background:#1a0a0a;border:1px solid #da3633;padding:2px 10px;border-radius:3px;cursor:pointer;margin-left:8px">Flag as junk</button>
    <button onclick="clearSourceSelection()"
      style="font-size:10px;color:#6e7681;background:transparent;border:1px solid #30363d;padding:2px 8px;border-radius:3px;cursor:pointer;margin-left:6px">Clear</button>`;
}
```

- [ ] **Step 3: Add `toggleSourceCheck`, `selectAllSources`, `bulkFlagSelected`, `clearSourceSelection`**

```javascript
function toggleSourceCheck(ids, checked) {
  for (const id of ids) {
    if (checked) state.selectedSourceIds.add(id);
    else state.selectedSourceIds.delete(id);
  }
  _renderBulkBar();
  // sync select-all checkbox state
  const selectAll = $('src-select-all');
  if (selectAll) selectAll.checked = _visibleSourceIds.length > 0 &&
    _visibleSourceIds.every(id => state.selectedSourceIds.has(id));
}

function selectAllSources(checked) {
  for (const id of _visibleSourceIds) {
    if (checked) state.selectedSourceIds.add(id);
    else state.selectedSourceIds.delete(id);
  }
  renderSources();
}

async function bulkFlagSelected() {
  const ids = [...state.selectedSourceIds];
  if (!ids.length) return;
  await Promise.all(ids.map(id =>
    fetch(`/api/sources/${encodeURIComponent(id)}/flag`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ junk: true }),
    })
  ));
  state.selectedSourceIds.clear();
  renderSources();
}

function clearSourceSelection() {
  state.selectedSourceIds.clear();
  renderSources();
}
```

- [ ] **Step 4: Verify bulk bar in browser**

1. Open Source Audit tab
2. Check a parent row checkbox — bulk bar should appear with "1 selected"
3. Click Clear — bulk bar should disappear
4. Check select-all header checkbox — all visible rows should check, bulk bar shows count

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(sources): checkbox state, bulk flag, select-all"
```

---

## Task 5 — JS: Tier override dropdown

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add `showTierDropdown` and `overrideTier`**

```javascript
function showTierDropdown(badgeEl, ids) {
  // Remove any open dropdown
  document.getElementById('src-tier-dropdown')?.remove();

  const rect = badgeEl.getBoundingClientRect();
  const dropdown = document.createElement('div');
  dropdown.id = 'src-tier-dropdown';
  dropdown.style.cssText = `position:fixed;top:${rect.bottom + 2}px;left:${rect.left}px;
    background:#161b22;border:1px solid #388bfd;border-radius:4px;z-index:100;min-width:48px;overflow:hidden`;

  const tiers = [
    { tier: 'A', color: '#3fb950' },
    { tier: 'B', color: '#e3b341' },
    { tier: 'C', color: '#6e7681' },
  ];
  dropdown.innerHTML = tiers.map(({ tier, color }) =>
    `<div onclick="overrideTier(${JSON.stringify(ids)}, '${tier}')"
       style="padding:4px 12px;font-size:10px;color:${color};cursor:pointer;font-family:'IBM Plex Mono',monospace"
       onmouseover="this.style.background='#21262d'" onmouseout="this.style.background=''">${tier}</div>`
  ).join('');

  document.body.appendChild(dropdown);

  // Close on outside click (defer so this click doesn't immediately close it)
  setTimeout(() => {
    document.addEventListener('click', function _handler(e) {
      if (!dropdown.contains(e.target)) {
        dropdown.remove();
        document.removeEventListener('click', _handler);
      }
    });
  }, 0);
}

async function overrideTier(ids, tier) {
  document.getElementById('src-tier-dropdown')?.remove();
  await Promise.all(ids.map(id =>
    fetch(`/api/sources/${encodeURIComponent(id)}/tier`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier }),
    })
  ));
  renderSources();
}
```

- [ ] **Step 2: Verify dropdown in browser**

1. Open Source Audit tab
2. Click a tier badge (A▾, B▾, C▾) — dropdown should appear with A/B/C options
3. Click outside — dropdown should close
4. Click a tier option — badge should update to new tier, sources re-render

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(sources): tier override dropdown — click badge to change A/B/C"
```

---

## Task 6 — JS: Rewrite `renderSourceRegistryTable`

**Files:**
- Modify: `static/app.js` (replace `renderSourceRegistryTable`, lines 2154–2219)

- [ ] **Step 1: Replace `renderSourceRegistryTable` entirely**

Find the existing `function renderSourceRegistryTable(sources) {` and replace the entire function:

```javascript
function renderSourceRegistryTable(sources) {
  const body = $('src-table-body');
  if (!body) return;

  // Client-side keyword post-filter
  const query = ($('src-search')?.value || '').trim();
  const filtered = applySourceSearch(query, sources);

  if (!filtered.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No sources found.</div>';
    _visibleSourceIds = [];
    _renderBulkBar();
    return;
  }

  // Track all visible IDs for select-all
  _visibleSourceIds = filtered.map(s => s.id);

  // Group by publication name
  const groups = {};
  const order  = [];
  for (const s of filtered) {
    const key = (s.name || s.domain || '—').trim();
    if (!groups[key]) { groups[key] = []; order.push(key); }
    groups[key].push(s);
  }

  const html = order.map((name, idx) => {
    const members   = groups[name];
    const gid       = idx;
    const rep       = members[0];
    const totalApp  = members.reduce((a, s) => a + (s.appearance_count ?? 0), 0);
    const totalCite = members.reduce((a, s) => a + (s.cited_count ?? 0), 0);
    const lastSeen  = members.map(s => s.last_seen || '').sort().at(-1) || null;
    const count     = members.length;
    const allIds    = members.map(s => s.id);
    const isBenchmark = (rep.collection_type || 'osint') === 'benchmark';
    const allChecked  = allIds.every(id => state.selectedSourceIds.has(id));

    const faviconHtml = rep.domain
      ? `<img src="https://www.google.com/s2/favicons?domain=${esc(rep.domain)}&sz=16" width="13" height="13"
           style="border-radius:2px;opacity:0.6;flex-shrink:0;margin-right:4px" onerror="this.style.display='none'" />`
      : '';

    const parent = `
<div style="display:flex;align-items:center;padding:8px 12px;border-bottom:1px solid #161b22;font-size:11px;background:#0d1117"
     onmouseover="this.style.background='#0d1421'" onmouseout="this.style.background='#0d1117'">
  <span style="width:24px;flex-shrink:0">
    <input type="checkbox" ${allChecked ? 'checked' : ''}
      onchange="toggleSourceCheck(${JSON.stringify(allIds)}, this.checked)" style="cursor:pointer" />
  </span>
  <span style="flex:2;min-width:180px;display:flex;align-items:center;overflow:hidden;cursor:pointer"
        onclick="toggleSourceGroup(${gid})">
    ${faviconHtml}
    <span style="color:#e6edf3;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(name)}</span>
    <span style="color:#484f58;font-size:9px;margin-left:6px;white-space:nowrap">${count} URL${count !== 1 ? 's' : ''}</span>
    ${isBenchmark ? `<span style="font-size:9px;background:#5a3e0a;color:#e3b341;border:1px solid #7d6022;border-radius:3px;padding:0 4px;margin-left:5px;flex-shrink:0">Benchmark</span>` : ''}
    <span id="src-arrow-${gid}" style="color:#484f58;font-size:9px;margin-left:5px;flex-shrink:0">▶</span>
  </span>
  <span style="width:100px;flex-shrink:0">${_typeBadge(rep.source_type)} ${_collectionBadge(rep.collection_type)}</span>
  <span style="width:55px;flex-shrink:0">
    <span onclick="showTierDropdown(this, ${JSON.stringify(allIds)})"
          style="display:inline-flex;align-items:center;gap:2px;cursor:pointer">
      ${_tierBadge(rep.credibility_tier)}<span style="font-size:8px;color:#484f58">▾</span>
    </span>
  </span>
  <span style="width:150px;flex-shrink:0">
    ${isBenchmark
      ? `<span style="color:#484f58;font-size:10px;font-style:italic">— benchmark anchor</span>`
      : _usageBar(totalApp, totalCite)}
  </span>
  <span style="width:80px;flex-shrink:0;font-size:10px;${_freshnessStyle(lastSeen)}">
    ${lastSeen ? lastSeen.slice(0, 10) : '—'}
  </span>
  <span style="width:90px;flex-shrink:0"></span>
</div>
<div id="src-group-${gid}" style="display:none">
  ${members.map(s => _childRow(s)).join('')}
</div>`;

    return parent;
  }).join('');

  body.innerHTML = html;
  _renderBulkBar();
}
```

- [ ] **Step 2: Verify full table renders**

Open Source Audit tab. Confirm:
- Each row has a checkbox on the left
- Tier badge shows `▾`
- Usage column shows count + bar + percentage (or `— benchmark anchor` for Verizon DBIR etc.)
- Last seen dates are coloured green/amber/red
- Expand a row — child rows show favicon + blue link + ↗ + copy pills

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(sources): rewrite renderSourceRegistryTable — usage col, freshness, checkboxes, tier, favicons"
```

---

## Task 7 — JS: Wire search into `renderSources`

**Files:**
- Modify: `static/app.js` (`renderSources` function, ~line 2087)

- [ ] **Step 1: Read `src-search` value in `renderSources`**

The search input has `oninput="applySourceFilters()"` which already calls `renderSources()` (via `applySourceFilters`). The search filtering now happens inside `renderSourceRegistryTable` via `applySourceSearch`. No additional change to `renderSources` is needed.

Verify this is wired correctly: `applySourceFilters` → `renderSources` → fetches from server → passes array to `renderSourceRegistryTable` → `applySourceSearch` filters it client-side.

- [ ] **Step 2: Smoke test end-to-end**

1. Open Source Audit tab — table renders with all sources
2. Type "future" in search box — only "Recorded Future" rows remain
3. Clear search — all rows return
4. Change region filter to APAC — server re-fetches, then search re-filters client-side
5. Expand a row — check favicon loads, blue link truncates long URLs with ellipsis, copy button shows ✓ for 1s on click
6. Click a tier badge — dropdown opens; click A/B/C — badge updates
7. Check a parent row — bulk bar appears. Click "Flag as junk" — sources flagged, bar clears
8. Check header select-all — all rows check; uncheck — all rows uncheck

- [ ] **Step 3: Final commit**

```bash
git add static/app.js static/index.html server.py
git commit -m "feat(sources): source audit tab redesign complete — search, usage col, freshness, tier override, bulk flag"
```

---

## Self-Review Against Spec

| Spec requirement | Covered in |
|---|---|
| Keyword search — client-side post-filter, no re-fetch | Task 3 (`applySourceSearch`) + Task 7 |
| Search in filter bar, left-anchored, blue focus | Task 2 |
| Merged Usage column — count + bar + % | Task 3 (`_usageBar`) + Task 6 |
| Parent row usage = aggregate sum(cited)/sum(appeared) | Task 6 (`totalApp`, `totalCite`) |
| Bar colour thresholds 60%/20% | Task 3 (`_usageBar`) |
| Freshness colour — 14/42 day thresholds | Task 3 (`_freshnessStyle`) |
| Null last_seen → grey dash | Task 3 (`_freshnessStyle`) |
| Tier override — click badge → dropdown | Task 5 |
| Parent tier change → all child IDs | Task 5 (`overrideTier` receives `allIds`) |
| Dropdown closes on outside click | Task 5 |
| New `POST /api/sources/{id}/tier` endpoint | Task 1 |
| Prominent links — blue, truncated, title tooltip | Task 3 (`_childRow`) |
| Favicon — with onerror fallback | Task 3 (`_childRow`) + Task 6 |
| ↗ pill button — open in new tab | Task 3 (`_childRow`) |
| copy pill — clipboard + 1s ✓ feedback | Task 3 (`copyUrl`, `_childRow`) |
| Checkboxes — 24px column | Task 2 + Task 6 |
| Select-all in header | Task 2 + Task 4 |
| `state.selectedSourceIds = new Set()` | Task 4 |
| Bulk action bar — conditional, amber border | Task 4 (`_renderBulkBar`) |
| Bulk flag — `Promise.all`, not sequential | Task 4 (`bulkFlagSelected`) |
| No "Flag all" button on parent rows | Task 6 (parent row has no flag button) |
| `index.html` search input added to HTML | Task 2 |
| Column layout matches spec table | Task 2 + Task 6 |
