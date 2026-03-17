# Agent Config Tab Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Config tab to the CRQ analyst workstation with an Intelligence Sources split-view (OSINT topics + YouTube sources) and a Prompts sub-tab for editing agent instruction bodies, all with diff-preview before saving to disk.

**Architecture:** Six FastAPI endpoints read/write config files directly. The frontend adds a new Config tab to the existing nav with two sub-tabs rendered in plain JS matching the existing IBM Plex Mono / dark-terminal aesthetic. Diffs are generated client-side via jsdiff CDN; all JSON is normalised to canonical form before diffing to eliminate whitespace noise.

**Tech Stack:** Python/FastAPI (backend), Vanilla JS + Tailwind CDN (frontend), jsdiff CDN (diff preview), pytest + httpx TestClient (backend tests).

**Spec:** `docs/superpowers/specs/2026-03-16-agent-config-tab-design.md`

---

## Chunk 1: Backend API

### Task 1: Backend — Topics + Sources endpoints

**Files:**
- Modify: `server.py` (after line 172, before `# ── API: Run Pipeline`)
- Create: `tests/test_config_api.py`

**Context:** `server.py` uses `_read_json(path)` for safe JSON reads and `JSONResponse` for errors. All new endpoints follow the same pattern. `BASE` is already defined as the repo root Path.

**Important — testability:** Do NOT define `_DATA` and `_AGENTS` as module-level constants. Instead, reference `BASE / "data"` and `BASE / ".claude" / "agents"` inline inside each endpoint function. This way, monkeypatching `server.BASE` in tests causes each endpoint to resolve its paths at call time, pointing at the test's temp directory. If they were module-level constants, they'd capture the real `BASE` at import time and the patch would have no effect.

- [ ] **Step 1: Create test file with failing tests for Topics endpoints**

```python
# tests/test_config_api.py
import json
import pytest
import server
from fastapi.testclient import TestClient

# client is built once at collection time — that's fine; BASE is patched per-test
client = TestClient(server.app)


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Redirect server.BASE to an isolated temp directory for each test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)

    topics = [{"id": "test-topic", "type": "event", "keywords": ["foo"], "regions": ["APAC"], "active": True}]
    (data_dir / "osint_topics.json").write_text(json.dumps(topics), encoding="utf-8")

    sources = [{"channel_id": "UCtest", "name": "Test Channel", "region_focus": ["AME"], "topics": ["test-topic"]}]
    (data_dir / "youtube_sources.json").write_text(json.dumps(sources), encoding="utf-8")

    agent_md = "---\nname: test-agent\nmodel: claude-haiku-4-5-20251001\ntools: []\n---\nYou are a test agent."
    (agents_dir / "test-agent.md").write_text(agent_md, encoding="utf-8")

    # Patch BASE on the module — endpoints must use BASE inline (not module-level _DATA/_AGENTS constants)
    monkeypatch.setattr(server, "BASE", tmp_path)
    yield tmp_path


def test_get_topics_returns_list():
    r = client.get("/api/config/topics")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["id"] == "test-topic"


def test_post_topics_writes_file(tmp_data):
    new_topics = [{"id": "new-topic", "type": "trend", "keywords": ["bar"], "regions": ["MED"], "active": False}]
    r = client.post("/api/config/topics", json={"topics": new_topics})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    saved = json.loads((tmp_data / "data" / "osint_topics.json").read_text())
    assert saved[0]["id"] == "new-topic"


def test_get_sources_returns_list():
    r = client.get("/api/config/sources")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["channel_id"] == "UCtest"


def test_post_sources_writes_file(tmp_data):
    new_sources = [{"channel_id": "UCnew", "name": "New", "region_focus": ["NCE"], "topics": []}]
    r = client.post("/api/config/sources", json={"sources": new_sources})
    assert r.status_code == 200
    saved = json.loads((tmp_data / "data" / "youtube_sources.json").read_text())
    assert saved[0]["channel_id"] == "UCnew"


def test_get_sources_empty_when_file_missing(tmp_data, monkeypatch):
    (tmp_data / "data" / "youtube_sources.json").unlink(missing_ok=True)
    r = client.get("/api/config/sources")
    assert r.status_code == 200
    assert r.json() == []


def test_get_prompts_returns_agent_list():
    r = client.get("/api/config/prompts")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data[0]["agent"] == "test-agent"
    assert "frontmatter" in data[0]
    assert "body" in data[0]
    assert data[0]["body"].strip() == "You are a test agent."


def test_post_prompts_preserves_frontmatter(tmp_data):
    r = client.post("/api/config/prompts/test-agent", json={"body": "New instructions."})
    assert r.status_code == 200
    content = (tmp_data / ".claude" / "agents" / "test-agent.md").read_text()
    assert "name: test-agent" in content
    assert "New instructions." in content


def test_post_prompts_unknown_agent_returns_400():
    r = client.post("/api/config/prompts/evil/../etc/passwd", json={"body": "x"})
    assert r.status_code == 400


def test_post_topics_atomic_write(tmp_data, monkeypatch):
    """Verify .tmp file is not left behind after successful write."""
    new_topics = [{"id": "atomic", "type": "event", "keywords": [], "regions": [], "active": True}]
    client.post("/api/config/topics", json={"topics": new_topics})
    tmp_files = list((tmp_data / "data").glob("*.tmp"))
    assert tmp_files == [], f"Temp files left behind: {tmp_files}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:/Users/frede/crq-agent-workspace
uv run pytest tests/test_config_api.py -v 2>&1 | head -40
```

