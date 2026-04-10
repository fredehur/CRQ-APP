# F-2 Dashboard Rework Implementation Plan

>
> **Frontend tasks:** Use the `frontend-design` skill when implementing index.html and app.js to ensure production-quality visual output.

**Goal:** Rebuild the CRQ Command Center dashboard with board-readable information hierarchy, rich intelligence cards, slide-over output panels, SSE-driven progress bar, and a History tab.

**Architecture:** Rebuild `static/index.html` and `static/app.js` in-place (Tailwind CDN + vanilla JS + marked.js CDN). Add 4 new FileResponse/text endpoints to `server.py`. No new build tooling or framework.

**Tech Stack:** FastAPI, Tailwind CSS (CDN), vanilla JS, marked.js (CDN), pytest + httpx for backend tests.

**Spec:** `docs/superpowers/specs/2026-03-13-dashboard-rework-design.md`

---

## Chunk 1: Backend — New server.py Endpoints

### Task 1: Add signals endpoint + output file endpoints to server.py

**Files:**
- Modify: `server.py` (after line 121, before `# ── API: Run Pipeline`)
- Create: `tests/test_server.py`

The 4 new endpoints follow the same `_read_json` / `FileResponse` pattern already in server.py.

> **Note:** The spec's Architecture section says "two new endpoints" — this is a typo. The spec's Data Sources table (authoritative) lists 4 endpoints. The plan implements all 4.

- [ ] **Step 1: Write failing tests for all 4 new endpoints**

Create `tests/test_server.py`:

```python
"""Tests for new server.py endpoints added in F-2."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_output, monkeypatch):
    """TestClient with OUTPUT patched to tmp_path.

    monkeypatch.setattr patches the module-level OUTPUT name. Endpoint functions
    reference OUTPUT at call time, so the patch takes effect without a reload.
    Do NOT call reload(server) — it would reset OUTPUT back to the real path.
    """
    import server
    monkeypatch.setattr(server, "OUTPUT", mock_output)
    return TestClient(server.app)


# ── /api/region/{region}/signals ─────────────────────────────────────────

def test_signals_returns_geo_and_cyber_keys(client, mock_output):
    # Write minimal signal files for APAC
    signals_dir = mock_output / "regional" / "apac"
    signals_dir.mkdir(parents=True, exist_ok=True)
    geo = {"summary": "geo summary", "lead_indicators": ["indicator 1"], "dominant_pillar": "Geopolitical"}
    cyber = {"summary": "cyber summary", "threat_vector": "phishing", "target_assets": ["OT networks"]}
    (signals_dir / "geo_signals.json").write_text(json.dumps(geo), encoding="utf-8")
    (signals_dir / "cyber_signals.json").write_text(json.dumps(cyber), encoding="utf-8")

    resp = client.get("/api/region/APAC/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert "geo" in body
    assert "cyber" in body
    assert body["geo"]["summary"] == "geo summary"
    assert body["cyber"]["threat_vector"] == "phishing"


def test_signals_returns_nulls_when_files_missing(client):
    resp = client.get("/api/region/LATAM/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert body["geo"] is None
    assert body["cyber"] is None


def test_signals_unknown_region_returns_404(client):
    resp = client.get("/api/region/UNKNOWN/signals")
    assert resp.status_code == 404
    # Also verify the error body — FastAPI returns 404 for unregistered routes too,
    # so this test checks the handler's explicit validation, not just route absence.
    assert "error" in resp.json()


# ── /api/outputs/global-md ───────────────────────────────────────────────

def test_global_md_returns_markdown_string(client, mock_output):
    (mock_output / "global_report.md").write_text("# Global Report\n\nSummary here.", encoding="utf-8")
    resp = client.get("/api/outputs/global-md")
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "# Global Report\n\nSummary here."


def test_global_md_returns_empty_when_missing(client):
    resp = client.get("/api/outputs/global-md")
    assert resp.status_code == 200
    assert resp.json()["markdown"] == ""


# ── /api/outputs/pdf ─────────────────────────────────────────────────────

def test_pdf_returns_404_when_missing(client):
    resp = client.get("/api/outputs/pdf")
    assert resp.status_code == 404


def test_pdf_returns_file_when_present(client, mock_output):
    (mock_output / "board_report.pdf").write_bytes(b"%PDF-1.4 fake")
    resp = client.get("/api/outputs/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# ── /api/outputs/pptx ────────────────────────────────────────────────────

def test_pptx_returns_404_when_missing(client):
    resp = client.get("/api/outputs/pptx")
    assert resp.status_code == 404


def test_pptx_returns_file_when_present(client, mock_output):
    (mock_output / "board_report.pptx").write_bytes(b"PK fake pptx")
    resp = client.get("/api/outputs/pptx")
    assert resp.status_code == 200
    assert "officedocument" in resp.headers["content-type"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_server.py -v
```

