# Risk Register Tab — Implementation Plan


**Goal:** Rename the Validate tab to "Risk Register", add inline CRUD editors for both CRQ databases, and add a VaCR intelligence pipeline that searches industry sources per scenario and presents benchmark evidence.

**Architecture:** Two independent workstreams — the database editor (Tasks 1–4) adds server endpoints and UI panels with no new files; the research pipeline (Tasks 5–8) adds `tools/vacr_researcher.py`, three server endpoints, and wires the UI into the existing SSE pattern. Both workstreams write to `output/pipeline/` and `data/` and share the same tab in `static/index.html`.

**Tech Stack:** FastAPI + `sse_starlette` + vanilla JS + Tailwind dark theme. Anthropic SDK (Haiku for extraction, Sonnet for reasoning). DuckDuckGo/Tavily via `tools/osint_search.py`.

---

## File Map

| File | Change |
|------|--------|
| `server.py` | Add 11 new endpoints (8 CRUD + 3 research). Add `research_state` dict. |
| `static/index.html` | Rename tab label. Add two editor panels above existing validate content. Add "RUN RESEARCH" button. |
| `static/app.js` | Add `loadRiskRegister()`, `loadMasterScenarios()`, CRUD handlers, `runResearch()`, `_listenResearchSSE()`, expand row rendering for research findings. Rename `renderValidateTab()` → `renderRiskRegisterTab()`. |
| `tools/vacr_researcher.py` | New script. Web search + Haiku extraction + Sonnet reasoning per scenario. CLI and importable. |

---

## WORKSTREAM A — CRQ Database Editor

### Task 1: Server endpoints — Regional Scenarios CRUD

**Files:**
- Modify: `server.py` (after line ~1047, after existing validation endpoints)

- [ ] **Step 1: Add the 4 regional endpoints to server.py**

Find the line `@app.get("/api/validation/status")` in `server.py` and add the following block immediately after the `get_validation_status` function:

```python
# ── API: Risk Register — Regional Scenarios ──────────────────────────────
_REGIONAL_DB = BASE / "data" / "mock_crq_database.json"
_MASTER_DB   = BASE / "data" / "master_scenarios.json"


@app.get("/api/risk-register/regional")
async def get_regional_scenarios():
    data = _read_json(_REGIONAL_DB)
    return data or {}


@app.put("/api/risk-register/regional/{scenario_id}")
async def update_regional_scenario(scenario_id: str, body: dict):
    data = _read_json(_REGIONAL_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    for region, scenarios in data.items():
        for i, s in enumerate(scenarios):
            if s.get("scenario_id") == scenario_id:
                # Merge update fields; preserve scenario_id and region structure
                data[region][i].update({k: v for k, v in body.items() if k != "scenario_id"})
                _REGIONAL_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
                return {"ok": True, "scenario_id": scenario_id}
    return JSONResponse({"error": f"Scenario {scenario_id} not found"}, status_code=404)


@app.post("/api/risk-register/regional")
async def add_regional_scenario(body: dict):
    data = _read_json(_REGIONAL_DB) or {}
    region = body.get("region", "").upper()
    if not region:
        return JSONResponse({"error": "region required"}, status_code=400)
    # Auto-generate scenario_id: REGION-NNN
    existing = [s for scenarios in data.values() for s in scenarios if s.get("scenario_id", "").startswith(region)]
    new_id = f"{region}-{len(existing) + 1:03d}"
    scenario = {
        "scenario_id": new_id,
        "department": body.get("department", ""),
        "scenario_name": body.get("scenario_name", "New Scenario"),
        "critical_assets": body.get("critical_assets", []),
        "value_at_cyber_risk_usd": body.get("value_at_cyber_risk_usd", 0),
    }
    data.setdefault(region, []).append(scenario)
    _REGIONAL_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "scenario_id": new_id}


@app.delete("/api/risk-register/regional/{scenario_id}")
async def delete_regional_scenario(scenario_id: str):
    data = _read_json(_REGIONAL_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    for region, scenarios in data.items():
        for i, s in enumerate(scenarios):
            if s.get("scenario_id") == scenario_id:
                data[region].pop(i)
                if not data[region]:
                    del data[region]
                _REGIONAL_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
                return {"ok": True}
    return JSONResponse({"error": f"Scenario {scenario_id} not found"}, status_code=404)
```

- [ ] **Step 2: Verify endpoints respond**

Run: `uv run uvicorn server:app --port 8001 --reload` (or if server already running, just test):
```bash
curl -s http://localhost:8001/api/risk-register/regional | python -c "import sys,json; d=json.load(sys.stdin); print(list(d.keys()))"
```
Expected: `['APAC', 'AME', 'LATAM', 'MED', 'NCE']`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat(risk-register): add regional scenarios CRUD endpoints"
```

---

### Task 2: Server endpoints — Master Scenarios CRUD

**Files:**
- Modify: `server.py` (after Task 1 block)

- [ ] **Step 1: Add the 4 master scenario endpoints to server.py**

Append immediately after the `delete_regional_scenario` function:

```python
# ── API: Risk Register — Master Scenarios ────────────────────────────────

@app.get("/api/risk-register/master")
async def get_master_scenarios():
    data = _read_json(_MASTER_DB)
    return {"scenarios": data.get("scenarios", [])} if data else {"scenarios": []}