Expected: Multiple FAILED — endpoints not found (404).

- [ ] **Step 3: Add Topics + Sources endpoints to server.py**

Insert after line 172 (after the `get_pptx` endpoint, before `# ── API: Run Pipeline`):

**Do NOT define `_DATA` or `_AGENTS` as module-level constants** — endpoints must compute paths inline from `BASE` so that monkeypatching `BASE` in tests works correctly.

```python
# ── API: Config ───────────────────────────────────────────────────────
def _write_json_atomic(path: Path, data) -> None:
    """Write JSON atomically via tmp file + os.replace."""
    import os
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


@app.get("/api/config/topics")
async def get_topics():
    path = BASE / "data" / "osint_topics.json"   # inline — do not extract to module constant
    raw = path.read_text(encoding="utf-8") if path.exists() else "[]"
    return json.loads(raw)


@app.post("/api/config/topics")
async def post_topics(body: dict):
    topics = body.get("topics")
    if not isinstance(topics, list):
        return JSONResponse({"error": "topics must be an array"}, status_code=400)
    _write_json_atomic(BASE / "data" / "osint_topics.json", topics)
    return {"ok": True}


@app.get("/api/config/sources")
async def get_sources():
    path = BASE / "data" / "youtube_sources.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/api/config/sources")
async def post_sources(body: dict):
    sources = body.get("sources")
    if not isinstance(sources, list):
        return JSONResponse({"error": "sources must be an array"}, status_code=400)
    _write_json_atomic(BASE / "data" / "youtube_sources.json", sources)
    return {"ok": True}
```

- [ ] **Step 4: Add Prompts endpoints to server.py**

Append immediately after the Sources endpoints:

```python
def _parse_agent_md(path: Path) -> dict:
    """Split agent .md into frontmatter object + body string."""
    import re
    content = path.read_text(encoding="utf-8")
    # Match --- block at start of file
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not m:
        return {"frontmatter": {}, "body": content, "_frontmatter_raw": ""}
    fm_raw = m.group(1)
    body = m.group(2)
    # Parse YAML frontmatter keys into dict (simple key: value, no nested support needed)
    fm = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return {"frontmatter": fm, "body": body, "_frontmatter_raw": fm_raw}


def _get_agent_allowlist() -> list[str]:
    """Return sorted list of agent stems from .claude/agents/*.md"""
    if not _AGENTS.exists():
        return []
    return sorted(p.stem for p in _AGENTS.glob("*.md"))


@app.get("/api/config/prompts")
async def get_prompts():
    agents = []
    for stem in _get_agent_allowlist():
        path = _AGENTS / f"{stem}.md"
        parsed = _parse_agent_md(path)
        agents.append({"agent": stem, "frontmatter": parsed["frontmatter"], "body": parsed["body"]})
    return agents


@app.post("/api/config/prompts/{agent}")
async def post_prompt(agent: str, body: dict):
    import os
    allowlist = _get_agent_allowlist()
    if agent not in allowlist:
        return JSONResponse({"error": f"Unknown agent: {agent}"}, status_code=400)
    new_body = body.get("body", "")
    path = _AGENTS / f"{agent}.md"
    parsed = _parse_agent_md(path)
    # Reconstruct file: original frontmatter block preserved verbatim
    new_content = f"---\n{parsed['_frontmatter_raw']}\n---\n{new_body}"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(tmp, path)
    return {"ok": True}
```

- [ ] **Step 5: Run tests — verify all pass**

```bash
cd c:/Users/frede/crq-agent-workspace
uv run pytest tests/test_config_api.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_config_api.py
git commit -m "feat: add config API endpoints for topics, sources, and agent prompts"
```

---

## Chunk 2: Frontend Scaffold + Nav

### Task 2: Add Config tab to HTML and wire switchTab

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`

**Context:** Nav tabs in `index.html` use class `nav-tab` with `onclick="switchTab('x')"`. Tab bodies are `div#tab-{name}` toggled with `hidden` class. `switchTab` in `app.js` line 300-308 iterates over a hardcoded array — add `'config'` to it.

- [ ] **Step 1: Add Config nav tab to index.html**

In `static/index.html`, find the nav block (lines 191-195) and add the Config tab:

```html
<!-- BEFORE -->
      <div class="nav-tab" id="nav-history"  onclick="switchTab('history')">History</div>

<!-- AFTER -->
      <div class="nav-tab" id="nav-history"  onclick="switchTab('history')">History</div>
      <div class="nav-tab" id="nav-config"   onclick="switchTab('config')">Config</div>
```

- [ ] **Step 2: Add jsdiff CDN script to index.html**

Add after the `marked` script tag (line 10):

```html
  <script src="https://cdn.jsdelivr.net/npm/diff@5.2.0/dist/diff.min.js"></script>
```

- [ ] **Step 3: Add Config tab body HTML to index.html**

Add after the closing `</div>` of `tab-history` (after line 275) and before the `<!-- Panel overlay -->` comment:

```html
<!-- ── CONFIG TAB ──────────────────────────────────────────────── -->
<div id="tab-config" class="hidden" style="height:calc(100vh - 36px);display:flex;flex-direction:column;overflow:hidden">

  <!-- Config sub-tab nav -->
  <div style="display:flex;border-bottom:1px solid #21262d;flex-shrink:0;padding:0 16px">
    <div class="nav-tab active" id="cfg-nav-sources" onclick="switchCfgTab('sources')">Intelligence Sources</div>
    <div class="nav-tab" id="cfg-nav-prompts" onclick="switchCfgTab('prompts')">Prompts</div>
  </div>

  <!-- Intelligence Sources sub-tab -->
  <div id="cfg-tab-sources" style="flex:1;display:grid;grid-template-columns:1fr 1fr;overflow:hidden">

    <!-- Topics panel -->
    <div style="border-right:1px solid #21262d;display:flex;flex-direction:column;overflow:hidden">
      <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;justify-content:space-between;flex-shrink:0">
        <span style="font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681">OSINT Topics</span>
        <div style="display:flex;gap:6px">
          <button id="btn-add-topic" onclick="addTopicRow()"
            style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:2px 10px;border-radius:2px;cursor:pointer">+ Add</button>
          <button id="btn-save-topics" onclick="saveTopics()" disabled
            style="font-size:10px;color:#6e7681;background:#0d1117;border:1px solid #21262d;padding:2px 10px;border-radius:2px;cursor:not-allowed;opacity:0.5">Save</button>
        </div>
      </div>
      <div id="topics-error" style="display:none;padding:6px 14px;font-size:10px;color:#ff7b72;background:#2d0000;border-bottom:1px solid #da3633"></div>
      <div id="topics-loading" style="padding:16px;font-size:11px;color:#6e7681">Loading...</div>
      <div id="topics-table" style="display:none;flex:1;overflow-y:auto"></div>
      <div id="topics-empty" style="display:none;padding:24px;text-align:center;font-size:11px;color:#6e7681">
        No topics yet. <button onclick="addTopicRow()" style="color:#3fb950;background:none;border:none;cursor:pointer;font-size:11px">Add your first topic</button>
      </div>
    </div>

    <!-- Sources panel -->
    <div style="display:flex;flex-direction:column;overflow:hidden">
      <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;justify-content:space-between;flex-shrink:0">
        <span style="font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:#6e7681">YouTube Sources</span>
        <div style="display:flex;gap:6px">
          <button id="btn-add-source" onclick="addSourceRow()"
            style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:2px 10px;border-radius:2px;cursor:pointer">+ Add</button>
          <button id="btn-save-sources" onclick="saveSources()" disabled
            style="font-size:10px;color:#6e7681;background:#0d1117;border:1px solid #21262d;padding:2px 10px;border-radius:2px;cursor:not-allowed;opacity:0.5">Save</button>
        </div>
      </div>
      <div id="sources-error" style="display:none;padding:6px 14px;font-size:10px;color:#ff7b72;background:#2d0000;border-bottom:1px solid #da3633"></div>
      <div id="sources-loading" style="padding:16px;font-size:11px;color:#6e7681">Loading...</div>
      <div id="sources-table" style="display:none;flex:1;overflow-y:auto"></div>
      <div id="sources-empty" style="display:none;padding:24px;text-align:center;font-size:11px;color:#6e7681">
        No sources yet. <button onclick="addSourceRow()" style="color:#3fb950;background:none;border:none;cursor:pointer;font-size:11px">Add your first source</button>
      </div>
    </div>
  </div>

  <!-- Prompts sub-tab -->
  <div id="cfg-tab-prompts" style="display:none;flex:1;flex-direction:column;overflow:hidden">
    <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px;flex-shrink:0">
      <select id="agent-select" onchange="onAgentSelect()"
        style="background:#0d1117;border:1px solid #21262d;color:#c9d1d9;padding:3px 8px;border-radius:2px;font-size:11px;font-family:'IBM Plex Mono',monospace">
      </select>
      <button id="btn-save-prompt" onclick="savePrompt()" disabled
        style="font-size:10px;color:#6e7681;background:#0d1117;border:1px solid #21262d;padding:2px 10px;border-radius:2px;cursor:not-allowed;opacity:0.5">Save</button>
    </div>
    <div id="prompts-error" style="display:none;padding:6px 14px;font-size:10px;color:#ff7b72;background:#2d0000;border-bottom:1px solid #da3633"></div>
    <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
      <!-- Frontmatter (read-only) -->
      <div id="fm-panel" style="padding:10px 14px;border-bottom:1px solid #21262d;flex-shrink:0;font-size:10px;color:#6e7681;display:flex;gap:16px;flex-wrap:wrap"></div>
      <!-- Body textarea -->
      <textarea id="prompt-body" oninput="onPromptEdit()"
        style="flex:1;resize:none;background:#080c10;border:none;color:#c9d1d9;padding:14px;font-size:12px;font-family:'IBM Plex Mono',monospace;line-height:1.6;outline:none"></textarea>
    </div>
  </div>
</div>

<!-- Diff preview modal -->
<div id="diff-modal" style="display:none;position:fixed;inset:0;z-index:70;background:rgba(0,0,0,0.75);backdrop-filter:blur(2px);align-items:center;justify-content:center">
  <div style="background:#0d1117;border:1px solid #21262d;border-radius:6px;width:700px;max-width:95vw;max-height:80vh;display:flex;flex-direction:column">
    <div style="padding:12px 16px;border-bottom:1px solid #21262d;display:flex;align-items:center;justify-content:space-between;flex-shrink:0">
      <span style="font-size:12px;color:#e6edf3">Preview changes</span>
      <button onclick="closeDiffModal()" style="color:#6e7681;font-size:14px;background:none;border:none;cursor:pointer">&#x2715;</button>
    </div>
    <pre id="diff-output" style="flex:1;overflow-y:auto;padding:14px;font-size:11px;line-height:1.5;white-space:pre-wrap;font-family:'IBM Plex Mono',monospace;margin:0"></pre>
    <div id="diff-backend-error" style="display:none;padding:6px 14px;font-size:10px;color:#ff7b72;background:#2d0000;border-top:1px solid #da3633"></div>
    <div style="padding:10px 16px;border-top:1px solid #21262d;display:flex;justify-content:flex-end;gap:8px;flex-shrink:0">
      <button onclick="closeDiffModal()"
        style="font-size:10px;color:#6e7681;background:#0d1117;border:1px solid #21262d;padding:4px 16px;border-radius:2px;cursor:pointer">Cancel</button>
      <button id="btn-diff-confirm" onclick="confirmSave()"
        style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:4px 16px;border-radius:2px;cursor:pointer">Confirm</button>
    </div>
  </div>
</div>

<!-- Unsaved changes modal -->
<div id="unsaved-modal" style="display:none;position:fixed;inset:0;z-index:80;background:rgba(0,0,0,0.75);align-items:center;justify-content:center">
  <div style="background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:24px;width:360px">
    <p style="font-size:12px;color:#c9d1d9;margin-bottom:16px">You have unsaved changes. Leave anyway?</p>
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button id="btn-unsaved-cancel" style="font-size:10px;color:#6e7681;background:#0d1117;border:1px solid #21262d;padding:4px 16px;border-radius:2px;cursor:pointer">Stay</button>
      <button id="btn-unsaved-confirm" style="font-size:10px;color:#ff7b72;background:#2d0000;border:1px solid #da3633;padding:4px 16px;border-radius:2px;cursor:pointer">Leave</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Update switchTab in app.js to include config**

In `static/app.js`, find `switchTab` (line 300) and update:

```js
// BEFORE
function switchTab(tab) {
  state.activeTab = tab;
  ['overview','reports','history'].forEach(t => {
    $(`tab-${t}`).classList.toggle('hidden', t !== tab);
    $(`nav-${t}`).classList.toggle('active', t === tab);
  });
  if (tab === 'reports') renderReports();
  if (tab === 'history') renderHistory();
}

