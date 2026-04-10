# Risk Register Tab Restructure Implementation Plan

**Goal:** Replace the single-scroll `tab-validate` with a two-column master-detail layout: scenario list (left, 40%) + scenario detail / validation (right, 60%), tab header strip with RUN button, and a collapsed Source Registry section at the bottom.

**Architecture:** HTML is restructured to a flex column with a fixed header strip, a CSS-grid two-column body (each column `overflow-y: auto`), and a collapsible source-registry panel below. JS functions for the removed sections (Scenario Library, Regional Register, old Benchmark Validation) are deleted; new orchestrator `renderRiskRegisterTab()` and helpers replace them. A new `PATCH /api/registers/{register_id}/scenarios/{scenario_id}` endpoint enables inline editing without full-register replacement.

**Tech Stack:** FastAPI (`server.py`), vanilla JS (`static/app.js`), inline HTML (`static/index.html`)

---

## File Map

| File | Change |
|---|---|
| `server.py` | Add `PATCH /api/registers/{register_id}/scenarios/{scenario_id}` after line 278 |
| `static/index.html` | Replace lines 997–1113 (`tab-validate` content) with new two-column layout |
| `static/app.js` | Delete 15+ old functions; update `switchTab` line 1357 and line 1365; update `loadRegisterValidationResults()`; add `renderRiskRegisterTab()`, `_renderScenarioList()`, `_selectScenario()`, `_renderScenarioDetail()`, `_renderEditZone()`, `saveScenarioEdit()`, `_showAddScenarioForm()`, `saveNewScenario()`, `toggleSourceRegistry()` |

---

## Task 1: Add PATCH Scenario Endpoint

**Files:**
- Modify: `server.py` — insert after `@app.delete("/api/registers/{register_id}")` block ending at line 278

- [ ] **Step 1: Insert endpoint in `server.py`**

Insert the following block after line 278 (after the `delete_register` function, before `@app.get("/api/registers/active")`):

```python
@app.patch("/api/registers/{register_id}/scenarios/{scenario_id}")
async def patch_scenario(register_id: str, scenario_id: str, payload: dict):
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    data = _read_json(path)
    if not data:
        return JSONResponse({"error": "Register file corrupt"}, status_code=500)
    scenarios = data.get("scenarios", [])
    for i, s in enumerate(scenarios):
        if s.get("scenario_id") == scenario_id:
            if "value_at_cyber_risk_usd" in payload:
                scenarios[i]["value_at_cyber_risk_usd"] = int(payload["value_at_cyber_risk_usd"])
            if "probability_pct" in payload:
                scenarios[i]["probability_pct"] = float(payload["probability_pct"])
            data["scenarios"] = scenarios
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return scenarios[i]
    return JSONResponse({"error": f"Scenario '{scenario_id}' not found"}, status_code=404)
```

- [ ] **Step 2: Smoke-test the endpoint**

Run the dev server (`uv run python server.py`) and verify with curl (use an actual register_id and scenario_id from your `data/registers/` directory):

```bash
curl -s -X PATCH "http://localhost:8001/api/registers/wind_power_plant/scenarios/scen-001" \
  -H "Content-Type: application/json" \
  -d '{"value_at_cyber_risk_usd": 22000000, "probability_pct": 31.7}' | python -m json.tool
```