@app.put("/api/risk-register/master/{incident_type}")
async def update_master_scenario(incident_type: str, body: dict):
    data = _read_json(_MASTER_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    for i, s in enumerate(data.get("scenarios", [])):
        if s.get("incident_type") == incident_type:
            data["scenarios"][i].update({k: v for k, v in body.items() if k != "incident_type"})
            _MASTER_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            return {"ok": True}
    return JSONResponse({"error": f"Scenario '{incident_type}' not found"}, status_code=404)


@app.post("/api/risk-register/master")
async def add_master_scenario(body: dict):
    data = _read_json(_MASTER_DB) or {"meta": {}, "scenarios": []}
    incident_type = body.get("incident_type", "").strip()
    if not incident_type:
        return JSONResponse({"error": "incident_type required"}, status_code=400)
    if any(s.get("incident_type") == incident_type for s in data.get("scenarios", [])):
        return JSONResponse({"error": f"'{incident_type}' already exists"}, status_code=409)
    scenario = {
        "incident_type": incident_type,
        "event_frequency_pct": body.get("event_frequency_pct", 0.0),
        "frequency_rank": body.get("frequency_rank", 99),
        "financial_impact_pct": body.get("financial_impact_pct", 0.0),
        "financial_rank": body.get("financial_rank", 99),
        "records_affected_pct": body.get("records_affected_pct", 0.0),
        "records_rank": body.get("records_rank", 99),
    }
    data["scenarios"].append(scenario)
    _MASTER_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "incident_type": incident_type}


@app.delete("/api/risk-register/master/{incident_type}")
async def delete_master_scenario(incident_type: str):
    # URL-encode spaces — FastAPI path param decodes automatically
    data = _read_json(_MASTER_DB)
    if not data:
        return JSONResponse({"error": "Database not found"}, status_code=404)
    original_len = len(data.get("scenarios", []))
    data["scenarios"] = [s for s in data.get("scenarios", []) if s.get("incident_type") != incident_type]
    if len(data["scenarios"]) == original_len:
        return JSONResponse({"error": f"Scenario '{incident_type}' not found"}, status_code=404)
    _MASTER_DB.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return {"ok": True}
```

- [ ] **Step 2: Verify master endpoint**

```bash
curl -s http://localhost:8001/api/risk-register/master | python -c "import sys,json; d=json.load(sys.stdin); print(len(d['scenarios']), 'scenarios')"
```
Expected: `9 scenarios`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat(risk-register): add master scenarios CRUD endpoints"
```

---

### Task 3: Rename tab + Regional Scenarios editor panel (HTML + JS)

**Files:**
- Modify: `static/index.html` (line 593 — nav tab label; line 841 — tab content)
- Modify: `static/app.js` (rename `renderValidateTab`, add `loadRiskRegister`)

- [ ] **Step 1: Rename nav tab in index.html**

Find line 593:
```html
      <div class="nav-tab" id="nav-validate" onclick="switchTab('validate')">Validate</div>
```
Change to:
```html
      <div class="nav-tab" id="nav-validate" onclick="switchTab('validate')">Risk Register</div>
```

- [ ] **Step 2: Add Regional Scenarios panel to index.html**

Find the opening of `<div id="tab-validate"` (line 841). Insert a new Regional Scenarios section before the existing `<!-- Header row -->` comment:

```html
  <!-- Regional Scenarios Editor -->
  <div style="margin-bottom:20px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
      <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">Regional Scenarios (CRQ Database)</span>
      <button onclick="addRegionalScenario()" style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:3px 10px;border-radius:2px;cursor:pointer">+ Add</button>
    </div>
    <div id="rr-regional-table" style="border:1px solid #21262d;border-radius:2px;overflow:hidden">
      <div style="color:#6e7681;font-size:11px;padding:12px">Loading...</div>
    </div>
  </div>

  <!-- Master Scenarios Editor -->
  <div style="margin-bottom:20px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
      <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">Master Scenario Types</span>
      <button onclick="addMasterScenario()" style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:3px 10px;border-radius:2px;cursor:pointer">+ Add</button>
    </div>
    <div id="rr-master-table" style="border:1px solid #21262d;border-radius:2px;overflow:hidden">
      <div style="color:#6e7681;font-size:11px;padding:12px">Loading...</div>
    </div>
  </div>

  <div style="border-top:1px solid #21262d;padding-top:14px;margin-bottom:14px">
    <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#484f58">Validation & Benchmark Research</span>
  </div>
```

- [ ] **Step 3: Add Research button to the existing header row in index.html**

Find the existing `RUN VALIDATION` button block:
```html
    <button id="btn-run-validate" onclick="runValidate()"
      style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:4px 14px;border-radius:2px;cursor:pointer">
      &#9654; RUN VALIDATION
    </button>
```
Replace with:
```html
    <div style="display:flex;gap:8px">
      <button id="btn-run-research" onclick="runResearch()"
        style="font-size:10px;color:#58a6ff;background:#1a2a3a;border:1px solid #1f6feb;padding:4px 14px;border-radius:2px;cursor:pointer">
        &#9654; RUN RESEARCH
      </button>
      <button id="btn-run-validate" onclick="runValidate()"
        style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:4px 14px;border-radius:2px;cursor:pointer">
        &#9654; RUN VALIDATION
      </button>
    </div>
```

- [ ] **Step 4: Add a research progress line to index.html**

After the existing `val-progress` div:
```html
  <!-- Progress line (hidden until running) -->
  <div id="val-progress" style="display:none;...">
```
Add a second progress div immediately after:
```html
  <div id="research-progress" style="display:none;font-size:10px;color:#58a6ff;margin-bottom:10px;padding:6px 10px;background:#161b22;border:1px solid #21262d;border-radius:2px"></div>
```

- [ ] **Step 5: Add loadRiskRegister and renderRiskRegisterTab to app.js**