Expected: most tests FAIL. Exception: `test_signals_unknown_region_returns_404` will PASS here because FastAPI returns 404 for any unregistered route — this is expected and OK. After Step 3, the test will pass for the right reason (handler validation, not missing route). All other tests must fail.

- [ ] **Step 3: Add the 4 new endpoints to server.py**

Insert after the `get_trace` function (after line ~121), before the `_emit` helper:

```python
@app.get("/api/region/{region}/signals")
async def get_region_signals(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    base = OUTPUT / "regional" / r.lower()
    return {
        "geo": _read_json(base / "geo_signals.json"),
        "cyber": _read_json(base / "cyber_signals.json"),
    }


@app.get("/api/outputs/global-md")
async def get_global_md():
    path = OUTPUT / "global_report.md"
    return {"markdown": path.read_text(encoding="utf-8") if path.exists() else ""}


@app.get("/api/outputs/pdf")
async def get_pdf():
    path = OUTPUT / "board_report.pdf"
    if not path.exists():
        return JSONResponse({"error": "PDF not found"}, status_code=404)
    return FileResponse(str(path), media_type="application/pdf",
                        filename="board_report.pdf")


@app.get("/api/outputs/pptx")
async def get_pptx():
    path = OUTPUT / "board_report.pptx"
    if not path.exists():
        return JSONResponse({"error": "PPTX not found"}, status_code=404)
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="board_report.pptx",
    )
```

- [ ] **Step 4: Run tests — verify they all pass**

```bash
uv run pytest tests/test_server.py -v
```

Expected: all 9 tests PASS (including `test_signals_unknown_region_returns_404` which now validates the error body).

- [ ] **Step 5: Run full test suite — verify no regressions**

```bash
uv run pytest --tb=short -q
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: add signals, global-md, pdf, pptx endpoints for dashboard F-2"
```

---

## Chunk 2: Frontend — index.html Scaffold

> **Use `frontend-design` skill for this task.**

### Task 2: Rewrite static/index.html

**Files:**
- Modify: `static/index.html` (full rewrite)

The HTML defines structure and IDs that `app.js` targets. All IDs listed here are contracts — `app.js` depends on them.

- [ ] **Step 1: Rewrite static/index.html**

The page structure (IDs are contracts for app.js):

```
<head>
  Tailwind CDN
  marked.js CDN: https://cdn.jsdelivr.net/npm/marked/marked.min.js
  Custom styles: progress bar animation, panel transition, Admiralty tooltip,
                 velocity arrows, chip hover popover
</head>
<body>

<!-- Fixed header -->
<header>
  Logo + "AeroGrid Wind Solutions — Geopolitical Risk Intelligence"
  Nav: [Overview tab] [History tab]
  Settings icon (⚙) → opens #settings-modal
  [Run All Regions] button id="btn-run-all"
  Pipeline status text id="pipeline-status"
</header>

<!-- Progress bar — hidden by default, shown during pipeline run -->
<div id="progress-bar-container" class="hidden">
  <div id="progress-label">Initializing...</div>
  <div id="progress-fill"></div>
</div>

<!-- Overview tab content -->
<div id="tab-overview">

  <!-- KPI strip -->
  <section id="kpi-strip">
    <div>Total VaCR Exposure <span id="kpi-vacr">—</span></div>
    <div>Escalated <span id="kpi-escalated">—</span></div>
    <div>Monitor <span id="kpi-monitor">—</span></div>
    <div>Clear <span id="kpi-clear">—</span></div>
    <div>Last Run <span id="kpi-timestamp">—</span></div>
    <div>Trend <span id="kpi-trend">—</span></div>
  </section>

  <!-- Executive summary -->
  <section id="executive-summary-section">
    <h2>Executive Summary</h2>
    <p id="executive-summary-text">No intelligence run yet. Click Run All Regions to generate the first report.</p>
  </section>

  <!-- Stale data banner (shown when viewing archived run) -->
  <div id="archive-banner" class="hidden">
    Viewing archived run — <span id="archive-timestamp"></span>
    <button onclick="returnToLatest()">Return to latest</button>
  </div>

  <!-- Escalated regions -->
  <section id="escalated-section">
    <h3>Active Threats</h3>
    <div id="escalated-cards"><!-- injected by app.js --></div>
  </section>

  <!-- Clear + Monitor regions -->
  <section id="clear-section">
    <h3>Regional Status</h3>
    <div id="clear-chips"><!-- injected by app.js --></div>
  </section>

  <!-- Global outputs button -->
  <div id="global-outputs-row">
    <button onclick="loadPanel('global', null)" id="btn-global-outputs">
      Board Deliverables
    </button>
  </div>

</div><!-- end #tab-overview -->

<!-- History tab content -->
<div id="tab-history" class="hidden">
  <h2>Run History</h2>
  <div id="run-history-list"><!-- injected by app.js --></div>
  <h3>Audit Trace <button onclick="toggleTrace()">▼</button></h3>
  <pre id="audit-trace" class="hidden"></pre>
</div>

<!-- Slide-over output panel -->
<div id="panel-overlay" class="hidden" onclick="closePanel()"></div>
<aside id="output-panel" class="hidden">
  <div id="panel-header">
    <span id="panel-title"></span>
    <button onclick="closePanel()">✕</button>
  </div>
  <div id="panel-tabs"><!-- tab buttons injected by loadPanel() --></div>
  <div id="panel-body"><!-- content injected by loadPanel() --></div>
</aside>

<!-- Settings modal -->
<div id="settings-modal" class="hidden">
  <div id="settings-content">
    <h3>Settings</h3>
    <label>Pipeline Mode
      <select id="mode-select">
        <option value="tools">Tools Mode</option>
        <option value="full">Full (LLM)</option>
      </select>
    </label>
    <button onclick="closeSettings()">Close</button>
  </div>
</div>

<script src="/static/app.js"></script>
</body>
```