Expected: JSON object of the updated scenario (not an error). If scenario ID doesn't exist, expect a 404.

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: add PATCH /api/registers/{id}/scenarios/{id} endpoint"
```

---

## Task 2: Replace `tab-validate` HTML

**Files:**
- Modify: `static/index.html` lines 997–1113

- [ ] **Step 1: Replace the entire `tab-validate` div**

Replace the block from `<!-- ── VALIDATE TAB ───` (line 997) through the closing `</div>` at line 1113 with:

```html
<!-- ── VALIDATE TAB ─────────────────────────────────────────────── -->
<div id="tab-validate" class="hidden" style="display:flex;flex-direction:column;height:calc(100vh - 60px);overflow:hidden">

  <!-- Tab header strip -->
  <div style="flex-shrink:0;padding:7px 16px;background:#0d1117;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px">
    <span id="rr-header-name" style="font-size:11px;font-weight:600;color:#c9d1d9">—</span>
    <span id="rr-header-count" style="font-size:10px;color:#484f58"></span>
    <span id="rr-header-ts" style="font-size:10px;color:#484f58;margin-left:auto"></span>
    <button onclick="runRegisterValidation()" style="background:#1f6feb22;border:1px solid #1f6feb;color:#79c0ff;border-radius:3px;padding:3px 10px;font-size:10px;cursor:pointer">&#9654; RUN</button>
  </div>

  <!-- Progress line (hidden until running) -->
  <div id="val-progress" style="display:none;flex-shrink:0;font-size:10px;color:#6e7681;padding:5px 16px;background:#161b22;border-bottom:1px solid #21262d"></div>

  <!-- Two-column body -->
  <div style="flex:1;display:grid;grid-template-columns:40% 60%;overflow:hidden;min-height:0">
    <!-- Left panel: Scenario list -->
    <div id="rr-scenario-list" style="overflow-y:auto;border-right:1px solid #21262d"></div>
    <!-- Right panel: Scenario detail -->
    <div id="rr-scenario-detail" style="overflow-y:auto"></div>
  </div>

  <!-- Source Registry (full-width, collapsed by default) -->
  <div style="flex-shrink:0;border-top:1px solid #21262d">
    <div onclick="toggleSourceRegistry()" style="display:flex;justify-content:space-between;align-items:center;padding:7px 16px;cursor:pointer">
      <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">Source Registry</span>
      <span id="rr-src-toggle" style="font-size:10px;color:#484f58">&#9654; Show</span>
    </div>
    <div id="rr-src-body" style="display:none;max-height:320px;overflow-y:auto;border-top:1px solid #21262d">
      <div style="display:grid;grid-template-columns:1fr 1fr">
        <div style="border-right:1px solid #21262d;padding:12px 14px">
          <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:8px">Registered Sources</div>
          <div id="val-sources"><div style="color:#6e7681;font-size:11px;padding:8px">Loading...</div></div>
        </div>
        <div style="padding:12px 14px">
          <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:8px">New Sources <span id="val-candidate-count" style="color:#e3b341"></span></div>
          <div id="val-candidates"><div style="color:#6e7681;font-size:11px;padding:8px">No candidates.</div></div>
        </div>
      </div>
    </div>
  </div>

</div>
```

- [ ] **Step 2: Update `switchTab` to display the validate tab as flex**

In `static/app.js` at line 1357, the display logic is:

```js
el.style.display = t === tab ? (t === 'config' || t === 'overview' || t === 'pipeline' || t === 'runlog' ? 'flex' : 'block') : '';
```

Change it to:

```js
el.style.display = t === tab ? (t === 'config' || t === 'overview' || t === 'pipeline' || t === 'runlog' || t === 'validate' ? 'flex' : 'block') : '';
```

This ensures the validate tab's flex layout activates when switching to it.

- [ ] **Step 3: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat: restructure tab-validate HTML to two-column master-detail layout"
```

---

## Task 3: Delete Removed JS Functions

**Files:**
- Modify: `static/app.js`

Delete the following complete function blocks. Each deletion is one Edit call — find the function by its opening `async function` or `function` signature and delete from the `async function`/`function` keyword through the closing `}`.

**Functions to delete (with their line ranges as of current file):**

| Function | Purpose |
|---|---|
| `renderValidateTab()` (line 2540) | Replaced by `renderRiskRegisterTab()` |
| `loadRiskRegister()` (line 2544) | Loads removed Regional Register section |
| `_rrEditForm()` (line 2590) | Helper for removed Regional Register rows |
| `toggleRRRow()` (line 2622) | Toggle expand for removed Regional rows |
| `saveRegionalScenario()` (line 2627) | Save handler for removed Regional Register |
| `deleteRegionalScenario()` (line 2643) | Delete handler for removed Regional Register |
| `addRegionalScenario()` (line 2650) | Add handler for removed Regional Register |
| `loadMasterScenarios()` (line 2662) | Loads removed Scenario Library section |
| `_masterEditForm()` (line 2720) | Helper for removed master scenario rows |
| `toggleMasterRow()` (line 2754) | Toggle expand for removed master rows |
| `saveMasterScenario()` (line 2759) | Save handler for removed Scenario Library |
| `deleteMasterScenario()` (line 2778) | Delete handler for removed Scenario Library |
| `addMasterScenario()` (line 2785) | Add handler for removed Scenario Library |
| `runResearch()` (line 2797) | Removed RUN RESEARCH button handler |
| `loadValScenarios()` (line 2824) | Loads removed old benchmark results table |
| `toggleResearchExpand()` (line 2886) | Toggle for removed research findings rows |
| `_renderResearchFindings()` (line 2892) | Renders removed research findings rows |
| `runValidate()` (line 3076) | Removed RUN VALIDATION button handler |
| `_listenValidationSSE()` (line 3098) | SSE listener for removed runValidate() |
| `_listenResearchSSE()` (line 3126) | SSE listener for removed runResearch() |
| `_renderRegisterValidationResults()` (line 3382) | Top-level wrapper, replaced by new helpers |