// AFTER
function switchTab(tab) {
  if (cfgState.dirty.topics || cfgState.dirty.sources || cfgState.dirty.prompt) {
    showUnsavedModal(() => _doSwitchTab(tab));
    return;
  }
  _doSwitchTab(tab);
}

function _doSwitchTab(tab) {
  state.activeTab = tab;
  ['overview','reports','history','config'].forEach(t => {
    $(`tab-${t}`).classList.toggle('hidden', t !== tab);
    $(`nav-${t}`).classList.toggle('active', t === tab);
  });
  if (tab === 'reports') renderReports();
  if (tab === 'history') renderHistory();
  if (tab === 'config') loadConfigTab();
}
```

- [ ] **Step 5: Add Config sub-tab switcher + cfgState to app.js**

Append to the top of **Section 2: State** in `app.js` (after line 32):

```js
// Config tab state
const cfgState = {
  topics: [],          // current in-memory topics array
  topicsBaseline: '',  // canonical JSON string at last fetch/save
  sources: [],
  sourcesBaseline: '',
  prompts: [],         // [{agent, frontmatter, body}]
  selectedAgent: null,
  promptBaseline: '',  // body string at last fetch/save
  dirty: { topics: false, sources: false, prompt: false },
  pendingNavAction: null, // fn to call after unsaved-modal confirm
  loaded: false,       // guard: skip re-fetch if already loaded this session
};
```

Add `switchCfgTab` + `_doSwitchCfgTab` functions at the end of `app.js` (before the `// ── Init` comment):

```js
// ── Config Tab ────────────────────────────────────────────────────────
function switchCfgTab(tab) {
  // Determine whether the tab being LEFT is dirty
  const leavingSources = $('cfg-tab-sources') && $('cfg-tab-sources').style.display !== 'none';
  const leavingPrompts = $('cfg-tab-prompts') && $('cfg-tab-prompts').style.display !== 'none';
  const isDirty = (leavingSources && (cfgState.dirty.topics || cfgState.dirty.sources)) ||
                  (leavingPrompts && cfgState.dirty.prompt);
  if (isDirty) {
    showUnsavedModal(() => _doSwitchCfgTab(tab));
    return;
  }
  _doSwitchCfgTab(tab);
}

function _doSwitchCfgTab(tab) {
  ['sources','prompts'].forEach(t => {
    $(`cfg-tab-${t}`).style.display = t === tab ? (t === 'sources' ? 'grid' : 'flex') : 'none';
    $(`cfg-nav-${t}`).classList.toggle('active', t === tab);
  });
}
```

- [ ] **Step 6: Open browser and verify Config tab appears in nav, clicking shows empty sub-tabs**