**Visual requirements (enforce via frontend-design skill):**
- Dark theme (`bg-gray-950`)
- Severity colours: CRITICAL=red, HIGH=orange, MEDIUM=amber, LOW/CLEAR=green, MONITOR=yellow
- Escalated cards: large, prominent, ordered CRITICAL → HIGH → MEDIUM
- Clear/monitor chips: compact inline row
- Panel slides in from right with smooth transition (`transform translate-x-full` → `translate-x-0`)
- Overlay backdrop dims the dashboard behind the panel
- Admiralty tooltip appears on hover of the ⓘ badge
- Velocity arrows: ↑ text-red (accelerating), → text-gray (stable), ↓ text-green (improving)
- Progress bar: animated fill, green on complete, red on error
- `data-audience="board"` on Admiralty, Signal type, Dominant pillar fields in cards

- [ ] **Step 2: Verify page loads without JS errors**

```bash
uv run python server.py &
# Open http://localhost:8000 in browser
# Expected: page loads, header visible, "No intelligence run yet" in summary
# Open browser DevTools console — no JS errors
```

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: rewrite dashboard HTML scaffold with new layout and component IDs"
```

---

## Chunk 3: Frontend — app.js Core (State, API, KPI, Cards, Chips)

> **Use `frontend-design` skill for this task.**

### Task 3: Rewrite app.js — data layer, KPI, escalated cards, clear chips

**Files:**
- Modify: `static/app.js` (full rewrite — build section by section)

Write app.js with clear section comments. Each section is self-contained:

- [ ] **Step 1: Write the Constants, State, and Helpers section**

```javascript
// ── Constants ──────────────────────────────────────────────────────────
const REGIONS = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
const REGION_LABELS = {
  APAC: 'Asia-Pacific', AME: 'Americas', LATAM: 'Latin America',
  MED: 'Mediterranean', NCE: 'Northern & Central Europe',
};
const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
const SEVERITY_STYLES = {
  CRITICAL: { card: 'border-red-700 bg-red-950/30',   badge: 'bg-red-600',    text: 'text-red-400' },
  HIGH:     { card: 'border-orange-700 bg-orange-950/30', badge: 'bg-orange-600', text: 'text-orange-400' },
  MEDIUM:   { card: 'border-amber-700 bg-amber-950/30',  badge: 'bg-amber-600',  text: 'text-amber-400' },
  LOW:      { card: 'border-green-800 bg-green-950/20',  badge: 'bg-green-700',  text: 'text-green-400' },
};
const VELOCITY_ARROWS = {
  accelerating: { arrow: '↑', cls: 'text-red-400',   label: 'accelerating' },
  stable:       { arrow: '→', cls: 'text-gray-400',  label: 'stable' },
  improving:    { arrow: '↓', cls: 'text-green-400', label: 'improving' },
  unknown:      { arrow: '—', cls: 'text-gray-600',  label: 'unknown' },
};
const ADMIRALTY_TOOLTIPS = {
  A: 'Always reliable', B: 'Usually reliable', C: 'Fairly reliable', D: 'Not usually reliable',
  '1': 'Confirmed by other sources', '2': 'Probably true',
  '3': 'Possibly true', '4': 'Cannot be judged',
};