- [ ] **Step 1: Delete `renderValidateTab`, `loadRiskRegister`, and all regional register helpers**

Delete the block from line 2538 (`// ── Section: Validate Tab ──`) through line 2660 (end of `addRegionalScenario()`). This removes `renderValidateTab`, `loadRiskRegister`, `_rrEditForm`, `toggleRRRow`, `saveRegionalScenario`, `deleteRegionalScenario`, `addRegionalScenario`.

- [ ] **Step 2: Delete master scenario functions**

Delete `loadMasterScenarios`, `_masterEditForm`, `toggleMasterRow`, `saveMasterScenario`, `deleteMasterScenario`, `addMasterScenario` — from line 2662 through line 2795.

- [ ] **Step 3: Delete research + old validation functions**

Delete `runResearch` (line 2797 through 2817), `loadValScenarios` (line 2824 through 2884), `toggleResearchExpand` (line 2886–2890), `_renderResearchFindings` (line 2892–2911).

Keep `applyRegionFilterAndSwitch` at line 2818 — it is used by the Sources tab.

- [ ] **Step 4: Delete SSE listeners and old validation runners**

Delete `runValidate` (line 3076–3096), `_listenValidationSSE` (line 3098–3124), `_listenResearchSSE` (line 3126–3145).

- [ ] **Step 5: Delete `_renderRegisterValidationResults`**

Delete the block from line 3382 (`function _renderRegisterValidationResults(data)`) through its closing `}` at line 3410.

Keep everything in the `// ── Register Validation Results ──` section EXCEPT that wrapper function:
- Keep `runRegisterValidation()` (line 3361)
- Keep `loadRegisterValidationResults()` (line 3377) — will be rewritten in Task 4
- Keep `_regValVerdictBadge()`, `_ctxBadge()`, `_renderSourceRow()`, `_renderSourcesBox()`, `_renderRegValDimension()`, `toggleRegValRow()`

- [ ] **Step 6: Update `switchTab` line 1365**

Change:

```js
if (tab === 'validate') { renderValidateTab(); loadRegisterValidationResults(); }
```

to:

```js
if (tab === 'validate') { renderRiskRegisterTab(); }
```

- [ ] **Step 7: Verify no references to deleted functions remain**

Search the file for each deleted function name — expect no matches:

```bash
grep -n "renderValidateTab\|loadRiskRegister\|loadMasterScenarios\|loadValScenarios\|runValidate\b\|runResearch\b\|_renderRegisterValidationResults\|_listenValidationSSE\|_listenResearchSSE" static/app.js
```

Expected: zero lines (or only within new function definitions added in Task 4–5).

- [ ] **Step 8: Commit**

```bash
git add static/app.js
git commit -m "refactor: delete removed validate-tab JS functions and update switchTab"
```

---

## Task 4: Update State + loadRegisterValidationResults + renderRiskRegisterTab + _renderScenarioList + _selectScenario

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add `validationData` and `selectedScenarioId` to state**

In the state initializer at line 24 (`let state = {`), add two fields. Locate `activeRegister: null,` and add after it:

```js
  validationData: null,       // register_validation.json content | null
  selectedScenarioId: null,   // currently selected scenario in the register tab
```

- [ ] **Step 2: Rewrite `loadRegisterValidationResults()`**

Replace the current body of `loadRegisterValidationResults()` (which is a 2-liner that renders directly) with:

```js
async function loadRegisterValidationResults() {
  const data = await fetchJSON('/api/register-validation/results');
  state.validationData = (data && data.status !== 'no_data' && data.scenarios) ? data : null;

  // Update timestamp in tab header
  const tsEl = $('rr-header-ts');
  if (tsEl) tsEl.textContent = state.validationData?.validated_at
    ? `Validated ${relTime(state.validationData.validated_at)}` : '';

  // Re-render left panel to show updated verdict badges
  _renderScenarioList();

  // Re-render right panel to show validation data for current selection
  if (state.selectedScenarioId) _selectScenario(state.selectedScenarioId);
}
```

- [ ] **Step 3: Add `renderRiskRegisterTab()`**

Add this function in the `// ── Section: Validate Tab ──` area (where `renderValidateTab` used to be):

```js
// ── Section: Risk Register Tab ────────────────────────────────────────

async function renderRiskRegisterTab() {
  const r = state.activeRegister;
  if (!r) {
    const listEl = $('rr-scenario-list');
    if (listEl) listEl.innerHTML = '<div style="padding:12px;color:#484f58;font-size:10px">No active register selected.</div>';
    return;
  }

  // Update tab header
  const nameEl = $('rr-header-name');
  const countEl = $('rr-header-count');
  if (nameEl) nameEl.textContent = r.display_name || '—';
  if (countEl) countEl.textContent = `${(r.scenarios || []).length} scenarios`;

  // Render left panel immediately from state
  _renderScenarioList();

  // Auto-select first scenario
  const first = (r.scenarios || [])[0];
  if (first) _selectScenario(first.scenario_id);

  // Load validation results (will re-render list + detail when done)
  loadRegisterValidationResults();

  // Pre-load source registry data
  loadValSources();
  loadValCandidates();
}
```

- [ ] **Step 4: Add `_renderScenarioList()`**

```js
function _renderScenarioList() {
  const el = $('rr-scenario-list');
  if (!el) return;
  const scenarios = state.activeRegister?.scenarios || [];

  // Build verdict lookup from state.validationData
  const valMap = {};
  if (state.validationData?.scenarios) {
    for (const s of state.validationData.scenarios) valMap[s.scenario_id] = s;
  }

  const rows = scenarios.map(s => {
    const vacr = s.value_at_cyber_risk_usd != null
      ? `$${(s.value_at_cyber_risk_usd / 1e6).toFixed(1)}M` : '—';
    const prob = s.probability_pct != null ? `${s.probability_pct}%` : '—';
    const val = valMap[s.scenario_id];
    const fVerdict = val?.financial?.verdict;
    const pVerdict = val?.probability?.verdict;
    const fBadge = fVerdict
      ? _regValVerdictBadge('$', fVerdict)
      : `<span style="font-size:10px;color:#484f58">—</span>`;
    const pBadge = pVerdict
      ? _regValVerdictBadge('%', pVerdict)
      : `<span style="font-size:10px;color:#484f58">—</span>`;
    const isSelected = s.scenario_id === state.selectedScenarioId;
    const selStyle = isSelected
      ? 'border-left:2px solid #1f6feb;background:#111820;'
      : 'border-left:2px solid transparent;';
    return `<div onclick="_selectScenario('${esc(s.scenario_id)}')"
      style="padding:8px 12px;border-bottom:1px solid #21262d;cursor:pointer;${selStyle}">
      <div style="font-size:11px;color:#e6edf3;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.scenario_name)}</div>
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:10px;color:#3fb950;font-family:monospace">${vacr}</span>
        <span style="font-size:10px;color:#484f58">${prob}</span>
        <span style="margin-left:auto;display:flex;gap:4px">${fBadge}${pBadge}</span>
      </div>
    </div>`;
  }).join('');

  const addBtn = `<div style="padding:8px 12px;border-top:1px solid #21262d">
    <button onclick="_showAddScenarioForm()" style="width:100%;background:transparent;border:1px dashed #21262d;color:#484f58;border-radius:3px;padding:6px;font-size:10px;cursor:pointer">+ Add Scenario</button>
  </div>`;

  el.innerHTML = (rows || '<div style="padding:12px;color:#484f58;font-size:10px">No scenarios.</div>') + addBtn;
}
```

- [ ] **Step 5: Add `_selectScenario(id)`**

```js
function _selectScenario(id) {
  if (!id) return;
  state.selectedScenarioId = id;
  _renderScenarioList(); // refresh highlight

  const scenario = (state.activeRegister?.scenarios || []).find(s => s.scenario_id === id);
  const valScenario = state.validationData?.scenarios?.find(s => s.scenario_id === id) || null;
  _renderScenarioDetail(scenario, valScenario);
}
```

