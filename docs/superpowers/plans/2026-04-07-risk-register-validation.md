# Risk Register Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-register support and a dedicated VaCR source validation pipeline that finds quantitative sources (monetary + probability) and maps them to register scenarios to produce per-scenario verdicts.

**Architecture:** Registers are JSON files in `data/registers/`. A persistent register bar in the UI lets the user switch the active register. A separate `/validate-register` command runs `tools/register_validator.py` → `register-validator-agent` to produce `output/validation/register_validation.json`. The geopolitical intelligence pipeline is untouched.

**Tech Stack:** FastAPI (`server.py`), SQLite (`data/sources.db`), Vanilla JS + Tailwind (`static/`), Anthropic SDK (`tools/suggest_tags.py`), Claude agent (`.claude/agents/`), Claude command (`.claude/commands/`)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `data/registers/aerogrid_enterprise.json` | Seed register — full enterprise |
| Create | `data/registers/wind_power_plant.json` | Seed register — wind park |
| Create | `data/active_register.json` | Active register pointer |
| Modify | `tools/update_source_registry.py` | DB migration — 3 new columns |
| Create | `tools/suggest_tags.py` | LLM tag suggestion script |
| Create | `tools/register_validator.py` | Validation pipeline — collect + score sources |
| Modify | `server.py` | 9 new API endpoints |
| Create | `.claude/agents/register-validator-agent.md` | Agent — produces register_validation.json |
| Create | `.claude/commands/validate-register.md` | Orchestrator command |
| Modify | `static/index.html` | Register bar, drawer, form, validation results section |
| Modify | `static/app.js` | Register state, drawer JS, form JS, validation results render |

---

## Task 1: DB Migration — add quantitative data columns to sources_registry

**Files:**
- Modify: `tools/update_source_registry.py`

- [ ] **Step 1: Add `migrate_db()` function after `init_db()`**

In `tools/update_source_registry.py`, add this function immediately after `init_db()`:

```python
def migrate_db(conn: sqlite3.Connection) -> None:
    """Idempotent migrations — ALTER TABLE fails silently if column exists."""
    migrations = [
        "ALTER TABLE sources_registry ADD COLUMN has_quantitative_data INTEGER DEFAULT 0",
        "ALTER TABLE sources_registry ADD COLUMN quantitative_figure TEXT",
        "ALTER TABLE sources_registry ADD COLUMN source_tags TEXT DEFAULT '[]'",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
```

- [ ] **Step 2: Call `migrate_db()` in the main flow**

Find the line in `tools/update_source_registry.py` where `init_db(conn)` is called (in the `main()` function or equivalent). Add `migrate_db(conn)` immediately after it:

```python
conn = sqlite3.connect(str(DB_PATH))
init_db(conn)
migrate_db(conn)   # ← add this line
```

- [ ] **Step 3: Verify migration runs cleanly**

```bash
uv run python tools/update_source_registry.py
```

Expected: exits 0 with no errors. Run a second time — must also exit 0 (idempotency check).

- [ ] **Step 4: Confirm columns exist**

```bash
uv run python -c "
import sqlite3
conn = sqlite3.connect('data/sources.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(sources_registry)').fetchall()]
assert 'has_quantitative_data' in cols, 'missing has_quantitative_data'
assert 'quantitative_figure' in cols, 'missing quantitative_figure'
assert 'source_tags' in cols, 'missing source_tags'
print('OK — all 3 columns present')
"
```

Expected output: `OK — all 3 columns present`

- [ ] **Step 5: Commit**

```bash
git add tools/update_source_registry.py
git commit -m "feat(db): add quantitative data + source_tags columns to sources_registry"
```

---

## Task 2: Seed Register Data Files

**Files:**
- Create: `data/registers/aerogrid_enterprise.json`
- Create: `data/registers/wind_power_plant.json`
- Create: `data/active_register.json`

- [ ] **Step 1: Create `data/registers/` directory and aerogrid_enterprise.json**

```bash
mkdir -p data/registers
```

Create `data/registers/aerogrid_enterprise.json`:

```json
{
  "register_id": "aerogrid_enterprise",
  "display_name": "AeroGrid Enterprise",
  "company_context": "Renewable energy company. 75% wind turbine manufacturing, 25% global service and maintenance. Crown jewels: proprietary turbine aerodynamic designs, OT/SCADA networks in blade manufacturing plants, real-time predictive maintenance algorithms, live telemetry data from wind farms.",
  "created_at": "2026-04-07",
  "last_validated_at": null,
  "scenarios": [
    {
      "scenario_id": "AE-001",
      "scenario_name": "Manufacturing IP and SCADA Compromise",
      "description": "Adversary exfiltrates proprietary turbine aerodynamic designs or compromises OT/SCADA networks in blade manufacturing plants, disrupting production and exposing IP.",
      "search_tags": ["ot_systems", "scada", "manufacturing", "ip_theft", "wind_turbine"],
      "value_at_cyber_risk_usd": 18500000,
      "figure_source": "internal_estimate",
      "probability_pct": 31.7,
      "probability_source": "industry_report"
    },
    {
      "scenario_id": "AE-002",
      "scenario_name": "Wind Farm Telemetry and Maintenance Disruption",
      "description": "Attack on live telemetry systems or remote maintenance scheduling disrupts service delivery and offshore wind farm operations.",
      "search_tags": ["telemetry", "remote_maintenance", "wind_farm", "energy_operator", "ransomware"],
      "value_at_cyber_risk_usd": 22000000,
      "figure_source": "internal_estimate",
      "probability_pct": 43.3,
      "probability_source": "industry_report"
    },
    {
      "scenario_id": "AE-003",
      "scenario_name": "Ransomware — Enterprise-wide",
      "description": "Ransomware encrypts corporate IT and OT systems across manufacturing and service divisions, causing operational shutdown and ransom demand.",
      "search_tags": ["ransomware", "manufacturing", "energy", "enterprise"],
      "value_at_cyber_risk_usd": 12000000,
      "figure_source": "internal_estimate",
      "probability_pct": 31.7,
      "probability_source": "industry_report"
    }
  ]
}
```

- [ ] **Step 2: Create `data/registers/wind_power_plant.json`**