Find `async function renderValidateTab()` in app.js and replace it:
```javascript
async function renderValidateTab() {
  await Promise.all([loadRiskRegister(), loadMasterScenarios(), loadValScenarios(), loadValSources(), loadValCandidates(), loadAuditTrace()]);
}

async function loadRiskRegister() {
  const el = document.getElementById('rr-regional-table');
  try {
    const data = await fetch('/api/risk-register/regional').then(r => r.json());
    // Flatten region-keyed object into array with region field
    const scenarios = Object.entries(data).flatMap(([region, arr]) =>
      arr.map(s => ({...s, region}))
    );
    if (!scenarios.length) {
      el.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No scenarios — click + Add.</div>';
      return;
    }
    const header = `<div style="display:flex;padding:5px 12px;border-bottom:1px solid #21262d;font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#484f58">
      <span style="width:60px;flex-shrink:0">Region</span>
      <span style="width:180px;flex-shrink:0">Scenario</span>
      <span style="width:120px;flex-shrink:0">Department</span>
      <span style="flex:1">Critical Assets</span>
      <span style="width:90px;flex-shrink:0;text-align:right">VaCR</span>
      <span style="width:24px;flex-shrink:0"></span>
    </div>`;
    const rows = scenarios.map(s => {
      const vacr = s.value_at_cyber_risk_usd ? `$${(s.value_at_cyber_risk_usd/1e6).toFixed(1)}M` : '—';
      const chips = (s.critical_assets || []).map(a =>
        `<span style="display:inline-block;background:#21262d;color:#8b949e;font-size:9px;padding:1px 6px;border-radius:2px;margin:1px">${a}</span>`
      ).join('');
      return `
        <div class="rr-row" data-id="${s.scenario_id}" style="border-bottom:1px solid #21262d">
          <div onclick="toggleRRRow('${s.scenario_id}')" style="display:flex;align-items:center;padding:7px 12px;font-size:11px;cursor:pointer">
            <span style="color:#58a6ff;width:60px;flex-shrink:0;font-family:monospace;font-weight:600">${s.region}</span>
            <span style="color:#e6edf3;width:180px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.scenario_name}</span>
            <span style="color:#8b949e;width:120px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.department}</span>
            <span style="flex:1;overflow:hidden">${chips}</span>
            <span style="color:#3fb950;width:90px;flex-shrink:0;text-align:right;font-family:monospace">${vacr}</span>
            <span style="width:24px;flex-shrink:0;text-align:center;color:#6e7681;font-size:10px">&#9660;</span>
          </div>
          <div id="rr-expand-${s.scenario_id}" style="display:none;padding:10px 12px;background:#0d1117;border-top:1px solid #21262d">
            ${_rrEditForm(s)}
          </div>
        </div>`;
    }).join('');
    el.innerHTML = header + rows;
  } catch(e) {
    el.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load regional scenarios.</div>';
  }
}

function _rrEditForm(s) {
  return `<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Scenario Name</div>
      <input id="rr-name-${s.scenario_id}" value="${s.scenario_name}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Department</div>
      <input id="rr-dept-${s.scenario_id}" value="${s.department}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">VaCR (USD)</div>
      <input id="rr-vacr-${s.scenario_id}" type="number" value="${s.value_at_cyber_risk_usd || 0}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Region</div>
      <select id="rr-region-${s.scenario_id}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box">
        ${['APAC','AME','LATAM','MED','NCE'].map(r => `<option value="${r}"${r===s.region?' selected':''}>${r}</option>`).join('')}
      </select>
    </div>
  </div>
  <div style="margin-bottom:8px">
    <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Critical Assets (comma-separated)</div>
    <textarea id="rr-assets-${s.scenario_id}" rows="2" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none;resize:vertical">${(s.critical_assets||[]).join(', ')}</textarea>
  </div>
  <div style="display:flex;gap:8px">
    <button onclick="saveRegionalScenario('${s.scenario_id}')" style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:3px 12px;border-radius:2px;cursor:pointer">Save</button>
    <button onclick="toggleRRRow('${s.scenario_id}')" style="font-size:10px;color:#6e7681;background:none;border:1px solid #30363d;padding:3px 12px;border-radius:2px;cursor:pointer">Cancel</button>
    <button onclick="deleteRegionalScenario('${s.scenario_id}')" style="font-size:10px;color:#f85149;background:none;border:1px solid #30363d;padding:3px 12px;border-radius:2px;cursor:pointer;margin-left:auto">Delete</button>
  </div>`;
}

function toggleRRRow(scenarioId) {
  const expand = document.getElementById(`rr-expand-${scenarioId}`);
  if (expand) expand.style.display = expand.style.display === 'none' ? 'block' : 'none';
}

async function saveRegionalScenario(scenarioId) {
  const name = document.getElementById(`rr-name-${scenarioId}`).value.trim();
  const dept = document.getElementById(`rr-dept-${scenarioId}`).value.trim();
  const vacr = parseInt(document.getElementById(`rr-vacr-${scenarioId}`).value) || 0;
  const region = document.getElementById(`rr-region-${scenarioId}`).value;
  const assetsRaw = document.getElementById(`rr-assets-${scenarioId}`).value;
  const assets = assetsRaw.split(',').map(a => a.trim()).filter(Boolean);
  const r = await fetch(`/api/risk-register/regional/${scenarioId}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scenario_name: name, department: dept, value_at_cyber_risk_usd: vacr, region, critical_assets: assets})
  });
  if (r.ok) { toggleRRRow(scenarioId); loadRiskRegister(); }
  else { alert('Save failed'); }
}