- [ ] **Step 6: Commit**

```bash
git add static/app.js
git commit -m "feat: renderRiskRegisterTab + scenario list + state.validationData"
```

---

## Task 5: Right Panel — Detail, Edit, Add Scenario, Source Registry Toggle

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add `_renderScenarioDetail(scenario, valScenario)`**

```js
function _renderScenarioDetail(scenario, valScenario) {
  const el = $('rr-scenario-detail');
  if (!el) return;
  if (!scenario) {
    el.innerHTML = `<div style="padding:20px;color:#484f58;font-size:10px">Select a scenario.</div>`;
    return;
  }

  const vacr = scenario.value_at_cyber_risk_usd != null
    ? `$${Number(scenario.value_at_cyber_risk_usd).toLocaleString('en-US')}` : '—';
  const prob = scenario.probability_pct != null ? `${scenario.probability_pct}%` : '—';

  // Numbers zone
  const numbersZone = `<div id="rr-numbers-zone" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:16px 14px;border-bottom:1px solid #21262d">
    <div>
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Value at Cyber Risk</div>
      <div style="font-size:18px;font-weight:600;color:#3fb950;font-family:monospace">${vacr}</div>
    </div>
    <div>
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Probability</div>
      <div style="font-size:18px;font-weight:600;color:#8b949e;font-family:monospace">${prob}</div>
    </div>
  </div>`;

  // Validation zone
  let validationZone;
  if (!valScenario) {
    validationZone = `<div style="padding:16px 14px;color:#484f58;font-size:10px">No validation data — click &#9654; RUN to validate this register.</div>`;
  } else {
    const versionChecks = state.validationData?.version_checks || [];
    const finHtml = _renderRegValDimension(scenario.scenario_id, 'financial', valScenario.financial, versionChecks);
    const probHtml = _renderRegValDimension(scenario.scenario_id, 'probability', valScenario.probability, versionChecks);
    const noteHtml = valScenario.asset_context_note
      ? `<div style="padding:0 12px 8px 12px;font-size:10px;color:#6e7681;font-style:italic">${esc(valScenario.asset_context_note)}</div>`
      : '';
    validationZone = `<div style="padding:8px 0">${finHtml}${probHtml}${noteHtml}</div>`;
  }

  // Audit trace (collapsed, global to last run)
  const auditZone = `<div style="border-top:1px solid #21262d;padding:6px 12px 10px">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
      <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">Audit Trace</span>
      <button onclick="toggleAuditTrace()" id="btn-toggle-trace" style="font-size:10px;color:#484f58;cursor:pointer;background:none;border:none">&#9654;</button>
    </div>
    <pre id="audit-trace" class="hidden" style="background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:10px;font-size:10px;color:#6e7681;overflow-x:auto;white-space:pre-wrap;max-height:180px;overflow-y:auto"></pre>
  </div>`;

  el.innerHTML = `
    <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;justify-content:space-between;align-items:center">
      <div>
        <div style="font-size:12px;font-weight:600;color:#c9d1d9">${esc(scenario.scenario_name)}</div>
        <div style="font-size:10px;color:#484f58;margin-top:2px;font-family:monospace">${esc(scenario.scenario_id)}</div>
      </div>
      <button onclick="_renderEditZone('${esc(scenario.scenario_id)}')"
        style="background:transparent;border:1px solid #30363d;color:#8b949e;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">&#9998; Edit</button>
    </div>
    ${numbersZone}
    ${validationZone}
    ${auditZone}`;

  loadAuditTrace();
}
```

- [ ] **Step 2: Add `_renderEditZone(scenarioId)`**

```js
function _renderEditZone(scenarioId) {
  const scenario = (state.activeRegister?.scenarios || []).find(s => s.scenario_id === scenarioId);
  if (!scenario) return;
  const zone = $('rr-numbers-zone');
  if (!zone) return;
  zone.innerHTML = `
    <div>
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Value at Cyber Risk (USD)</div>
      <input id="rr-edit-vacr" type="number" value="${scenario.value_at_cyber_risk_usd || 0}"
        style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:14px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none;font-family:monospace" />
    </div>
    <div>
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Probability (%)</div>
      <input id="rr-edit-prob" type="number" step="0.1" min="0" max="100" value="${scenario.probability_pct || 0}"
        style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:14px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none;font-family:monospace" />
    </div>
    <div style="grid-column:1/-1;display:flex;gap:6px;margin-top:4px">
      <button onclick="saveScenarioEdit('${esc(scenarioId)}')"
        style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:3px 12px;border-radius:2px;cursor:pointer">Save</button>
      <button onclick="_selectScenario('${esc(scenarioId)}')"
        style="font-size:10px;color:#6e7681;background:none;border:1px solid #30363d;padding:3px 12px;border-radius:2px;cursor:pointer">Cancel</button>
    </div>`;
}
```

- [ ] **Step 3: Add `saveScenarioEdit(scenarioId)`**

```js
async function saveScenarioEdit(scenarioId) {
  const vacrInput = $('rr-edit-vacr');
  const probInput = $('rr-edit-prob');
  if (!vacrInput || !probInput) return;
  const vacr = parseFloat(vacrInput.value) || 0;
  const prob = parseFloat(probInput.value) || 0;
  const registerId = state.activeRegister?.register_id;
  if (!registerId) return;

  const r = await fetch(
    `/api/registers/${encodeURIComponent(registerId)}/scenarios/${encodeURIComponent(scenarioId)}`,
    {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({value_at_cyber_risk_usd: vacr, probability_pct: prob}),
    }
  );
  if (!r.ok) { alert('Save failed'); return; }

  const updated = await r.json();
  // Update state without a network round-trip
  const idx = (state.activeRegister.scenarios || []).findIndex(s => s.scenario_id === scenarioId);
  if (idx !== -1) state.activeRegister.scenarios[idx] = {...state.activeRegister.scenarios[idx], ...updated};

  _selectScenario(scenarioId); // re-renders both list and detail
}
```

- [ ] **Step 4: Add `_showAddScenarioForm()`**

```js
function _showAddScenarioForm() {
  const el = $('rr-scenario-detail');
  if (!el) return;
  const prevId = state.selectedScenarioId || '';
  el.innerHTML = `
    <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:12px;font-weight:600;color:#c9d1d9">Add Scenario</span>
      <button onclick="_selectScenario('${esc(prevId)}')"
        style="background:transparent;border:1px solid #30363d;color:#8b949e;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">&#10005; Cancel</button>
    </div>
    <div style="padding:16px 14px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
        <div style="grid-column:1/-1">
          <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Scenario Name</div>
          <input id="rr-add-name" type="text" placeholder="e.g. Ransomware"
            style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
        </div>
        <div>
          <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">VaCR (USD)</div>
          <input id="rr-add-vacr" type="number" value="0"
            style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
        </div>
        <div>
          <div style="font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681;margin-bottom:4px">Probability (%)</div>
          <input id="rr-add-prob" type="number" step="0.1" min="0" max="100" value="0"
            style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
        </div>
      </div>
      <div id="rr-add-err" style="font-size:10px;color:#f85149;margin-bottom:8px;display:none"></div>
      <button onclick="saveNewScenario()"
        style="background:#238636;color:#fff;border:none;border-radius:3px;padding:5px 16px;font-size:10px;cursor:pointer">Save Scenario</button>
    </div>`;
}
```

- [ ] **Step 5: Add `saveNewScenario()`**

```js
async function saveNewScenario() {
  const name = $('rr-add-name')?.value.trim();
  const vacr = parseFloat($('rr-add-vacr')?.value) || 0;
  const prob = parseFloat($('rr-add-prob')?.value) || 0;
  const errEl = $('rr-add-err');
  if (errEl) errEl.style.display = 'none';

  if (!name) {
    if (errEl) { errEl.textContent = 'Scenario name is required.'; errEl.style.display = 'block'; }
    return;
  }

  const register = state.activeRegister;
  if (!register) return;

  const newScenario = {
    scenario_id: `scen-${Date.now()}`,
    scenario_name: name,
    value_at_cyber_risk_usd: vacr,
    probability_pct: prob,
    probability_source: 'internal_estimate',
  };

  const updatedRegister = {...register, scenarios: [...(register.scenarios || []), newScenario]};
  const r = await fetch(`/api/registers/${encodeURIComponent(register.register_id)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(updatedRegister),
  });
  if (!r.ok) {
    if (errEl) { errEl.textContent = 'Save failed.'; errEl.style.display = 'block'; }
    return;
  }

  state.activeRegister = updatedRegister;
  state.selectedScenarioId = newScenario.scenario_id;
  _renderScenarioList();
  _selectScenario(newScenario.scenario_id);
}
```

- [ ] **Step 6: Add `toggleSourceRegistry()`**

```js
function toggleSourceRegistry() {
  const body = $('rr-src-body');
  const toggle = $('rr-src-toggle');
  if (!body) return;
  const isOpen = body.style.display !== 'none';
  body.style.display = isOpen ? 'none' : 'block';
  if (toggle) toggle.innerHTML = isOpen ? '&#9654; Show' : '&#9660; Hide';
  if (!isOpen) {
    loadValSources();
    loadValCandidates();
  }
}
```

- [ ] **Step 7: Verify the tab functions end-to-end in the browser**

1. Start the dev server: `uv run python server.py`
2. Open `http://localhost:8001`
3. Switch to the "Risk Register" tab (nav item that was "Validate")
4. Confirm: header strip shows register name + scenario count + RUN button
5. Confirm: left panel lists scenarios with VaCR, probability, verdict badges (or `—` if no data yet)
6. Confirm: first scenario is auto-selected (blue left border, right panel shows detail)
7. Confirm: right panel shows "VALUE AT CYBER RISK" and "PROBABILITY" labels with values
8. Confirm: clicking a different scenario updates the selection + right panel
9. Click ✎ Edit — confirm inputs appear, Cancel restores read-only, Save patches correctly
10. Click + Add Scenario — confirm right panel becomes the add form; fill + save → new scenario appears in list auto-selected
11. Click ▶ RUN — confirm button text changes to "Running..." while request is in flight
12. Click Source Registry toggle at the bottom — confirm it expands to show two-column source panels
13. Confirm the `val-progress` div is still in DOM (used by `runRegisterValidation`) — it should be below the header strip

- [ ] **Step 8: Final commit**

```bash
git add static/app.js server.py static/index.html
git commit -m "feat: risk register tab master-detail layout — scenario list, detail panel, inline edit, add scenario, source registry"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|---|---|
| Tab header strip: name, count, timestamp, RUN | Task 2 (HTML) + Task 4 (`renderRiskRegisterTab`) |
| Left panel 40%, right panel 60%, independent scroll | Task 2 (CSS grid + overflow-y) |
| Scenario list: name, VaCR, prob, verdict badges | Task 4 (`_renderScenarioList`) |
| Grey `—` when no validation data for verdict slots | Task 4 (`_renderScenarioList` — uses `—` span) |
| First scenario auto-selected on load | Task 4 (`renderRiskRegisterTab`) |
| Click row → selection highlight + right panel | Task 4 (`_selectScenario`) |
| Right panel: numbers zone (VaCR + probability) | Task 5 (`_renderScenarioDetail`) |
| Edit mode: inputs + Save/Cancel | Task 5 (`_renderEditZone`) |
| Save calls PATCH + updates state | Task 1 (endpoint) + Task 5 (`saveScenarioEdit`) |
| Validation zone: `_renderRegValDimension` per dim | Task 5 (`_renderScenarioDetail`) |
| No data placeholder | Task 5 (`_renderScenarioDetail`) |
| `asset_context_note` italic muted | Task 5 (`_renderScenarioDetail`) |
| AUDIT TRACE collapsed in right panel | Task 5 (`_renderScenarioDetail`) |
| + Add Scenario → right panel takeover | Task 5 (`_showAddScenarioForm`) |
| Cancel Add → restore previous selection | Task 5 (`_showAddScenarioForm` — stores prevId) |
| Save new scenario → appended + auto-selected | Task 5 (`saveNewScenario`) |
| Source Registry: full-width, collapsed, two sub-sections | Task 2 (HTML) + Task 5 (`toggleSourceRegistry`) |
| Switch Register: global bar only, no duplication | Not touched — spec says global bar is the single owner |
| `state.validationData` stored in state | Task 4 (state init + `loadRegisterValidationResults`) |
| `state.selectedScenarioId` in state | Task 4 (state init + `_selectScenario`) |
| `PATCH /api/registers/{id}/scenarios/{id}` | Task 1 |
| Delete Scenario Library + Regional Register HTML | Task 2 |
| Delete removed JS functions | Task 3 |