```bash
# Server should already be running on port 8000. If not:
uv run uvicorn server:app --reload --port 8000
```

Navigate to `http://127.0.0.1:8000/` — click Config tab. Expected: Config nav tab visible, Intelligence Sources and Prompts sub-tabs render, "Loading..." shown in both panels.

- [ ] **Step 7: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat: add Config tab scaffold — nav, sub-tabs, diff modal, unsaved modal"
```

---

## Chunk 3: Intelligence Sources Sub-tab

### Task 3: Topics panel data layer + table render

**Files:**
- Modify: `static/app.js`

Append all Config JS functions after `switchCfgTab` and before `// ── Init`.

- [ ] **Step 1: Add loadConfigTab + topic/source loaders**

```js
async function loadConfigTab() {
  if (cfgState.loaded) return; // already loaded this session — preserve in-memory state and dirty flags
  // Parallel fetch — topics, sources, prompts
  const [topicsRaw, sourcesRaw, promptsRaw] = await Promise.all([
    fetch('/api/config/topics').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
    fetch('/api/config/sources').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
    fetch('/api/config/prompts').then(r => r.ok ? r.json() : []).catch(() => []),
  ]);

  // Normalise JSON to canonical form (eliminates whitespace diff noise)
  cfgState.topicsBaseline = JSON.stringify(JSON.parse(topicsRaw), null, 2);
  cfgState.topics = JSON.parse(cfgState.topicsBaseline);
  cfgState.sourcesBaseline = JSON.stringify(JSON.parse(sourcesRaw), null, 2);
  cfgState.sources = JSON.parse(cfgState.sourcesBaseline);
  cfgState.prompts = promptsRaw;
  cfgState.dirty = { topics: false, sources: false, prompt: false };
  cfgState.loaded = true;

  renderTopicsTable();
  renderSourcesTable();
  renderPromptsPanel();
}
```

- [ ] **Step 2: Add renderTopicsTable**

```js
function renderTopicsTable() {
  const loading = $('topics-loading');
  const table = $('topics-table');
  const empty = $('topics-empty');
  loading.style.display = 'none';

  if (cfgState.topics.length === 0) {
    table.style.display = 'none';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  table.style.display = 'block';

  const REGIONS = ['APAC','AME','LATAM','MED','NCE'];
  const TYPES = ['event','trend','mixed'];

  table.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:11px">
      <thead>
        <tr style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #21262d">
          <th style="padding:6px 10px;text-align:left;width:160px">ID</th>
          <th style="padding:6px 10px;text-align:left;width:80px">Type</th>
          <th style="padding:6px 10px;text-align:left">Keywords</th>
          <th style="padding:6px 10px;text-align:left;width:140px">Regions</th>
          <th style="padding:6px 10px;text-align:center;width:50px">Active</th>
          <th style="padding:6px 10px;width:60px"></th>
        </tr>
      </thead>
      <tbody id="topics-tbody">
        ${cfgState.topics.map((t, i) => renderTopicRow(t, i)).join('')}
      </tbody>
    </table>`;
}

function renderTopicRow(t, i) {
  // t._isNew marks rows added via addTopicRow() — id field is editable until saved
  const isNew = !!t._isNew;
  const REGIONS = ['APAC','AME','LATAM','MED','NCE'];
  const regionOpts = REGIONS.map(r =>
    `<option value="${r}" ${(t.regions||[]).includes(r) ? 'selected' : ''}>${r}</option>`
  ).join('');

  return `<tr style="border-bottom:1px solid #161b22" id="topic-row-${i}">
    <td style="padding:4px 10px">
      ${isNew
        ? `<input type="text" value="${esc(t.id||'')}" oninput="onTopicField(${i},'id',this.value)"
             style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:140px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">`
        : `<span style="color:#8b949e">${esc(t.id)}</span>`}
    </td>
    <td style="padding:4px 10px">
      <select onchange="onTopicField(${i},'type',this.value)"
        style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 4px;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">
        ${['event','trend','mixed'].map(tp => `<option value="${tp}" ${t.type===tp?'selected':''}>${tp}</option>`).join('')}
      </select>
    </td>
    <td style="padding:4px 10px">
      <input type="text" value="${esc((t.keywords||[]).join(', '))}" oninput="onTopicField(${i},'keywords',this.value)"
        style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">
    </td>
    <td style="padding:4px 10px">
      <select multiple onchange="onTopicField(${i},'regions',[...this.selectedOptions].map(o=>o.value))"
        style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;font-size:10px;font-family:'IBM Plex Mono',monospace;border-radius:2px;width:130px;height:52px">
        ${regionOpts}
      </select>
    </td>
    <td style="padding:4px 10px;text-align:center">
      <input type="checkbox" ${t.active ? 'checked' : ''} onchange="onTopicField(${i},'active',this.checked)"
        style="accent-color:#3fb950;cursor:pointer">
    </td>
    <td style="padding:4px 10px">
      <button onclick="deleteTopicRow(${i})" id="del-topic-${i}"
        style="font-size:10px;color:#6e7681;background:none;border:1px solid #30363d;padding:1px 8px;border-radius:2px;cursor:pointer">Del</button>
    </td>
  </tr>`;
}
```

- [ ] **Step 3: Add topic mutation helpers**

