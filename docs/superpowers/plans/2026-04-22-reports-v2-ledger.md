# Reports V2 ledger — implementation plan

**Goal:** Replace the v1 Reports card grid with a dense ledger table driven by the existing `/api/briefs/` contract. Add the small set of `app.css` primitives the ledger needs.

**Architecture:** Pure client-side rework. New JS renderer in `static/app.js` builds a single table from the `/api/briefs/` response, with status pills derived client-side, per-row actions, version menu with edge-flip, thumbnail-on-hover popover, and a toast stack for regenerate errors. `app.css` gets new primitives (status pills, dense ledger table, popover, toast). No backend changes. `tokens.css` untouched.

**Tech Stack:** Python 3 / FastAPI (unchanged, backend untouched) · vanilla JS (no framework) · safe-DOM only (no `innerHTML`, per v1 policy) · CSS custom properties on `app.css` · Playwright for UI testing.

**Spec reference:** `docs/superpowers/specs/2026-04-22-reports-v2-ledger.md`.

---

## File Structure

**Files modified:**

- `static/design/styles/app.css` — add status tokens + status-pill / ledger / popover / toast / row-actions primitives.
- `static/app.js` — replace `renderReports*` family with ledger renderer; add status/freshness utilities, version menu, thumbnail popover, toast stack, error-wired regenerate.
- `static/index.html` — remove v1 `.rpt-*` CSS from the inline `<style>` block.

**Files created:**

- `docs/design/handoff/app-css-audit.md` — shared audit artifact. Reports V2 section at top.
- `tests/ui/test_reports_ledger.py` — Playwright tests for the new ledger (adjust path to match existing Playwright test location if different).

**Files untouched:** `server.py`, `tokens.css`, all brief PDF CSS, every other tab's code.

---

## Task 1: Create audit artifact with Reports V2 section

**Files:**
- Create: `docs/design/handoff/app-css-audit.md`

- [ ] **Step 1: Inventory existing primitives in app.css relevant to Reports V2**

Read `static/design/styles/app.css` and note: `.btn`, `.btn--ghost`, `.pill`, `.pill--critical/high/medium/monitor`, `.table`, `.card`, `.modal`. Note any existing popover / tooltip / toast primitive (likely none).

- [ ] **Step 2: Create the audit file**

```markdown
# App CSS audit

**Shared audit artifact for:**
- Reports V2 ledger spec (below)
- App CSS migration sweep spec (lower — to be filled by migration plan)

---

## Reports V2 — primitive coverage

### Already in app.css (reused by the ledger unchanged)
| Primitive | Location | Notes |
|---|---|---|
| `.btn`, `.btn--ghost` | app.css:298+ | Row-action strip buttons |
| `.pill` | tokens.css:146 | Base pill structure |
| `.table` | app.css:441+ | Base table structure |

### Additions required by Reports V2
| Primitive | Type | Reason |
|---|---|---|
| `--status-ready`, `--status-stale`, `--status-error` | Token | Status dot colors, distinct from severity palette |
| `.pill--status-ready`, `.pill--status-stale`, `.pill--status-empty`, `.pill--status-error` | Primitive | Status pill variants with leading dot |
| `.table--ledger` | Modifier | Tighter row padding (--s-3), sticky thead, grouped tbody |
| `.popover` | Primitive | Thumbnail hover on audience cell |
| `.toast`, `.toast-stack` | Primitive | Regenerate error surface |
| `.row-actions` | Primitive | Right-aligned action strip with gap |

### Reused unchanged vs changed
No existing primitives are modified. All additions only.

---

## App CSS migration sweep — to be filled
(See `docs/superpowers/plans/2026-04-22-app-css-migration-sweep.md` when that work runs.)
```

- [ ] **Step 3: Commit**

```bash
git add docs/design/handoff/app-css-audit.md
git commit -m "docs(audit): seed app-css audit with Reports V2 section"
```

---

## Task 2: Add status tokens + status-pill primitives to app.css

**Files:**
- Modify: `static/design/styles/app.css`

- [ ] **Step 1: Add status tokens to the dark-surface block**

Locate the existing dark-surface `:root` block in `app.css` (around line 20). Add after the severity-tint lines:

```css
  /* Status tokens (content freshness — deliberately separate from severity) */
  --status-ready:     #2BB673;   /* soft green-teal, content is current */
  --status-stale:     #D4A017;   /* muted amber, distinct from --sev-medium */
  --status-error:     #D1242F;   /* transient error flash; reuses sev-critical hue */
```

- [ ] **Step 2: Append status-pill primitives to the end of app.css**

```css
/* ---------- Status pills (Reports V2 ledger) ---------- */

.pill--status-ready,
.pill--status-stale,
.pill--status-empty,
.pill--status-error {
  display: inline-flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-2) var(--s-5);
  border-radius: var(--r-md);
  font-size: var(--fs-label);
  font-weight: var(--w-medium);
  letter-spacing: var(--tr-label);
  text-transform: uppercase;
  background: var(--surface-2);
  color: var(--text-secondary);
}

.pill--status-ready::before,
.pill--status-stale::before,
.pill--status-error::before {
  content: "";
  width: 8px; height: 8px;
  border-radius: 50%;
}

.pill--status-ready::before  { background: var(--status-ready); }
.pill--status-stale::before  { background: var(--status-stale); }
.pill--status-error::before  { background: var(--status-error); }

.pill--status-empty {
  color: var(--text-tertiary);
  background: transparent;
  border: 1px solid var(--border-hairline);
}
```

- [ ] **Step 3: Reload the app in the browser and visually verify**

Reload `/#reports`. CSS file should parse without errors (check DevTools console). The pill classes aren't consumed yet — this step only verifies parse.

- [ ] **Step 4: Commit**

```bash
git add static/design/styles/app.css
git commit -m "style(app): add status tokens and status-pill primitives"
```

---

## Task 3: Add `.table--ledger` modifier to app.css

**Files:**
- Modify: `static/design/styles/app.css`

- [ ] **Step 1: Append ledger-table primitive after the status pills**

```css
/* ---------- Ledger table (Reports V2) ---------- */

.table--ledger {
  font-size: var(--fs-body);
  border-collapse: collapse;
  width: 100%;
}

.table--ledger thead {
  position: sticky; top: 0;
  background: var(--surface-1);
  z-index: 1;
}

.table--ledger thead th {
  text-align: left;
  padding: var(--s-4) var(--s-5);
  font-size: var(--fs-label);
  font-weight: var(--w-semibold);
  letter-spacing: var(--tr-label);
  text-transform: uppercase;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-subtle);
}

.table--ledger tbody td {
  padding: var(--s-3) var(--s-5);
  border-bottom: 1px solid var(--border-hairline);
  vertical-align: middle;
}

.table--ledger tbody tr:hover td { background: var(--surface-2); }

.table--ledger .ledger-group-head td {
  padding: var(--s-5) var(--s-5) var(--s-3);
  font-size: var(--fs-label);
  font-weight: var(--w-semibold);
  letter-spacing: var(--tr-label);
  text-transform: uppercase;
  color: var(--text-tertiary);
  background: transparent;
  border-bottom: 0;
}

.table--ledger .ledger-group-head:hover td { background: transparent; }
```

- [ ] **Step 2: Reload, visually verify CSS parses**

- [ ] **Step 3: Commit**

```bash
git add static/design/styles/app.css
git commit -m "style(app): add .table--ledger modifier for dense grouped tables"
```

---

## Task 4: Add `.popover` primitive to app.css

**Files:**
- Modify: `static/design/styles/app.css`

- [ ] **Step 1: Append popover primitive**

```css
/* ---------- Popover (hover previews) ---------- */

.popover {
  position: absolute;
  z-index: 30;
  background: var(--surface-2);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-overlay);
  padding: var(--s-4);
  max-width: 260px;
  pointer-events: none;
}

.popover[data-side="left"]  { transform: translateX(-100%); }
.popover[data-side="right"] { transform: translateX(0); }

.popover__thumb {
  width: 240px; height: 320px;
  background: var(--surface-inset);
  border: 1px solid var(--border-hairline);
  border-radius: var(--r-sm);
  object-fit: contain;
}
```

- [ ] **Step 2: Reload, visually verify CSS parses**

- [ ] **Step 3: Commit**

```bash
git add static/design/styles/app.css
git commit -m "style(app): add .popover primitive with side-flip support"
```

