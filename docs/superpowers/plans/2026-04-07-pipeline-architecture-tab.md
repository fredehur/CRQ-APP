# Pipeline Architecture Tab — Implementation Plan


**Goal:** Add a "Pipeline" tab to the CRQ app that visually explains the full agentic intelligence pipeline — both as an agentic framework reference and as an intelligence methodology guide — with a side panel that surfaces agent prompts for editing (relocating the existing Config > Prompts sub-tab).

**Architecture:** Pure frontend feature. A new top-level tab in `static/index.html` with pipeline node data defined as a JS constant in `static/app.js`. Nodes render dynamically from data; clicking any node opens a right-side panel with three sections (Analytical Role, Agentic Architecture, Agent Configuration). No new backend endpoints — prompt editor reuses existing `/api/config/prompts` endpoints.

**Tech Stack:** Vanilla JS, Tailwind CSS (CDN), IBM Plex Mono, existing app patterns in `static/index.html` + `static/app.js`

---

## File Map

| File | Change |
|---|---|
| `static/index.html` | Add Pipeline nav tab + tab div + CSS; remove Config Prompts sub-tab HTML |
| `static/app.js` | Register 'pipeline' in `_doSwitchTab`; add `PIPELINE_NODES` data constant; add render/panel functions; add pipeline prompt editor functions; update `loadConfigTab` to drop prompts; clean up dirty-check for prompt |

---

## Task 1: Register Pipeline tab in nav and tab switcher

**Files:**
- Modify: `static/index.html` — nav bar
- Modify: `static/app.js:1230` — `_doSwitchTab`

- [ ] **Step 1: Add nav item to `index.html`**

In `static/index.html`, find the nav block (around line 313). Add after the `nav-sources` item:

```html
      <div class="nav-tab" id="nav-pipeline" onclick="switchTab('pipeline')">Pipeline</div>
```

- [ ] **Step 2: Add empty tab div to `index.html`**

Find the closing `</div>` of `tab-rsm` (around line 537). After it, add:

```html
<!-- ── PIPELINE TAB ─────────────────────────────────────────────────── -->
<div id="tab-pipeline" class="hidden" style="height:calc(100vh - 36px);overflow:hidden;display:flex;flex-direction:column"></div>
```

- [ ] **Step 3: Register in `_doSwitchTab` in `app.js`**

Change line 1230 from:
```js
  ['overview', 'reports', 'history', 'trends', 'config', 'validate', 'sources'].forEach(t => {
```
To:
```js
  ['overview', 'reports', 'history', 'trends', 'config', 'validate', 'sources', 'pipeline'].forEach(t => {
```

Change line 1234 from:
```js
    el.style.display = t === tab ? (t === 'config' || t === 'overview' ? 'flex' : 'block') : '';
```
To:
```js
    el.style.display = t === tab ? (t === 'config' || t === 'overview' || t === 'pipeline' ? 'flex' : 'block') : '';
```

After line 1243, add:
```js
  if (tab === 'pipeline') renderPipelineTab();
```

- [ ] **Step 4: Verify**

