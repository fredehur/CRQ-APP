# Analyst Dashboard UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `static/index.html` + `static/app.js` as an analyst workstation — split-pane layout, SIGINT Terminal aesthetic, signal convergence explorer, Reports tab, and window-parameterised run trigger.

**Architecture:** Three-layer change. `server.py` gets two additions (new `/api/region/{region}/clusters` endpoint + `window` query param on `/api/run/all`). `index.html` is a full structural rewrite using the same CDN stack (Tailwind + marked.js). `app.js` is a full logic rewrite keeping the existing SSE/event-queue pattern, the agent console, and the history/archive logic.

**Prerequisite:** Plan 1 (`2026-03-16-pipeline-data-contract.md`) must be complete — specifically `signal_clusters.json` must be written by the regional-analyst-agent and `synthesis_brief` must be in `global_report.json` before UI work starts. The UI degrades gracefully when these files are absent.

**Tech Stack:** FastAPI (server.py), Tailwind CSS CDN, marked.js CDN, IBM Plex Mono (Google Fonts CDN), vanilla JS (no build step), Playwright (e2e tests)

---

## Chunk 1: `server.py` additions

### Files
- Modify: `server.py`
- Create: `tests/test_server_api.py`

---

### Task 1: Add `/api/region/{region}/clusters` endpoint

- [ ] **Write the failing test**

Create `tests/test_server_api.py`:

```python
import pytest
from fastapi.testclient import TestClient
import json
import os
from server import app

client = TestClient(app)


def test_clusters_endpoint_no_data():
    """Returns empty clusters object when signal_clusters.json does not exist."""
    r = client.get("/api/region/LATAM/clusters")
    assert r.status_code == 200
    body = r.json()
    assert "region" in body
    assert body["region"] == "LATAM"


def test_clusters_endpoint_invalid_region():
    """Returns 404 for unknown region."""
    r = client.get("/api/region/INVALID/clusters")
    assert r.status_code == 404


def test_run_all_accepts_window_param():
    """POST /api/run/all accepts window query param without error."""
    r = client.post("/api/run/all?mode=tools&window=7d")
    # May return 409 if pipeline is running — that's fine, it means the endpoint accepted the param
    assert r.status_code in (200, 409)


def test_run_all_rejects_invalid_window():
    """POST /api/run/all rejects invalid window value."""
    r = client.post("/api/run/all?mode=tools&window=99x")
    assert r.status_code == 422  # FastAPI validation error


def test_run_region_accepts_window_param():
    """POST /api/run/region/LATAM accepts window query param without error."""
    r = client.post("/api/run/region/LATAM?mode=tools&window=30d")
    assert r.status_code in (200, 409)


def test_run_region_rejects_invalid_window():
    """POST /api/run/region/APAC rejects invalid window value."""
    r = client.post("/api/run/region/APAC?mode=tools&window=bad")
    assert r.status_code == 422
```

- [ ] **Run tests to confirm they fail**

```bash
cd c:/Users/frede/crq-agent-workspace && uv run pytest tests/test_server_api.py -v
```