```json
{
  "register_id": "wind_power_plant",
  "display_name": "Wind Power Plant",
  "company_context": "Pure wind power plant operator. No manufacturing. Primary assets: wind turbines, grid connections, OT/SCADA control systems, energy generation capacity.",
  "created_at": "2026-04-07",
  "last_validated_at": null,
  "scenarios": [
    {
      "scenario_id": "WP-001",
      "scenario_name": "Wind Farm OT Ransomware",
      "description": "Ransomware attack targeting OT/SCADA systems controlling wind turbines. Could cause full site shutdown and loss of grid generation capacity.",
      "search_tags": ["ot_systems", "energy_operator", "ransomware", "scada", "wind_turbine"],
      "value_at_cyber_risk_usd": 8000000,
      "figure_source": "internal_estimate",
      "probability_pct": 12.0,
      "probability_source": "internal_estimate"
    },
    {
      "scenario_id": "WP-002",
      "scenario_name": "OT System Intrusion",
      "description": "Adversary gains persistent access to wind farm control systems. Could enable sabotage, data theft, or ransomware staging.",
      "search_tags": ["ot_systems", "system_intrusion", "energy_operator", "wind_farm"],
      "value_at_cyber_risk_usd": 5200000,
      "figure_source": "internal_estimate",
      "probability_pct": 31.0,
      "probability_source": "industry_report"
    },
    {
      "scenario_id": "WP-003",
      "scenario_name": "Physical Site Sabotage",
      "description": "Physical attack or sabotage at remote unmanned wind park sites. Includes deliberate damage to turbines, substations, or grid connection infrastructure.",
      "search_tags": ["physical_security", "energy_infrastructure", "sabotage", "wind_farm"],
      "value_at_cyber_risk_usd": 3100000,
      "figure_source": "internal_estimate",
      "probability_pct": 3.3,
      "probability_source": "industry_report"
    }
  ]
}
```

- [ ] **Step 3: Create `data/active_register.json`**

```json
{ "register_id": "aerogrid_enterprise" }
```

- [ ] **Step 4: Verify JSON is valid**

```bash
uv run python -c "
import json
from pathlib import Path
for p in Path('data/registers').glob('*.json'):
    json.loads(p.read_text())
    print(f'OK: {p.name}')
json.loads(Path('data/active_register.json').read_text())
print('OK: active_register.json')
"
```

Expected: 3 OK lines, no errors.

- [ ] **Step 5: Commit**

```bash
git add data/registers/ data/active_register.json
git commit -m "feat(data): seed aerogrid_enterprise and wind_power_plant registers"
```

---

## Task 3: Register CRUD + Active Register API

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add REGISTERS_DIR constant and helper near top of `server.py`**

After the existing path constants (OUTPUT, DELIVERABLES, etc.), add:

```python
REGISTERS_DIR    = BASE / "data" / "registers"
ACTIVE_REGISTER  = BASE / "data" / "active_register.json"
```

Also add a helper after `_read_json`:

```python
def _active_register_id() -> str:
    data = _read_json(ACTIVE_REGISTER)
    return data.get("register_id", "aerogrid_enterprise") if data else "aerogrid_enterprise"
```

- [ ] **Step 2: Add GET /api/registers endpoint**

```python
@app.get("/api/registers")
async def list_registers():
    REGISTERS_DIR.mkdir(parents=True, exist_ok=True)
    active_id = _active_register_id()
    registers = []
    for f in sorted(REGISTERS_DIR.glob("*.json")):
        data = _read_json(f)
        if data:
            data["is_active"] = data.get("register_id") == active_id
            registers.append(data)
    return registers
```

- [ ] **Step 3: Add POST /api/registers endpoint**

```python
@app.post("/api/registers")
async def create_register(payload: dict):
    register_id = payload.get("register_id", "").strip()
    if not register_id:
        return JSONResponse({"error": "register_id required"}, status_code=400)
    path = REGISTERS_DIR / f"{register_id}.json"
    if path.exists():
        return JSONResponse({"error": f"Register '{register_id}' already exists"}, status_code=409)
    REGISTERS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
```

- [ ] **Step 4: Add PUT /api/registers/{register_id} endpoint**

```python
@app.put("/api/registers/{register_id}")
async def update_register(register_id: str, payload: dict):
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    payload["register_id"] = register_id
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
```

- [ ] **Step 5: Add DELETE /api/registers/{register_id} endpoint**

```python
@app.delete("/api/registers/{register_id}")
async def delete_register(register_id: str):
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    if _active_register_id() == register_id:
        return JSONResponse({"error": "Cannot delete the active register"}, status_code=409)
    path.unlink()
    return {"deleted": register_id}
```

- [ ] **Step 6: Add GET + POST /api/registers/active endpoints**

```python
@app.get("/api/registers/active")
async def get_active_register():
    active_id = _active_register_id()
    path = REGISTERS_DIR / f"{active_id}.json"
    data = _read_json(path)
    return data or {"error": "active register file not found", "register_id": active_id}


@app.post("/api/registers/active")
async def set_active_register(payload: dict):
    register_id = payload.get("register_id", "").strip()
    if not register_id:
        return JSONResponse({"error": "register_id required"}, status_code=400)
    path = REGISTERS_DIR / f"{register_id}.json"
    if not path.exists():
        return JSONResponse({"error": f"Register '{register_id}' not found"}, status_code=404)
    ACTIVE_REGISTER.write_text(json.dumps({"register_id": register_id}), encoding="utf-8")
    return {"active": register_id}
```

- [ ] **Step 7: Start server and smoke-test**

```bash
uv run uvicorn server:app --reload --port 8000
```

In a second terminal:
```bash
curl -s http://localhost:8000/api/registers | python -m json.tool
curl -s http://localhost:8000/api/registers/active | python -m json.tool
curl -s -X POST http://localhost:8000/api/registers/active \
  -H "Content-Type: application/json" \
  -d '{"register_id":"wind_power_plant"}' | python -m json.tool
curl -s http://localhost:8000/api/registers/active | python -m json.tool
```

Expected: list shows 2 registers; active switches to wind_power_plant.

- [ ] **Step 8: Commit**

```bash
git add server.py
git commit -m "feat(api): register CRUD and active register endpoints"
```

---

## Task 4: LLM Tag Suggestion — tool script + API endpoint

**Files:**
- Create: `tools/suggest_tags.py`
- Modify: `server.py`

- [ ] **Step 1: Add anthropic SDK dependency**

```bash
uv add anthropic
```

Expected: `pyproject.toml` updated, no errors.

- [ ] **Step 2: Create `tools/suggest_tags.py`**

```python
"""
suggest_tags.py — LLM-assisted search tag generation for register scenarios.

Usage:
    uv run python tools/suggest_tags.py --name "Wind Farm OT Ransomware" \
        --description "Ransomware targeting SCADA systems..."
Outputs: JSON array of tags to stdout.
"""

import argparse
import json
import sys

import anthropic


def suggest_tags(name: str, description: str) -> list[str]:
    client = anthropic.Anthropic()
    prompt = (
        f"You are helping build search tags for a cyber risk scenario so a pipeline can find "
        f"quantitative sources (dollar figures and probability percentages) about it.\n\n"
        f"Scenario name: {name}\n"
        f"Description: {description}\n\n"
        f"Return ONLY a JSON array of 4-8 lowercase snake_case search tags. "
        f"Tags should capture: industry sector, attack type, asset type, and threat actor context. "
        f"Example: [\"ot_systems\", \"energy_operator\", \"ransomware\", \"scada\"]\n\n"
        f"JSON array only — no explanation, no markdown."
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", required=True)
    args = parser.parse_args()
    tags = suggest_tags(args.name, args.description)
    print(json.dumps(tags))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test the script directly**

```bash
uv run python tools/suggest_tags.py \
  --name "Wind Farm OT Ransomware" \
  --description "Ransomware attack targeting OT/SCADA systems controlling wind turbines"