---

## Task 5: Add `.toast` + `.toast-stack` primitives to app.css

**Files:**
- Modify: `static/design/styles/app.css`

- [ ] **Step 1: Append toast primitives**

```css
/* ---------- Toast (transient notifications) ---------- */

.toast-stack {
  position: fixed;
  top: calc(var(--h-header) + var(--s-4));
  right: var(--s-5);
  display: flex; flex-direction: column; gap: var(--s-3);
  z-index: 40;
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  min-width: 280px;
  max-width: 420px;
  padding: var(--s-4) var(--s-5);
  background: var(--surface-2);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--text-secondary);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-overlay);
  color: var(--text-secondary);
  font-size: var(--fs-body);
  display: flex; align-items: flex-start; gap: var(--s-4);
}

.toast--error { border-left-color: var(--status-error); }

.toast__close {
  background: transparent; border: 0; color: var(--text-tertiary);
  cursor: pointer; padding: 0 var(--s-2); font-size: 16px;
}

.toast__close:hover { color: var(--text-primary); }
```

- [ ] **Step 2: Reload, visually verify CSS parses**

- [ ] **Step 3: Commit**

```bash
git add static/design/styles/app.css
git commit -m "style(app): add .toast and .toast-stack primitives"
```

---

## Task 6: Add `.row-actions` primitive to app.css

**Files:**
- Modify: `static/design/styles/app.css`

- [ ] **Step 1: Append row-actions primitive**

```css
/* ---------- Row actions (table action strip) ---------- */

.row-actions {
  display: inline-flex; gap: var(--s-3);
  justify-content: flex-end; align-items: center;
  white-space: nowrap;
}

.row-actions .btn { padding: var(--s-2) var(--s-4); font-size: var(--fs-small); }

.row-actions__menu-trigger {
  background: transparent; border: 0;
  color: var(--text-tertiary); cursor: pointer;
  padding: var(--s-2);
}

.row-actions__menu-trigger:hover { color: var(--text-primary); }
```

- [ ] **Step 2: Reload, visually verify CSS parses**

- [ ] **Step 3: Commit**

```bash
git add static/design/styles/app.css
git commit -m "style(app): add .row-actions primitive for table action strips"
```

---

## Task 7: Implement `computeRowStatus` + `formatFreshness` JS utilities

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Locate the Reports rendering section of app.js**

Search for `renderReports` or similar. Identify a suitable location near the existing ledger-related code (use the section added in v1 as reference).

- [ ] **Step 2: Add utility functions before the renderers**