// ── State ─────────────────────────────────────────────────────────────
let state = {
  manifest: null,       // run_manifest.json
  globalReport: null,   // global_report.json
  regionData: {},       // { APAC: data.json, ... }
  viewingArchive: null, // { name, manifest } when viewing historical run
  activeTab: 'overview',
};

// ── Helpers ───────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const fmtUSD = n => n ? '$' + (n / 1e6).toFixed(1) + 'M' : '$0';
const fmtTime = iso => iso
  ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  : '—';

function admiraltyTooltip(rating) {
  if (!rating || rating.length < 2) return rating || '—';
  const rel = ADMIRALTY_TOOLTIPS[rating[0]] || rating[0];
  const cred = ADMIRALTY_TOOLTIPS[rating[1]] || rating[1];
  return `${rating}: ${rel} source, ${cred}`;
}
```

- [ ] **Step 2: Write the API layer**

```javascript
// ── API ───────────────────────────────────────────────────────────────
async function fetchJSON(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return r.json();
  } catch { return null; }
}

async function loadLatestData() {
  const [manifest, globalReport] = await Promise.all([
    fetchJSON('/api/manifest'),
    fetchJSON('/api/global-report'),
  ]);
  state.manifest = manifest;
  state.globalReport = globalReport;

  if (manifest && manifest.status !== 'no_data' && manifest.regions) {
    const regionFetches = Object.keys(manifest.regions).map(async r => {
      state.regionData[r] = await fetchJSON(`/api/region/${r}`);
    });
    await Promise.all(regionFetches);
  }
  renderAll();
}

async function loadArchiveRun(run) {
  state.viewingArchive = run;
  state.manifest = run.manifest;
  state.globalReport = null; // archived global report not served
  state.regionData = {};
  renderAll();
  showArchiveBanner(run);
}