```

Expected: JSON array like `["ot_systems", "energy_operator", "ransomware", "scada", "wind_turbine"]`

- [ ] **Step 4: Add `POST /api/registers/suggest-tags` endpoint to `server.py`**

Add after the register CRUD endpoints (before other sections):

```python
@app.post("/api/registers/suggest-tags")
async def suggest_register_tags(payload: dict):
    name = payload.get("name", "").strip()
    description = payload.get("description", "").strip()
    if not name or not description:
        return JSONResponse({"error": "name and description required"}, status_code=400)
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "python", str(BASE / "tools" / "suggest_tags.py"),
        "--name", name, "--description", description,
        cwd=str(BASE),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return JSONResponse({"error": stderr.decode(errors="replace")[:200]}, status_code=500)
    try:
        tags = json.loads(stdout.decode().strip())
        return {"tags": tags}
    except json.JSONDecodeError:
        return JSONResponse({"error": "tag suggestion returned invalid JSON"}, status_code=500)
```

- [ ] **Step 5: Test endpoint**

```bash
curl -s -X POST http://localhost:8000/api/registers/suggest-tags \
  -H "Content-Type: application/json" \
  -d '{"name":"Wind Farm OT Ransomware","description":"Ransomware targeting SCADA"}' \
  | python -m json.tool
```

Expected: `{"tags": ["ot_systems", ...]}`

- [ ] **Step 6: Commit**

```bash
git add tools/suggest_tags.py server.py
git commit -m "feat(api): LLM tag suggestion endpoint for register scenarios"
```

---

## Task 5: Register Bar — persistent UI element

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add register bar CSS to the `<style>` block in `index.html`**

Find `/* Header */` in the `<style>` block. Add after the `#app-header` CSS rule:

```css
/* Register bar */
#register-bar {
  position: fixed; top: 36px; left: 0; right: 0; z-index: 35;
  height: 24px;
  background: #080c10;
  border-bottom: 1px solid #21262d;
  display: flex; align-items: center;
  padding: 0 16px; gap: 8px;
  font-size: 10px;
}
#register-drawer {
  position: fixed; top: 60px; left: 16px; z-index: 50;
  background: #0d1117; border: 1px solid #21262d; border-radius: 4px;
  width: 320px; overflow: hidden;
  display: none;
}
```

- [ ] **Step 2: Update body `padding-top` and all fixed-height tabs**

In the `<style>` block, change:
```css
body { background: #070a0e; color: #c9d1d9; padding-top: 36px; }
```
to:
```css
body { background: #070a0e; color: #c9d1d9; padding-top: 60px; }
```

Also update `#tab-overview` and `#tab-sources`:
```css
#tab-overview { flex-direction: column; height: calc(100vh - 60px); }
```
```css
/* Find the tab-sources inline style — update it to: */
/* max-height: calc(100vh - 60px) */
```

For `tab-sources`, the inline style is on the element itself (line 907). Change `max-height:calc(100vh - 36px)` to `max-height:calc(100vh - 60px)`.

- [ ] **Step 3: Add register bar HTML after the `<header>` element**

Find the closing `</header>` tag in `index.html`. Add immediately after it:

```html
<!-- Register bar -->
<div id="register-bar">
  <span style="color:#6e7681">▣</span>
  <span style="color:#6e7681">Active:</span>
  <span id="register-bar-name" style="color:#c9d1d9;font-weight:600">—</span>
  <span style="color:#21262d">·</span>
  <span id="register-bar-count" style="color:#484f58">— scenarios</span>
  <span style="flex:1"></span>
  <span id="register-bar-toggle" onclick="toggleRegisterDrawer()"
    style="color:#6e7681;cursor:pointer;letter-spacing:0.04em">Switch Register ▾</span>
</div>

<!-- Register drawer (hidden by default) -->
<div id="register-drawer">
  <div style="padding:8px 12px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #21262d">
    <span style="font-size:10px;font-weight:600;color:#8b949e;letter-spacing:0.05em">RISK REGISTERS</span>
    <button onclick="showRegisterForm()" style="background:#238636;color:#fff;border:none;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">+ New</button>
  </div>
  <div id="register-list" style="max-height:240px;overflow-y:auto"></div>
  <div id="register-form-panel" style="display:none;border-top:1px solid #21262d;padding:12px"></div>
</div>
```

- [ ] **Step 4: Verify layout**