async function deleteRegionalScenario(scenarioId) {
  if (!confirm(`Delete scenario ${scenarioId}?`)) return;
  const r = await fetch(`/api/risk-register/regional/${scenarioId}`, {method: 'DELETE'});
  if (r.ok) loadRiskRegister();
  else alert('Delete failed');
}

async function addRegionalScenario() {
  const region = prompt('Region (APAC/AME/LATAM/MED/NCE):')?.toUpperCase();
  if (!['APAC','AME','LATAM','MED','NCE'].includes(region)) return;
  const r = await fetch('/api/risk-register/regional', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({region, scenario_name: 'New Scenario', department: '', critical_assets: [], value_at_cyber_risk_usd: 0})
  });
  if (r.ok) loadRiskRegister();
  else alert('Add failed');
}
```

- [ ] **Step 6: Verify in browser**

Open `http://localhost:8001` → Risk Register tab. You should see the Regional Scenarios table with 5 rows. Click a row to expand edit form. Edit VaCR, click Save — row should update without page reload.

- [ ] **Step 7: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(risk-register): regional scenarios editor panel with inline CRUD"
```

---

### Task 4: Master Scenarios editor panel (JS only)

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add loadMasterScenarios and CRUD handlers to app.js**

Append after `addRegionalScenario`:

```javascript
async function loadMasterScenarios() {
  const el = document.getElementById('rr-master-table');
  try {
    const data = await fetch('/api/risk-register/master').then(r => r.json());
    const scenarios = data.scenarios || [];
    if (!scenarios.length) {
      el.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No master scenarios.</div>';
      return;
    }
    const header = `<div style="display:flex;padding:5px 12px;border-bottom:1px solid #21262d;font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#484f58">
      <span style="flex:1">Incident Type</span>
      <span style="width:70px;flex-shrink:0;text-align:right">Freq Rank</span>
      <span style="width:80px;flex-shrink:0;text-align:right">Fin. Rank</span>
      <span style="width:80px;flex-shrink:0;text-align:right">Freq %</span>
      <span style="width:80px;flex-shrink:0;text-align:right">Fin. %</span>
      <span style="width:24px;flex-shrink:0"></span>
    </div>`;
    const rows = scenarios.map(s => {
      const safeId = s.incident_type.replace(/\s+/g, '_');
      return `
        <div class="rr-master-row" data-type="${s.incident_type}" style="border-bottom:1px solid #21262d">
          <div onclick="toggleMasterRow('${safeId}')" style="display:flex;align-items:center;padding:7px 12px;font-size:11px;cursor:pointer">
            <span style="color:#e6edf3;flex:1">${s.incident_type}</span>
            <span style="color:#8b949e;width:70px;flex-shrink:0;text-align:right;font-family:monospace">#${s.frequency_rank}</span>
            <span style="color:#8b949e;width:80px;flex-shrink:0;text-align:right;font-family:monospace">#${s.financial_rank}</span>
            <span style="color:#3fb950;width:80px;flex-shrink:0;text-align:right;font-family:monospace">${s.event_frequency_pct}%</span>
            <span style="color:#e3b341;width:80px;flex-shrink:0;text-align:right;font-family:monospace">${s.financial_impact_pct}%</span>
            <span style="width:24px;flex-shrink:0;text-align:center;color:#6e7681;font-size:10px">&#9660;</span>
          </div>
          <div id="rr-master-expand-${safeId}" style="display:none;padding:10px 12px;background:#0d1117;border-top:1px solid #21262d">
            ${_masterEditForm(s, safeId)}
          </div>
        </div>`;
    }).join('');
    el.innerHTML = header + rows;
  } catch {
    el.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load master scenarios.</div>';
  }
}

function _masterEditForm(s, safeId) {
  return `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px">
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Frequency Rank</div>
      <input id="ms-freq-rank-${safeId}" type="number" value="${s.frequency_rank}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Financial Rank</div>
      <input id="ms-fin-rank-${safeId}" type="number" value="${s.financial_rank}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Records Rank</div>
      <input id="ms-rec-rank-${safeId}" type="number" value="${s.records_rank}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Event Freq %</div>
      <input id="ms-evt-pct-${safeId}" type="number" step="0.1" value="${s.event_frequency_pct}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Financial Impact %</div>
      <input id="ms-fin-pct-${safeId}" type="number" step="0.1" value="${s.financial_impact_pct}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
    <div>
      <div style="font-size:9px;color:#6e7681;margin-bottom:3px">Records Affected %</div>
      <input id="ms-rec-pct-${safeId}" type="number" step="0.01" value="${s.records_affected_pct}" style="width:100%;background:#161b22;border:1px solid #30363d;color:#e6edf3;font-size:11px;padding:4px 8px;border-radius:2px;box-sizing:border-box;outline:none" />
    </div>
  </div>
  <div style="display:flex;gap:8px">
    <button onclick="saveMasterScenario('${s.incident_type}', '${safeId}')" style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:3px 12px;border-radius:2px;cursor:pointer">Save</button>
    <button onclick="toggleMasterRow('${safeId}')" style="font-size:10px;color:#6e7681;background:none;border:1px solid #30363d;padding:3px 12px;border-radius:2px;cursor:pointer">Cancel</button>
    <button onclick="deleteMasterScenario('${s.incident_type}')" style="font-size:10px;color:#f85149;background:none;border:1px solid #30363d;padding:3px 12px;border-radius:2px;cursor:pointer;margin-left:auto">Delete</button>
  </div>`;
}