function returnToLatest() {
  state.viewingArchive = null;
  hideArchiveBanner();
  loadLatestData();
}
```

- [ ] **Step 3: Write the KPI render function**

```javascript
// ── Render: KPIs ──────────────────────────────────────────────────────
function renderKPIs() {
  const m = state.manifest;
  if (!m || m.status === 'no_data') {
    ['kpi-vacr','kpi-escalated','kpi-monitor','kpi-clear','kpi-timestamp','kpi-trend']
      .forEach(id => $(id).textContent = '—');
    return;
  }
  $('kpi-vacr').textContent = fmtUSD(m.total_vacr_exposure_usd);
  $('kpi-timestamp').textContent = fmtTime(m.run_timestamp);

  const regions = Object.values(m.regions || {});
  $('kpi-escalated').textContent = regions.filter(r => r.status === 'escalated').length;
  $('kpi-monitor').textContent   = regions.filter(r => r.status === 'monitor').length;
  $('kpi-clear').textContent     = regions.filter(r => r.status === 'clear').length;

  // Trend: compare total_vacr to previous run if available (set by History load)
  $('kpi-trend').textContent = '—';
}
```

- [ ] **Step 4: Write the escalated cards render function**

```javascript
// ── Render: Escalated Cards ───────────────────────────────────────────
function renderCards() {
  const container = $('escalated-cards');
  const m = state.manifest;

  if (!m || m.status === 'no_data') {
    container.innerHTML = '<p class="text-gray-500 text-sm">No data — run the pipeline to generate intelligence.</p>';
    $('escalated-section').classList.add('hidden');
    return;
  }

  const escalated = Object.entries(m.regions || {})
    .filter(([, r]) => r.status === 'escalated')
    .sort(([, a], [, b]) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity));

  if (escalated.length === 0) {
    container.innerHTML = '<p class="text-green-400 text-sm">No active threats across all regions.</p>';
    return;
  }
  $('escalated-section').classList.remove('hidden');

  container.innerHTML = escalated.map(([region, summary]) => {
    const data = state.regionData[region] || {};
    const sev = (summary.severity || 'LOW').toUpperCase();
    const styles = SEVERITY_STYLES[sev] || SEVERITY_STYLES.LOW;
    const vel = VELOCITY_ARROWS[data.velocity] || VELOCITY_ARROWS.unknown;
    const admiraltyTip = admiraltyTooltip(data.admiralty);

    return `
<div class="rounded-lg border ${styles.card} p-5 flex flex-col gap-3">
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="severity-badge ${styles.badge}">${sev}</span>
      <span class="font-semibold text-lg">${REGION_LABELS[region] || region}</span>
    </div>
    <span class="text-2xl font-bold ${styles.text}">${fmtUSD(summary.vacr_usd)}</span>
  </div>

  <div class="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
    <div><span class="text-gray-500">Scenario</span> <span class="font-medium">${data.primary_scenario || '—'}</span></div>
    <div><span class="text-gray-500">Financial Rank</span> <span class="font-medium">${data.financial_rank ? '#' + data.financial_rank : '—'}</span></div>
    <div data-audience="board"><span class="text-gray-500">Admiralty</span>
      <span class="font-medium" title="${admiraltyTip}">${data.admiralty || '—'} <span class="text-gray-600 cursor-help">ⓘ</span></span>
    </div>
    <div data-audience="board"><span class="text-gray-500">Signal</span> <span class="font-medium">${data.signal_type || '—'}</span></div>
    <div data-audience="board"><span class="text-gray-500">Pillar</span> <span class="font-medium">${data.dominant_pillar || '—'}</span></div>
    <div><span class="text-gray-500">Velocity</span>
      <span class="font-medium ${vel.cls}">${vel.arrow} ${vel.label}</span>
    </div>
  </div>

  ${data.rationale ? `<p class="text-sm text-gray-400 italic border-l-2 border-gray-700 pl-3">"${data.rationale}"</p>` : ''}

  <div class="flex gap-2 pt-1">
    <button onclick="loadPanel('regional', '${region}', 'brief')"
      class="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 rounded text-sm font-medium transition-colors">
      Read Full Brief
    </button>
    <button onclick="loadPanel('regional', '${region}', 'signals')"
      class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition-colors">
      View Signals
    </button>
    <!-- Note: spec wireframe labels this "View Outputs" but "View Signals" is more accurate
         given the panel shows geo/cyber signal detail, not file exports -->
  </div>
</div>`;
  }).join('');
}
```

- [ ] **Step 5: Write the clear/monitor chips render function**

```javascript
// ── Render: Clear & Monitor Chips ─────────────────────────────────────
function renderChips() {
  const container = $('clear-chips');
  const m = state.manifest;
  if (!m || m.status === 'no_data') { container.innerHTML = ''; return; }

  const nonEscalated = Object.entries(m.regions || {})
    .filter(([, r]) => r.status !== 'escalated');

  container.innerHTML = nonEscalated.map(([region, summary]) => {
    const data = state.regionData[region] || {};
    const isMonitor = summary.status === 'monitor';
    const chipCls = isMonitor
      ? 'border-yellow-700 bg-yellow-950/20 text-yellow-300'
      : 'border-green-800 bg-green-950/20 text-green-400';
    const icon = isMonitor ? '⚠' : '✓';
    const admLabel = data.admiralty ? ` <span class="text-gray-500 text-xs">${data.admiralty}</span>` : '';
    const rationale = data.rationale || 'No credible top-4 financial impact scenario active.';

    return `
<div class="relative inline-block group">
  <div class="flex items-center gap-1.5 border ${chipCls} rounded-full px-3 py-1 text-sm cursor-pointer select-none">
    <span>${icon}</span>
    <span>${REGION_LABELS[region] || region}</span>
    <span class="text-gray-500 text-xs uppercase">${summary.status}</span>
    ${admLabel}
  </div>
  <div class="absolute bottom-full left-0 mb-1 w-64 bg-gray-800 border border-gray-700 rounded p-2 text-xs text-gray-300
              hidden group-hover:block z-10 shadow-lg">
    ${rationale}
  </div>
</div>`;
  }).join('');
}
```

- [ ] **Step 6: Write the executive summary render and the master renderAll function**

```javascript
// ── Render: Executive Summary ─────────────────────────────────────────
function renderSummary() {
  const el = $('executive-summary-text');
  const gr = state.globalReport;
  if (gr && gr.executive_summary) {
    el.textContent = gr.executive_summary;
  } else if (!state.manifest || state.manifest.status === 'no_data') {
    el.textContent = 'No intelligence run yet. Click Run All Regions to generate the first report.';
  } else {
    el.textContent = 'Executive summary unavailable.';
  }
}