```javascript
function computeRowStatus(audience) {
  if (!audience.latest_meta) return "empty";
  if (audience.latest_meta.pipeline_run_id !== audience.current_run_id) return "stale";
  return "ready";
}

function formatFreshness(latestMeta) {
  if (!latestMeta || !latestMeta.created_at) return "—";
  const ts = new Date(latestMeta.created_at);
  const now = new Date();
  const diffMs = now - ts;
  const diffH = diffMs / 3600000;
  const timeStr = ts.toISOString().slice(11, 16) + " UTC";
  const dateStr = ts.toISOString().slice(0, 10);
  if (diffH < 24) return `Today ${ts.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`;
  if (diffH < 48) return `Yesterday ${timeStr}`;
  const days = Math.floor(diffH / 24);
  return `${days}d ago · ${dateStr} ${timeStr}`;
}
```

- [ ] **Step 3: Load the page, open DevTools, manually call the utilities to verify**

In the browser console:
```javascript
computeRowStatus({ latest_meta: null, current_run_id: "r1" })  // "empty"
computeRowStatus({ latest_meta: { pipeline_run_id: "r1" }, current_run_id: "r1" })  // "ready"
computeRowStatus({ latest_meta: { pipeline_run_id: "r0" }, current_run_id: "r1" })  // "stale"
formatFreshness({ created_at: new Date().toISOString() })  // "Today HH:MM"
```

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(reports-ledger): add computeRowStatus and formatFreshness utilities"
```

---

## Task 8: Implement `renderLedgerRow` + `renderReportsLedger`

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add ledger row builder**

```javascript
function renderLedgerRow(audience) {
  const tr = document.createElement("tr");
  tr.dataset.audienceId = audience.id;

  const status = computeRowStatus(audience);

  // Column 1 — audience (with hover popover attach in later task)
  const td1 = document.createElement("td");
  td1.textContent = audience.title;
  td1.className = "ledger-audience";
  tr.appendChild(td1);

  // Column 2 — status pill
  const td2 = document.createElement("td");
  const pill = document.createElement("span");
  pill.className = `pill pill--status-${status}`;
  pill.textContent = status.charAt(0).toUpperCase() + status.slice(1);
  td2.appendChild(pill);
  tr.appendChild(td2);

  // Column 3 — freshness
  const td3 = document.createElement("td");
  td3.textContent = formatFreshness(audience.latest_meta);
  tr.appendChild(td3);

  // Column 4 — actions
  const td4 = document.createElement("td");
  td4.appendChild(renderRowActions(audience, status));
  tr.appendChild(td4);

  return tr;
}

function renderRowActions(audience, status) {
  const wrap = document.createElement("div");
  wrap.className = "row-actions";

  if (status !== "empty") {
    wrap.appendChild(mkActionBtn("Preview", () => openPreview(audience)));
  }

  wrap.appendChild(mkActionBtn("Regenerate", (btn) => doRegenerate(audience, btn, false)));

  if (audience.canNarrate) {
    wrap.appendChild(mkActionBtn("Narrate", (btn) => doRegenerate(audience, btn, true)));
  }

  if (status !== "empty") {
    wrap.appendChild(mkActionBtn("Download", () => openDownload(audience)));
    const menu = document.createElement("button");
    menu.className = "row-actions__menu-trigger";
    menu.textContent = "▾"; // ▾
    menu.onclick = (e) => openVersionMenu(audience, menu, e);
    wrap.appendChild(menu);
  }

  return wrap;
}

function mkActionBtn(label, handler) {
  const b = document.createElement("button");
  b.className = "btn btn--ghost";
  b.textContent = label;
  b.onclick = () => handler(b);
  return b;
}

function openPreview(audience) {
  window.open(`/api/briefs/${audience.id}/pdf`, "_blank");
}

function openDownload(audience) {
  window.open(`/api/briefs/${audience.id}/pdf?download=1`, "_blank");
}

async function doRegenerate(audience, btn, narrate) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Regenerating…";
  try {
    const url = `/api/briefs/${audience.id}/regenerate${narrate ? "?narrate=1" : ""}`;
    const resp = await fetch(url, { method: "POST" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    await refreshReportsLedger();
  } catch (err) {
    showErrorToast(`Regenerate failed for ${audience.title}: ${err.message}`);
    flashErrorPill(audience.id);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

function flashErrorPill(audienceId) {
  const row = document.querySelector(`tr[data-audience-id="${audienceId}"]`);
  if (!row) return;
  const pill = row.querySelector(".pill");
  if (!pill) return;
  const prior = pill.className;
  pill.className = "pill pill--status-error";
  pill.textContent = "Error";
  setTimeout(() => { pill.className = prior; }, 3000);
}
```

- [ ] **Step 2: Add the full ledger renderer**

```javascript
const LEDGER_GROUPS = [
  { label: "Leadership",        predicate: (a) => a.id === "ciso" || a.id === "board" },
  { label: "RSM — Regional", predicate: (a) => a.id.startsWith("rsm-") },
];

async function renderReportsLedger(container) {
  const resp = await fetch("/api/briefs/");
  if (!resp.ok) {
    container.textContent = `Failed to load briefs: HTTP ${resp.status}`;
    return;
  }
  const data = await resp.json();
  const audiences = data.audiences || [];

  while (container.firstChild) container.removeChild(container.firstChild);

  const table = document.createElement("table");
  table.className = "table table--ledger";

  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  ["Audience", "Status", "Freshness", "Actions"].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  table.appendChild(thead);

  for (const group of LEDGER_GROUPS) {
    const rows = audiences.filter(group.predicate);
    if (rows.length === 0) continue;

    const tbody = document.createElement("tbody");
    const headTr = document.createElement("tr");
    headTr.className = "ledger-group-head";
    const headTd = document.createElement("td");
    headTd.colSpan = 4;
    headTd.textContent = group.label;
    headTr.appendChild(headTd);
    tbody.appendChild(headTr);

    rows.forEach((a) => tbody.appendChild(renderLedgerRow(a)));
    table.appendChild(tbody);
  }

  container.appendChild(table);
}

async function refreshReportsLedger() {
  const container = document.querySelector("#reports-tab-content") || document.querySelector("[data-tab='reports']");
  if (container) await renderReportsLedger(container);
}
```

Note: container selector may need adjustment to match how Reports tab content is attached in the current DOM. Check `renderReports` callsite from v1 for the exact parent node.

- [ ] **Step 3: Wire `renderReportsLedger` to the Reports tab activation**

Find the existing Reports-tab activation point (in v1 this called `renderReports`). Replace the call with `renderReportsLedger(container)`.

- [ ] **Step 4: Reload `/#reports`, visually verify all 7 rows render**

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(reports-ledger): render ledger table with per-row actions"
```

---

## Task 9: Implement `renderVersionMenu` with flip-up + outside-click close

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add version menu open / close / reposition logic**

```javascript
let _openVersionMenu = null;

async function openVersionMenu(audience, trigger, evt) {
  evt.stopPropagation();
  closeVersionMenu();

  const resp = await fetch(`/api/briefs/${audience.id}/versions`);
  if (!resp.ok) {
    showErrorToast(`Failed to load versions: HTTP ${resp.status}`);
    return;
  }
  const versions = (await resp.json()).versions || [];

  const menu = document.createElement("div");
  menu.className = "popover";
  menu.style.pointerEvents = "auto";
  menu.style.minWidth = "280px";

  if (versions.length === 0) {
    menu.textContent = "No prior versions.";
  } else {
    versions.forEach((v) => {
      const row = document.createElement("div");
      row.style.padding = "var(--s-3) var(--s-4)";
      row.style.cursor = "pointer";
      row.textContent = `${v.created_at}${v.narrator ? " · narrated" : ""}`;
      row.onclick = () => useVersion(audience, v);
      menu.appendChild(row);
    });
  }

  document.body.appendChild(menu);
  positionMenuRelative(menu, trigger);

  _openVersionMenu = menu;
  setTimeout(() => {
    document.addEventListener("click", closeOnOutside, { once: true });
    window.addEventListener("scroll", closeVersionMenu, { once: true, capture: true });
    document.addEventListener("keydown", closeOnEscape);
  }, 0);
}

function positionMenuRelative(menu, trigger) {
  const rect = trigger.getBoundingClientRect();
  const viewportH = window.innerHeight;
  const flipUp = rect.top > viewportH * 0.6;
  menu.style.left = `${rect.left + window.scrollX}px`;
  if (flipUp) {
    menu.style.top = `${rect.top + window.scrollY - 8}px`;
    menu.style.transform = "translateY(-100%)";
  } else {
    menu.style.top = `${rect.bottom + window.scrollY + 4}px`;
  }
}

function closeVersionMenu() {
  if (_openVersionMenu && _openVersionMenu.parentNode) {
    _openVersionMenu.parentNode.removeChild(_openVersionMenu);
  }
  _openVersionMenu = null;
  document.removeEventListener("keydown", closeOnEscape);
}

function closeOnOutside(e) {
  if (_openVersionMenu && !_openVersionMenu.contains(e.target)) {
    closeVersionMenu();
  }
}

function closeOnEscape(e) {
  if (e.key === "Escape") closeVersionMenu();
}

function useVersion(audience, version) {
  audience._activeVersion = version;  // row-scoped state
  closeVersionMenu();
  // re-render just the row
  const row = document.querySelector(`tr[data-audience-id="${audience.id}"]`);
  if (row) row.replaceWith(renderLedgerRow(audience));
}
```

- [ ] **Step 2: Reload, click the `▾` trigger on a ready row, verify menu opens**

Verify: menu appears below (or above, for bottom rows); clicking outside closes; pressing Escape closes; scrolling closes.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(reports-ledger): version menu with flip-up and outside-click close"
```

---

## Task 10: Implement `renderThumbnailPopover` (hover)

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add hover popover logic**

```javascript
let _hoverPopover = null;
let _hoverTimer = null;

function attachThumbnailHover(cell, audience) {
  cell.addEventListener("mouseenter", () => {
    if (_hoverTimer) clearTimeout(_hoverTimer);
    const status = computeRowStatus(audience);
    if (status === "empty") return;
    showThumbnailPopover(cell, audience);
  });
  cell.addEventListener("mouseleave", () => {
    _hoverTimer = setTimeout(closeThumbnailPopover, 150);
  });
}

function showThumbnailPopover(cell, audience) {
  closeThumbnailPopover();
  const pop = document.createElement("div");
  pop.className = "popover";

  const img = document.createElement("img");
  img.className = "popover__thumb";
  img.src = `/api/briefs/${audience.id}/thumbnail`;
  img.alt = `${audience.title} cover`;
  pop.appendChild(img);

  document.body.appendChild(pop);

  const rect = cell.getBoundingClientRect();
  const rightEdge = window.innerWidth - rect.right;
  const flipLeft = rightEdge < 280;
  if (flipLeft) {
    pop.dataset.side = "left";
    pop.style.left = `${rect.left + window.scrollX - 8}px`;
  } else {
    pop.dataset.side = "right";
    pop.style.left = `${rect.right + window.scrollX + 8}px`;
  }
  pop.style.top = `${rect.top + window.scrollY}px`;

  _hoverPopover = pop;
}

function closeThumbnailPopover() {
  if (_hoverPopover && _hoverPopover.parentNode) {
    _hoverPopover.parentNode.removeChild(_hoverPopover);
  }
  _hoverPopover = null;
}
```

- [ ] **Step 2: Wire the hover handler into `renderLedgerRow`**

In `renderLedgerRow`, after creating `td1`, add:

```javascript
attachThumbnailHover(td1, audience);
```

- [ ] **Step 3: Reload, hover a ready row's audience cell, verify popover shows with cover image**

Also verify: near right edge of viewport, popover flips to the left side.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(reports-ledger): thumbnail hover popover with edge-flip"
```

---

## Task 11: Implement `showErrorToast` + stack management

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add toast stack logic**

```javascript
let _toastStack = null;

function getToastStack() {
  if (_toastStack && _toastStack.parentNode) return _toastStack;
  _toastStack = document.createElement("div");
  _toastStack.className = "toast-stack";
  document.body.appendChild(_toastStack);
  return _toastStack;
}

function showErrorToast(message) {
  const stack = getToastStack();
  while (stack.children.length >= 3) stack.removeChild(stack.firstChild);

  const toast = document.createElement("div");
  toast.className = "toast toast--error";

  const body = document.createElement("div");
  body.style.flex = "1";
  body.textContent = message;
  toast.appendChild(body);

  const close = document.createElement("button");
  close.className = "toast__close";
  close.textContent = "×";
  let timer = setTimeout(() => dismiss(), 6000);

  const dismiss = () => {
    clearTimeout(timer);
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  };

  close.onclick = dismiss;
  toast.addEventListener("mouseenter", () => clearTimeout(timer));
  toast.addEventListener("mouseleave", () => { timer = setTimeout(dismiss, 6000); });

  toast.appendChild(close);
  stack.appendChild(toast);
}
```

- [ ] **Step 2: Verify wiring — `doRegenerate` already calls `showErrorToast` on failure (from Task 8)**

- [ ] **Step 3: Force an error to test**

In DevTools, temporarily override `fetch` for the regenerate endpoint:
```javascript
const origFetch = window.fetch;
window.fetch = (url, opts) => url.includes("/regenerate") ? Promise.resolve({ ok: false, status: 500 }) : origFetch(url, opts);
```
Click Regenerate — confirm toast appears, auto-dismisses after 6s, close button works. Restore with `window.fetch = origFetch`.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(reports-ledger): error toast stack for regenerate failures"
```

---

## Task 12: Delete v1 `renderReports*` family + v1 `.rpt-*` inline CSS

**Files:**
- Modify: `static/app.js`
- Modify: `static/index.html`

- [ ] **Step 1: Identify v1 functions in app.js**

Search app.js for function names starting `renderReports` that are NOT the new `renderReportsLedger`. Also search for v1 helper functions (thumbnail loader, version-menu builder from v1, audience-card builder). From the memory: v1 had no legacy rail-renderer family anymore (`renderReportsRail`, `renderAudienceContent`, `selectAudience`, `_hubGenerate`, 4 per-audience view renderers were already deleted before). So the v1 functions to delete are the card-grid specific ones introduced in the v1 redesign.

Delete all v1 rendering code that is not referenced by the new `renderReportsLedger` path.

- [ ] **Step 2: Identify v1 inline CSS in index.html**

Search the inline `<style>` block in `static/index.html` for `.rpt-` prefixes. Found at roughly lines 293-391 (per the memory — verify actual current location).

Delete all `.rpt-*` CSS rules.

- [ ] **Step 3: Reload `/#reports`, verify ledger renders identically (nothing visually broken)**

No `.rpt-*` class should be referenced by the new code.

- [ ] **Step 4: Commit**

```bash
git add static/app.js static/index.html
git commit -m "chore(reports): delete v1 card-grid code and inline CSS"
```

---

## Task 13: Playwright smoke test — row rendering + Regenerate

**Files:**
- Create: `tests/ui/test_reports_ledger.py` (verify existing Playwright test dir path; adjust if the repo uses `tests/playwright/` or similar)

- [ ] **Step 1: Write the failing test**

```python
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.playwright
def test_reports_ledger_renders_seven_rows(page: Page, live_server_url: str):
    page.goto(f"{live_server_url}/#reports")
    page.wait_for_selector(".table--ledger")
    rows = page.locator(".table--ledger tbody tr[data-audience-id]")
    expect(rows).to_have_count(7)


@pytest.mark.playwright
def test_reports_ledger_empty_row_has_empty_pill(page: Page, live_server_url: str):
    page.goto(f"{live_server_url}/#reports")
    page.wait_for_selector(".table--ledger")
    empty_pill = page.locator(".pill--status-empty").first
    expect(empty_pill).to_be_visible()


@pytest.mark.playwright
def test_reports_regenerate_sends_post(page: Page, live_server_url: str):
    page.goto(f"{live_server_url}/#reports")
    page.wait_for_selector(".table--ledger")
    with page.expect_request(lambda r: "/regenerate" in r.url and r.method == "POST"):
        page.locator("button", has_text="Regenerate").first.click()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/ui/test_reports_ledger.py -v
```

Expected: PASS if all earlier tasks are complete. If the server-fixture setup or Playwright config is not yet present in the repo, the test collects but errors — fix the fixture/config before proceeding.

- [ ] **Step 3: If fixture missing, add a minimal `conftest.py` near the test file**

```python
import pytest

@pytest.fixture(scope="session")
def live_server_url():
    return "http://localhost:8001"
```

Precondition: dev server already running on 8001.

- [ ] **Step 4: Run again, confirm PASS**

```bash
uv run pytest tests/ui/test_reports_ledger.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/ui/test_reports_ledger.py tests/ui/conftest.py
git commit -m "test(reports-ledger): Playwright smoke for row render + regenerate"
```

---

## Task 14: Playwright interaction test — version menu open + close

**Files:**
- Modify: `tests/ui/test_reports_ledger.py`

- [ ] **Step 1: Append interaction tests**

```python
@pytest.mark.playwright
def test_version_menu_opens_and_outside_click_closes(page: Page, live_server_url: str):
    page.goto(f"{live_server_url}/#reports")
    page.wait_for_selector(".table--ledger")
    trigger = page.locator(".row-actions__menu-trigger").first
    trigger.click()
    menu = page.locator(".popover").first
    expect(menu).to_be_visible()
    page.locator("body").click(position={"x": 10, "y": 10})
    expect(menu).not_to_be_visible()


@pytest.mark.playwright
def test_version_menu_closes_on_escape(page: Page, live_server_url: str):
    page.goto(f"{live_server_url}/#reports")
    page.wait_for_selector(".table--ledger")
    trigger = page.locator(".row-actions__menu-trigger").first
    trigger.click()
    menu = page.locator(".popover").first
    expect(menu).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest tests/ui/test_reports_ledger.py::test_version_menu_opens_and_outside_click_closes tests/ui/test_reports_ledger.py::test_version_menu_closes_on_escape -v
```

Expected: PASS (requires at least one row with a `▾` trigger — i.e. one non-empty audience in the fixture state).

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_reports_ledger.py
git commit -m "test(reports-ledger): version menu open/close interactions"
```

---

## Task 15: Manual browser walk + final PR-ready commit

**Files:** none modified.

- [ ] **Step 1: Walk the ledger end-to-end in the browser**

Checklist:
- [ ] Open `/#reports` — ledger renders with 2 groups, 7 rows total.
- [ ] Leadership group shows 2 rows (CISO, Board).
- [ ] RSM group shows 5 rows (APAC, AME, LATAM, MED, NCE).
- [ ] Each row's status pill matches the underlying state (at least one of each of: ready, stale, empty if fixtures allow).
- [ ] Hover audience cell on a ready row → thumbnail popover appears.
- [ ] Hover near right viewport edge → popover flips left.
- [ ] Click Regenerate on an empty row → button shows `Regenerating…`, completes without error, row refreshes.
- [ ] Click Preview on a ready row → PDF opens in new tab.
- [ ] Click Narrate on an RSM row → regenerate triggered with narrate flag (check Network tab).
- [ ] Click Download on a ready row → PDF downloads.
- [ ] Open version menu on a ready row → dropdown opens; click outside closes it.
- [ ] Open version menu near viewport bottom → menu flips up.
- [ ] Force a regenerate error (DevTools fetch override) → toast appears top-right, row pill flashes error, toast dismisses after 6s.

- [ ] **Step 2: Full pytest suite**

```bash
uv run pytest -q --ignore=tests/test_export_ciso_docx.py
```

Expected: previously-green tests still green. Known pre-existing skip: `test_phase2_figures_carry_evidence_tier` (Anthropic credits) per memory.

- [ ] **Step 3: Verify no leftover v1 references**

```bash
grep -rn "\.rpt-" static/index.html static/app.js
grep -rn "renderReports\b\|renderReportsRail\|selectAudience\|_hubGenerate" static/app.js
```

Expected: no matches, or only the new `renderReportsLedger` function.

- [ ] **Step 4: Final commit if any cleanup done; otherwise review prior commits and prepare PR**

```bash
git log --oneline -20
```

PR title: `feat(reports): v2 ledger — replace card grid with dense ledger + per-row actions`.

PR description enumerates: audit seeded, primitives added (6 new), JS refactor (new renderers + deleted legacy), Playwright coverage (5 tests), manual QA passed.

---

## Self-review

Checking this plan against the spec at `docs/superpowers/specs/2026-04-22-reports-v2-ledger.md`:

**Spec coverage:**
- Targeted audit (spec §4) → Task 1.
- Status tokens + pill variants (spec §5) → Tasks 2.
- `.table--ledger` (spec §5) → Task 3.
- `.popover` (spec §5) → Task 4.
- `.toast` + `.toast-stack` (spec §5) → Task 5.
- `.row-actions` (spec §5) → Task 6.
- `renderReportsLedger` family + JS refactor (spec §6) → Tasks 7, 8, 9, 10, 11.
- Data contract (spec §7) → honored throughout Tasks 7–11.
- UI spec: column layout (spec §8 row diagram) → Task 8. Row states → Task 8. Thumbnail popover → Task 10. Version menu → Task 9. Regenerate behavior → Task 8. Error toast → Task 11.
- Delete v1 (spec §3 scope) → Task 12.
- Testing (spec §9) → Tasks 13, 14, 15 manual walk.
- DoD (spec §11) items all map onto Task 15 checklist.

**Placeholder scan:** no TBD / TODO / "handle appropriately". All code blocks contain concrete implementations. All commands explicit.

**Type / naming consistency:** `audience.id`, `audience.title`, `audience.canNarrate`, `audience.latest_meta`, `audience.current_run_id` used consistently across Tasks 7–11. `computeRowStatus` returns lowercase strings; `renderLedgerRow` capitalizes via `slice(0,1).toUpperCase()`. `row-actions__menu-trigger` class used consistently between CSS (Task 6) and JS (Task 8) and Playwright selectors (Task 14).

**Caveats that the implementer should confirm:**
- Exact Playwright test directory (the repo may have an established location; `tests/ui/` is a best guess).
- Container selector for Reports tab content in Task 8 Step 2 — must match the current DOM structure.
- Task 12 Step 1 — verify which v1 functions actually exist before deletion.

Gaps / ambiguity: none remaining.