function toggleMasterRow(safeId) {
  const el = document.getElementById(`rr-master-expand-${safeId}`);
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

async function saveMasterScenario(incidentType, safeId) {
  const body = {
    frequency_rank: parseInt(document.getElementById(`ms-freq-rank-${safeId}`).value),
    financial_rank: parseInt(document.getElementById(`ms-fin-rank-${safeId}`).value),
    records_rank: parseInt(document.getElementById(`ms-rec-rank-${safeId}`).value),
    event_frequency_pct: parseFloat(document.getElementById(`ms-evt-pct-${safeId}`).value),
    financial_impact_pct: parseFloat(document.getElementById(`ms-fin-pct-${safeId}`).value),
    records_affected_pct: parseFloat(document.getElementById(`ms-rec-pct-${safeId}`).value),
  };
  const encoded = encodeURIComponent(incidentType);
  const r = await fetch(`/api/risk-register/master/${encoded}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  if (r.ok) { toggleMasterRow(safeId); loadMasterScenarios(); }
  else alert('Save failed');
}

async function deleteMasterScenario(incidentType) {
  if (!confirm(`Delete master scenario "${incidentType}"?`)) return;
  const r = await fetch(`/api/risk-register/master/${encodeURIComponent(incidentType)}`, {method: 'DELETE'});
  if (r.ok) loadMasterScenarios();
  else alert('Delete failed');
}

async function addMasterScenario() {
  const name = prompt('New incident type name:')?.trim();
  if (!name) return;
  const r = await fetch('/api/risk-register/master', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({incident_type: name})
  });
  if (r.ok) loadMasterScenarios();
  else { const e = await r.json(); alert(e.error || 'Add failed'); }
}
```

- [ ] **Step 2: Verify in browser**

Open Risk Register tab → Master Scenarios table shows 9 rows. Click "System intrusion" → expand form shows rank/pct fields. Edit Financial Rank, Save → row updates.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(risk-register): master scenarios editor panel with inline CRUD"
```

---

## WORKSTREAM B — VaCR Intelligence Pipeline

### Task 5: vacr_researcher.py

**Files:**
- Create: `tools/vacr_researcher.py`

This script searches industry sources for benchmark cost data per scenario and uses Sonnet to reason whether evidence supports, challenges, or doesn't cover the current VaCR.

- [ ] **Step 1: Create tools/vacr_researcher.py**

```python
#!/usr/bin/env python3
"""VaCR Benchmark Researcher — searches industry sources per scenario and reasons against current VaCR.

Usage:
    uv run python tools/vacr_researcher.py <incident_type> <current_vacr_usd> [--sector energy|manufacturing]

Writes: output/pipeline/vacr_research.json (appends/updates this scenario's entry)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = REPO_ROOT / "output" / "pipeline" / "vacr_research.json"

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

EXTRACTION_PROMPT = """\
You are extracting financial impact data from a cybersecurity industry report.

Extract all dollar-denominated financial impact figures for cyber incidents. For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to (e.g. "manufacturing", "energy", "all")
- cost_low_usd: lower bound in USD as integer (null if not stated)
- cost_median_usd: median or average in USD as integer (null if not stated)
- cost_high_usd: upper bound in USD as integer (null if not stated)
- note: brief description of what this figure represents
- raw_quote: the exact text excerpt this came from (max 200 chars)

Return ONLY a JSON array. If no financial figures found, return [].

Text to analyze:
{raw_text}"""

REASONING_PROMPT = """\
You are a cyber risk quantification analyst reviewing benchmark data against a company's VaCR (Value at Cyber Risk) estimate.

Scenario: {incident_type}
Sector: {sector}
Current VaCR: ${current_vacr_usd:,}

Benchmark findings from industry sources:
{findings_text}

For each finding, assess whether it supports (↑ suggests higher), challenges (↓ suggests lower), or is inconclusive (→) relative to the current VaCR.
Then write a one-sentence agent_summary across all findings.

Return a JSON object:
{{
  "findings": [
    {{
      "source": "<source name>",
      "quote": "<exact quote, max 150 chars>",
      "figure_usd": <median figure as integer, or null>,
      "direction": "↑ or ↓ or → or ?",
      "assessment": "<one sentence>"
    }}
  ],
  "overall_direction": "↑ or ↓ or → or ?",
  "agent_summary": "<one sentence summarising all evidence>"
}}

If no findings provided, return {{"findings": [], "overall_direction": "?", "agent_summary": "No benchmark data found for this scenario."}}
"""


def _search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search using Tavily if key available, else DuckDuckGo."""
    import os
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_key:
        try:
            import requests
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": max_results, "search_depth": "basic"},
                timeout=20,
            )
            results = resp.json().get("results", [])
            return [{"title": r.get("title", ""), "content": r.get("content", ""), "url": r.get("url", "")} for r in results]
        except Exception as e:
            print(f"[vacr-researcher] Tavily failed: {e}", file=sys.stderr)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "content": r.get("body", ""), "url": r.get("href", "")} for r in results]
    except Exception as e:
        print(f"[vacr-researcher] DDG failed: {e}", file=sys.stderr)
        return []


def _extract_figures(text: str, source_name: str) -> list[dict]:
    """Run Haiku over text to extract financial figures."""
    if not text.strip():
        return []
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(raw_text=text[:12_000])}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        figures = json.loads(content)
        for f in figures:
            f["_source_name"] = source_name
            f["_source_url"] = ""
        return figures
    except Exception as e:
        print(f"[vacr-researcher] Haiku extraction failed for {source_name}: {e}", file=sys.stderr)
        return []