// ── Master Render ──────────────────────────────────────────────────────
function renderAll() {
  renderKPIs();
  renderSummary();
  renderCards();
  renderChips();
}
```

- [ ] **Step 7: Verify cards and chips render correctly in browser**

```bash
# Server must be running: uv run python server.py
# Open http://localhost:8000
# Expected:
#   - KPI strip populated from run_manifest.json
#   - Executive summary text visible
#   - 3 escalated cards (AME/APAC/MED) with all fields
#   - 2 clear chips (LATAM/NCE) with hover popover showing rationale
#   - No console errors
```

- [ ] **Step 8: Commit**

```bash
git add static/app.js
git commit -m "feat: app.js data layer, KPI render, escalated cards, clear chips"
```

---

## Chunk 4: Frontend — Panels, Progress Bar, History, Settings, Init

> **Use `frontend-design` skill for this task.**

### Task 4: Output panel system

**Files:**
- Modify: `static/app.js` (append sections)

- [ ] **Step 1: Write the panel system**

```javascript
// ── Panel System ──────────────────────────────────────────────────────
function openPanel(title, tabs) {
  // tabs: [{ id, label, render: async fn → html string }]
  $('panel-title').textContent = title;

  const tabBar = $('panel-tabs');
  tabBar.innerHTML = tabs.map((t, i) =>
    `<button id="tab-btn-${t.id}" onclick="activatePanelTab('${t.id}')"
      class="panel-tab px-4 py-2 text-sm ${i === 0 ? 'active' : ''}">${t.label}</button>`
  ).join('');

  // Render first tab immediately, others on demand
  window._panelTabs = tabs;
  window._panelTabCache = {};
  activatePanelTab(tabs[0].id);

  $('panel-overlay').classList.remove('hidden');
  $('output-panel').classList.remove('hidden');
  requestAnimationFrame(() => $('output-panel').classList.add('panel-open'));
}

async function activatePanelTab(tabId) {
  // Update active button style
  document.querySelectorAll('.panel-tab').forEach(b => b.classList.remove('active'));
  $(`tab-btn-${tabId}`)?.classList.add('active');

  const body = $('panel-body');
  if (window._panelTabCache[tabId]) {
    body.innerHTML = window._panelTabCache[tabId];
    return;
  }
  body.innerHTML = '<p class="text-gray-500 text-sm p-4">Loading...</p>';
  const tab = window._panelTabs.find(t => t.id === tabId);
  if (tab) {
    const html = await tab.render();
    window._panelTabCache[tabId] = html;
    body.innerHTML = html;
  }
}

function closePanel() {
  $('output-panel').classList.remove('panel-open');
  setTimeout(() => {
    $('output-panel').classList.add('hidden');
    $('panel-overlay').classList.add('hidden');
    window._panelTabs = null;
    window._panelTabCache = {};
  }, 300); // match CSS transition duration
}

// Escape key closes panel
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });

async function loadPanel(type, region, defaultTab) {
  if (type === 'regional') {
    const label = REGION_LABELS[region] || region;
    openPanel(`${label} — Intelligence`, [
      {
        id: 'brief',
        label: 'Brief',
        render: async () => {
          const data = await fetchJSON(`/api/region/${region}/report`);
          if (!data || !data.report) return '<p class="text-gray-500 p-4">No brief available for this region.</p>';
          return `<div class="prose prose-invert max-w-none p-4">${marked.parse(data.report)}</div>`;
        }
      },
      {
        id: 'signals',
        label: 'Signal Detail',
        render: async () => {
          const data = await fetchJSON(`/api/region/${region}/signals`);
          if (!data) return '<p class="text-gray-500 p-4">No signal data available.</p>';
          const geo = data.geo;
          const cyber = data.cyber;
          let html = '<div class="p-4 space-y-5">';
          if (geo) {
            html += `<div>
              <h4 class="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Geopolitical Signals</h4>
              <p class="text-sm text-gray-200 mb-2">${geo.summary || ''}</p>
              ${geo.lead_indicators?.length ? '<ul class="list-disc list-inside space-y-1">' + geo.lead_indicators.map(i => `<li class="text-sm text-gray-300">${i}</li>`).join('') + '</ul>' : ''}
            </div>`;
          }
          if (cyber) {
            html += `<div>
              <h4 class="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Cyber Signals</h4>
              <p class="text-sm text-gray-200 mb-2">${cyber.summary || ''}</p>
              ${cyber.threat_vector ? `<p class="text-sm"><span class="text-gray-500">Threat vector:</span> ${cyber.threat_vector}</p>` : ''}
              ${cyber.target_assets?.length ? '<p class="text-sm text-gray-500 mt-1">Target assets:</p><ul class="list-disc list-inside">' + cyber.target_assets.map(a => `<li class="text-sm text-gray-300">${a}</li>`).join('') + '</ul>' : ''}
            </div>`;
          }
          html += '</div>';
          return html;
        }
      },
    ]);
    if (defaultTab) activatePanelTab(defaultTab);

  } else if (type === 'global') {
    openPanel('Board Deliverables', [
      {
        id: 'report',
        label: 'Report',
        render: async () => {
          const data = await fetchJSON('/api/outputs/global-md');
          if (!data || !data.markdown) return '<p class="text-gray-500 p-4">Global report not available.</p>';
          return `<div class="prose prose-invert max-w-none p-4">${marked.parse(data.markdown)}</div>`;
        }
      },
      {
        id: 'pdf',
        label: 'PDF',
        render: async () => `
          <div class="p-4 space-y-3">
            <div class="flex justify-end">
              <a href="/api/outputs/pdf" download class="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm">
                Download PDF
              </a>
            </div>
            <iframe src="/api/outputs/pdf" class="w-full rounded border border-gray-700"
              style="height: calc(100vh - 200px)"></iframe>
          </div>`
      },
      {
        id: 'pptx',
        label: 'PowerPoint',
        render: async () => `
          <div class="p-4 flex flex-col items-center gap-4 pt-12">
            <p class="text-gray-400 text-sm">PowerPoint files cannot be previewed in the browser.</p>
            <a href="/api/outputs/pptx" download
              class="px-4 py-2 bg-blue-700 hover:bg-blue-600 rounded text-sm font-medium">
              Download board_report.pptx
            </a>
          </div>`
      },
    ]);
  }
}
```

- [ ] **Step 2: Verify panels open and close in browser**

```
# Open http://localhost:8000 with data present
# Click "Read Full Brief" on AME card
# Expected: panel slides in from right, Brief tab shows rendered markdown
# Click "View Signals" — Signal Detail tab shows geo + cyber sections
# Click "Board Deliverables" button
# Expected: global panel opens, Report tab shows rendered global_report.md
# PDF tab shows iframe (if board_report.pdf exists), download button works
# Press Escape — panel closes
```

- [ ] **Step 3: Write the progress bar + SSE handler**

```javascript
// ── Progress Bar + SSE ────────────────────────────────────────────────
const PHASE_LABELS = {
  gatekeeper: 'Phase 1 — Regional Analysis',
  trend:      'Phase 2 — Velocity Analysis',
  diff:       'Phase 3 — Cross-Regional Diff',
  dashboard:  'Phase 4–5 — Global Report & Exports',
  complete:   'Pipeline complete',
};
const PHASE_ORDER = ['gatekeeper', 'trend', 'diff', 'dashboard', 'complete'];