Start the server and open `http://localhost:8000`. Confirm:
- Register bar appears below the nav at correct height
- No content is hidden behind the bars
- All tabs scroll correctly

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): add persistent register bar and drawer shell"
```

---

## Task 6: Register Drawer State and JS

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add register state to the `state` object**

Find the `let state = {` block. Add these fields:

```js
registers: [],
activeRegister: null,
registerDrawerOpen: false,
```

- [ ] **Step 2: Add `loadRegisters()` function**

Add in Section 4 (API functions), after `loadLatestData`:

```js
async function loadRegisters() {
  const registers = await fetchJSON('/api/registers');
  if (!registers) return;
  state.registers = registers;
  state.activeRegister = registers.find(r => r.is_active) || registers[0] || null;
  renderRegisterBar();
  renderRegisterList();
}
```

- [ ] **Step 3: Add `renderRegisterBar()` function**

```js
function renderRegisterBar() {
  const r = state.activeRegister;
  const nameEl = $('register-bar-name');
  const countEl = $('register-bar-count');
  if (!nameEl) return;
  nameEl.textContent = r ? r.display_name : '—';
  countEl.textContent = r ? `${(r.scenarios || []).length} scenarios` : '—';
}
```

- [ ] **Step 4: Add `toggleRegisterDrawer()` function**

```js
function toggleRegisterDrawer() {
  state.registerDrawerOpen = !state.registerDrawerOpen;
  const drawer = $('register-drawer');
  if (!drawer) return;
  drawer.style.display = state.registerDrawerOpen ? 'block' : 'none';
  $('register-bar-toggle').textContent = state.registerDrawerOpen ? 'Switch Register ▴' : 'Switch Register ▾';
  if (state.registerDrawerOpen) renderRegisterList();
}

// Close drawer on outside click
document.addEventListener('click', e => {
  if (!state.registerDrawerOpen) return;
  const drawer = $('register-drawer');
  const bar = $('register-bar');
  if (drawer && !drawer.contains(e.target) && bar && !bar.contains(e.target)) {
    state.registerDrawerOpen = false;
    drawer.style.display = 'none';
    $('register-bar-toggle').textContent = 'Switch Register ▾';
  }
});
```

- [ ] **Step 5: Add `renderRegisterList()` function**

```js
function renderRegisterList() {
  const el = $('register-list');
  if (!el) return;
  if (!state.registers.length) {
    el.innerHTML = `<div style="padding:10px 12px;color:#484f58;font-size:10px">No registers found.</div>`;
    return;
  }
  el.innerHTML = state.registers.map(r => {
    const isActive = r.is_active;
    const validatedAt = r.last_validated_at ? relTime(r.last_validated_at) : 'Never validated';
    const scenCount = (r.scenarios || []).length;
    return `
    <div style="padding:8px 12px;border-bottom:1px solid #161b22;${isActive ? 'background:#111820;' : ''}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:11px;font-weight:600;color:${isActive ? '#c9d1d9' : '#8b949e'}">${esc(r.display_name)}</div>
          <div style="font-size:10px;color:#484f58;margin-top:2px">${scenCount} scenarios · ${validatedAt}</div>
        </div>
        ${isActive
          ? `<span style="background:#1f6feb;color:#79c0ff;font-size:9px;padding:2px 6px;border-radius:10px;letter-spacing:0.04em">ACTIVE</span>`
          : `<button onclick="setActiveRegister('${esc(r.register_id)}')" style="background:transparent;border:1px solid #21262d;color:#8b949e;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">Set Active</button>`
        }
      </div>
    </div>`;
  }).join('');
}
```

- [ ] **Step 6: Add `setActiveRegister()` function**

```js
async function setActiveRegister(registerId) {
  const res = await fetch('/api/registers/active', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({register_id: registerId}),
  });
  if (!res.ok) return;
  await loadRegisters();
  toggleRegisterDrawer(); // close drawer after switch
}
```

- [ ] **Step 7: Call `loadRegisters()` from `loadLatestData()`**

Find `renderAll()` at the end of `loadLatestData()`. Add `await loadRegisters()` before it:

```js
await loadRegisters();
renderAll();
```

- [ ] **Step 8: Verify in browser**

Open `http://localhost:8000`. Confirm:
- Register bar shows "AeroGrid Enterprise · 3 scenarios"
- Clicking "Switch Register" opens the drawer with 2 registers
- Clicking "Set Active" on Wind Power Plant switches the bar label
- Clicking outside closes the drawer