```js
function onTopicField(i, field, value) {
  if (field === 'keywords') {
    cfgState.topics[i].keywords = value.split(',').map(s => s.trim()).filter(Boolean);
  } else {
    cfgState.topics[i][field] = value;
  }
  markDirty('topics');
}

function addTopicRow() {
  // _isNew flag drives editable id field in renderTopicRow — no DOM surgery needed
  // Strip _isNew before POST (see saveTopics)
  cfgState.topics.push({ id: '', type: 'event', keywords: [], regions: [], active: true, _isNew: true });
  renderTopicsTable(); // full re-render — renderTopicRow reads t._isNew
  markDirty('topics');
}

function deleteTopicRow(i) {
  const btn = $(`del-topic-${i}`);
  if (btn && btn.dataset.confirming) {
    cfgState.topics.splice(i, 1);
    renderTopicsTable();
    markDirty('topics');
  } else {
    if (btn) { btn.textContent = 'Sure?'; btn.style.color = '#ff7b72'; btn.dataset.confirming = '1'; }
    setTimeout(() => { if (btn) { btn.textContent = 'Del'; btn.style.color = '#6e7681'; delete btn.dataset.confirming; } }, 3000);
  }
}

function markDirty(panel) {
  cfgState.dirty[panel] = true;
  const btnMap = { topics: 'btn-save-topics', sources: 'btn-save-sources', prompt: 'btn-save-prompt' };
  const btn = $(btnMap[panel]);
  if (btn) {
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.style.color = '#3fb950';
    btn.style.borderColor = '#238636';
    btn.style.cursor = 'pointer';
  }
}

function resetSaveBtn(panel) {
  cfgState.dirty[panel] = false;
  const btnMap = { topics: 'btn-save-topics', sources: 'btn-save-sources', prompt: 'btn-save-prompt' };
  const btn = $(btnMap[panel]);
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.style.color = '#6e7681';
    btn.style.borderColor = '#21262d';
    btn.style.cursor = 'not-allowed';
  }
}
```

- [ ] **Step 4: Add Sources panel render + mutation helpers**

```js
function renderSourcesTable() {
  const loading = $('sources-loading');
  const table = $('sources-table');
  const empty = $('sources-empty');
  loading.style.display = 'none';

  if (cfgState.sources.length === 0) {
    table.style.display = 'none';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  table.style.display = 'block';

  const REGIONS = ['APAC','AME','LATAM','MED','NCE'];
  const topicIds = cfgState.topics.map(t => t.id).filter(Boolean);

  table.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:11px">
      <thead>
        <tr style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.06em;border-bottom:1px solid #21262d">
          <th style="padding:6px 10px;text-align:left">Channel ID</th>
          <th style="padding:6px 10px;text-align:left">Name</th>
          <th style="padding:6px 10px;text-align:left;width:140px">Region Focus</th>
          <th style="padding:6px 10px;text-align:left;width:140px">Topics</th>
          <th style="padding:6px 10px;width:60px"></th>
        </tr>
      </thead>
      <tbody id="sources-tbody">
        ${cfgState.sources.map((s, i) => renderSourceRow(s, i, topicIds)).join('')}
      </tbody>
    </table>`;
}

function renderSourceRow(s, i, topicIds) {
  const REGIONS = ['APAC','AME','LATAM','MED','NCE'];
  const regionOpts = REGIONS.map(r =>
    `<option value="${r}" ${(s.region_focus||[]).includes(r)?'selected':''}>${r}</option>`
  ).join('');

  const topicOpts = topicIds.map(id => {
    const isSaved = (s.topics||[]).includes(id);
    return `<option value="${id}" ${isSaved?'selected':''}>${esc(id)}</option>`;
  });
  // Add missing IDs with warning
  (s.topics||[]).filter(id => !topicIds.includes(id)).forEach(id => {
    topicOpts.push(`<option value="${id}" selected style="color:#e3b341">${esc(id)} (missing)</option>`);
  });

  return `<tr style="border-bottom:1px solid #161b22" id="source-row-${i}">
    <td style="padding:4px 10px">
      <input type="text" value="${esc(s.channel_id||'')}" oninput="onSourceField(${i},'channel_id',this.value)"
        style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">
    </td>
    <td style="padding:4px 10px">
      <input type="text" value="${esc(s.name||'')}" oninput="onSourceField(${i},'name',this.value)"
        style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;padding:2px 6px;width:100%;font-size:11px;font-family:'IBM Plex Mono',monospace;border-radius:2px">
    </td>
    <td style="padding:4px 10px">
      <select multiple onchange="onSourceField(${i},'region_focus',[...this.selectedOptions].map(o=>o.value))"
        style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;font-size:10px;font-family:'IBM Plex Mono',monospace;border-radius:2px;width:130px;height:52px">
        ${regionOpts}
      </select>
    </td>
    <td style="padding:4px 10px">
      <select multiple onchange="onSourceField(${i},'topics',[...this.selectedOptions].map(o=>o.value))"
        style="background:#080c10;border:1px solid #21262d;color:#c9d1d9;font-size:10px;font-family:'IBM Plex Mono',monospace;border-radius:2px;width:130px;height:52px">
        ${topicOpts.join('')}
      </select>
    </td>
    <td style="padding:4px 10px">
      <button onclick="deleteSourceRow(${i})" id="del-source-${i}"
        style="font-size:10px;color:#6e7681;background:none;border:1px solid #30363d;padding:1px 8px;border-radius:2px;cursor:pointer">Del</button>
    </td>
  </tr>`;
}