Start the server (`uv run python server.py`), open the app. A "Pipeline" nav tab should appear. Clicking it switches to an empty tab with no errors in the console.

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(pipeline): add Pipeline tab to nav and tab switcher"
```

---

## Task 2: Tab layout + fixed header elements

**Files:**
- Modify: `static/index.html` — Pipeline tab div content + CSS

- [ ] **Step 1: Add CSS for Pipeline tab to `index.html` `<style>` block**

Find the closing `</style>` tag (around line 303). Before it, add:

```css
    /* Pipeline tab */
    #pipeline-header {
      flex-shrink: 0;
      background: #080c10;
      border-bottom: 1px solid #21262d;
      padding: 10px 20px;
    }
    #pipeline-requirement {
      font-size: 10px;
      color: #6e7681;
      letter-spacing: 0.04em;
      margin-bottom: 8px;
    }
    #pipeline-requirement strong { color: #8b949e; }
    #admiralty-legend {
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
      font-size: 9px;
      color: #484f58;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    #admiralty-legend .adm-pair { display: flex; flex-direction: column; gap: 2px; }
    #admiralty-legend .adm-label { color: #6e7681; }
    #admiralty-legend .adm-note { color: #484f58; font-size: 9px; text-transform: none; letter-spacing: 0; margin-top: 4px; max-width: 600px; font-style: italic; }

    /* Pipeline two-panel layout */
    #pipeline-body {
      flex: 1;
      display: flex;
      overflow: hidden;
    }
    #pipeline-flow {
      flex: 0 0 62%;
      overflow-y: auto;
      padding: 24px 32px;
      border-right: 1px solid #21262d;
    }
    #pipeline-panel {
      flex: 0 0 38%;
      display: none;
      flex-direction: column;
      overflow: hidden;
      background: #080c10;
    }
    #pipeline-panel.open { display: flex; }

    /* Pipeline nodes */
    .pl-phase-label {
      font-size: 9px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 16px;
      margin-top: 8px;
      padding-left: 4px;
    }
    .pl-node {
      background: #0d1117;
      border: 1px solid #21262d;
      border-radius: 4px;
      padding: 12px 14px;
      cursor: pointer;
      transition: border-color 150ms;
      margin-bottom: 0;
    }
    .pl-node:hover { border-color: #3fb950; }
    .pl-node.active { border-color: #3fb950; background: #0a130a; }
    .pl-node-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }
    .pl-phase-badge {
      font-size: 9px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 2px;
      background: #21262d;
      color: #8b949e;
      flex-shrink: 0;
    }
    .pl-node-name {
      font-size: 11px;
      font-weight: 600;
      color: #e6edf3;
      flex: 1;
    }
    .pl-phase-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .pl-node-role {
      font-size: 10px;
      color: #6e7681;
      margin-bottom: 8px;
      line-height: 1.5;
    }
    .pl-badges { display: flex; gap: 6px; flex-wrap: wrap; }
    .pl-badge {
      font-size: 9px;
      padding: 1px 7px;
      border-radius: 2px;
      letter-spacing: 0.04em;
    }
    .pl-badge-model    { background: #1a2d3a; color: #79c0ff; border: 1px solid #1f4a6e; }
    .pl-badge-type-det { background: #1a1a2e; color: #a371f7; border: 1px solid #3d2d7a; }
    .pl-badge-type-llm { background: #1a2e1a; color: #3fb950; border: 1px solid #238636; }
    .pl-badge-type-gate{ background: #2e2a1a; color: #e3b341; border: 1px solid #6e5c1a; }
    .pl-badge-type-orch{ background: #2e1a1a; color: #ff7b72; border: 1px solid #6e2020; }
    .pl-badge-concept  { background: #1a1a1a; color: #484f58; border: 1px solid #30363d; }

    /* Connector with animated dot */
    .pl-connector {
      position: relative;
      width: 2px;
      height: 36px;
      background: #21262d;
      margin: 0 auto;
      overflow: visible;
    }
    .pl-connector::after {
      content: '';
      position: absolute;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #3fb950;
      left: -2px;
      top: 0;
      animation: pl-dot-travel 2.4s ease-in-out infinite;
    }
    @keyframes pl-dot-travel {
      0%   { top: 0;              opacity: 0; }
      8%   { opacity: 1; }
      92%  { opacity: 1; }
      100% { top: calc(100% - 6px); opacity: 0; }
    }

    /* Fan-out block */
    .pl-fanout {
      border: 1px dashed #21262d;
      border-radius: 4px;
      padding: 12px;
      margin: 0;
    }
    .pl-fanout-label {
      font-size: 9px;
      color: #484f58;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .pl-region-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 5px 8px;
      border-radius: 2px;
      cursor: pointer;
      transition: background 100ms;
      margin-bottom: 3px;
    }
    .pl-region-row:hover { background: #0d1117; }
    .pl-region-name { font-size: 10px; color: #8b949e; }
    .pl-region-badge {
      font-size: 9px;
      padding: 1px 7px;
      border-radius: 2px;
    }
    .badge-escalate { background: #2d1111; color: #ff7b72; border: 1px solid #6e2020; }
    .badge-monitor  { background: #1a1a2d; color: #79c0ff; border: 1px solid #1f4a6e; }
    .badge-clear    { background: #1a2d1a; color: #3fb950; border: 1px solid #238636; }

    /* Side panel */
    #pipeline-panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      border-bottom: 1px solid #21262d;
      flex-shrink: 0;
    }
    #pipeline-panel-title { font-size: 11px; color: #e6edf3; font-weight: 600; }
    #pipeline-panel-body  { flex: 1; overflow-y: auto; padding: 16px 14px; }
    .pl-panel-section { margin-bottom: 20px; }
    .pl-panel-section-label {
      font-size: 9px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #484f58;
      margin-bottom: 8px;
      padding-bottom: 4px;
      border-bottom: 1px solid #21262d;
    }
    .pl-panel-body { font-size: 11px; color: #8b949e; line-height: 1.65; }
    .pl-panel-body strong { color: #c9d1d9; }
    .pl-io-row {
      display: flex;
      gap: 8px;
      font-size: 10px;
      color: #6e7681;
      margin-top: 6px;
      flex-wrap: wrap;
    }
    .pl-io-label { color: #484f58; }
    .pl-io-file  { color: #79c0ff; font-size: 9px; }
    .pl-principle {
      margin-top: 8px;
      padding: 8px 10px;
      background: #0d1117;
      border: 1px solid #21262d;
      border-radius: 3px;
    }
    .pl-principle-name { font-size: 10px; color: #e3b341; margin-bottom: 3px; }
    .pl-principle-desc { font-size: 10px; color: #6e7681; line-height: 1.55; }

    /* Config section in side panel */
    .pl-config-divider {
      font-size: 9px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #484f58;
      margin: 16px 0 8px;
      padding-bottom: 4px;
      border-bottom: 1px solid #21262d;
    }
    #pl-prompt-fm { font-size: 10px; color: #6e7681; display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }
    #pl-prompt-body {
      width: 100%;
      resize: vertical;
      min-height: 200px;
      background: #080c10;
      border: 1px solid #21262d;
      color: #c9d1d9;
      padding: 10px;
      font-size: 11px;
      font-family: 'IBM Plex Mono', monospace;
      line-height: 1.6;
      outline: none;
      border-radius: 2px;
    }
    #pl-prompt-save {
      margin-top: 6px;
      font-size: 10px;
      padding: 3px 12px;
      background: #1a3a1a;
      border: 1px solid #238636;
      color: #3fb950;
      border-radius: 2px;
      cursor: pointer;
    }
    #pl-prompt-save:disabled { opacity: 0.4; cursor: not-allowed; background: #0d1117; border-color: #21262d; color: #6e7681; }
    #pl-prompt-note { font-size: 9px; color: #484f58; margin-top: 6px; font-style: italic; }

    /* Glossary */
    #pl-glossary { margin-top: 32px; }
    #pl-glossary-toggle {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      padding: 8px 0;
      border-top: 1px solid #21262d;
    }
    #pl-glossary-toggle span { font-size: 10px; color: #6e7681; letter-spacing: 0.06em; text-transform: uppercase; }
    #pl-glossary-body { display: none; margin-top: 12px; }
    #pl-glossary-body.open { display: block; }
    .pl-glossary-term { margin-bottom: 12px; }
    .pl-glossary-name { font-size: 10px; color: #e3b341; margin-bottom: 3px; }
    .pl-glossary-def  { font-size: 10px; color: #6e7681; line-height: 1.6; }
```

- [ ] **Step 2: Add fixed header HTML inside `tab-pipeline`**

Replace the empty `tab-pipeline` div added in Task 1 with:

```html
<!-- ── PIPELINE TAB ─────────────────────────────────────────────────── -->
<div id="tab-pipeline" class="hidden" style="height:calc(100vh - 36px);overflow:hidden;display:flex;flex-direction:column">

  <!-- Fixed header: requirement + admiralty -->
  <div id="pipeline-header">
    <div id="pipeline-requirement">
      <strong>Analytical Requirement</strong> — Does a credible geopolitical or cyber threat exist in any of AeroGrid's five operational regions that could materially disrupt operations, supply chains, or safety at critical assets?
    </div>
    <div id="admiralty-legend">
      <div class="adm-pair">
        <span class="adm-label">Source Reliability</span>
        <span>A — Completely reliable &nbsp;·&nbsp; B — Usually reliable &nbsp;·&nbsp; C — Fairly reliable &nbsp;·&nbsp; D — Not usually reliable</span>
      </div>
      <div class="adm-pair">
        <span class="adm-label">Information Credibility</span>
        <span>1 — Confirmed &nbsp;·&nbsp; 2 — Probably true &nbsp;·&nbsp; 3 — Possibly true &nbsp;·&nbsp; 4 — Doubtful</span>
      </div>
      <div class="adm-pair" style="flex-basis:100%">
        <span class="adm-note">Admiralty ratings are assigned by the Gatekeeper at triage and propagate through the pipeline. They reflect source corroboration quality — not model confidence scores.</span>
      </div>
    </div>
  </div>

  <!-- Two-panel body -->
  <div id="pipeline-body">
    <!-- Flow column -->
    <div id="pipeline-flow">
      <div id="pipeline-nodes-container"></div>
      <div id="pl-glossary">
        <div id="pl-glossary-toggle" onclick="toggleGlossary()">
          <span>▸ Agentic Concepts Glossary</span>
        </div>
        <div id="pl-glossary-body"></div>
      </div>
    </div>
    <!-- Side panel -->
    <div id="pipeline-panel">
      <div id="pipeline-panel-header">
        <span id="pipeline-panel-title">—</span>
        <button onclick="closePipelinePanel()" style="background:none;border:none;color:#6e7681;cursor:pointer;font-size:14px">✕</button>
      </div>
      <div id="pipeline-panel-body"></div>
    </div>
  </div>

</div>
```

- [ ] **Step 3: Verify layout**

Reload app, click Pipeline tab. Should show the requirement banner, Admiralty legend, and an empty two-panel body below. No console errors.

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat(pipeline): add tab layout, fixed header, admiralty legend"
```

---

## Task 3: Define PIPELINE_NODES data constant

**Files:**
- Modify: `static/app.js` — add constant before the tab switcher functions (around line 1218)

- [ ] **Step 1: Insert the data constant in `app.js`**

Find the comment `// ── Run trigger ───` (around line 1246). Directly above it, insert:

```js
// ── Pipeline Tab Data ─────────────────────────────────────────────────
const PIPELINE_NODES = [
  {
    id: 'phase-0',
    phase: '0',
    name: 'Validate & Initialise',
    analyticalPhase: 'collection',
    phaseColor: '#79c0ff',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Establish collection parameters.</strong> Verifies the pipeline has everything it needs before any intelligence work begins — CRQ schema integrity, environment variables, OSINT mode, prior analyst feedback, and regional footprint context blocks. No intelligence judgment is made here.`,
    inputOutput: 'Input: <span class="pl-io-file">data/mock_crq_database.json</span> <span class="pl-io-file">.env</span> &nbsp;→&nbsp; Output: <span class="pl-io-file">output/logs/system_trace.log</span> (cleared) · footprint context blocks',
    agenticArch: `<strong>Deterministic gate.</strong> Runs Python validation scripts with no LLM involvement. Output is computed — it either passes or fails with a specific error. The pipeline cannot proceed if schema validation or environment checks fail.`,
    principles: ['deterministic', 'filesystem-as-state'],
  },
  {
    id: 'phase-1',
    phase: '1',
    name: 'Signal Acquisition',
    analyticalPhase: 'collection',
    phaseColor: '#79c0ff',
    type: 'deterministic',
    conceptTags: ['parallel fan-out ×5'],
    agentFile: null,
    isFanout: true,
    analyticalRole: `<strong>Acquire raw signals from open sources across all five regions simultaneously.</strong> No analytical judgment here — collection only. Each region's pipeline runs independently: OSINT research collector (or mock collectors), YouTube signals, scenario mapping, collection quality gate, and geopolitical context builder. The five pipelines share no state.`,
    inputOutput: 'Input: OSINT APIs / mock fixtures · <span class="pl-io-file">data/master_scenarios.json</span> &nbsp;→&nbsp; Output: <span class="pl-io-file">output/regional/{region}/geo_signals.json</span> · <span class="pl-io-file">cyber_signals.json</span> · <span class="pl-io-file">scenario_map.json</span> · <span class="pl-io-file">youtube_signals.json</span> · <span class="pl-io-file">collection_quality.json</span>',
    agenticArch: `<strong>Parallel fan-out ×5.</strong> Five regional pipelines are spawned simultaneously using the Agent tool with <code>run_in_background: true</code>. Each writes to its own output directory. They share no state and do not communicate with each other. This is not just an efficiency choice — regional assessments are structurally independent.`,
    principles: ['parallel-fanout', 'filesystem-as-state'],
  },
  {
    id: 'phase-1a',
    phase: '1a',
    name: 'Gatekeeper Triage',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'llm-agent',
    model: 'haiku',
    conceptTags: [],
    agentFile: 'gatekeeper-agent',
    analyticalRole: `<strong>Binary triage.</strong> Reads the collected signals and makes one decision: ESCALATE, MONITOR, or CLEAR. Assigns an Admiralty rating based on signal corroboration quality across geopolitical and cyber feeds. Passes through the scenario match from the scenario mapper as an advisory hint — the Gatekeeper does not re-derive it. This decision gates all downstream analytical work.`,
    inputOutput: 'Input: <span class="pl-io-file">geo_signals.json</span> · <span class="pl-io-file">cyber_signals.json</span> · <span class="pl-io-file">scenario_map.json</span> · <span class="pl-io-file">collection_quality.json</span> &nbsp;→&nbsp; Output: <span class="pl-io-file">gatekeeper_decision.json</span> · one word (ESCALATE / MONITOR / CLEAR)',
    agenticArch: `<strong>Lightweight fast model (Haiku).</strong> The Gatekeeper makes a binary routing decision — not a narrative assessment. Haiku is chosen for speed and cost efficiency on a structured triage task. Output is a single word plus a structured JSON file. The JSON is written to disk via a deterministic Python tool — the agent cannot write free-form output. This enforces schema compliance structurally.`,
    principles: ['filesystem-as-state'],
  },
  {
    id: 'phase-1b',
    phase: '1b',
    name: 'Regional Analyst',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'llm-agent',
    model: 'sonnet',
    conceptTags: ['stop hook'],
    agentFile: 'regional-analyst-agent',
    analyticalRole: `<strong>Full analytical treatment for escalated regions only.</strong> Produces the regional intelligence brief: scenario identification and validation, threat actor attribution, adversarial activity assessment, and AeroGrid-specific impact analysis. Follows the three-pillar structure — why (world events without AeroGrid), how (adversary activity without AeroGrid), so what (AeroGrid named only here). Also writes <code>sections.json</code> for the dashboard and <code>signal_clusters.json</code> for source attribution.`,
    inputOutput: 'Input: signal files · <span class="pl-io-file">gatekeeper_decision.json</span> · VaCR · geopolitical context · threat score &nbsp;→&nbsp; Output: <span class="pl-io-file">report.md</span> · <span class="pl-io-file">data.json</span> · <span class="pl-io-file">signal_clusters.json</span> · <span class="pl-io-file">sections.json</span>',
    agenticArch: `<strong>Sonnet with a stop hook.</strong> Sonnet is chosen for the nuanced analytical work of coupling signals to scenarios and assessing impact on specific assets. The agent's output is not accepted until an external auditor (the Jargon Auditor, Task 1c) passes it. The agent cannot self-certify completion.`,
    principles: ['stop-hook'],
  },
  {
    id: 'phase-1c',
    phase: '1c',
    name: 'Jargon Auditor',
    analyticalPhase: 'review',
    phaseColor: '#e3b341',
    type: 'quality-gate',
    conceptTags: ['stop hook', 'deterministic'],
    agentFile: null,
    analyticalRole: `<strong>Analytical voice enforcement.</strong> Intelligence briefs must read as human assessments — not system logs. The auditor catches: SOC/SIEM language, pipeline artefact references, generic source labels, fabricated citations, VaCR financial jargon, and forbidden pipeline language. On failure, it returns the specific violations. The analyst must rewrite with the violations listed explicitly.`,
    inputOutput: 'Input: <span class="pl-io-file">report.md</span> &nbsp;→&nbsp; Output: exit code 0 (PASS) or exit code 2 (FAIL + violation list)',
    agenticArch: `<strong>Deterministic Python script — no LLM.</strong> Exit code 0 = pass. Exit code 2 = fail with violations printed. On failure, the regional analyst is re-delegated with the exact violation list — not a vague instruction to rewrite. Capped at 1 rewrite cycle. All results are logged to <code>system_trace.log</code> as HOOK_PASS or HOOK_FAIL.`,
    principles: ['stop-hook', 'deterministic'],
  },
  {
    id: 'phase-2',
    phase: '2',
    name: 'Velocity Analysis',
    analyticalPhase: 'collection',
    phaseColor: '#79c0ff',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Historical pattern — is this region escalating more frequently?</strong> Reads all archived pipeline runs and computes escalation velocity per region. Velocity contextualises a single-cycle assessment: a region escalating for the third consecutive cycle warrants different weight than a first-time escalation. Patches velocity data directly into each regional <code>data.json</code>.`,
    inputOutput: 'Input: <span class="pl-io-file">output/runs/*/regional/*/data.json</span> &nbsp;→&nbsp; Output: <span class="pl-io-file">output/pipeline/trend_brief.json</span> · velocity fields patched into regional <span class="pl-io-file">data.json</span>',
    agenticArch: `<strong>Deterministic computation.</strong> Reads archived run files, counts escalations per region over the run history, and writes computed velocity metrics. No LLM involved — no risk of fabricated trend claims.`,
    principles: ['deterministic', 'filesystem-as-state'],
  },
  {
    id: 'phase-2b',
    phase: '2.5',
    name: 'Trend Synthesis',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'llm-agent',
    model: 'sonnet',
    conceptTags: [],
    agentFile: 'trends-synthesis-agent',
    analyticalRole: `<strong>Longitudinal intelligence — what patterns are emerging across cycles?</strong> Reads all archived run data and synthesises cross-run patterns: which scenarios are accelerating, which regions are stabilising, what new threat actors are appearing. Produces a structured trend analysis that feeds the Global Builder and the Trends tab.`,
    inputOutput: 'Input: <span class="pl-io-file">output/pipeline/trend_brief.json</span> · all archived <span class="pl-io-file">output/runs/*/regional/*/data.json</span> &nbsp;→&nbsp; Output: <span class="pl-io-file">output/pipeline/trend_analysis.json</span>',
    agenticArch: `<strong>Non-fatal phase.</strong> If this agent fails, the pipeline continues. The dashboard will show no trend data for this run, but all other outputs are unaffected. This is an intentional resilience decision — trend synthesis should not block the primary intelligence product.`,
    principles: ['filesystem-as-state'],
  },
  {
    id: 'phase-3',
    phase: '3',
    name: 'Cross-Regional Diff',
    analyticalPhase: 'assessment',
    phaseColor: '#3fb950',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Change detection — what is new this cycle?</strong> Compares the current run's regional assessments to the prior run. Produces a delta brief that highlights new escalations, cleared regions, changed Admiralty ratings, and scenario shifts. The Global Builder uses this to contextualize its cross-regional synthesis.`,
    inputOutput: 'Input: current regional <span class="pl-io-file">data.json</span> files · prior run archive &nbsp;→&nbsp; Output: delta brief (captured as variable)',
    agenticArch: `<strong>Deterministic diff computation.</strong> Compares structured JSON fields across runs. No LLM — no risk of fabricating change narratives.`,
    principles: ['deterministic'],
  },
  {
    id: 'phase-4',
    phase: '4',
    name: 'Global Builder',
    analyticalPhase: 'product',
    phaseColor: '#a371f7',
    type: 'llm-agent',
    model: 'sonnet',
    conceptTags: ['builder / validator pair', 'stop hook'],
    agentFile: 'global-builder-agent',
    analyticalRole: `<strong>Cross-regional synthesis — the executive intelligence picture.</strong> Reads all approved regional briefs, the velocity data, and the delta brief. Synthesises: which regions are co-escalating and why, what cross-regional patterns exist, what the headline threat is for the cycle, and what caveats apply. Produces the structured global report that feeds the board deliverables.`,
    inputOutput: 'Input: approved <span class="pl-io-file">report.md</span> per escalated region · <span class="pl-io-file">data.json</span> per region · <span class="pl-io-file">trend_brief.json</span> · delta brief &nbsp;→&nbsp; Output: <span class="pl-io-file">output/pipeline/global_report.json</span>',
    agenticArch: `<strong>One half of a builder/validator pair.</strong> The Global Builder produces the synthesis. It does not validate its own output — a separate agent does that. This structural separation prevents the validator from being influenced by the builder's reasoning, which would undermine the independence of review. Stop hooks validate JSON schema and jargon before the validator is called.`,
    principles: ['builder-validator', 'stop-hook'],
  },
  {
    id: 'phase-4b',
    phase: '4b',
    name: 'Global Validator',
    analyticalPhase: 'review',
    phaseColor: '#e3b341',
    type: 'quality-gate',
    model: 'haiku',
    conceptTags: ['builder / validator pair', 'circuit breaker'],
    agentFile: 'global-validator-agent',
    analyticalRole: `<strong>Independent peer review — devil's advocate.</strong> Reads only the finished global report and cross-references it against the regional source files it should reflect. Checks for: unsupported claims, missing regional evidence, internal contradictions, incorrect Admiralty propagation. Returns APPROVED or REWRITE with a specific failure list.`,
    inputOutput: 'Input: <span class="pl-io-file">output/pipeline/global_report.json</span> · regional <span class="pl-io-file">data.json</span> files &nbsp;→&nbsp; Output: APPROVED or REWRITE + failure list',
    agenticArch: `<strong>Structural independence is the mechanism.</strong> The validator is spawned as a separate agent sub-process with no shared conversation context with the builder. It cannot be influenced by the builder's reasoning — intentionally or otherwise. It reads only the output and the source data.<br><br><strong>Circuit breaker:</strong> If the validator returns REWRITE twice, the pipeline force-approves with a HOOK_FAIL log entry. This prevents infinite rewrite loops while preserving a complete audit trail of what failed and why.`,
    principles: ['builder-validator', 'circuit-breaker'],
  },
  {
    id: 'phase-5',
    phase: '5',
    name: 'Export & Dissemination',
    analyticalPhase: 'product',
    phaseColor: '#a371f7',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Format-specific dissemination.</strong> The same intelligence product rendered for different audiences: interactive dashboard (CISO + ops teams), executive PDF and PowerPoint (board), and Word brief (CISO deep-dive). No new intelligence is generated here — all content derives from the validated global report and approved regional briefs.`,
    inputOutput: 'Input: <span class="pl-io-file">global_report.json</span> · regional <span class="pl-io-file">data.json</span> &nbsp;→&nbsp; Output: <span class="pl-io-file">dashboard.html</span> · <span class="pl-io-file">board_report.pdf</span> · <span class="pl-io-file">board_report.pptx</span> · <span class="pl-io-file">ciso_brief.docx</span>',
    agenticArch: `<strong>Deterministic rendering.</strong> Jinja2 templates, python-pptx, fpdf2, and Playwright PDF export. No LLM. Output fidelity depends on validated input — the quality gates earlier in the pipeline are what guarantee the content here is trustworthy.`,
    principles: ['deterministic'],
  },
  {
    id: 'phase-6',
    phase: '6',
    name: 'Archive & Memory',
    analyticalPhase: 'product',
    phaseColor: '#a371f7',
    type: 'deterministic',
    conceptTags: [],
    agentFile: null,
    analyticalRole: `<strong>Institutional memory.</strong> Every run is archived with a timestamp and feeds the next cycle's velocity analysis and trend synthesis. The source registry records which sources appeared and were cited. Analyst feedback from prior runs is surfaced at the start of the next run — the system learns from analyst corrections over time.`,
    inputOutput: 'Input: all pipeline outputs &nbsp;→&nbsp; Output: <span class="pl-io-file">output/runs/{timestamp}/</span> · <span class="pl-io-file">data/sources.db</span> updated · <span class="pl-io-file">output/latest/</span> symlinked',
    agenticArch: `<strong>Filesystem as persistent state.</strong> Archived runs are plain files in <code>output/runs/</code>. The source registry is SQLite. No external database. Every artefact is human-readable and independently inspectable.`,
    principles: ['filesystem-as-state'],
  },
];

const PIPELINE_PRINCIPLES = {
  'deterministic': {
    name: 'Deterministic Gate',
    desc: 'This step runs Python code with no LLM involved. The output is computed from the input. It cannot hallucinate, fabricate, or reason incorrectly — it either produces the expected output or exits with an error code.',
  },
  'filesystem-as-state': {
    name: 'Filesystem as State',
    desc: 'Agents communicate through files on disk, not through shared memory or conversation context. Each agent reads what the previous one wrote. This means every handoff is a file you can open and inspect. The pipeline is fully auditable at rest.',
  },
  'parallel-fanout': {
    name: 'Parallel Fan-out',
    desc: 'Multiple agents run simultaneously, each in isolation. They write to separate directories and do not share state. This is not just an efficiency choice — it ensures each regional assessment is independent of the others. One region\'s analysis cannot contaminate another\'s.',
  },
  'stop-hook': {
    name: 'Stop Hook',
    desc: 'The agent\'s output is rejected by default. An external validator — a separate process with no access to the agent\'s reasoning — must explicitly pass the output before the pipeline continues. The agent cannot self-certify. If the validator fails, the agent rewrites with the specific violations listed. This is how quality is enforced structurally rather than asked for politely.',
  },
  'builder-validator': {
    name: 'Builder / Validator Pair',
    desc: 'Production and review are separated into two distinct agents. The builder produces the output. The validator reviews it. The validator has no access to the builder\'s conversation context — it reads only the finished artefact and the source material it should reflect. This structural independence means the validator cannot be influenced by the builder\'s reasoning, even inadvertently.',
  },
  'circuit-breaker': {
    name: 'Circuit Breaker',
    desc: 'If a rewrite loop runs more than a set number of cycles (typically 2), the pipeline force-approves and logs a HOOK_FAIL entry. This prevents infinite loops while ensuring the failure is recorded in the audit trail. The system makes a deliberate trade-off: prefer a completed run with a known failure logged over a hung pipeline.',
  },
};

const PIPELINE_GLOSSARY = [
  { term: 'Agent / Sub-agent', def: 'An autonomous process powered by a language model that can use tools, read files, make decisions, and write output. In this pipeline, sub-agents are spawned by the orchestrator for specific tasks — each with its own model selection, tool permissions, and stop hooks.' },
  { term: 'Orchestrator', def: 'The top-level Claude instance (Opus model) that runs the pipeline. It spawns agents, waits for results, runs quality gates, and decides when to proceed. The orchestrator coordinates — it does not produce intelligence content itself.' },
  { term: 'Stop Hook', def: 'A validator that runs after an agent produces output and before the pipeline accepts it. Exit code 0 = accepted. Any other exit code = rejected. The agent must rewrite. Stop hooks are the primary mechanism for enforcing output quality without relying on the agent to self-review.' },
  { term: 'Builder / Validator Pair', def: 'A design pattern where one agent produces output and a separate, independent agent reviews it. The validator is spawned with no shared context from the builder — it cannot be influenced by the builder\'s reasoning. This pattern prevents "echo-chamber validation" where a self-reviewing agent confirms its own assumptions.' },
  { term: 'Circuit Breaker', def: 'A limit on rewrite loops. If a stop hook fails more than N times, the pipeline force-approves and logs the failure rather than looping indefinitely. The trade-off: a completed pipeline with a logged failure is more useful than a hung pipeline.' },
  { term: 'Parallel Fan-out', def: 'Spawning multiple agents simultaneously to work on independent tasks. In Phase 1, five regional pipelines run in parallel. They write to separate output directories and share no state. Fan-in is the step where the orchestrator waits for all parallel tasks to complete before proceeding.' },
  { term: 'Deterministic Gate', def: 'A pipeline step that runs code with no LLM — Python scripts, validators, schema checkers. Output is computed, not generated. Deterministic gates cannot hallucinate. They are used for schema validation, jargon auditing, velocity computation, and export rendering.' },
  { term: 'Filesystem as State', def: 'Agents communicate by writing and reading files on disk. No shared in-memory state. No direct agent-to-agent messaging. Every handoff is a file. This makes the pipeline fully auditable: at any point, you can inspect exactly what every agent wrote and what every subsequent agent received.' },
  { term: 'Model Selection', def: 'Different agents use different Claude models. Haiku (fast, cheap) for binary triage decisions and devil\'s advocate validation. Sonnet (capable, balanced) for analytical synthesis and report writing. Opus (most capable) for orchestration. Matching model to task is an intentional architecture decision — not every step needs the most powerful model.' },
];
```

- [ ] **Step 2: Verify no syntax errors**

Open browser console after reloading the app. Confirm no JS parse errors.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(pipeline): add PIPELINE_NODES data constant and glossary"
```

---

## Task 4: Render pipeline nodes

**Files:**
- Modify: `static/app.js` — add rendering functions after the data constant

- [ ] **Step 1: Add `renderPipelineTab` and `renderPipelineNode` to `app.js`**

Directly after the `PIPELINE_GLOSSARY` constant, add:

```js
// ── Pipeline Tab Rendering ────────────────────────────────────────────
let _plActiveNode = null;

function renderPipelineTab() {
  const container = $('pipeline-nodes-container');
  if (!container || container.dataset.rendered) return;
  container.dataset.rendered = '1';

  const phaseColors = { collection: '#79c0ff', assessment: '#3fb950', review: '#e3b341', product: '#a371f7' };
  const phaseLabels = { collection: 'Collection', assessment: 'Assessment', review: 'Review', product: 'Product' };
  let lastPhase = null;
  let html = '';

  PIPELINE_NODES.forEach((node, i) => {
    if (node.analyticalPhase !== lastPhase) {
      if (lastPhase !== null) html += `<div class="pl-connector"></div>`;
      html += `<div class="pl-phase-label" style="color:${phaseColors[node.analyticalPhase]}">${phaseLabels[node.analyticalPhase]}</div>`;
      lastPhase = node.analyticalPhase;
    } else if (i > 0) {
      html += `<div class="pl-connector"></div>`;
    }

    if (node.isFanout) {
      html += renderFanoutNode(node);
    } else {
      html += renderSingleNode(node);
    }
  });

  container.innerHTML = html;
  renderGlossary();
}

function renderSingleNode(node) {
  const typeBadgeClass = { deterministic: 'pl-badge-type-det', 'llm-agent': 'pl-badge-type-llm', 'quality-gate': 'pl-badge-type-gate', orchestrator: 'pl-badge-type-orch' }[node.type] || 'pl-badge-type-det';
  const typeLabel = { deterministic: 'deterministic', 'llm-agent': 'llm · agent', 'quality-gate': 'quality gate', orchestrator: 'orchestrator' }[node.type] || node.type;

  return `
<div class="pl-node" id="plnode-${node.id}" onclick="openPipelinePanel('${node.id}')">
  <div class="pl-node-header">
    <span class="pl-phase-badge">${esc(node.phase)}</span>
    <span class="pl-node-name">${esc(node.name)}</span>
    <span class="pl-phase-dot" style="background:${node.phaseColor}"></span>
  </div>
  <div class="pl-node-role">${node.analyticalRole.replace(/<[^>]+>/g, '').substring(0, 120)}…</div>
  <div class="pl-badges">
    <span class="pl-badge ${typeBadgeClass}">${typeLabel}</span>
    ${node.model ? `<span class="pl-badge pl-badge-model">${esc(node.model)}</span>` : ''}
    ${(node.conceptTags || []).map(t => `<span class="pl-badge pl-badge-concept">${esc(t)}</span>`).join('')}
  </div>
</div>`;
}

function renderFanoutNode(node) {
  const regionOutcomes = [
    { region: 'APAC', badge: 'ESCALATE', cls: 'badge-escalate' },
    { region: 'AME',  badge: 'MONITOR',  cls: 'badge-monitor' },
    { region: 'LATAM',badge: 'CLEAR',    cls: 'badge-clear' },
    { region: 'MED',  badge: 'ESCALATE', cls: 'badge-escalate' },
    { region: 'NCE',  badge: 'MONITOR',  cls: 'badge-monitor' },
  ];
  return `
<div class="pl-node" id="plnode-${node.id}" onclick="openPipelinePanel('${node.id}')">
  <div class="pl-node-header">
    <span class="pl-phase-badge">${esc(node.phase)}</span>
    <span class="pl-node-name">${esc(node.name)}</span>
    <span class="pl-phase-dot" style="background:${node.phaseColor}"></span>
  </div>
  <div class="pl-node-role">Parallel collection across all five regions. Each pipeline is independent.</div>
  <div class="pl-badges" style="margin-bottom:10px">
    <span class="pl-badge pl-badge-type-det">deterministic</span>
    <span class="pl-badge pl-badge-concept">parallel fan-out ×5</span>
  </div>
  <div class="pl-fanout">
    <div class="pl-fanout-label">Regional pipelines — example outcomes</div>
    ${regionOutcomes.map(r => `
    <div class="pl-region-row" onclick="event.stopPropagation();openPipelinePanel('${node.id}')">
      <span class="pl-region-name">${r.region}</span>
      <span class="pl-region-badge ${r.cls}">${r.badge}</span>
    </div>`).join('')}
  </div>
</div>`;
}

function renderGlossary() {
  const body = $('pl-glossary-body');
  if (!body) return;
  body.innerHTML = PIPELINE_GLOSSARY.map(g => `
<div class="pl-glossary-term">
  <div class="pl-glossary-name">${esc(g.term)}</div>
  <div class="pl-glossary-def">${esc(g.def)}</div>
</div>`).join('');
}

function toggleGlossary() {
  const body = $('pl-glossary-body');
  const toggle = $('pl-glossary-toggle');
  if (!body) return;
  body.classList.toggle('open');
  toggle.querySelector('span').textContent = body.classList.contains('open')
    ? '▾ Agentic Concepts Glossary'
    : '▸ Agentic Concepts Glossary';
}
```

- [ ] **Step 2: Verify nodes render**

Reload app, click Pipeline. Should see the full list of phase nodes with badges, phase labels, and animated connector dots.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(pipeline): render pipeline flow nodes with connectors and fan-out"
```

---

## Task 5: Side panel open/close and content rendering

**Files:**
- Modify: `static/app.js` — add side panel functions

- [ ] **Step 1: Add panel functions to `app.js` after `renderGlossary`**

```js
function openPipelinePanel(nodeId) {
  const node = PIPELINE_NODES.find(n => n.id === nodeId);
  if (!node) return;

  // Mark active node
  if (_plActiveNode) {
    const prev = $(`plnode-${_plActiveNode}`);
    if (prev) prev.classList.remove('active');
  }
  _plActiveNode = nodeId;
  const el = $(`plnode-${nodeId}`);
  if (el) el.classList.add('active');

  // Render panel
  $('pipeline-panel-title').textContent = `${node.phase} — ${node.name}`;
  $('pipeline-panel-body').innerHTML = renderPanelContent(node);
  $('pipeline-panel').classList.add('open');

  // Load prompt if agent-backed
  if (node.agentFile) plLoadPrompt(node.agentFile);
}

function closePipelinePanel() {
  $('pipeline-panel').classList.remove('open');
  if (_plActiveNode) {
    const el = $(`plnode-${_plActiveNode}`);
    if (el) el.classList.remove('active');
    _plActiveNode = null;
  }
}

function renderPanelContent(node) {
  // Section 1: Analytical Role
  let html = `
<div class="pl-panel-section">
  <div class="pl-panel-section-label">Analytical Role</div>
  <div class="pl-panel-body">${node.analyticalRole}</div>
  <div class="pl-io-row">
    <span class="pl-io-label">IO ·</span>
    <span>${node.inputOutput}</span>
  </div>
</div>`;

  // Section 2: Agentic Architecture
  html += `
<div class="pl-panel-section">
  <div class="pl-panel-section-label">How This Is Built</div>
  <div class="pl-panel-body">${node.agenticArch}</div>`;

  if (node.principles && node.principles.length) {
    node.principles.forEach(key => {
      const p = PIPELINE_PRINCIPLES[key];
      if (!p) return;
      html += `
  <div class="pl-principle">
    <div class="pl-principle-name">${esc(p.name)}</div>
    <div class="pl-principle-desc">${esc(p.desc)}</div>
  </div>`;
    });
  }
  html += `</div>`;

  // Section 3: Agent Configuration (only for LLM agents)
  if (node.agentFile) {
    html += `
<div class="pl-panel-section">
  <div class="pl-config-divider">Agent Configuration</div>
  <div id="pl-prompt-fm"></div>
  <textarea id="pl-prompt-body" oninput="plOnPromptEdit()"></textarea>
  <div style="display:flex;align-items:center;gap:8px;margin-top:6px">
    <button id="pl-prompt-save" onclick="plSavePrompt()" disabled>Save</button>
  </div>
  <div id="pl-prompt-note">Changes affect future pipeline runs, not the current architectural description above.</div>
</div>`;
  }

  return html;
}
```

- [ ] **Step 2: Verify side panel opens and closes**

Click any node — side panel slides in with both sections populated. Click ✕ — panel closes and node loses active style.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(pipeline): side panel open/close with analytical role and agentic arch content"
```

---

## Task 6: Pipeline prompt editor in side panel

**Files:**
- Modify: `static/app.js` — add pipeline-scoped prompt functions

- [ ] **Step 1: Add prompt functions to `app.js`**

After `renderPanelContent`, add:

```js
// ── Pipeline prompt editor ────────────────────────────────────────────
let _plPromptState = { agent: null, baseline: '', dirty: false };

async function plLoadPrompt(agentName) {
  // Reuse cfgState.prompts if already loaded; otherwise fetch
  let prompts = cfgState.prompts;
  if (!prompts || !prompts.length) {
    prompts = await fetch('/api/config/prompts').then(r => r.ok ? r.json() : []).catch(() => []);
    cfgState.prompts = prompts;
  }
  const obj = prompts.find(p => p.agent === agentName);
  const fmEl = $('pl-prompt-fm');
  const bodyEl = $('pl-prompt-body');
  const saveEl = $('pl-prompt-save');
  if (!fmEl || !bodyEl) return;

  if (!obj) {
    bodyEl.value = `Agent file not found: .claude/agents/${agentName}.md`;
    bodyEl.disabled = true;
    if (saveEl) saveEl.disabled = true;
    return;
  }

  const fm = obj.frontmatter || {};
  fmEl.innerHTML = Object.entries(fm).map(([k, v]) =>
    `<span><span style="color:#3fb950">${esc(k)}:</span> <span style="color:#8b949e">${esc(String(v))}</span></span>`
  ).join('');
  bodyEl.value = obj.body || '';
  bodyEl.disabled = false;
  _plPromptState = { agent: agentName, baseline: obj.body || '', dirty: false };
  if (saveEl) { saveEl.disabled = true; }
}

function plOnPromptEdit() {
  _plPromptState.dirty = true;
  const saveEl = $('pl-prompt-save');
  if (saveEl) saveEl.disabled = false;
}

async function plSavePrompt() {
  const bodyEl = $('pl-prompt-body');
  const saveEl = $('pl-prompt-save');
  if (!bodyEl || !_plPromptState.agent) return;
  const body = bodyEl.value;
  openDiffModal(_plPromptState.baseline, body, async () => {
    const r = await fetch(`/api/config/prompts/${encodeURIComponent(_plPromptState.agent)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body }),
    });
    return r.json();
  }, 'pl-prompt');
  _plPromptState.baseline = body;
  _plPromptState.dirty = false;
  if (saveEl) saveEl.disabled = true;
  // Invalidate cfgState so Config tab re-loads fresh on next visit
  cfgState.loaded = false;
}
```

- [ ] **Step 2: Verify prompt editor**

Click a node that has `agentFile` set (e.g. Gatekeeper Triage, Regional Analyst). The side panel Section 3 should show the frontmatter fields and the agent's prompt body in the textarea. Editing text should enable the Save button.

- [ ] **Step 3: Verify save round-trip**

Edit one character in the prompt, click Save, confirm the diff modal appears, confirm, reload the page, click the same node — the edit should persist.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(pipeline): prompt editor in side panel with load/save/diff"
```

---

## Task 7: Remove Config Prompts sub-tab

**Files:**
- Modify: `static/index.html` — remove Prompts nav tab and sub-tab content
- Modify: `static/app.js` — update `loadConfigTab`, remove prompt dirty-check from `switchTab`

- [ ] **Step 1: Remove Prompts nav item from `index.html`**

Find and remove this line (around line 423):
```html
    <div class="nav-tab" id="cfg-nav-prompts" onclick="switchCfgTab('prompts')">Prompts</div>
```

- [ ] **Step 2: Remove the Prompts sub-tab div from `index.html`**

Find and remove this entire block (lines 499–509):
```html
  <!-- Prompts sub-tab -->
  <div id="cfg-tab-prompts" style="display:none;flex:1;flex-direction:column;overflow:hidden">
    <div style="padding:10px 14px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:10px;flex-shrink:0">
      <select id="agent-select" onchange="onAgentSelect()" style="background:#0d1117;border:1px solid #21262d;color:#c9d1d9;padding:3px 8px;border-radius:2px;font-size:11px;font-family:'IBM Plex Mono',monospace"></select>
      <button id="btn-save-prompt" onclick="savePrompt()" disabled style="font-size:10px;color:#6e7681;background:#0d1117;border:1px solid #21262d;padding:2px 10px;border-radius:2px;cursor:not-allowed;opacity:0.5">Save</button>
    </div>
    <div id="prompts-error" style="display:none;padding:6px 14px;font-size:10px;color:#ff7b72;background:#2d0000;border-bottom:1px solid #da3633"></div>
    <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
      <div id="fm-panel" style="padding:10px 14px;border-bottom:1px solid #21262d;flex-shrink:0;font-size:10px;color:#6e7681;display:flex;gap:16px;flex-wrap:wrap"></div>
      <textarea id="prompt-body" oninput="onPromptEdit()" style="flex:1;resize:none;background:#080c10;border:none;color:#c9d1d9;padding:14px;font-size:12px;font-family:'IBM Plex Mono',monospace;line-height:1.6;outline:none"></textarea>
    </div>
  </div>
```

- [ ] **Step 3: Update `loadConfigTab` in `app.js`**

Change the `loadConfigTab` function so it no longer fetches prompts or calls `renderPromptsPanel`:

```js
async function loadConfigTab() {
  if (cfgState.loaded) return;
  const [topicsRaw, sourcesRaw] = await Promise.all([
    fetch('/api/config/topics').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
    fetch('/api/config/sources').then(r => r.ok ? r.text() : '[]').catch(() => '[]'),
  ]);
  cfgState.topicsBaseline = JSON.stringify(JSON.parse(topicsRaw), null, 2);
  cfgState.topics = JSON.parse(cfgState.topicsBaseline);
  cfgState.sourcesBaseline = JSON.stringify(JSON.parse(sourcesRaw), null, 2);
  cfgState.sources = JSON.parse(cfgState.sourcesBaseline);
  cfgState.dirty = { topics: false, sources: false, prompt: false };
  cfgState.loaded = true;
  renderTopicsTable();
  renderSourcesTable();
  loadSuggestions();
}
```

- [ ] **Step 4: Update unsaved-changes check in `switchTab`**

The `switchTab` function checks `cfgState.dirty.prompt`. This now refers to the pipeline panel prompt. Since the pipeline panel is not a tab-switch target (it's a panel inside the Pipeline tab), this check is now only relevant for Config topics/sources. Update `switchTab`:

```js
function switchTab(tab) {
  if (cfgState.dirty.topics || cfgState.dirty.sources) {
    showUnsavedModal(() => _doSwitchTab(tab));
    return;
  }
  _doSwitchTab(tab);
}
```

- [ ] **Step 5: Verify Config tab**

Click Config. Should show Intelligence Sources and Footprint sub-tabs only. No Prompts tab. No console errors.

- [ ] **Step 6: Verify Pipeline prompt editor still works**

Click Pipeline → click Gatekeeper Triage node → confirm prompt loads in side panel Section 3.

- [ ] **Step 7: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(pipeline): remove Config Prompts sub-tab, prompt editor now lives in Pipeline side panel"
```

---

## Task 8: Final polish — phase transition connectors and empty state

**Files:**
- Modify: `static/app.js` — fix connector rendering between phase groups
- Modify: `static/index.html` — verify tab default state

- [ ] **Step 1: Verify connector dots animate correctly**

In the pipeline flow, the `.pl-connector` divs between nodes should show a small green dot travelling top-to-bottom continuously. Check there are connectors between all adjacent nodes (not just between phase groups). 

If connectors only appear at phase boundaries, update `renderPipelineTab` in `app.js`. Replace the connector logic:

```js
PIPELINE_NODES.forEach((node, i) => {
  if (node.analyticalPhase !== lastPhase) {
    if (lastPhase !== null) html += `<div class="pl-connector"></div>`;
    html += `<div class="pl-phase-label" style="color:${phaseColors[node.analyticalPhase]}">${phaseLabels[node.analyticalPhase]}</div>`;
    lastPhase = node.analyticalPhase;
  } else if (i > 0) {
    html += `<div class="pl-connector"></div>`;
  }
  // ...
});
```

This already adds connectors between all nodes. If they're missing, confirm `pl-connector` CSS is present in the `<style>` block from Task 2.

- [ ] **Step 2: Verify tab shows correctly on first visit**

Open app, click Pipeline tab immediately. Nodes should render, no blank screen, no console errors. The `renderPipelineTab` guard (`if (container.dataset.rendered) return`) prevents double-rendering on repeated tab switches.

- [ ] **Step 3: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(pipeline): final polish — connector dots and render guard"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| New "Pipeline" nav tab | Task 1 |
| Intelligence Requirement banner | Task 2 |
| Admiralty Scale Legend (persistent) | Task 2 |
| Two-panel layout 62/38 | Task 2 |
| Vertical phase nodes with color coding | Task 4 |
| Phase badge, node name, phase dot | Task 4 |
| Type badges (deterministic / llm-agent / quality-gate) | Task 4 |
| Model badge (haiku / sonnet) | Task 4 |
| Agentic concept tags on nodes | Task 4 |
| Animated connector dots | Task 2 (CSS) + Task 4 (HTML) |
| Phase 1 fan-out with 5 regional rows + illustrative badges | Task 4 |
| Side panel: Section 1 Analytical Role + IO | Task 5 |
| Side panel: Section 2 How This Is Built + principles | Task 5 |
| Principle definitions rendered as expandable cards | Task 5 |
| Side panel: Section 3 Agent Configuration (prompt editor) | Task 6 |
| Prompt save round-trip via existing API | Task 6 |
| Agentic Concepts Glossary (collapsible) | Task 4 |
| Config Prompts sub-tab removed | Task 7 |
| `loadConfigTab` drops prompt fetch | Task 7 |
| `switchTab` dirty-check updated | Task 7 |
| All 12 pipeline nodes with full content | Task 3 |

**Placeholder scan:** No TBDs. All node content is fully written in `PIPELINE_NODES`. All code in every step is complete.

**Type consistency:** `node.id` used consistently across `renderSingleNode`, `openPipelinePanel`, `$('plnode-${node.id}')`. `node.agentFile` checked consistently in `renderPanelContent` and `openPipelinePanel`. `cfgState.prompts` reused across `loadConfigTab` and `plLoadPrompt` — consistent field name.

**One risk:** `openDiffModal` is called in `plSavePrompt` — confirm this function exists in `app.js` before Task 6. Search for `openDiffModal` in `app.js` to verify.