Expected: `test_clusters_endpoint_no_data` and `test_clusters_endpoint_invalid_region` FAIL (endpoint doesn't exist yet); `test_run_all_accepts_window_param` may pass; `test_run_all_rejects_invalid_window` FAIL.

- [ ] **Add `/api/region/{region}/clusters` to `server.py`**

After the existing `/api/region/{region}/signals` block (around line 134), add:

```python
@app.get("/api/region/{region}/clusters")
async def get_region_clusters(region: str):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    data = _read_json(OUTPUT / "regional" / r.lower() / "signal_clusters.json")
    if data is None:
        return {"region": r, "clusters": [], "total_signals": 0, "sources_queried": 0, "status": "no_data"}
    return data
```

- [ ] **Add `window` param to `/api/run/all` and `/api/run/region/{region}`**

Update both endpoint signatures (FastAPI validates the `Literal` type, returning 422 on invalid values). Also update both driver function signatures to accept `window`:

```python
from typing import Literal

@app.post("/api/run/all")
async def run_all(
    mode: str = Query(default="tools"),
    window: Literal["1d", "7d", "30d", "90d"] = Query(default="7d"),
):
    if pipeline_state["running"]:
        return JSONResponse({"error": "Pipeline already running"}, status_code=409)
    driver = _run_full_mode if mode == "full" else _run_tools_mode
    asyncio.create_task(driver(REGIONS, window=window))
    return {"started": True, "mode": mode, "regions": REGIONS, "window": window}


@app.post("/api/run/region/{region}")
async def run_region(
    region: str,
    mode: str = Query(default="tools"),
    window: Literal["1d", "7d", "30d", "90d"] = Query(default="7d"),
):
    r = region.upper()
    if r not in REGIONS:
        return JSONResponse({"error": f"Unknown region: {region}"}, status_code=404)
    if pipeline_state["running"]:
        return JSONResponse({"error": "Pipeline already running"}, status_code=409)
    driver = _run_full_mode if mode == "full" else _run_tools_mode
    asyncio.create_task(driver([r], window=window))
    return {"started": True, "mode": mode, "regions": [r], "window": window}
```

**Update driver signatures** (the current tools-mode driver calls `regional_search.py` and `write_manifest.py` — not `geo_collector.py` directly; in tools-mode, `window` is passed to `write_manifest.py`; in full-mode, `window` is not yet wired through the Claude CLI call):

```python
# Before:
async def _run_tools_mode(regions: list[str]):

# After:
async def _run_tools_mode(regions: list[str], window: str = "7d"):
    # ... existing body unchanged except:
    # Replace:  await _run("write_manifest.py")
    # With:     await _run("write_manifest.py", "--window", window)


# Before:
async def _run_full_mode(regions: list[str]):

# After:
async def _run_full_mode(regions: list[str], window: str = "7d"):
    # window is accepted for API consistency but not yet passed to claude CLI
    # (full-mode window support is deferred to a future plan)
```

- [ ] **Run all server tests**

```bash
uv run pytest tests/test_server_api.py -v
```

Expected: all 6 PASS.

- [ ] **Commit**

```bash
git add server.py tests/test_server_api.py
git commit -m "feat: add /api/region/{region}/clusters endpoint and window param to run"
```

---

## Chunk 2: `static/index.html` — full rewrite

### Files
- Rewrite: `static/index.html`

The HTML provides structure and style. All dynamic content is injected by `app.js`. No inline JS in the HTML.

---

### Task 2: Write the new `index.html`

- [ ] **Read current `static/index.html` fully before overwriting** (already read in planning — confirm no custom logic embedded in HTML `<script>` tags besides `tailwind.config`)

- [ ] **Write the new `static/index.html`**

Key structural decisions:
- Load IBM Plex Mono from Google Fonts CDN
- Tailwind config extends with SIGINT colors (no change to CDN usage pattern)
- Body background: `#070a0e`
- Layout: fixed header (36px) → progress bar slot → two-panel main (`display:grid; grid-template-columns: 280px 1fr`)
- Left panel: `id="left-panel"` — fixed height with its own scroll
- Right panel: `id="right-panel"` — flex column with overflow-y-auto body
- Three nav tabs: `id="nav-overview"`, `id="nav-reports"`, `id="nav-history"` (tab bodies: `id="tab-overview"`, `id="tab-reports"`, `id="tab-history"`)
- Run trigger: window `<select id="window-select">` + `<button id="btn-run-all">`
- Agent console: identical markup to current (copy verbatim — no changes)
- Settings modal: remove mode selector, keep close button

Full markup:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CRQ Analyst</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: { mono: ['"IBM Plex Mono"', 'monospace'] },
          colors: {
            bg:      '#070a0e',
            surface: '#0d1117',
            border:  '#21262d',
            accent:  '#3fb950',
            dim:     '#6e7681',
            'sev-c': '#ff7b72',
            'sev-h': '#ffa657',
            'sev-m': '#e3b341',
            'sev-ok':'#3fb950',
            'sev-mon':'#79c0ff',
          }
        }
      }
    }
  </script>
  <style>
    * { font-family: 'IBM Plex Mono', monospace; }
    body { background: #070a0e; color: #c9d1d9; padding-top: 36px; }

    /* Header */
    #app-header {
      position: fixed; top: 0; left: 0; right: 0; z-index: 40;
      height: 36px;
      background: #0d1117;
      border-bottom: 1px solid #21262d;
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 16px;
    }

    /* Progress bar */
    #progress-bar-container {
      position: fixed; top: 36px; left: 0; right: 0; z-index: 30;
      background: #0d1117; border-bottom: 1px solid #21262d;
    }
    #progress-fill { height: 100%; background: #3fb950; transition: width 300ms ease-in-out; }

    /* Split pane — only visible on Overview tab */
    #split-pane {
      display: grid;
      grid-template-columns: 280px 1fr;
      height: calc(100vh - 36px);
      overflow: hidden;
    }

    /* Left panel */
    #left-panel {
      border-right: 1px solid #21262d;
      display: flex; flex-direction: column;
      overflow-y: auto;
      background: #080c10;
    }

    /* Right panel */
    #right-panel {
      display: flex; flex-direction: column;
      overflow: hidden;
    }
    #right-panel-body { flex: 1; overflow-y: auto; padding: 12px 16px; }

    /* Region rows */
    .region-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 12px; border-bottom: 1px solid #161b22;
      cursor: pointer; transition: background 0.1s;
    }
    .region-row:hover { background: #161b22; }
    .region-row.active { background: #1c2128; border-left: 2px solid #3fb950; padding-left: 10px; }

    /* Cluster cards */
    .cluster-card {
      background: #0d1117; border: 1px solid #21262d; border-radius: 4px;
      margin-bottom: 8px; overflow: hidden;
    }
    .cluster-card-header {
      padding: 8px 12px; display: flex; align-items: center; gap: 8px;
      cursor: pointer;
    }
    .cluster-card-header:hover { background: #161b22; }
    .cluster-sources { border-top: 1px solid #161b22; }
    .source-row {
      display: flex; gap: 10px; padding: 5px 12px;
      border-bottom: 1px solid #161b22; font-size: 11px;
    }
    .source-row:last-child { border-bottom: none; }

    /* Nav tabs */
    .nav-tab {
      height: 36px; padding: 0 14px;
      display: flex; align-items: center;
      font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
      color: #6e7681; border-bottom: 2px solid transparent;
      cursor: pointer; transition: color 0.1s;
    }
    .nav-tab:hover { color: #c9d1d9; }
    .nav-tab.active { color: #3fb950; border-bottom-color: #3fb950; }

    /* Sev badges */
    .sev { font-size: 9px; padding: 1px 5px; border-radius: 2px; letter-spacing: 0.06em; }
    .sev-c { color: #ff7b72; background: #2d0000; border: 1px solid #da3633; }
    .sev-h { color: #ffa657; background: #2d1800; border: 1px solid #9e6a03; }
    .sev-m { color: #e3b341; background: #2d2200; border: 1px solid #d29922; }
    .sev-ok{ color: #3fb950; background: #0a1a0a; border: 1px solid #238636; }
    .sev-mon{color: #79c0ff; background: #1a1a2d; border: 1px solid #1f6feb; }

    /* Pillar pills */
    .pill-geo   { color: #79c0ff; background: #0d1f36; border: 1px solid #1f6feb; font-size: 9px; padding: 1px 5px; border-radius: 10px; }
    .pill-cyber { color: #d2a8ff; background: #1a0d36; border: 1px solid #6e40c9; font-size: 9px; padding: 1px 5px; border-radius: 10px; }

    /* Conv dot */
    .conv-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
    .conv-strong { background: #da3633; }
    .conv-weak   { background: #d29922; }
    .conv-none   { background: #30363d; }

    /* Reports tab */
    #tab-reports { padding: 20px 24px; overflow-y: auto; max-height: calc(100vh - 36px); }
    #report-preview { font-family: 'IBM Plex Mono', monospace; font-size: 12px; line-height: 1.7; color: #c9d1d9; }
    #report-preview h1, #report-preview h2, #report-preview h3 { color: #e6edf3; margin: 1em 0 0.5em; }
    #report-preview p { margin-bottom: 0.75em; }
    #report-preview code { background: #161b22; padding: 1px 4px; border-radius: 2px; }

    /* History tab */
    #tab-history { padding: 20px 24px; overflow-y: auto; max-height: calc(100vh - 36px); }

    /* Run button */
    #btn-run-all {
      background: #1a3a1a; border: 1px solid #238636; color: #3fb950;
      padding: 3px 12px; border-radius: 2px; font-size: 10px;
      letter-spacing: 0.06em; cursor: pointer; transition: background 0.1s;
    }
    #btn-run-all:hover { background: #1f4d1f; }
    #btn-run-all:disabled { opacity: 0.4; cursor: not-allowed; }

    #window-select {
      background: #0d1117; border: 1px solid #21262d; color: #8b949e;
      padding: 2px 6px; border-radius: 2px; font-size: 10px;
      font-family: 'IBM Plex Mono', monospace; margin-right: 6px;
    }

    /* Agent console (identical to current) */
    #agent-console {
      position: fixed; bottom: 12px; right: 12px; width: 300px; max-height: 260px;
      z-index: 40; background: #0d1117; border: 1px solid #21262d;
      border-radius: 6px; box-shadow: 0 8px 32px rgba(0,0,0,0.6);
      display: flex; flex-direction: column;
    }
    #agent-console-toggle {
      position: fixed; bottom: 12px; right: 12px; z-index: 40;
      background: #0d1117; border: 1px solid #21262d; color: #6e7681;
      font-size: 10px; padding: 3px 10px; border-radius: 10px; cursor: pointer;
    }

    /* Slide-over panel */
    #output-panel {
      transform: translateX(100%); transition: transform 300ms ease-in-out;
      position: fixed; top: 0; right: 0; bottom: 0; z-index: 60;
      width: 100%; max-width: 680px;
      background: #0d1117; border-left: 1px solid #21262d;
      display: flex; flex-direction: column;
    }
    #output-panel.panel-open { transform: translateX(0); }
    #panel-overlay {
      display: none; position: fixed; inset: 0; z-index: 50;
      background: rgba(0,0,0,0.6); backdrop-filter: blur(2px);
    }
    #panel-overlay.visible { display: block; }
  </style>
</head>
<body>

<!-- Fixed header -->
<header id="app-header">
  <div style="display:flex;align-items:center;gap:0">
    <span style="color:#3fb950;font-size:11px;letter-spacing:0.05em;margin-right:20px">// CRQ ANALYST</span>
    <nav style="display:flex;height:36px">
      <div class="nav-tab active" id="nav-overview" onclick="switchTab('overview')">Overview</div>
      <div class="nav-tab" id="nav-reports"  onclick="switchTab('reports')">Reports</div>
      <div class="nav-tab" id="nav-history"  onclick="switchTab('history')">History</div>
    </nav>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <span id="pipeline-status" style="font-size:10px;color:#6e7681">Idle</span>
    <select id="window-select">
      <option value="1d">Last 24h</option>
      <option value="7d" selected>Last 7 days</option>
      <option value="30d">Last 30 days</option>
      <option value="90d">Last quarter</option>
    </select>
    <button id="btn-run-all" onclick="runAll()">▶ RUN ALL</button>
  </div>
</header>

<!-- Progress bar -->
<div id="progress-bar-container" class="hidden" style="padding:4px 16px">
  <div style="display:flex;align-items:center;gap:10px">
    <span id="progress-label" style="font-size:10px;color:#6e7681;white-space:nowrap">Initializing...</span>
    <div style="flex:1;background:#21262d;border-radius:2px;height:2px;overflow:hidden">
      <div id="progress-fill" style="width:0%"></div>
    </div>
  </div>
</div>

<!-- ── OVERVIEW TAB — split pane ─────────────────────────────────── -->
<div id="tab-overview">
  <div id="split-pane">

    <!-- Left panel -->
    <div id="left-panel">
      <!-- Global synthesis -->
      <div id="global-synthesis" style="padding:12px;border-bottom:1px solid #21262d">
        <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:6px">Global Synthesis</div>
        <p id="synthesis-brief" style="font-size:11px;color:#8b949e;line-height:1.5">No run data — click Run All to start.</p>
        <div id="status-counts" style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap"></div>
        <div id="run-meta" style="margin-top:6px;font-size:9px;color:#6e7681"></div>
      </div>
      <!-- Region rows injected by app.js -->
      <div id="region-list"></div>
    </div>

    <!-- Right panel -->
    <div id="right-panel">
      <div id="right-panel-header" style="padding:10px 16px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:8px;flex-shrink:0">
        <span id="right-region-badge" class="sev"></span>
        <span id="right-region-name" style="font-size:13px;color:#e6edf3"></span>
        <span id="right-admiralty-badge" class="admiralty-badge" style="margin-left:auto;font-size:10px;color:#6e7681;cursor:help"></span>
        <span id="right-run-ts" style="font-size:9px;color:#6e7681"></span>
      </div>
      <div id="right-panel-body">
        <p id="right-empty-state" style="color:#6e7681;font-size:11px">Select a region to explore signals.</p>
      </div>
    </div>

  </div>
</div>

<!-- ── REPORTS TAB ──────────────────────────────────────────────── -->
<div id="tab-reports" class="hidden">
  <div style="margin-bottom:16px;display:flex;gap:10px">
    <a id="btn-dl-pdf"  href="/api/outputs/pdf"  target="_blank"
       style="background:#1a3a1a;border:1px solid #238636;color:#3fb950;padding:4px 14px;border-radius:2px;font-size:10px;text-decoration:none">↓ PDF</a>
    <a id="btn-dl-pptx" href="/api/outputs/pptx" target="_blank"
       style="background:#1a3a1a;border:1px solid #238636;color:#3fb950;padding:4px 14px;border-radius:2px;font-size:10px;text-decoration:none">↓ PPTX</a>
    <span id="report-generated-ts" style="font-size:10px;color:#6e7681;align-self:center"></span>
  </div>
  <div id="report-preview">Loading report...</div>
</div>

<!-- ── HISTORY TAB ─────────────────────────────────────────────── -->
<div id="tab-history" class="hidden">
  <h2 style="font-size:13px;color:#e6edf3;margin-bottom:12px">Run History</h2>
  <div id="run-history-list" style="margin-bottom:24px"></div>
  <div style="border-top:1px solid #21262d;padding-top:14px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">Audit Trace</span>
      <button onclick="toggleTrace()" style="font-size:10px;color:#6e7681;cursor:pointer;background:none;border:none">▼</button>
    </div>
    <pre id="audit-trace" class="hidden" style="background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:12px;font-size:10px;color:#6e7681;overflow-x:auto;white-space:pre-wrap"></pre>
  </div>
</div>

<!-- Panel overlay -->
<div id="panel-overlay" onclick="closePanel()"></div>

<!-- Slide-over output panel (for report.md viewer, kept for compat) -->
<aside id="output-panel" aria-hidden="true">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid #21262d;flex-shrink:0">
    <span id="panel-title" style="font-size:13px;color:#e6edf3"></span>
    <button onclick="closePanel()" style="color:#6e7681;font-size:16px;cursor:pointer;background:none;border:none">✕</button>
  </div>
  <div id="panel-tabs" style="display:flex;border-bottom:1px solid #21262d;flex-shrink:0"></div>
  <div id="panel-body" style="flex:1;overflow-y:auto;padding:16px;font-size:12px;color:#c9d1d9"></div>
</aside>

<!-- Agent Activity Console (verbatim from current) -->
<div id="agent-console" class="hidden" style="">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 10px;border-bottom:1px solid #21262d;flex-shrink:0">
    <span style="font-size:10px;color:#c9d1d9;letter-spacing:0.04em">Agent Activity</span>
    <button onclick="hideConsole()" style="color:#6e7681;font-size:12px;cursor:pointer;background:none;border:none">✕</button>
  </div>
  <div id="console-log" style="overflow-y:auto;flex:1;padding:6px;display:flex;flex-direction:column;gap:2px"></div>
</div>
<button id="agent-console-toggle" class="hidden" onclick="showConsole()"
  style="">⬛ Agent Activity</button>

<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Open http://localhost:8000 in browser — verify shell renders**

Expected: dark near-black background, monospace font, three nav tabs in header, left panel visible with "No run data" message, right panel empty.

- [ ] **Commit**

```bash
git add static/index.html
git commit -m "feat: rebuild index.html — split-pane SIGINT layout shell"
```

---

## Chunk 3: `static/app.js` — full rewrite

### Files
- Rewrite: `static/app.js`
- Create: `tests/test_ui.py` (Playwright e2e)

---

### Task 3: Write the new `app.js`

The new `app.js` is structured in 8 clear sections. Write them in order:

**Section 1 — Constants**

```js
const REGIONS = ['APAC', 'AME', 'LATAM', 'MED', 'NCE'];
const REGION_LABELS = {
  APAC: 'Asia-Pacific', AME: 'Americas', LATAM: 'Latin America',
  MED: 'Mediterranean', NCE: 'Northern & Central Europe',
};
const SEV_CLASS = {
  CRITICAL: 'sev sev-c', HIGH: 'sev sev-h', MEDIUM: 'sev sev-m',
  LOW: 'sev sev-ok', CLEAR: 'sev sev-ok', MONITOR: 'sev sev-mon',
};
const SEV_COLOR = {
  CRITICAL: '#ff7b72', HIGH: '#ffa657', MEDIUM: '#e3b341',
  LOW: '#3fb950', CLEAR: '#3fb950', MONITOR: '#79c0ff',
};
const SEV_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'MONITOR', 'LOW', 'CLEAR'];
const ADMIRALTY_MAP = {
  A: 'Always reliable', B: 'Usually reliable', C: 'Fairly reliable',
  D: 'Not usually reliable', E: 'Unreliable', F: 'Cannot be judged',
  '1': 'Confirmed', '2': 'Probably true', '3': 'Possibly true',
  '4': 'Cannot be judged', '5': 'Improbable', '6': 'Truth cannot be judged',
};
```

**Section 2 — State**

```js
let state = {
  manifest: null,
  globalReport: null,
  regionData: {},         // data.json per region
  regionClusters: {},     // signal_clusters.json per region
  selectedRegion: null,
  activeTab: 'overview',
  expandedClusters: new Set(),
};

// Agent console state
let _consolePinned = true, _consoleEverStarted = false;
```

**Section 3 — Helpers**

```js
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmtTime = iso => iso
  ? new Date(iso).toLocaleString('en-US', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'})
  : '—';
const relTime = iso => {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso);
  const h = Math.floor(diff / 3600000);
  if (h < 1) return 'just now';
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
};
const admiraltyTooltip = rating => {
  if (!rating || rating.length < 2) return rating || '—';
  const rel = ADMIRALTY_MAP[rating[0]], cred = ADMIRALTY_MAP[rating[1]];
  return `${rating} — ${rel || '?'} / ${cred || '?'}`;
};
const convDot = n => {
  const cls = n >= 3 ? 'conv-strong' : n >= 2 ? 'conv-weak' : 'conv-none';
  return `<span class="conv-dot ${cls}"></span>`;
};
const sevClass = sev => SEV_CLASS[(sev||'').toUpperCase()] || 'sev';
```

**Section 4 — API**

```js
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
    await Promise.all(REGIONS.map(async r => {
      const [data, clusters] = await Promise.all([
        fetchJSON(`/api/region/${r}`),
        fetchJSON(`/api/region/${r}/clusters`),
      ]);
      state.regionData[r] = data;
      state.regionClusters[r] = clusters;
    }));
  }

  // Default selected region: highest total_signals, tie-break by severity
  if (!state.selectedRegion) {
    state.selectedRegion = pickDefaultRegion();
  }
  renderAll();
}

function pickDefaultRegion() {
  const scored = REGIONS.map(r => {
    const c = state.regionClusters[r];
    const d = state.regionData[r];
    const signals = c?.total_signals ?? 0;
    const sevScore = SEV_ORDER.indexOf((d?.severity||'').toUpperCase());
    return { r, signals, sevScore: sevScore === -1 ? 99 : sevScore };
  });
  scored.sort((a, b) => b.signals - a.signals || a.sevScore - b.sevScore);
  return scored[0]?.r || 'APAC';
}
```

**Section 5 — Render: Left Panel**

```js
function renderLeftPanel() {
  const m = state.manifest;
  const gr = state.globalReport;

  // Synthesis brief
  const brief = gr?.synthesis_brief || (m?.status === 'no_data' ? 'No run data — click Run All to start.' : 'Run in progress...');
  $('synthesis-brief').textContent = brief;

  // Status counts
  if (m && m.status !== 'no_data' && m.regions) {
    const vals = Object.values(m.regions);
    const nEsc = vals.filter(r => r.status === 'escalated').length;
    const nMon = vals.filter(r => r.status === 'monitor').length;
    const nClr = vals.filter(r => r.status === 'clear').length;
    $('status-counts').innerHTML = [
      nEsc ? `<span class="sev sev-c">${nEsc} ESCALATED</span>` : '',
      nMon ? `<span class="sev sev-mon">${nMon} MONITOR</span>` : '',
      nClr ? `<span class="sev sev-ok">${nClr} CLEAR</span>` : '',
    ].filter(Boolean).join('');
  } else {
    $('status-counts').innerHTML = '';
  }

  // Run meta
  if (m?.run_timestamp) {
    const window = m.window_used ? ` — ${m.window_used} window` : '';
    $('run-meta').textContent = `${fmtTime(m.run_timestamp)} (${relTime(m.run_timestamp)})${window}`;
  } else {
    $('run-meta').textContent = '';
  }

  // Region rows
  $('region-list').innerHTML = REGIONS.map(r => {
    const d = state.regionData[r];
    const c = state.regionClusters[r];
    const sev = (d?.severity || d?.status || 'UNKNOWN').toUpperCase();
    const signals = c?.total_signals ?? 0;
    const maxConv = Math.max(0, ...(c?.clusters?.map(cl => cl.convergence) ?? [0]));
    const isActive = r === state.selectedRegion;
    const color = SEV_COLOR[sev] || '#6e7681';
    return `
<div class="region-row ${isActive ? 'active' : ''}" onclick="selectRegion('${r}')">
  <span style="font-size:12px;font-weight:500;color:${color}">${r}</span>
  <div style="display:flex;align-items:center;gap:6px">
    ${convDot(maxConv)}
    <span style="font-size:10px;color:${signals > 0 ? color : '#6e7681'}">${signals > 0 ? signals + ' signals' : sev === 'CLEAR' ? 'clear' : '—'}</span>
  </div>
</div>`;
  }).join('');
}
```

**Section 6 — Render: Right Panel**

```js
function renderRightPanel() {
  const r = state.selectedRegion;
  if (!r) return;

  const d = state.regionData[r] || {};
  const c = state.regionClusters[r];
  const sev = (d.severity || 'UNKNOWN').toUpperCase();
  const status = d.status || 'unknown';

  // Header
  $('right-region-badge').className = sevClass(sev);
  $('right-region-badge').textContent = sev;
  $('right-region-name').textContent = REGION_LABELS[r] || r;
  $('right-admiralty-badge').textContent = d.admiralty || '';
  $('right-admiralty-badge').title = admiraltyTooltip(d.admiralty);
  $('right-run-ts').textContent = d.timestamp ? fmtTime(d.timestamp) : '';

  // Body
  $('right-empty-state').style.display = 'none';
  const body = $('right-panel-body');

  if (!d.region && !c) {
    // No data at all
    body.innerHTML = `<p style="color:#6e7681;font-size:11px">No run data for ${r}. Run the pipeline to populate signals.</p>`;
    return;
  }

  if (status === 'clear') {
    body.innerHTML = renderClearPanel(r, d, c);
    return;
  }

  if (!c || !c.clusters || c.clusters.length === 0) {
    body.innerHTML = `<p style="color:#6e7681;font-size:11px">No signal clusters yet — pipeline may still be processing.</p>`;
    return;
  }

  body.innerHTML = c.clusters.map((cl, i) => renderClusterCard(r, cl, i)).join('');
}

function renderClusterCard(region, cl, i) {
  const id = `cluster-${region}-${i}`;
  const isExpanded = state.expandedClusters.has(id);
  const pillCls = cl.pillar === 'Cyber' ? 'pill-cyber' : 'pill-geo';
  const convColor = cl.convergence >= 3 ? '#ff7b72' : cl.convergence >= 2 ? '#e3b341' : '#6e7681';

  const sourcesHtml = isExpanded ? `
<div class="cluster-sources">
  ${(cl.sources || []).map(s => `
  <div class="source-row">
    <span style="color:#388bfd;min-width:90px;flex-shrink:0">${esc(s.name || '')}</span>
    <span style="color:#8b949e">${esc(s.headline || '')}</span>
  </div>`).join('')}
</div>` : '';

  return `
<div class="cluster-card">
  <div class="cluster-card-header" onclick="toggleCluster('${id}')">
    <span class="${pillCls}">${cl.pillar || '?'}</span>
    <span style="flex:1;font-size:12px;color:#e6edf3">${esc(cl.name || '')}</span>
    <span style="font-size:10px;color:${convColor}">×${cl.convergence} ${isExpanded ? '▾' : '▸'}</span>
  </div>
  ${sourcesHtml}
</div>`;
}

function renderClearPanel(region, d, c) {
  const queried = c?.sources_queried ?? '—';
  return `
<div style="padding:8px 0">
  <div style="color:#3fb950;font-size:12px;margin-bottom:12px">✓ Signal check confirmed — no active threats detected</div>
  <div style="background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:12px;font-size:11px;color:#8b949e">
    <div style="margin-bottom:6px"><span style="color:#6e7681">Gatekeeper rationale: </span>${esc(d.rationale || '—')}</div>
    <div style="margin-bottom:6px"><span style="color:#6e7681">Admiralty: </span>${esc(d.admiralty || '—')} — ${admiraltyTooltip(d.admiralty)}</div>
    <div style="margin-bottom:6px"><span style="color:#6e7681">Window: </span>${esc(c?.window_used || d.window_used || '—')}</div>
    <div><span style="color:#6e7681">Sources queried: </span>${queried}</div>
  </div>
</div>`;
}

function toggleCluster(id) {
  if (state.expandedClusters.has(id)) {
    state.expandedClusters.delete(id);
  } else {
    state.expandedClusters.add(id);
  }
  renderRightPanel();
}

function selectRegion(r) {
  state.selectedRegion = r;
  state.expandedClusters.clear();
  renderLeftPanel();
  renderRightPanel();
}
```

**Section 7 — Render: Reports + History**

```js
async function renderReports() {
  const md = await fetchJSON('/api/outputs/global-md');
  if (md?.markdown) {
    $('report-preview').innerHTML = marked.parse(md.markdown);
  } else {
    $('report-preview').textContent = 'No report available — run the pipeline first.';
  }
  if (state.manifest?.run_timestamp) {
    $('report-generated-ts').textContent = `Generated ${fmtTime(state.manifest.run_timestamp)}`;
  }
}

async function renderHistory() {
  const runs = await fetchJSON('/api/runs') || [];
  $('run-history-list').innerHTML = runs.length === 0
    ? '<p style="color:#6e7681;font-size:11px">No archived runs yet.</p>'
    : runs.map(run => {
        const m = run.manifest || {};
        // Note: archive-run loading (click to view a past run) is out of scope for this plan.
        // The row renders the timestamp and window_used for visual completeness; onclick is intentionally omitted.
        return `<div style="border:1px solid #21262d;border-radius:4px;padding:10px 12px;margin-bottom:6px;font-size:11px;color:#8b949e">
          <span style="color:#e6edf3">${esc(m.run_timestamp ? fmtTime(m.run_timestamp) : run.name)}</span>
          ${m.window_used ? `<span style="color:#6e7681;margin-left:8px">${esc(m.window_used)} window</span>` : ''}
        </div>`;
      }).join('');

  const trace = await fetchJSON('/api/trace');
  if (trace?.log) $('audit-trace').textContent = trace.log;
}

function toggleTrace() {
  $('audit-trace').classList.toggle('hidden');
}
```

**Section 8 — Tab switching + Run + Agent Console + SSE**

```js
function renderAll() {
  renderLeftPanel();
  renderRightPanel();
}

function switchTab(tab) {
  state.activeTab = tab;
  ['overview','reports','history'].forEach(t => {
    $(`tab-${t}`).classList.toggle('hidden', t !== tab);
    $(`nav-${t}`).classList.toggle('active', t === tab);
  });
  if (tab === 'reports') renderReports();
  if (tab === 'history') renderHistory();
}

// ── Run trigger ───────────────────────────────────────────────
async function runAll() {
  const windowVal = $('window-select').value;
  const btn = $('btn-run-all');
  btn.disabled = true;
  $('pipeline-status').textContent = 'Running...';
  showConsole();
  _consoleEverStarted = true;
  try {
    const r = await fetch(`/api/run/all?mode=tools&window=${windowVal}`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      $('pipeline-status').textContent = err.error || 'Run failed';
      btn.disabled = false;
    }
  } catch {
    $('pipeline-status').textContent = 'Server offline';
    btn.disabled = false;
  }
}

// ── Agent Console ─────────────────────────────────────────────
function showConsole() {
  $('agent-console').classList.remove('hidden');
  $('agent-console-toggle').classList.add('hidden');
}
function hideConsole() {
  $('agent-console').classList.add('hidden');
  if (_consoleEverStarted) $('agent-console-toggle').classList.remove('hidden');
}
function appendConsoleEntry(html) {
  const log = $('console-log');
  const div = document.createElement('div');
  div.innerHTML = html;
  log.appendChild(div);
  if (_consolePinned) log.scrollTop = log.scrollHeight;
}

document.addEventListener('DOMContentLoaded', () => {
  const log = $('console-log');
  if (log) {
    log.addEventListener('scroll', () => {
      _consolePinned = log.scrollTop >= log.scrollHeight - log.clientHeight - 5;
    });
  }
});

// ── SSE stream (identical pattern to current) ─────────────────
function startEventStream() {
  const es = new EventSource('/api/logs/stream');
  es.addEventListener('phase', e => {
    const d = JSON.parse(e.data);
    appendConsoleEntry(`<span style="color:#3fb950;font-size:10px">[${d.phase}] ${esc(d.message||'')}</span>`);
  });
  es.addEventListener('gatekeeper', e => {
    const d = JSON.parse(e.data);
    const color = d.decision === 'ESCALATE' ? '#ff7b72' : d.decision === 'MONITOR' ? '#79c0ff' : '#3fb950';
    appendConsoleEntry(`<span style="color:${color};font-size:10px">[GK] ${esc(d.region)} → ${esc(d.decision)}</span>`);
  });
  es.addEventListener('pipeline', e => {
    const d = JSON.parse(e.data);
    if (d.status === 'complete') {
      $('pipeline-status').textContent = 'Idle';
      $('btn-run-all').disabled = false;
      loadLatestData();
    } else if (d.status === 'error') {
      $('pipeline-status').textContent = 'Run failed — check console';
      $('btn-run-all').disabled = false;
      appendConsoleEntry(`<span style="color:#ff7b72;font-size:10px">[ERROR] ${esc(d.message||'')}</span>`);
    }
  });
  es.addEventListener('log', e => {
    const d = JSON.parse(e.data);
    appendConsoleEntry(`<span style="color:#6e7681;font-size:9px">${esc(d.line||'')}</span>`);
  });
  es.onerror = () => {};
}

// ── Panel (kept for compat, used by archive viewer) ───────────
function closePanel() {
  $('output-panel').classList.remove('panel-open');
  $('panel-overlay').classList.remove('visible');
  $('output-panel').setAttribute('aria-hidden', 'true');
}

// ── Init ──────────────────────────────────────────────────────
loadLatestData();
startEventStream();
```

- [ ] **Commit after writing `app.js`**

```bash
git add static/app.js
git commit -m "feat: rebuild app.js — split-pane analyst workstation"
```

---

### Task 4: Playwright e2e tests

- [ ] **Create `tests/test_ui.py`**

```python
import pytest
from playwright.sync_api import sync_playwright, expect


BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        yield page
        browser.close()


def test_header_renders(page):
    """Header logo and nav tabs visible."""
    expect(page.locator("text=// CRQ ANALYST")).to_be_visible()
    expect(page.locator("#nav-overview")).to_be_visible()
    expect(page.locator("#nav-reports")).to_be_visible()
    expect(page.locator("#nav-history")).to_be_visible()


def test_split_pane_visible_on_overview(page):
    """Split pane visible on overview tab; left and right panels present."""
    page.click("#nav-overview")
    expect(page.locator("#left-panel")).to_be_visible()
    expect(page.locator("#right-panel")).to_be_visible()


def test_window_selector_present(page):
    """Window selector and run button present in header."""
    expect(page.locator("#window-select")).to_be_visible()
    expect(page.locator("#btn-run-all")).to_be_visible()


def test_region_rows_rendered(page):
    """All 5 region rows are present in the left panel."""
    region_list = page.locator("#region-list")
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        expect(region_list.get_by_text(r)).to_be_visible()


def test_reports_tab_switches(page):
    """Clicking Reports tab hides overview and shows reports content."""
    page.click("#nav-reports")
    expect(page.locator("#tab-reports")).to_be_visible()
    expect(page.locator("#tab-overview")).to_be_hidden()


def test_history_tab_switches(page):
    """Clicking History tab shows history content."""
    page.click("#nav-history")
    expect(page.locator("#tab-history")).to_be_visible()


def test_overview_tab_returns(page):
    """Clicking Overview tab restores split pane."""
    page.click("#nav-overview")
    expect(page.locator("#split-pane")).to_be_visible()
```

- [ ] **Start the server, run e2e tests**

In a terminal, start the server:
```bash
uv run python server.py
```

In another terminal:
```bash
uv run pytest tests/test_ui.py -v
```

Expected: all 7 PASS.

- [ ] **Fix any failures, then commit**

```bash
git add tests/test_ui.py
git commit -m "test: add Playwright e2e tests for analyst dashboard"
```

---

## Explicitly Out of Scope (this plan)

- **Per-region error indicator in left panel** — the spec's Run Trigger Error States table row 3 ("Region-level error → region row shows error indicator") is deferred. The left panel renders severity/signal count only. A future plan can add the error state indicator.
- **Archive run loading** — clicking a history row to reload a past run is deferred (noted inline in Section 7).
- **Full-mode window passthrough** — `_run_full_mode` accepts `window` for API consistency but does not yet pass it to the Claude CLI call. Deferred to a future pipeline improvement plan.

---

## End-to-End Smoke Test

- [ ] **Run a full mock pipeline with window selector**

1. Open http://localhost:8000
2. Set window selector to "Last 7 days"
3. Click **▶ RUN ALL**
4. Watch Agent Activity Console — confirm phase events appear
5. After completion, confirm:
   - Left panel shows synthesis_brief (not "No run data")
   - Region rows show signal counts and convergence dots
   - Clicking a region (e.g. AME) shows signal clusters in right panel
   - Expanding a cluster reveals source headlines
   - Clicking LATAM (clear) shows confirmation screen
   - Reports tab renders markdown preview
   - History tab shows the completed run

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: analyst dashboard UI — split-pane workstation complete"
```