function onSourceField(i, field, value) {
  cfgState.sources[i][field] = value;
  markDirty('sources');
}

function addSourceRow() {
  cfgState.sources.push({ channel_id: '', name: '', region_focus: [], topics: [] });
  renderSourcesTable();
  markDirty('sources');
}

function deleteSourceRow(i) {
  const btn = $(`del-source-${i}`);
  if (btn && btn.dataset.confirming) {
    cfgState.sources.splice(i, 1);
    renderSourcesTable();
    markDirty('sources');
  } else {
    if (btn) { btn.textContent = 'Sure?'; btn.style.color = '#ff7b72'; btn.dataset.confirming = '1'; }
    setTimeout(() => { if (btn) { btn.textContent = 'Del'; btn.style.color = '#6e7681'; delete btn.dataset.confirming; } }, 3000);
  }
}
```

- [ ] **Step 5: Verify in browser — load Config tab, see Topics and Sources tables render**

Navigate to `http://127.0.0.1:8000/` → Config tab → Intelligence Sources. Expected: Topics table shows existing OSINT topics from `data/osint_topics.json`. Sources panel shows "No sources yet" (file doesn't exist yet). Both Load fine with no console errors.

- [ ] **Step 6: Commit**

```bash
git add static/app.js
git commit -m "feat: Intelligence Sources sub-tab — Topics and Sources tables with edit/add/delete"
```

---

## Chunk 4: Save flow, Prompts sub-tab, toast

### Task 4: Save + diff preview flow for all panels

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add diff modal + save orchestration**

```js
// ── Diff modal + save flow ─────────────────────────────────────────────
let _pendingSave = null; // { panel, postFn }

function openDiffModal(beforeStr, afterStr, postFn, panel) {
  _pendingSave = { postFn, panel };
  $('diff-backend-error').style.display = 'none';

  const lines = Diff.diffLines(beforeStr, afterStr);
  let html = '';
  lines.forEach(part => {
    const color = part.added ? '#3fb950' : part.removed ? '#ff7b72' : '#6e7681';
    const prefix = part.added ? '+ ' : part.removed ? '- ' : '  ';
    const escapedLines = esc(part.value).split('\n').filter((_, i, arr) => i < arr.length - 1 || part.value.endsWith('\n') || arr.length === 1);
    escapedLines.forEach(line => {
      html += `<span style="color:${color}">${prefix}${line}\n</span>`;
    });
  });

  $('diff-output').innerHTML = html || '<span style="color:#6e7681">No changes detected.</span>';
  $('diff-modal').style.display = 'flex';
}

function closeDiffModal() {
  $('diff-modal').style.display = 'none';
  _pendingSave = null;
}

async function confirmSave() {
  if (!_pendingSave) return;
  const { postFn, panel } = _pendingSave;
  $('btn-diff-confirm').disabled = true;
  $('diff-backend-error').style.display = 'none';
  try {
    const result = await postFn();
    if (!result.ok) throw new Error(result.error || 'Save failed');
    closeDiffModal();
    showToast('Saved successfully');
    resetSaveBtn(panel);
    // Update baseline to new saved state
    if (panel === 'topics') cfgState.topicsBaseline = JSON.stringify(cfgState.topics, null, 2);
    if (panel === 'sources') cfgState.sourcesBaseline = JSON.stringify(cfgState.sources, null, 2);
    if (panel === 'prompt') cfgState.promptBaseline = $('prompt-body').value;
  } catch (err) {
    $('diff-backend-error').textContent = err.message;
    $('diff-backend-error').style.display = 'block';
  } finally {
    $('btn-diff-confirm').disabled = false;
  }
}

async function saveTopics() {
  // Strip _isNew flag before serialising — it is a UI-only marker, not part of the schema
  cfgState.topics.forEach(t => delete t._isNew);
  // Uniqueness validation
  const ids = cfgState.topics.map(t => t.id).filter(Boolean);
  const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
  const errEl = $('topics-error');
  if (dupes.length) {
    errEl.textContent = `Duplicate topic IDs: ${dupes.join(', ')}`;
    errEl.style.display = 'block';
    return;
  }
  errEl.style.display = 'none';

  const afterStr = JSON.stringify(cfgState.topics, null, 2);
  openDiffModal(cfgState.topicsBaseline, afterStr, async () => {
    const r = await fetch('/api/config/topics', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ topics: cfgState.topics }),
    });
    return r.json();
  }, 'topics');
}

async function saveSources() {
  $('sources-error').style.display = 'none';
  const afterStr = JSON.stringify(cfgState.sources, null, 2);
  openDiffModal(cfgState.sourcesBaseline, afterStr, async () => {
    const r = await fetch('/api/config/sources', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ sources: cfgState.sources }),
    });
    return r.json();
  }, 'sources');
}
```

- [ ] **Step 2: Add Prompts panel render + save**