def _reason_against_vacr(incident_type: str, current_vacr_usd: int, sector: str, all_figures: list[dict]) -> dict:
    """Run Sonnet to reason whether findings support/challenge the VaCR."""
    if not all_figures:
        findings_text = "No benchmark figures found."
    else:
        lines = []
        for f in all_figures[:20]:  # cap at 20 figures
            src = f.get("_source_name", "Unknown source")
            note = f.get("note", "")
            quote = f.get("raw_quote", "")
            median = f.get("cost_median_usd")
            tag = f.get("scenario_tag", "")
            lines.append(f"- {src}: {tag} | median=${median:,} | {note} | \"{quote}\"" if median else f"- {src}: {tag} | {note} | \"{quote}\"")
        findings_text = "\n".join(lines)

    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": REASONING_PROMPT.format(
                incident_type=incident_type,
                sector=sector,
                current_vacr_usd=current_vacr_usd,
                findings_text=findings_text,
            )}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        print(f"[vacr-researcher] Sonnet reasoning failed: {e}", file=sys.stderr)
        return {
            "findings": [],
            "overall_direction": "?",
            "agent_summary": f"Reasoning failed: {e}",
        }


def research_scenario(incident_type: str, current_vacr_usd: int, sector: str = "energy") -> dict:
    """Full pipeline for one scenario. Returns result dict."""
    print(f"[vacr-researcher] Researching: {incident_type} (VaCR ${current_vacr_usd:,})", file=sys.stderr)

    # Build queries targeting known benchmark sources
    queries = [
        f'"{incident_type}" cost {sector} 2024 2025 site:ibm.com OR site:verizon.com OR site:mandiant.com',
        f'"{incident_type}" financial impact manufacturing energy 2024 benchmark',
        f'"{incident_type}" average cost USD million 2024 2025 industry report',
    ]

    all_figures = []
    for query in queries:
        print(f"[vacr-researcher]   Searching: {query[:80]}...", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            source_name = r.get("title") or r.get("url", "Unknown")
            figures = _extract_figures(content, source_name)
            # Only keep figures matching this scenario type
            relevant = [f for f in figures if incident_type.lower() in f.get("scenario_tag", "").lower()
                        or f.get("scenario_tag", "") == incident_type]
            all_figures.extend(relevant)

    reasoning = _reason_against_vacr(incident_type, current_vacr_usd, sector, all_figures)

    result = {
        "incident_type": incident_type,
        "current_vacr_usd": current_vacr_usd,
        "sector": sector,
        "direction": reasoning.get("overall_direction", "?"),
        "findings": reasoning.get("findings", []),
        "agent_summary": reasoning.get("agent_summary", ""),
        "researched_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def _update_output(result: dict) -> None:
    """Append/replace this scenario's result in output/pipeline/vacr_research.json."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {"generated_at": None, "results": []}

    # Replace existing entry for this incident_type or append
    results = [r for r in existing.get("results", []) if r.get("incident_type") != result["incident_type"]]
    results.append(result)
    existing["results"] = results
    existing["generated_at"] = datetime.now(timezone.utc).isoformat()
    OUTPUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: vacr_researcher.py <incident_type> <current_vacr_usd> [--sector energy|manufacturing]", file=sys.stderr)
        sys.exit(1)
    incident_type = sys.argv[1]
    current_vacr_usd = int(sys.argv[2])
    sector = "energy"
    if "--sector" in sys.argv:
        idx = sys.argv.index("--sector")
        sector = sys.argv[idx + 1]
    result = research_scenario(incident_type, current_vacr_usd, sector)
    _update_output(result)
    print(json.dumps(result, indent=2))
```

- [ ] **Step 2: Smoke-test the script**

```bash
uv run python tools/vacr_researcher.py "Ransomware" 22000000 --sector manufacturing 2>&1 | tail -20
```
Expected: JSON output with `incident_type: "Ransomware"`, `direction` field, `findings` array (may be empty in mock/offline env), `output/pipeline/vacr_research.json` written.

- [ ] **Step 3: Commit**

```bash
git add tools/vacr_researcher.py
git commit -m "feat(risk-register): add vacr_researcher.py — benchmark web search + Haiku extract + Sonnet reasoning"
```

---

### Task 6: Server endpoints — Research trigger + SSE + results

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add research_state and three endpoints to server.py**

After the `threat_landscape_state` dict (around line 43), add:

```python
research_state = {
    "running": False,
    "progress": [],   # list of {incident_type, status: "running"|"done"|"error"}
    "started_at": None,
}
```

Then after the `delete_master_scenario` endpoint (end of Task 2 block), append:

```python
# ── API: Risk Register — VaCR Research Pipeline ──────────────────────────

@app.get("/api/risk-register/research")
async def get_research_results():
    data = _read_json(PIPELINE / "vacr_research.json")
    return data or {"generated_at": None, "results": []}


@app.post("/api/risk-register/research")
async def trigger_research():
    if research_state["running"]:
        return JSONResponse({"error": "Research already running"}, status_code=409)
    asyncio.create_task(_run_research())
    return {"started": True}


@app.get("/api/risk-register/research/status")
async def get_research_status():
    return research_state


async def _run_research():
    """Run vacr_researcher.py for all master scenarios in parallel. Emits SSE events."""
    import importlib.util, sys as _sys
    research_state.update(running=True, progress=[], started_at=time.time())
    await _emit("research", {"status": "started"})

    # Load master scenarios to get incident types + find matching regional VaCR
    master_data = _read_json(BASE / "data" / "master_scenarios.json") or {}
    scenarios = master_data.get("scenarios", [])
    regional_data = _read_json(BASE / "data" / "mock_crq_database.json") or {}

    # Build a map of incident_type -> best VaCR (highest across regions for that scenario)
    # Since regional scenarios use different names, we use the highest regional VaCR as proxy
    all_regional_vacr = [
        s.get("value_at_cyber_risk_usd", 0)
        for region_list in regional_data.values()
        for s in region_list
        if s.get("value_at_cyber_risk_usd", 0) > 0
    ]
    default_vacr = max(all_regional_vacr) if all_regional_vacr else 0

    research_state["progress"] = [{"incident_type": s["incident_type"], "status": "pending"} for s in scenarios]

    async def _research_one(scenario: dict) -> None:
        incident_type = scenario["incident_type"]
        # Update progress
        for p in research_state["progress"]:
            if p["incident_type"] == incident_type:
                p["status"] = "running"
        done_count = sum(1 for p in research_state["progress"] if p["status"] == "done")
        await _emit("research", {"status": "step", "incident_type": incident_type,
                                  "message": f"Researching: {incident_type}... [{done_count}/{len(scenarios)} complete]"})
        try:
            # Run in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            spec = importlib.util.spec_from_file_location("vacr_researcher", BASE / "tools" / "vacr_researcher.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            result = await loop.run_in_executor(
                None,
                lambda: mod.research_scenario(incident_type, default_vacr, "energy")
            )
            mod._update_output(result)

            for p in research_state["progress"]:
                if p["incident_type"] == incident_type:
                    p["status"] = "done"
            done_count = sum(1 for p in research_state["progress"] if p["status"] == "done")
            await _emit("research", {"status": "step", "incident_type": incident_type,
                                      "message": f"Done: {incident_type} [{done_count}/{len(scenarios)} complete]"})
        except Exception as exc:
            for p in research_state["progress"]:
                if p["incident_type"] == incident_type:
                    p["status"] = "error"
            await _emit("research", {"status": "error", "incident_type": incident_type, "message": str(exc)})

    try:
        await asyncio.gather(*[_research_one(s) for s in scenarios])
        await _emit("research", {"status": "complete"})
    except Exception as exc:
        await _emit("research", {"status": "error", "message": str(exc)})
    finally:
        research_state.update(running=False)
```

- [ ] **Step 2: Verify endpoints exist**

```bash
curl -s http://localhost:8001/api/risk-register/research | python -c "import sys,json; d=json.load(sys.stdin); print('results:', len(d.get('results',[])))"
```
Expected: `results: 0` (or count of previously researched scenarios)

```bash
curl -s http://localhost:8001/api/risk-register/research/status
```
Expected: `{"running": false, "progress": [], "started_at": null}`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat(risk-register): add research pipeline endpoints — trigger, SSE, results"
```

---

### Task 7: Research UI — button, progress, findings expand

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add runResearch and _listenResearchSSE to app.js**

Append after `_listenValidationSSE`:

```javascript
async function runResearch() {
  const btn = document.getElementById('btn-run-research');
  const prog = document.getElementById('research-progress');
  btn.disabled = true;
  prog.style.display = 'block';
  prog.textContent = 'Starting research run...';
  try {
    const r = await fetch('/api/risk-register/research', {method: 'POST'});
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      prog.textContent = `Error: ${err.error || 'Run failed'}`;
      btn.disabled = false;
      return;
    }
    _listenResearchSSE(btn, prog);
  } catch {
    prog.textContent = 'Server offline';
    btn.disabled = false;
  }
}

function _listenResearchSSE(btn, prog) {
  const es = new EventSource('/api/logs/stream');
  es.addEventListener('research', e => {
    const d = JSON.parse(e.data);
    if (d.status === 'step') {
      prog.textContent = d.message || d.incident_type || 'Researching...';
    } else if (d.status === 'complete') {
      prog.textContent = '✓ Research complete';
      btn.disabled = false;
      es.close();
      // Reload scenarios table to show research expand arrows
      loadValScenarios();
    } else if (d.status === 'error') {
      prog.textContent = `✗ Error: ${d.message || d.incident_type || 'unknown'}`;
      btn.disabled = false;
      es.close();
    }
  });
  setTimeout(() => { es.close(); btn.disabled = false; }, 600_000);
}
```

- [ ] **Step 2: Update loadValScenarios to show research expand arrows**

Find `loadValScenarios` in `app.js`. The function currently builds rows and sets `el.innerHTML`. Modify the row-building section to:

1. Fetch research results alongside flags: `const [data, research] = await Promise.all([fetch('/api/validation/flags').then(r=>r.json()), fetch('/api/risk-register/research').then(r=>r.json()).catch(()=>({results:[]}))])`

2. Build a lookup map: `const researchMap = Object.fromEntries((research.results||[]).map(r => [r.incident_type, r]))`

3. In each row, add a research expand arrow if findings exist:
```javascript
const resResult = researchMap[s.scenario];
const hasResearch = resResult && resResult.findings && resResult.findings.length > 0;
const directionIcon = resResult ? (resResult.direction === '↑' ? '↑' : resResult.direction === '↓' ? '↓' : resResult.direction === '→' ? '→' : '?') : '';
const dirColor = resResult?.direction === '↑' ? '#f85149' : resResult?.direction === '↓' ? '#3fb950' : '#8b949e';
```

4. Add direction + expand toggle to each row:
```javascript
return `<div style="border-bottom:1px solid #21262d">
  <div style="display:flex;align-items:center;padding:7px 12px;font-size:11px${hasResearch ? ';cursor:pointer' : ''}"
       ${hasResearch ? `onclick="toggleResearchExpand('${s.scenario}')"` : ''}>
    <span style="color:#e6edf3;width:180px;flex-shrink:0">${s.scenario}</span>
    <span style="color:#8b949e;width:60px;flex-shrink:0;font-family:monospace">${vacr}</span>
    <span style="color:${verdictColor};width:120px;flex-shrink:0;font-weight:500">${verdict}</span>
    <span style="color:#6e7681;width:60px;flex-shrink:0">${dev}</span>
    <span style="width:100px;flex-shrink:0">${osintBadges}</span>
    <span style="width:80px;flex-shrink:0">${velLabel}</span>
    <span style="color:#484f58;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${srcLabel}</span>
    ${hasResearch ? `<span style="color:${dirColor};width:30px;flex-shrink:0;text-align:right;font-weight:700">${directionIcon}</span>` : '<span style="width:30px;flex-shrink:0"></span>'}
  </div>
  ${hasResearch ? `<div id="research-expand-${s.scenario.replace(/\s+/g,'_')}" style="display:none;padding:10px 12px;background:#0d1117;border-top:1px solid #21262d">
    ${_renderResearchFindings(resResult)}
  </div>` : ''}
</div>`;
```

5. Add helper functions after `loadValScenarios`:
```javascript
function toggleResearchExpand(scenario) {
  const id = `research-expand-${scenario.replace(/\s+/g,'_')}`;
  const el = document.getElementById(id);
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function _renderResearchFindings(res) {
  const dirColors = {'↑': '#f85149', '↓': '#3fb950', '→': '#8b949e', '?': '#6e7681'};
  const findings = (res.findings || []).map(f => {
    const dc = dirColors[f.direction] || '#6e7681';
    const fig = f.figure_usd ? `$${(f.figure_usd/1e6).toFixed(2)}M` : '';
    return `<div style="padding:6px 0;border-bottom:1px solid #21262d;display:flex;gap:10px;align-items:flex-start">
      <span style="color:${dc};font-size:14px;font-weight:700;flex-shrink:0;width:16px">${f.direction}</span>
      <div style="flex:1;min-width:0">
        <div style="display:flex;gap:8px;align-items:baseline;margin-bottom:2px">
          <span style="color:#58a6ff;font-size:10px;font-weight:600">${f.source}</span>
          ${fig ? `<span style="color:#e3b341;font-family:monospace;font-size:10px">${fig}</span>` : ''}
        </div>
        ${f.quote ? `<div style="color:#6e7681;font-size:10px;font-style:italic;margin-bottom:2px">"${f.quote}"</div>` : ''}
        <div style="color:#8b949e;font-size:11px">${f.assessment}</div>
      </div>
    </div>`;
  }).join('');
  return `<div style="margin-bottom:8px;padding:6px 8px;background:#161b22;border-radius:2px;font-size:11px;color:#c9d1d9;font-style:italic">${res.agent_summary}</div>
    ${findings || '<div style="color:#6e7681;font-size:11px">No findings.</div>'}`;
}
```

- [ ] **Step 3: Verify in browser**

Run Research → progress line updates with scenario names. After complete, click a scenario row → expands to show direction arrow, source badges, quotes, assessments.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(risk-register): research UI — progress SSE, findings expand per scenario"
```

---

### Task 8: Wire archive_run.py to include vacr_research.json

**Files:**
- Verify: `tools/archive_run.py`

- [ ] **Step 1: Check archive_run.py copies all pipeline files**

```bash
grep -n "vacr\|glob\|pipeline\|copy" tools/archive_run.py | head -20
```

If `archive_run.py` copies all files from `output/pipeline/` with a glob (e.g. `shutil.copytree` or `glob("output/pipeline/*.json")`), no change is needed — `vacr_research.json` is automatically included.

If it has an explicit allowlist, add `"vacr_research.json"` to it.

- [ ] **Step 2: Verify (after a research run)**

```bash
uv run python tools/archive_run.py
ls output/runs/$(ls output/runs/ | tail -1)/ | grep vacr
```
Expected: `vacr_research.json` present in the latest archived run folder.

- [ ] **Step 3: Commit only if archive_run.py was modified**

```bash
git add tools/archive_run.py
git commit -m "feat(risk-register): include vacr_research.json in run archive"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| Tab rename Validate → Risk Register | Task 3 Step 1 |
| Regional Scenarios panel with inline CRUD | Tasks 1 + 3 |
| Master Scenarios panel with inline CRUD | Tasks 2 + 4 |
| Critical assets as tag chips / comma textarea | Task 3 Step 5 (`_rrEditForm`) |
| Add/Delete row buttons | Tasks 3 + 4 |
| `tools/vacr_researcher.py` — search + extract + reason | Task 5 |
| Server research trigger endpoint | Task 6 |
| SSE progress stream | Task 6 (`_emit("research", ...)`) |
| RUN RESEARCH button | Task 3 Step 3 |
| Progress line `Researching: X [N/9 complete]` | Task 7 Step 1 |
| Expandable findings row with direction + source + quote | Task 7 Step 2 |
| `output/pipeline/vacr_research.json` storage | Task 5 (`_update_output`) |
| Archive per run | Task 8 |

**All requirements covered. No placeholders found.**

**Type consistency:** `scenario_id` used consistently for regional CRUD. `incident_type` used for master CRUD. `encodeURIComponent` applied before URL use in JS. `_emit("research", ...)` matches SSE listener `es.addEventListener('research', ...)`.