let progressPercent = 0;

function showProgressBar(label, percent) {
  $('progress-bar-container').classList.remove('hidden');
  $('progress-label').textContent = label;
  $('progress-fill').style.width = percent + '%';
  $('progress-fill').classList.remove('bg-red-600');
  $('progress-fill').classList.add('bg-blue-500');
}

function completeProgressBar(timestamp) {
  $('progress-fill').style.width = '100%';
  $('progress-fill').classList.replace('bg-blue-500', 'bg-green-500');
  $('progress-label').textContent = 'Pipeline complete — ' + fmtTime(timestamp);
  setTimeout(() => {
    $('progress-bar-container').classList.add('hidden');
    loadLatestData(); // refresh all data
  }, 3000);
}

function errorProgressBar(phase) {
  $('progress-fill').classList.replace('bg-blue-500', 'bg-red-600');
  $('progress-label').textContent = `Pipeline failed at ${PHASE_LABELS[phase] || phase}`;
  $('btn-run-all').disabled = false;
  $('btn-run-all').textContent = 'Run All Regions';
}

function initSSE() {
  const source = new EventSource('/api/logs/stream');

  source.addEventListener('phase', e => {
    const data = JSON.parse(e.data);
    const phaseIndex = PHASE_ORDER.indexOf(data.phase);
    const percent = phaseIndex >= 0 ? Math.round((phaseIndex / (PHASE_ORDER.length - 1)) * 90) : 0;

    if (data.phase === 'complete') {
      // Use client time here — server timestamp will arrive via manifest refresh
      completeProgressBar(new Date().toISOString());
    } else if (data.status === 'running') {
      showProgressBar(PHASE_LABELS[data.phase] || data.phase, percent);
    } else if (data.status === 'complete') {
      showProgressBar(PHASE_LABELS[data.phase] + ' ✓', Math.min(percent + 10, 90));
    }
  });

  source.addEventListener('error', e => {
    try {
      const data = JSON.parse(e.data);
      errorProgressBar(data.phase || 'unknown');
    } catch { /* ping or malformed */ }
  });

  source.addEventListener('pipeline', e => {
    const data = JSON.parse(e.data);
    if (data.status === 'started') {
      progressPercent = 0;
      showProgressBar('Initializing...', 5);
      $('btn-run-all').disabled = true;
      $('btn-run-all').textContent = 'Running...';
    }
  });
}