```js
// ── Prompts panel ─────────────────────────────────────────────────────
function renderPromptsPanel() {
  const sel = $('agent-select');
  if (!cfgState.prompts.length) {
    sel.disabled = true;
    $('prompt-body').value = 'No agent files found in .claude/agents/.';
    $('prompt-body').disabled = true;
    return;
  }
  sel.innerHTML = cfgState.prompts.map(p =>
    `<option value="${esc(p.agent)}">${esc(p.agent)}</option>`
  ).join('');
  sel.disabled = false;
  $('prompt-body').disabled = false;
  cfgState.selectedAgent = cfgState.prompts[0].agent;
  loadAgentIntoEditor(cfgState.prompts[0]);
}

function loadAgentIntoEditor(agentObj) {
  // Render frontmatter as read-only labeled fields
  const fm = agentObj.frontmatter || {};
  $('fm-panel').innerHTML = Object.entries(fm).map(([k, v]) =>
    `<span><span style="color:#3fb950">${esc(k)}:</span> <span style="color:#8b949e">${esc(String(v))}</span></span>`
  ).join('');

  $('prompt-body').value = agentObj.body || '';
  cfgState.promptBaseline = agentObj.body || '';
  cfgState.selectedAgent = agentObj.agent;
  resetSaveBtn('prompt');
}

function onAgentSelect() {
  const agent = $('agent-select').value;
  if (cfgState.dirty.prompt) {
    showUnsavedModal(() => {
      const obj = cfgState.prompts.find(p => p.agent === agent);
      if (obj) loadAgentIntoEditor(obj);
    });
    // Reset select to current agent (modal will handle navigation)
    $('agent-select').value = cfgState.selectedAgent;
    return;
  }
  const obj = cfgState.prompts.find(p => p.agent === agent);
  if (obj) loadAgentIntoEditor(obj);
}

function onPromptEdit() {
  markDirty('prompt');
}

async function savePrompt() {
  const body = $('prompt-body').value;
  openDiffModal(cfgState.promptBaseline, body, async () => {
    const r = await fetch(`/api/config/prompts/${encodeURIComponent(cfgState.selectedAgent)}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ body }),
    });
    return r.json();
  }, 'prompt');
}
```

- [ ] **Step 3: Add toast + unsaved modal helpers**

```js
// ── Toast ─────────────────────────────────────────────────────────────
let _toastTimer = null;
function showToast(msg) {
  let el = $('cfg-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'cfg-toast';
    el.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:90;background:#1a3a1a;border:1px solid #238636;color:#3fb950;font-size:10px;padding:6px 14px;border-radius:4px;font-family:"IBM Plex Mono",monospace;transition:opacity 0.3s';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.style.opacity = '1';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.style.opacity = '0'; }, 3000);
}

// ── Unsaved modal ──────────────────────────────────────────────────────
function showUnsavedModal(onConfirm) {
  cfgState.pendingNavAction = onConfirm;
  $('unsaved-modal').style.display = 'flex';
  $('btn-unsaved-cancel').onclick = () => {
    $('unsaved-modal').style.display = 'none';
    cfgState.pendingNavAction = null;
  };
  $('btn-unsaved-confirm').onclick = () => {
    $('unsaved-modal').style.display = 'none';
    cfgState.dirty = { topics: false, sources: false, prompt: false };
    if (cfgState.pendingNavAction) cfgState.pendingNavAction();
    cfgState.pendingNavAction = null;
  };
}
```

- [ ] **Step 4: Verify full save flow in browser**

1. Open Config tab → Intelligence Sources
2. Edit a topic keyword → Save button turns green
3. Click Save → diff modal opens showing the change
4. Click Confirm → toast "Saved successfully" appears bottom-right, Save button greys out
5. Verify file updated: `cat data/osint_topics.json`
6. Edit a prompt body → Save → diff → Confirm → check `.claude/agents/{agent}.md` frontmatter is intact

- [ ] **Step 5: Run backend tests one final time**

```bash
cd c:/Users/frede/crq-agent-workspace
uv run pytest tests/test_config_api.py -v
```

Expected: All 9 PASS.

- [ ] **Step 6: Final commit**

```bash
git add static/app.js static/index.html
git commit -m "feat: Config tab complete — save/diff flow, Prompts editor, toast, unsaved modal"
```

---

## Manual Verification Checklist

Before declaring done, verify each behaviour in the browser:

- [ ] Config tab appears in nav alongside Overview / Reports / History
- [ ] Clicking Config loads Topics and Sources in parallel (no blocking)
- [ ] Topics table renders existing `data/osint_topics.json` rows
- [ ] Adding a topic row creates an editable `id` field; existing rows have read-only `id`
- [ ] Duplicate topic IDs block Save with inline error
- [ ] Delete shows "Sure?" confirmation; second click removes row
- [ ] Saving Topics opens diff modal showing only real changes (no whitespace noise)
- [ ] Sources panel shows empty state when `youtube_sources.json` absent
- [ ] Sources `topics` multi-select populates from current Topics in-memory state
- [ ] Prompts panel renders all agents in alphabetical dropdown
- [ ] Frontmatter keys display as read-only labeled fields
- [ ] Body textarea is editable; Save Prompt opens diff modal
- [ ] Confirming a prompt save preserves the frontmatter block verbatim in the file
- [ ] Navigating away from dirty sub-tab shows unsaved-changes modal
- [ ] Cancel in unsaved modal returns to current sub-tab with edits intact
- [ ] Confirm in unsaved modal discards dirty state and navigates
- [ ] Toast appears bottom-right, auto-hides after 3 seconds, does not stack