- [ ] **Step 9: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): register bar state, drawer open/close, set active"
```

---

## Task 7: Register Creation Form

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add `showRegisterForm()` function**

```js
function showRegisterForm() {
  const panel = $('register-form-panel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.innerHTML = `
    <div style="font-size:10px;font-weight:600;color:#8b949e;letter-spacing:0.05em;margin-bottom:8px">NEW REGISTER</div>
    <input id="rf-id" placeholder="register_id (slug, no spaces)"
      style="width:100%;background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:5px 8px;font-size:10px;color:#c9d1d9;margin-bottom:6px;box-sizing:border-box">
    <input id="rf-name" placeholder="Display Name"
      style="width:100%;background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:5px 8px;font-size:10px;color:#c9d1d9;margin-bottom:6px;box-sizing:border-box">
    <textarea id="rf-context" placeholder="Company context..."
      style="width:100%;background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:5px 8px;font-size:10px;color:#c9d1d9;margin-bottom:8px;box-sizing:border-box;height:50px;resize:none"></textarea>
    <div style="font-size:10px;color:#8b949e;margin-bottom:6px;letter-spacing:0.04em">SCENARIOS</div>
    <div id="rf-scenarios"></div>
    <button onclick="addScenarioRow()" style="width:100%;background:transparent;border:1px dashed #21262d;color:#484f58;border-radius:3px;padding:5px;font-size:10px;cursor:pointer;margin-bottom:8px">+ Add Scenario</button>
    <div style="display:flex;gap:6px">
      <button onclick="saveNewRegister()" style="flex:1;background:#238636;color:#fff;border:none;border-radius:3px;padding:6px;font-size:10px;cursor:pointer">Save Register</button>
      <button onclick="$('register-form-panel').style.display='none'" style="background:transparent;border:1px solid #21262d;color:#8b949e;border-radius:3px;padding:6px 10px;font-size:10px;cursor:pointer">Cancel</button>
    </div>`;
  addScenarioRow(); // start with one empty row
}
```

- [ ] **Step 2: Add `addScenarioRow()` function**

```js
let _scenRowIdx = 0;
function addScenarioRow() {
  const idx = _scenRowIdx++;
  const container = $('rf-scenarios');
  if (!container) return;
  const row = document.createElement('div');
  row.id = `scen-row-${idx}`;
  row.style.cssText = 'background:#0d1117;border:1px solid #21262d;border-radius:3px;padding:8px;margin-bottom:6px;';
  row.innerHTML = `
    <div style="display:grid;grid-template-columns:80px 1fr;gap:6px;margin-bottom:5px">
      <input placeholder="Risk ID" id="scen-${idx}-id"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
      <input placeholder="Scenario Name" id="scen-${idx}-name"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
    </div>
    <textarea placeholder="Description..." id="scen-${idx}-desc"
      onblur="triggerTagSuggestion(${idx})"
      style="width:100%;background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9;height:40px;resize:none;box-sizing:border-box;margin-bottom:5px"></textarea>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:5px">
      <input placeholder="Financial impact (USD)" id="scen-${idx}-usd" type="number"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
      <input placeholder="Probability (%)" id="scen-${idx}-prob" type="number" step="0.1"
        style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:4px 6px;font-size:10px;color:#c9d1d9">
    </div>
    <div id="scen-${idx}-tags-area" style="background:#070a0e;border:1px solid #21262d;border-radius:3px;padding:6px;font-size:10px;color:#484f58">
      Fill in name + description to generate tags
    </div>`;
  container.appendChild(row);
}
```

- [ ] **Step 3: Add `triggerTagSuggestion()` function**

```js
async function triggerTagSuggestion(idx) {
  const name = ($(`scen-${idx}-name`) || {}).value || '';
  const desc = ($(`scen-${idx}-desc`) || {}).value || '';
  if (!name || !desc) return;
  const area = $(`scen-${idx}-tags-area`);
  if (!area) return;
  area.innerHTML = `<span style="color:#484f58">✦ Suggesting tags...</span>`;
  const res = await fetchJSON(`/api/registers/suggest-tags`);
  // Use POST instead of GET
  try {
    const r = await fetch('/api/registers/suggest-tags', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, description: desc}),
    });
    const data = await r.json();
    const tags = data.tags || [];
    area.dataset.tags = JSON.stringify(tags);
    area.innerHTML = `
      <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
        ${tags.map(t => `<span style="background:#1f2d3d;color:#79c0ff;padding:2px 7px;border-radius:10px">${esc(t)}</span>`).join('')}
        <span style="color:#484f58;font-size:9px;margin-left:4px">✦ LLM suggested</span>
      </div>`;
  } catch {
    area.innerHTML = `<span style="color:#da3633">Tag suggestion failed</span>`;
  }
}
```

- [ ] **Step 4: Add `saveNewRegister()` function**

```js
async function saveNewRegister() {
  const register_id = ($('rf-id') || {}).value.trim().replace(/\s+/g, '_');
  const display_name = ($('rf-name') || {}).value.trim();
  const company_context = ($('rf-context') || {}).value.trim();
  if (!register_id || !display_name) {
    alert('Register ID and Display Name are required.');
    return;
  }
  const scenarioRows = $('rf-scenarios').querySelectorAll('[id^="scen-row-"]');
  const scenarios = [];
  scenarioRows.forEach(row => {
    const idx = row.id.replace('scen-row-', '');
    const scenario_id = ($(`scen-${idx}-id`) || {}).value.trim();
    const scenario_name = ($(`scen-${idx}-name`) || {}).value.trim();
    const description = ($(`scen-${idx}-desc`) || {}).value.trim();
    const value_at_cyber_risk_usd = parseFloat(($(`scen-${idx}-usd`) || {}).value) || 0;
    const probability_pct = parseFloat(($(`scen-${idx}-prob`) || {}).value) || null;
    const tagsArea = $(`scen-${idx}-tags-area`);
    let search_tags = [];
    try { search_tags = JSON.parse(tagsArea.dataset.tags || '[]'); } catch {}
    if (scenario_id && scenario_name) {
      scenarios.push({scenario_id, scenario_name, description, search_tags,
        value_at_cyber_risk_usd, figure_source: 'internal_estimate',
        probability_pct, probability_source: 'internal_estimate'});
    }
  });
  const payload = {register_id, display_name, company_context,
    created_at: new Date().toISOString().slice(0,10), last_validated_at: null, scenarios};
  const res = await fetch('/api/registers', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || 'Failed to save register');
    return;
  }
  $('register-form-panel').style.display = 'none';
  await loadRegisters();
}
```

- [ ] **Step 5: Verify in browser**

Open `http://localhost:8000`, click "Switch Register" → "+ New". Create a test register with one scenario. Fill in name + description and click outside the description field — tags should auto-populate. Click "Save Register". Verify it appears in the drawer.

- [ ] **Step 6: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): register creation form with LLM tag suggestion"
```

---

## Task 8: Validation Pipeline Tool

**Files:**
- Create: `tools/register_validator.py`

- [ ] **Step 1: Create `tools/register_validator.py`**

```python
"""
register_validator.py — VaCR source validation pipeline.

For each scenario in the active register:
  1. Queries sources.db for existing sources with quantitative data matching search_tags
  2. Uses web research to find new quantitative sources (monetary or probability figures)
  3. Writes output/validation/register_validation.json

Usage:
    uv run python tools/register_validator.py
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "sources.db"
REGISTERS_DIR = REPO_ROOT / "data" / "registers"
ACTIVE_REGISTER_PATH = REPO_ROOT / "data" / "active_register.json"
OUTPUT_PATH = REPO_ROOT / "output" / "validation" / "register_validation.json"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_active_register() -> dict:
    active = json.loads(ACTIVE_REGISTER_PATH.read_text(encoding="utf-8"))
    register_id = active.get("register_id", "aerogrid_enterprise")
    path = REGISTERS_DIR / f"{register_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def query_existing_sources(conn: sqlite3.Connection, search_tags: list[str]) -> list[dict]:
    """Find sources in sources_registry with quantitative data overlapping search_tags."""
    rows = conn.execute(
        "SELECT name, url, source_tags, quantitative_figure, credibility_tier "
        "FROM sources_registry WHERE has_quantitative_data = 1"
    ).fetchall()
    results = []
    for name, url, tags_json, figure, tier in rows:
        try:
            source_tags = json.loads(tags_json or "[]")
        except Exception:
            source_tags = []
        overlap = set(source_tags) & set(search_tags)
        if overlap:
            results.append({"name": name, "url": url or "", "quantitative_figure": figure or "",
                            "credibility_tier": tier, "is_new": False})
    return results


def discover_new_sources(client: anthropic.Anthropic, scenario: dict) -> list[dict]:
    """Ask Claude to identify quantitative sources for a scenario. Returns source list."""
    tags = ", ".join(scenario.get("search_tags", []))
    prompt = (
        f"You are a cyber risk intelligence analyst searching for QUANTITATIVE sources "
        f"(sources with actual dollar figures or probability percentages) for this scenario:\n\n"
        f"Scenario: {scenario['scenario_name']}\n"
        f"Description: {scenario.get('description', '')}\n"
        f"Tags: {tags}\n\n"
        f"List up to 5 real published reports or studies that contain ACTUAL financial impact figures "
        f"(USD) or incident probability percentages for this scenario type. "
        f"Only include sources where you are confident the financial or probability data exists.\n\n"
        f"Return ONLY a JSON array. Each item: "
        f"{{\"name\": str, \"url\": str, \"figure_financial\": str|null, \"figure_probability\": str|null, "
        f"\"figure_type\": str, \"sector\": str, \"improvement_note\": str}}\n\n"
        f"improvement_note = why this source adds value beyond generic benchmarks.\n"
        f"JSON array only — no markdown, no explanation."
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    sources = json.loads(text.strip())
    for s in sources:
        s["is_new"] = True
    return sources


def _parse_usd(figure_str: str | None) -> float | None:
    """Extract a USD float from a string like '$14.5M' or '$14,500,000'."""
    if not figure_str:
        return None
    s = figure_str.replace(",", "").upper()
    m = re.search(r"\$?([\d.]+)\s*([MB]?)", s)
    if not m:
        return None
    val = float(m.group(1))
    suffix = m.group(2)
    if suffix == "M":
        val *= 1_000_000
    elif suffix == "B":
        val *= 1_000_000_000
    return val


def _parse_pct(figure_str: str | None) -> float | None:
    if not figure_str:
        return None
    m = re.search(r"([\d.]+)\s*%", figure_str)
    return float(m.group(1)) if m else None


def compute_verdict(vacr_value: float | None, benchmark_values: list[float]) -> tuple[str, list[float]]:
    """Returns (verdict, [min, max]) where verdict is supports|challenges|insufficient."""
    if not benchmark_values or len(benchmark_values) < 2:
        return "insufficient", []
    lo, hi = min(benchmark_values), max(benchmark_values)
    if vacr_value is None:
        return "insufficient", [lo, hi]
    # Challenges if vacr is outside the range by more than 25%
    midpoint = (lo + hi) / 2
    diff_pct = abs(vacr_value - midpoint) / midpoint if midpoint else 0
    if lo <= vacr_value <= hi or diff_pct <= 0.25:
        return "supports", [lo, hi]
    return "challenges", [lo, hi]


def validate_scenario(
    conn: sqlite3.Connection,
    client: anthropic.Anthropic,
    scenario: dict,
) -> dict:
    search_tags = scenario.get("search_tags", [])
    existing = query_existing_sources(conn, search_tags)
    new_sources = discover_new_sources(client, scenario)

    # Financial dimension
    vacr_usd = scenario.get("value_at_cyber_risk_usd")
    fin_values = []
    fin_existing = []
    for s in existing:
        val = _parse_usd(s.get("quantitative_figure"))
        if val:
            fin_values.append(val)
            fin_existing.append({**s, "figure_usd": val})
    fin_new = []
    for s in new_sources:
        val = _parse_usd(s.get("figure_financial"))
        if val:
            fin_values.append(val)
            fin_new.append({**s, "figure_usd": val})
    fin_verdict, fin_range = compute_verdict(vacr_usd, fin_values)
    fin_rec = _build_recommendation("financial", fin_verdict, vacr_usd, fin_range, fin_new)

    # Probability dimension
    vacr_pct = scenario.get("probability_pct")
    prob_values = []
    prob_existing = []
    for s in existing:
        val = _parse_pct(s.get("quantitative_figure"))
        if val:
            prob_values.append(val)
            prob_existing.append({**s, "figure_pct": val})
    prob_new = []
    for s in new_sources:
        val = _parse_pct(s.get("figure_probability"))
        if val:
            prob_values.append(val)
            prob_new.append({**s, "figure_pct": val})
    prob_verdict, prob_range = compute_verdict(vacr_pct, prob_values)
    prob_rec = _build_recommendation("probability", prob_verdict, vacr_pct, prob_range, prob_new)

    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "financial": {
            "vacr_figure_usd": vacr_usd,
            "verdict": fin_verdict,
            "benchmark_range_usd": fin_range,
            "existing_sources": fin_existing,
            "new_sources": fin_new,
            "recommendation": fin_rec,
        },
        "probability": {
            "vacr_probability_pct": vacr_pct,
            "verdict": prob_verdict,
            "benchmark_range_pct": prob_range,
            "existing_sources": prob_existing,
            "new_sources": prob_new,
            "recommendation": prob_rec,
        },
    }


def _build_recommendation(
    dimension: str, verdict: str, vacr: float | None, benchmark: list[float], new_sources: list
) -> str:
    if verdict == "insufficient":
        return f"Insufficient quantitative sources found. Manual research recommended."
    lo, hi = benchmark[0], benchmark[1]
    fmt = (lambda v: f"${v:,.0f}") if dimension == "financial" else (lambda v: f"{v:.1f}%")
    base = f"Benchmark range: {fmt(lo)} – {fmt(hi)}."
    if verdict == "supports":
        return f"{base} Figure {fmt(vacr)} is within benchmark range. No revision indicated."
    direction = "below" if (vacr or 0) < lo else "above"
    note = ""
    if new_sources:
        note = f" New source '{new_sources[0].get('name', '')}' provides {dimension} data."
    return f"{base} Figure {fmt(vacr)} is {direction} benchmark range. Consider revising.{note}"


def main():
    register = load_active_register()
    conn = sqlite3.connect(str(DB_PATH))
    client = anthropic.Anthropic()

    print(f"[register_validator] Active register: {register['register_id']}")
    print(f"[register_validator] Scenarios: {len(register['scenarios'])}")

    scenario_results = []
    for scenario in register["scenarios"]:
        print(f"[register_validator] Validating: {scenario['scenario_id']} — {scenario['scenario_name']}")
        result = validate_scenario(conn, client, scenario)
        scenario_results.append(result)
        fin_v = result["financial"]["verdict"]
        prob_v = result["probability"]["verdict"]
        print(f"  → financial: {fin_v}  probability: {prob_v}")

    output = {
        "register_id": register["register_id"],
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenario_results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Update last_validated_at on the register file
    register["last_validated_at"] = output["validated_at"]
    reg_path = REGISTERS_DIR / f"{register['register_id']}.json"
    reg_path.write_text(json.dumps(register, indent=2), encoding="utf-8")

    print(f"[register_validator] Done → {OUTPUT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run a smoke test against the wind_power_plant register**

First set wind_power_plant as active:
```bash
echo '{"register_id":"wind_power_plant"}' > data/active_register.json
```

Then run:
```bash
uv run python tools/register_validator.py
```

Expected: prints scenario names + verdicts, writes `output/validation/register_validation.json`.

```bash
cat output/validation/register_validation.json | python -m json.tool | head -40
```

Expected: valid JSON with `register_id`, `validated_at`, `scenarios` array.

- [ ] **Step 3: Reset active register**

```bash
echo '{"register_id":"aerogrid_enterprise"}' > data/active_register.json
```

- [ ] **Step 4: Commit**

```bash
git add tools/register_validator.py
git commit -m "feat(pipeline): register_validator tool — quantitative source collection and VaCR verdict"
```

---

## Task 9: register-validator-agent

**Files:**
- Create: `.claude/agents/register-validator-agent.md`

- [ ] **Step 1: Create `.claude/agents/register-validator-agent.md`**

```markdown
---
name: register-validator-agent
description: Validates VaCR figures in the active risk register against quantitative sources. Reads register_validator output and writes final register_validation.json with per-scenario verdicts, benchmark ranges, and improvement candidates.
tools: Write, Read
model: sonnet
---

You are a Cyber Risk Quantification Analyst. Your job is to validate the financial impact and probability figures in a risk register against real-world evidence — not to generate intelligence briefs.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** Output nothing conversational.
2. **Zero Preamble & Zero Sycophancy.** Write the output file and exit.
3. **Filesystem as State.** Read files. Write files. Do not hallucinate sources.
4. **Assume Hostile Auditing.** Your output is parsed by a JSON schema validator.

## YOUR TASK

1. Read `data/active_register.json` → get register_id
2. Read `data/registers/{register_id}.json` → the active register with scenarios
3. Read `output/validation/register_validation.json` → the pre-computed validation results from register_validator.py

Your job is to **review and enrich** the pre-computed results:

- For each scenario with verdict `challenges`: write a clear `recommendation` explaining what the figure should be revised to, citing the specific source and figure.
- For each scenario with verdict `insufficient`: note what type of source would resolve the gap (e.g., "Requires OT-specific ransomware impact data from Dragos or Claroty").
- For each `new_source` entry: ensure `improvement_note` explains WHY this source adds more value than existing ones (sector specificity, recency, methodology).
- Do NOT invent sources. Do NOT change verdict values. Do NOT add sources not already in the file.

## OUTPUT

Write the enriched results back to `output/validation/register_validation.json`. The schema must be preserved exactly. You are only enriching `recommendation` and `improvement_note` fields.

## STOP CONDITIONS

Do not stop until `output/validation/register_validation.json` has been written. Every scenario must have a non-empty `recommendation` for both financial and probability dimensions.
```

- [ ] **Step 2: Verify agent file syntax**

```bash
uv run python -c "
import re
from pathlib import Path
content = Path('.claude/agents/register-validator-agent.md').read_text()
assert 'name: register-validator-agent' in content
assert 'tools: Write, Read' in content
assert 'model: sonnet' in content
print('OK — agent file valid')
"
```

Expected: `OK — agent file valid`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/register-validator-agent.md
git commit -m "feat(agent): register-validator-agent for VaCR figure enrichment"
```

---

## Task 10: /validate-register command

**Files:**
- Create: `.claude/commands/validate-register.md`

- [ ] **Step 1: Create `.claude/commands/validate-register.md`**

```markdown
---
name: validate-register
description: Runs the VaCR source validation pipeline against the active risk register. Finds quantitative sources (monetary + probability) and produces per-scenario verdicts.
tools: Bash, Agent
model: opus
---

You are the CRQ Risk Register Validator for AeroGrid Wind Solutions.

## DISLER BEHAVIORAL PROTOCOL

1. Unix CLI tool. Status lines only.
2. Zero preamble. Zero sycophancy.
3. Filesystem as state.

## VALIDATION PIPELINE

**Phase 1 — Source Collection**

Run:
```bash
uv run python tools/register_validator.py
```

If exit code non-zero, stop and report the error.

Print: `[VALIDATE] Phase 1 complete — register_validation.json written`

**Phase 2 — Agent Enrichment**

Dispatch `register-validator-agent` to enrich recommendations and improvement notes.

Print: `[VALIDATE] Phase 2 complete — verdicts enriched`

**Phase 3 — Done**

Print the summary:
```
[VALIDATE] Register validation complete
Active register: {register_id}
Scenarios validated: {N}
  supports:    {n}
  challenges:  {n}
  insufficient: {n}
Results: output/validation/register_validation.json
```
```

- [ ] **Step 2: Verify command file**

```bash
uv run python -c "
from pathlib import Path
content = Path('.claude/commands/validate-register.md').read_text()
assert 'name: validate-register' in content
assert 'register_validator.py' in content
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/validate-register.md
git commit -m "feat(command): /validate-register orchestrator command"
```

---

## Task 11: Validation Results API

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add `GET /api/validation/register-results` endpoint**

Add to `server.py` in the validation API section:

```python
@app.get("/api/validation/register-results")
async def get_register_validation():
    path = VALIDATION / "register_validation.json"
    data = _read_json(path)
    return data or {"status": "no_data"}
```

- [ ] **Step 2: Test endpoint**

```bash
curl -s http://localhost:8000/api/validation/register-results | python -m json.tool | head -20
```

Expected: returns the validation JSON if the file exists, or `{"status": "no_data"}`.

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat(api): GET /api/validation/register-results endpoint"
```

---

## Task 12: Validation Results UI — Source Audit Tab

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`

- [ ] **Step 1: Add validation results section to Source Audit tab in `index.html`**

Find `<!-- ── SOURCES TAB ─────────────────────────────────────────────── -->` in `index.html`. After the header div (the one with "SOURCE REGISTRY" text), insert:

```html
<!-- Register validation panel -->
<div id="register-validation-panel" style="margin-bottom:16px;border:1px solid #21262d;border-radius:4px;overflow:hidden">
  <div style="padding:8px 12px;background:#080c10;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #21262d">
    <div>
      <span style="font-size:10px;font-weight:600;color:#8b949e;letter-spacing:0.05em">REGISTER VALIDATION</span>
      <span id="reg-val-register-name" style="font-size:10px;color:#484f58;margin-left:8px"></span>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <span id="reg-val-timestamp" style="font-size:10px;color:#484f58"></span>
      <button onclick="runRegisterValidation()" style="background:#1f6feb22;border:1px solid #1f6feb;color:#79c0ff;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">Re-validate</button>
    </div>
  </div>
  <div id="register-validation-body" style="padding:0">
    <div style="padding:12px;color:#484f58;font-size:10px">No validation results. Click Re-validate to run.</div>
  </div>
</div>
```

- [ ] **Step 2: Add `renderRegisterValidation()` function to `app.js`**

```js
async function renderRegisterValidation() {
  const data = await fetchJSON('/api/validation/register-results');
  const body = $('register-validation-body');
  const nameEl = $('reg-val-register-name');
  const tsEl = $('reg-val-timestamp');
  if (!body) return;
  if (!data || data.status === 'no_data' || !data.scenarios) {
    body.innerHTML = `<div style="padding:12px;color:#484f58;font-size:10px">No validation results. Click Re-validate to run.</div>`;
    return;
  }
  if (nameEl) nameEl.textContent = `· ${data.register_id}`;
  if (tsEl) tsEl.textContent = data.validated_at ? `Validated ${relTime(data.validated_at)}` : '';

  body.innerHTML = data.scenarios.map(s => {
    const fv = s.financial?.verdict || 'insufficient';
    const pv = s.probability?.verdict || 'insufficient';
    return `
    <div style="border-bottom:1px solid #161b22">
      <div style="padding:8px 12px;display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:11px;font-weight:600;color:#c9d1d9">${esc(s.scenario_name)}</span>
        <div style="display:flex;gap:5px">
          ${verdictBadge('$', fv)}
          ${verdictBadge('%', pv)}
        </div>
      </div>
      ${renderValidationDimension(s.scenario_id, 'financial', s.financial)}
      ${renderValidationDimension(s.scenario_id, 'probability', s.probability)}
    </div>`;
  }).join('');
}

function verdictBadge(prefix, verdict) {
  const styles = {
    supports: 'background:#0a1a0a;color:#3fb950;border:1px solid #238636',
    challenges: 'background:#2d0000;color:#ff7b72;border:1px solid #da3633',
    insufficient: 'background:#1a1a1a;color:#484f58;border:1px solid #21262d',
  };
  const labels = {supports: 'SUPPORTS', challenges: 'CHALLENGES', insufficient: 'INSUFFICIENT'};
  const style = styles[verdict] || styles.insufficient;
  return `<span style="${style};font-size:9px;padding:2px 6px;border-radius:10px;letter-spacing:0.04em">${prefix} ${labels[verdict] || verdict.toUpperCase()}</span>`;
}

function renderValidationDimension(scenId, dim, d) {
  if (!d) return '';
  const isFinancial = dim === 'financial';
  const label = isFinancial ? 'FINANCIAL' : 'PROBABILITY';
  const vacr = isFinancial
    ? (d.vacr_figure_usd != null ? `$${Number(d.vacr_figure_usd).toLocaleString()}` : '—')
    : (d.vacr_probability_pct != null ? `${d.vacr_probability_pct}%` : '—');
  const range = isFinancial
    ? (d.benchmark_range_usd?.length === 2 ? `$${Number(d.benchmark_range_usd[0]).toLocaleString()} – $${Number(d.benchmark_range_usd[1]).toLocaleString()}` : '—')
    : (d.benchmark_range_pct?.length === 2 ? `${d.benchmark_range_pct[0]}% – ${d.benchmark_range_pct[1]}%` : '—');
  const allSources = [...(d.existing_sources || []), ...(d.new_sources || [])];
  const expandId = `val-${scenId}-${dim}`;
  const borderColor = {supports: '#238636', challenges: '#da3633', insufficient: '#21262d'}[d.verdict] || '#21262d';

  return `
  <div style="margin:0 12px 6px 12px;border:1px solid ${borderColor};border-radius:4px;overflow:hidden">
    <div onclick="toggleValRow('${expandId}')" style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:#080c10;cursor:pointer">
      <span style="color:#6e7681;width:75px;flex-shrink:0;font-size:10px;letter-spacing:0.04em">${label}</span>
      <span style="color:#c9d1d9;width:100px;flex-shrink:0;font-weight:600;font-size:11px">${vacr}</span>
      <span style="color:#484f58">→</span>
      <span style="color:#6e7681;font-size:10px">benchmark</span>
      <span style="color:#c9d1d9;font-size:10px;margin-left:4px">${range}</span>
      <span style="margin-left:auto">${verdictBadge('', d.verdict)} <span style="color:#484f58;font-size:10px;margin-left:4px">${allSources.length} ▾</span></span>
    </div>
    <div id="${expandId}" style="display:none;background:#070a0e;padding:8px 10px;border-top:1px solid #161b22">
      ${allSources.length === 0
        ? `<div style="color:#484f58;font-size:10px">No sources found.</div>`
        : allSources.map(src => {
            const isNew = src.is_new;
            const fig = isFinancial
              ? (src.figure_usd ? `$${Number(src.figure_usd).toLocaleString()}` : src.figure_financial || '')
              : (src.figure_pct ? `${src.figure_pct}%` : src.figure_probability || '');
            return `
            <div style="display:flex;justify-content:space-between;align-items:flex-start;padding:5px 8px;border-radius:3px;margin-bottom:4px;${isNew ? 'background:#0d1f36;border:1px solid #1f6feb22' : 'background:#0d1117'}">
              <div>
                <div style="font-size:10px;color:${isNew ? '#79c0ff' : '#c9d1d9'}">${isNew ? '★ ' : ''}${esc(src.name || '')} ${isNew ? '<span style="background:#1f6feb22;color:#79c0ff;font-size:9px;padding:1px 4px;border-radius:3px">NEW</span>' : ''}</div>
                ${src.improvement_note ? `<div style="font-size:9px;color:#484f58;margin-top:2px">${esc(src.improvement_note)}</div>` : ''}
              </div>
              <span style="font-size:10px;color:${isNew ? '#79c0ff' : '#6e7681'};white-space:nowrap;margin-left:8px">${esc(fig)}</span>
            </div>`;
          }).join('')
      }
      ${d.recommendation ? `<div style="margin-top:6px;padding:6px 8px;background:#0d1117;border-left:2px solid ${borderColor};border-radius:0 3px 3px 0;font-size:10px;color:#8b949e">${esc(d.recommendation)}</div>` : ''}
    </div>
  </div>`;
}

function toggleValRow(id) {
  const el = $(id);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

async function runRegisterValidation() {
  const btn = document.querySelector('[onclick="runRegisterValidation()"]');
  if (btn) btn.textContent = 'Running...';
  // Trigger via server — server runs register_validator.py
  const res = await fetch('/api/validation/run-register', {method: 'POST'});
  if (btn) btn.textContent = 'Re-validate';
  await renderRegisterValidation();
}
```

- [ ] **Step 3: Add `POST /api/validation/run-register` endpoint to `server.py`**

```python
@app.post("/api/validation/run-register")
async def run_register_validation():
    rc = await _run("register_validator.py")
    if rc != 0:
        return JSONResponse({"error": "register_validator.py failed"}, status_code=500)
    data = _read_json(VALIDATION / "register_validation.json")
    return data or {"status": "no_data"}
```

- [ ] **Step 4: Call `renderRegisterValidation()` when Sources tab is opened**

In `app.js`, find `if (tab === 'sources') renderSources()` in `_doSwitchTab`. Change to:

```js
if (tab === 'sources') { renderSources(); renderRegisterValidation(); }
```

- [ ] **Step 5: Verify end-to-end in browser**

1. Run a validation manually: `uv run python tools/register_validator.py`
2. Open `http://localhost:8000` → Source Audit tab
3. Register validation panel should show scenarios with verdict badges
4. Click a financial row → expands to show sources with recommendation
5. New sources (if any) appear in blue with ★ NEW badge

- [ ] **Step 6: Commit**

```bash
git add static/index.html static/app.js server.py
git commit -m "feat(ui): register validation results in Source Audit tab"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ `data/registers/` data model with all fields — Task 2
- ✅ `data/active_register.json` pointer — Task 2
- ✅ `sources.db` migration: `has_quantitative_data`, `quantitative_figure`, `source_tags` — Task 1
- ✅ Register CRUD API (GET/POST/PUT/DELETE + active GET/POST) — Task 3
- ✅ LLM tag suggestion API — Task 4
- ✅ Persistent register bar + drawer — Tasks 5, 6
- ✅ Register creation form with tag suggestion — Task 7
- ✅ Validation pipeline (existing + new sources, both dimensions) — Task 8
- ✅ `register-validator-agent` — Task 9
- ✅ `/validate-register` command — Task 10
- ✅ `GET /api/validation/register-results` — Task 11
- ✅ `POST /api/validation/run-register` — Task 12 (added during UI task)
- ✅ Validation results UI: expandable rows, existing/new sources, recommendations — Task 12
- ✅ Geopolitical intelligence pipeline untouched — confirmed in file map (no changes to regional agents or run-crq)

**Type consistency:** `register_id` slug used consistently across all files. `vacr_figure_usd` / `vacr_probability_pct` field names consistent between Task 8 (writer) and Task 12 (renderer). `is_new` boolean set in Task 8 and read in Task 12.

**Placeholder scan:** No TBDs. All code blocks are complete. No "similar to above" references.