async function runAll() {
  const mode = $('mode-select').value;
  await fetch(`/api/run/all?mode=${mode}`, { method: 'POST' });
}
```

- [ ] **Step 4: Write the History tab, settings modal, archive banner, and init**

```javascript
// ── History Tab ────────────────────────────────────────────────────────
async function renderHistory() {
  const runs = await fetchJSON('/api/runs');
  const container = $('run-history-list');
  if (!runs || runs.length === 0) {
    container.innerHTML = '<p class="text-gray-500 text-sm">No archived runs yet.</p>';
    return;
  }
  container.innerHTML = runs.map(run => {
    const m = run.manifest || {};
    const regions = Object.values(m.regions || {});
    const escalated = regions.filter(r => r.status === 'escalated').length;
    return `
<div class="flex items-center justify-between border-b border-gray-800 py-3 text-sm">
  <div class="text-gray-300">${fmtTime(m.run_timestamp)}</div>
  <div class="font-medium">${fmtUSD(m.total_vacr_exposure_usd)}</div>
  <div class="text-gray-400">${escalated} escalated</div>
  <button onclick="loadArchiveRun(${JSON.stringify(run).replace(/"/g, '&quot;')})"
    class="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs">View</button>
</div>`;
  }).join('');

  // Audit trace
  const trace = await fetchJSON('/api/trace');
  if (trace && trace.log) {
    $('audit-trace').textContent = trace.log;
  }
}

function toggleTrace() {
  $('audit-trace').classList.toggle('hidden');
}

// ── Archive Banner ─────────────────────────────────────────────────────
function showArchiveBanner(run) {
  const m = run.manifest || {};
  $('archive-timestamp').textContent = fmtTime(m.run_timestamp);
  $('archive-banner').classList.remove('hidden');
}

function hideArchiveBanner() {
  $('archive-banner').classList.add('hidden');
}

// ── Nav Tabs ───────────────────────────────────────────────────────────
function switchTab(tab) {
  state.activeTab = tab;
  $('tab-overview').classList.toggle('hidden', tab !== 'overview');
  $('tab-history').classList.toggle('hidden', tab !== 'history');
  if (tab === 'history') renderHistory();
}

// ── Settings Modal ─────────────────────────────────────────────────────
function openSettings() {
  $('settings-modal').classList.remove('hidden');
}
function closeSettings() {
  $('settings-modal').classList.add('hidden');
}

// ── Init ───────────────────────────────────────────────────────────────
(async function init() {
  await loadLatestData();
  initSSE();
})();
```

- [ ] **Step 5: Verify full end-to-end in browser**

```
# Open http://localhost:8000
# 1. Overview tab loads with all data populated
# 2. Click History tab → run list shows, audit trace expands
# 3. Click "View" on a historical run → archive banner appears, KPIs update
# 4. Click "Return to latest" → returns to current run
# 5. Click ⚙ → settings modal opens, mode selector visible
# 6. Start a pipeline run (Tools mode) → progress bar appears,
#    advances through phases, disappears when complete,
#    data refreshes automatically
# 7. No console errors throughout
```

- [ ] **Step 6: Commit**

```bash
git add static/app.js
git commit -m "feat: app.js panels, progress bar, history tab, settings, init"
```

---

## Chunk 5: Integration & Polish

### Task 5: Full integration test + CSS polish

- [ ] **Step 1: Run all backend tests**

```bash
uv run pytest --tb=short -q
```

Expected: all tests pass including the new `test_server.py`.

- [ ] **Step 2: Start server and run full pipeline**

```bash
uv run python server.py &
# In Claude Code: /run-crq
# Watch browser while pipeline runs:
# - Progress bar advances through phases
# - After complete: bar disappears, cards refresh with new data
```

- [ ] **Step 3: Verify all card fields are populated from real output**

After a successful run, check in browser:
- AME card: CRITICAL badge, $22.0M, Ransomware, Rank #1, B2 Admiralty, Trend signal, Geopolitical pillar
- APAC card: HIGH badge, $18.5M, System intrusion, Rank #3
- MED chip: ⚠ Monitor (yellow chip — MED is monitor status, not escalated, so it does NOT appear as a card)
- LATAM chip: ✓ Clear with hover rationale
- NCE chip: ✓ Clear with hover rationale
- Executive summary: multi-sentence board-level text from global_report.json
- "Read Full Brief" on AME → rendered markdown with Why/How/So What headers
- "Board Deliverables" → PDF tab renders iframe

- [ ] **Step 4: Commit and push**

```bash
git add -A
git commit -m "feat: F-2 dashboard rework complete — board-ready intelligence UI"
git push origin main
```
