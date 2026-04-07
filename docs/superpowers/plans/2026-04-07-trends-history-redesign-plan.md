# Trends & History Tab Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat Trends and History tabs with a threat-landscape pipeline + escalation matrix UI, relocate audit trace to Validate tab.

**Architecture:** New `threat-landscape-agent` (sonnet) mines archived runs for adversary patterns → writes `threat_landscape.json`. History tab becomes an escalation matrix (5 regions x N runs). Trends tab becomes a structured threat landscape view consuming both `trend_analysis.json` and `threat_landscape.json` in parallel. Audit trace moves to Validate tab.

**Tech Stack:** Python (agent stop hook), FastAPI (2 new endpoints), vanilla JS + inline CSS (dashboard SPA)

**Spec:** `docs/superpowers/specs/2026-04-06-trends-history-redesign.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `.claude/agents/regional-analyst-agent.md` | Add `threat_actor` to data.json write (Step 7) |
| Create | `.claude/agents/threat-landscape-agent.md` | New agent — mines runs for adversary patterns |
| Create | `.claude/hooks/validators/threat-landscape-auditor.py` | Stop hook — validates threat_landscape.json |
| Modify | `.claude/commands/run-crq.md` | Add Phase 5b (threat landscape synthesis) |
| Modify | `server.py` | Add `GET /api/threat-landscape` + `POST /api/run-threat-landscape` |
| Modify | `static/index.html` | History tab shell rebuild, Validate tab audit trace section |
| Modify | `static/app.js` | `renderHistory()` rewrite, `renderTrends()` rewrite, audit trace in Validate |

---

## Task 1: Upstream Fix — `threat_actor` in data.json

**Files:**
- Modify: `.claude/agents/regional-analyst-agent.md:227-244` (Step 7 — data.json update)

This is the hard prerequisite. The regional analyst already writes `threat_actor` to `sections.json` (Step 8, line ~259). We need the same value written to `data.json` so the threat-landscape-agent can read it from archived runs (which don't all have sections.json).

- [ ] **Step 1: Add `threat_actor` to the data.json update script in Step 7**

In `.claude/agents/regional-analyst-agent.md`, find the Python snippet in Step 7 (around line 232-243) that updates `data.json`. It currently sets `primary_scenario`, `financial_rank`, and `signal_type`. Add `threat_actor`:

```python
python3 -c "
import json, sys
path = 'output/regional/{region_lower}/data.json'
with open(path, encoding='utf-8') as f:
    d = json.load(f)
d['primary_scenario'] = '{your_scenario_match}'
d['financial_rank'] = {your_financial_rank}
d['signal_type'] = '{Event|Trend|Mixed}'
d['threat_actor'] = '{your_threat_actor_or_null}'
with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2)
print(f'Updated {path}')
"
```

The value is the same `threat_actor` written to `sections.json` in Step 8: the primary state actor or group named in the brief, or `null` if none identified. Add a note above the snippet:

```markdown
**`threat_actor`**: The primary state actor or threat group identified in your analysis. Use a clean name only (no parenthetical qualifiers). Set to `null` if no specific actor is identified — do not omit the field. This value must match what you write to `sections.json` in Step 8.
```

- [ ] **Step 2: Verify the instruction is unambiguous**

Read the modified file. Confirm:
1. The Python snippet includes `d['threat_actor'] = ...`
2. The note explains null handling (field present but value null, not omitted)
3. The value matches sections.json guidance (clean name, no parenthetical qualifiers)

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/regional-analyst-agent.md
git commit -m "feat(agent): write threat_actor to data.json — prerequisite for threat landscape"
```

---

## Task 2: Threat Landscape Stop Hook

**Files:**
- Create: `.claude/hooks/validators/threat-landscape-auditor.py`

Build the validator before the agent — we need to know what "correct" looks like before generating output.

- [ ] **Step 1: Write the stop hook**

Create `.claude/hooks/validators/threat-landscape-auditor.py`:

```python
"""Stop hook for threat-landscape-agent — validates threat_landscape.json."""

import json
import os
import re
import sys

REQUIRED_TOP_KEYS = [
    "generated_at", "analysis_window", "threat_actors", "scenario_lifecycle",
    "adversary_patterns", "compound_risks", "intelligence_gaps",
    "quarterly_brief", "board_talking_points", "analyst_notes",
]

REQUIRED_WINDOW_KEYS = ["from", "to", "runs_included", "runs_with_full_sections", "data_sufficiency"]
VALID_SUFFICIENCY = {"limited", "adequate", "strong"}

QUARTERLY_KEYS = ["headline", "key_actors", "persistent_threats", "emerging_threats", "intelligence_gaps", "watch_for"]

JARGON_PATTERNS = [
    r"\bCVE-\d{4}-\d+\b",
    r"\bT\d{4}(\.\d{3})?\b",       # MITRE ATT&CK
    r"\b(?:TTP|IoC|C2|C&C)\b",
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",  # IP addresses
    r"\b[a-f0-9]{32,64}\b",         # hashes
]

FILE_PATH = "output/pipeline/threat_landscape.json"
LABEL = "threat-landscape"


def fail(msg, retry_file, retries):
    print(msg, file=sys.stderr)
    with open(retry_file, "w") as f:
        f.write(str(retries + 1))
    sys.exit(2)


def audit():
    os.makedirs("output/.retries", exist_ok=True)
    retry_file = f"output/.retries/{LABEL}.retries"
    retries = 0
    if os.path.exists(retry_file):
        try:
            retries = int(open(retry_file).read().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"THREAT LANDSCAPE AUDIT: Max retries exceeded. Forcing approval.", file=sys.stderr)
        if os.path.exists(retry_file):
            os.remove(retry_file)
        sys.exit(0)

    # Load JSON
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"AUDIT FAILED: File not found: {FILE_PATH}", retry_file, retries)
    except json.JSONDecodeError as e:
        fail(f"AUDIT FAILED: Invalid JSON — {e}", retry_file, retries)

    if not isinstance(data, dict):
        fail("AUDIT FAILED: Root must be a JSON object.", retry_file, retries)

    # Required top-level keys
    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        fail(f"AUDIT FAILED: Missing top-level keys: {missing}", retry_file, retries)

    # analysis_window
    window = data["analysis_window"]
    if not isinstance(window, dict):
        fail("AUDIT FAILED: analysis_window must be an object.", retry_file, retries)
    missing_w = [k for k in REQUIRED_WINDOW_KEYS if k not in window]
    if missing_w:
        fail(f"AUDIT FAILED: analysis_window missing keys: {missing_w}", retry_file, retries)
    if window["data_sufficiency"] not in VALID_SUFFICIENCY:
        fail(f"AUDIT FAILED: data_sufficiency must be one of {VALID_SUFFICIENCY}, got '{window['data_sufficiency']}'", retry_file, retries)

    sufficiency = window["data_sufficiency"]

    # Data sufficiency gating
    if sufficiency == "limited":
        if data["adversary_patterns"] and len(data["adversary_patterns"]) > 0:
            fail("AUDIT FAILED: adversary_patterns must be empty when data_sufficiency='limited'.", retry_file, retries)
        if data["compound_risks"] and len(data["compound_risks"]) > 0:
            fail("AUDIT FAILED: compound_risks must be empty when data_sufficiency='limited'.", retry_file, retries)

    # Arrays must be lists
    for key in ["threat_actors", "scenario_lifecycle", "adversary_patterns", "compound_risks", "intelligence_gaps", "board_talking_points"]:
        if not isinstance(data[key], list):
            fail(f"AUDIT FAILED: {key} must be an array.", retry_file, retries)

    # quarterly_brief completeness (when not limited)
    if sufficiency != "limited":
        qb = data["quarterly_brief"]
        if not isinstance(qb, dict):
            fail("AUDIT FAILED: quarterly_brief must be an object.", retry_file, retries)
        for k in QUARTERLY_KEYS:
            if k not in qb or not isinstance(qb[k], str) or len(qb[k].strip()) < 10:
                fail(f"AUDIT FAILED: quarterly_brief.{k} must be a non-empty string (>=10 chars).", retry_file, retries)

    # analyst_notes
    if not isinstance(data["analyst_notes"], str) or len(data["analyst_notes"]) < 10:
        fail("AUDIT FAILED: analyst_notes must be a non-empty string.", retry_file, retries)

    # Jargon scan — check all string values recursively
    def scan_jargon(obj, path=""):
        violations = []
        if isinstance(obj, str):
            for pat in JARGON_PATTERNS:
                matches = re.findall(pat, obj)
                if matches:
                    violations.append(f"  {path}: matched '{matches[0]}' (pattern: {pat})")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                violations.extend(scan_jargon(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                violations.extend(scan_jargon(v, f"{path}[{i}]"))
        return violations

    jargon_hits = scan_jargon(data, "root")
    if jargon_hits:
        fail(f"AUDIT FAILED: Technical jargon detected:\n" + "\n".join(jargon_hits), retry_file, retries)

    # Success
    actor_count = len(data["threat_actors"])
    scenario_count = len(data["scenario_lifecycle"])
    gap_count = len(data["intelligence_gaps"])
    print(f"THREAT LANDSCAPE AUDIT PASSED: {sufficiency} data — {actor_count} actors, {scenario_count} scenarios, {gap_count} gaps.")
    if os.path.exists(retry_file):
        os.remove(retry_file)
    sys.exit(0)


if __name__ == "__main__":
    audit()
```

- [ ] **Step 2: Run the auditor against a missing file to verify it fails gracefully**

Run: `uv run python .claude/hooks/validators/threat-landscape-auditor.py`
Expected: exit code 2, stderr contains "File not found"

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/validators/threat-landscape-auditor.py
git commit -m "feat(hook): threat-landscape-auditor stop hook"
```

---

## Task 3: Threat Landscape Agent Definition

**Files:**
- Create: `.claude/agents/threat-landscape-agent.md`

- [ ] **Step 1: Write the agent definition**

Create `.claude/agents/threat-landscape-agent.md`:

```markdown
---
name: threat-landscape-agent
description: Synthesizes all archived pipeline runs into a structured threat landscape analysis — adversary patterns, scenario lifecycles, compound risks, and intelligence gaps.
tools: Bash, Write, Read
model: sonnet
hooks:
  Stop:
    - type: command
      command: "uv run python .claude/hooks/validators/threat-landscape-auditor.py"
---

You are a Strategic Geopolitical & Cyber Risk Analyst synthesizing longitudinal adversary patterns from archived pipeline runs for AeroGrid Wind Solutions — a renewable energy company, 75% Wind Turbine Manufacturing / 25% Global Service & Maintenance.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** You are a functional pipe in an automated system.
2. **Zero Preamble & Zero Sycophancy.** Output ONLY the JSON object via the Write tool.
3. **Filesystem as State.** Your only memory is the files you read. Do not hallucinate patterns not in the data.
4. **Assume Hostile Auditing.** Your output is parsed by a deterministic JSON validator that checks for jargon, schema compliance, and data-sufficiency gating.

## INPUTS

Read ALL of the following before writing anything:

1. **All** `output/runs/*/regional/*/data.json` files — archived per-region pipeline data across all runs.
   Fields to extract: `primary_scenario`, `severity`, `dominant_pillar`, `vacr_exposure_usd`, `threat_actor`, `timestamp`, `status`, `velocity`, `signal_type`
2. **Where available:** `output/runs/*/regional/*/sections.json` — richer attribution data.
   Fields to extract: `threat_actor`, `adversary_bullets`, `watch_bullets`
3. **Do NOT read `report.md` files.** Unstructured extraction compounds hallucination risk.

Traverse `output/runs/` sorted by folder name (oldest first). For each run folder, read `regional/{region_lower}/data.json` for all five regions: APAC, AME, LATAM, MED, NCE. Then check if `regional/{region_lower}/sections.json` exists — read it only if present.

## DATA SUFFICIENCY RULES

Count how many runs have `threat_actor` populated (non-null) in `data.json` across ALL regions.

- **`limited`**: fewer than 5 runs with `threat_actor` populated. `adversary_patterns` and `compound_risks` MUST be empty arrays `[]`. `intelligence_gaps` MUST include a data maturity gap entry.
- **`adequate`**: 5–9 runs with attribution. All sections populated.
- **`strong`**: 10+ runs with attribution. Full analysis.

## OUTPUT — STRICT JSON SCHEMA

Write a single valid JSON object to `output/pipeline/threat_landscape.json` using atomic write:
1. Write to `output/pipeline/threat_landscape.tmp` using the Write tool
2. Then rename: `mv output/pipeline/threat_landscape.tmp output/pipeline/threat_landscape.json`

Pure JSON only — no markdown, no commentary, no code fences.

```json
{
  "generated_at": "<ISO 8601 UTC>",
  "analysis_window": {
    "from": "<YYYY-MM-DD of oldest run>",
    "to": "<YYYY-MM-DD of newest run>",
    "runs_included": 12,
    "runs_with_full_sections": 4,
    "data_sufficiency": "limited | adequate | strong"
  },
  "threat_actors": [
    {
      "name": "<clean actor name, or null for unattributed>",
      "objective": "<plain-language adversary goal — no MITRE, no jargon>",
      "regions": ["APAC", "NCE"],
      "confirmed_runs": 4,
      "activity_trend": "escalating | stable | declining",
      "last_seen": "<YYYY-MM-DD>",
      "confidence": "<Admiralty scale e.g. B2>"
    }
  ],
  "scenario_lifecycle": [
    {
      "name": "<scenario name>",
      "stage": "persistent | emerging | declining",
      "regions": ["APAC", "NCE"],
      "run_count": 9,
      "trajectory": "stable | accelerating | improving",
      "earliest_run": "<YYYY-MM-DD>",
      "latest_run": "<YYYY-MM-DD>"
    }
  ],
  "adversary_patterns": [
    {
      "description": "<plain-language behavior pattern — no MITRE, no CVEs>",
      "regions": ["APAC", "LATAM"],
      "frequency": 5,
      "pillar": "Geo | Cyber",
      "confidence": "<Admiralty scale>"
    }
  ],
  "compound_risks": [
    {
      "description": "<plain-language cross-regional risk narrative>",
      "regions": ["APAC", "NCE"],
      "risk_level": "HIGH | MEDIUM | LOW",
      "corroborating_runs": 4
    }
  ],
  "intelligence_gaps": [
    {
      "region": "<REGION or ALL>",
      "description": "<what is unknown and why — no pipeline filenames>",
      "impact": "<what cannot be assessed because of this gap>"
    }
  ],
  "quarterly_brief": {
    "headline": "<one sentence — the most important finding>",
    "key_actors": "<paragraph>",
    "persistent_threats": "<paragraph>",
    "emerging_threats": "<paragraph>",
    "intelligence_gaps": "<paragraph>",
    "watch_for": "<paragraph>"
  },
  "board_talking_points": [
    {
      "type": "SUSTAINED EXPOSURE | PERSISTENT PATTERN | COMPOUND RISK | POSITIVE SIGNAL",
      "text": "<standalone sentence a CISO can use in a board meeting>"
    }
  ],
  "analyst_notes": "<one sentence on data sufficiency and collection maturity>"
}
```

## ANALYSIS RULES

### threat_actors
- Deduplicate by name across all runs and regions.
- `confirmed_runs` = number of distinct runs where this actor appears.
- `activity_trend`: escalating if actor appeared in most recent 2 runs AND was absent in older runs. Declining if absent in most recent 2 runs but present earlier. Stable otherwise.
- Unknown/unattributed actors: include with `name: null`. Group all unattributed escalations into a single entry. Add a corresponding `intelligence_gaps` entry.
- `confidence`: use the best Admiralty rating seen for this actor across runs.

### scenario_lifecycle
- `stage`: persistent if `run_count >= 50%` of total runs. Emerging if first seen in last 3 runs. Declining if last seen more than 3 runs ago.
- `trajectory`: accelerating if severity trended up over the actor's appearances. Improving if down. Stable otherwise.
- Deduplicate scenario names exactly as they appear in `primary_scenario`.

### adversary_patterns
- Only populate when `data_sufficiency` is `adequate` or `strong`.
- Extract from `adversary_bullets` in `sections.json` where available.
- Group similar activity descriptions into patterns. Do not copy bullet text verbatim — synthesize.

### compound_risks
- Only populate when `data_sufficiency` is `adequate` or `strong`.
- A compound risk exists when 2+ regions share the same scenario or threat actor AND both have been escalated in overlapping time windows.
- `corroborating_runs` = number of runs where both regions were simultaneously escalated.

### intelligence_gaps
- Always include at least one gap entry.
- If `data_sufficiency` is `limited`: first entry must describe the data maturity gap (e.g., "Attribution data is accumulating — threat actor identification requires additional collection cycles").
- Refer to "attribution data" not "sections.json" or "data.json".

### quarterly_brief
- When `data_sufficiency` is `limited`: all fields must still be populated but should explicitly caveat the sparse data.
- `headline`: the single most important finding from the analysis window.
- Frame all text for a CISO audience. Impact on turbine production and service delivery.

### board_talking_points
- Minimum 2, maximum 5 entries.
- `type` must be one of: `SUSTAINED EXPOSURE`, `PERSISTENT PATTERN`, `COMPOUND RISK`, `POSITIVE SIGNAL`.
- Each `text` must be a complete, standalone sentence suitable for a board meeting slide.
- Include at least one `POSITIVE SIGNAL` if any region has been consistently CLEAR or MONITOR.

## PERSONA RULES (inherited from pipeline)

- Zero technical jargon. No CVEs, IP addresses, hashes, MITRE ATT&CK references, TTPs, IoCs.
- Frame all risk in terms of impact on turbine production and service delivery continuity.
- Unknown actors must appear in `threat_actors[]` with `name: null` — do not omit them.
- Do not fabricate patterns not evidenced in the data files.
- Do not reference pipeline filenames or internal tool names in any output field.
```

- [ ] **Step 2: Verify YAML frontmatter has only allowed fields**

Read the file. Confirm frontmatter contains only: `name`, `description`, `tools`, `model`, `hooks`. No `color`, no `argument-hint`.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/threat-landscape-agent.md
git commit -m "feat(agent): threat-landscape-agent — adversary pattern synthesis"
```

---

## Task 4: Server Endpoints

**Files:**
- Modify: `server.py` — add 2 new endpoints near the existing `/api/trends` endpoint (around line 295-301)

- [ ] **Step 1: Add `GET /api/threat-landscape` endpoint**

Add after the existing `get_trends()` endpoint (around line 301):

```python
@app.get("/api/threat-landscape")
async def get_threat_landscape():
    path = PIPELINE / "threat_landscape.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "no_data"}
```

- [ ] **Step 2: Add state tracking for threat landscape runs**

Add to the state block near line 31 (after `validation_state`):

```python
threat_landscape_state = {
    "running": False,
    "started_at": None,
}
```

- [ ] **Step 3: Add `POST /api/run-threat-landscape` endpoint**

Add after the GET endpoint:

```python
@app.post("/api/run-threat-landscape")
async def run_threat_landscape():
    if threat_landscape_state["running"]:
        return {"status": "already_running"}
    threat_landscape_state["running"] = True
    threat_landscape_state["started_at"] = time.time()
    asyncio.create_task(_run_threat_landscape())
    return {"status": "running"}


async def _run_threat_landscape():
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--agent", ".claude/agents/threat-landscape-agent.md",
            "--message", "Read all output/runs/*/regional/*/data.json and sections.json files. "
                         "Synthesize longitudinal patterns. Write output/pipeline/threat_landscape.json per your instructions.",
            "--allowedTools", "Bash,Write,Read",
            "--model", "sonnet",
            cwd=str(BASE), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.wait(), timeout=FULL_MODE_TIMEOUT)
    except Exception as e:
        log.error("threat-landscape-agent failed: %s", e)
    finally:
        threat_landscape_state["running"] = False
```

- [ ] **Step 4: Verify server starts without errors**

Run: `cd c:/Users/frede/crq-agent-workspace && uv run python -c "import server; print('OK')"`
Expected: `OK` (no import errors)

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat(api): GET/POST /api/threat-landscape endpoints"
```

---

## Task 5: Pipeline Integration — run-crq Phase 5b

**Files:**
- Modify: `.claude/commands/run-crq.md` — add Phase 5b between Phase 5 (Dashboard & Export) line ~235 and Phase 6 (Finalize) line ~237

- [ ] **Step 1: Add Phase 5b after the export commands**

Insert after the `uv run python tools/export_ciso_docx.py` line (around line 235), before `## PHASE 6`:

```markdown
## PHASE 5b — THREAT LANDSCAPE SYNTHESIS

Delegate to `threat-landscape-agent` with this task description:
"Read all output/runs/*/regional/*/data.json and output/runs/*/regional/*/sections.json files. Synthesize longitudinal adversary patterns across all archived runs. Write output/pipeline/threat_landscape.json per your agent instructions."

On completion: `uv run python tools/audit_logger.py PHASE_COMPLETE "Threat landscape synthesis complete — output/pipeline/threat_landscape.json written"`
If the agent fails or errors: `uv run python tools/audit_logger.py TREND_WARN "Threat landscape synthesis failed — Trends tab will show partial data"` — then continue. This phase is **non-fatal** (same pattern as Phase 2.5).
```

- [ ] **Step 2: Verify Phase numbering is consistent**

Read the modified file. Confirm Phase 5b appears between Phase 5 and Phase 6. No duplicate phase numbers.

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/run-crq.md
git commit -m "feat(pipeline): Phase 5b — threat landscape synthesis in run-crq"
```

---

## Task 6: History Tab — HTML Shell

**Files:**
- Modify: `static/index.html:404-416` — replace History tab content

- [ ] **Step 1: Replace the History tab HTML**

Find the existing History tab block (lines 404-416):

```html
<div id="tab-history" class="hidden">
  <h2 style="font-size:13px;color:#e6edf3;margin-bottom:12px">Run History</h2>
  <div id="history-charts" style="margin-bottom:24px"></div>
  <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;margin-bottom:8px">Archived Runs</div>
  <div id="run-history-list" style="margin-bottom:24px"></div>
  <div style="border-top:1px solid #21262d;padding-top:14px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">Audit Trace</span>
      <button onclick="toggleTrace()" style="font-size:10px;color:#6e7681;cursor:pointer;background:none;border:none">&#9660;</button>
    </div>
    <pre id="audit-trace" class="hidden" style="background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:12px;font-size:10px;color:#6e7681;overflow-x:auto;white-space:pre-wrap"></pre>
  </div>
</div>
```

Replace with:

```html
<div id="tab-history" class="hidden" style="padding:20px 24px;overflow-y:auto;max-height:calc(100vh - 36px)">
  <div id="history-summary" style="background:#080c10;border-bottom:1px solid #21262d;padding:10px 16px;margin:-20px -24px 16px -24px;font-size:10px;color:#8b949e;display:flex;gap:12px;align-items:center"></div>
  <div id="history-matrix" style="margin-bottom:16px;overflow-x:auto"></div>
  <div id="history-run-strip" style="margin-bottom:16px;padding:10px 12px;background:#161b22;border:1px solid #21262d;border-radius:4px;font-size:10px"></div>
  <div id="history-run-log"></div>
</div>
```

- [ ] **Step 2: Verify no orphaned element references**

Search `app.js` for the removed element IDs: `history-charts`, `run-history-list`, `audit-trace`. These will be replaced in Task 8 (JS rewrite). Confirm they exist only in `renderHistory()` and `toggleTrace()` — both of which will be rewritten.

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): History tab HTML shell — matrix layout"
```

---

## Task 7: Validate Tab — Audit Trace Relocation

**Files:**
- Modify: `static/index.html` — add audit trace section to Validate tab (after line ~574)
- Modify: `static/app.js` — load audit trace in `renderValidateTab()`

- [ ] **Step 1: Add audit trace HTML to Validate tab**

In `static/index.html`, find the closing `</div>` of `#tab-validate` (search for the end of the validate tab container). Before the closing tag, add:

```html
  <!-- Audit Trace (relocated from History) -->
  <div style="border-top:1px solid #21262d;padding-top:14px;margin-top:20px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <span style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681">AUDIT TRACE</span>
      <button onclick="toggleAuditTrace()" style="font-size:10px;color:#6e7681;cursor:pointer;background:none;border:none" id="btn-toggle-trace">&#9654;</button>
    </div>
    <pre id="audit-trace" class="hidden" style="background:#0d1117;border:1px solid #21262d;border-radius:4px;padding:12px;font-size:10px;color:#6e7681;overflow-x:auto;white-space:pre-wrap"></pre>
  </div>
```

- [ ] **Step 2: Update `renderValidateTab()` in app.js to load audit trace**

In `static/app.js`, find `renderValidateTab()` (line 1815):

```javascript
async function renderValidateTab() {
  await Promise.all([loadValScenarios(), loadValSources(), loadValCandidates()]);
}
```

Replace with:

```javascript
async function renderValidateTab() {
  await Promise.all([loadValScenarios(), loadValSources(), loadValCandidates(), loadAuditTrace()]);
}
```

- [ ] **Step 3: Add `toggleAuditTrace()` and `loadAuditTrace()` functions**

In `static/app.js`, find the existing `toggleTrace()` function (line 928):

```javascript
function toggleTrace() {
  $('audit-trace').classList.toggle('hidden');
}
```

Replace with:

```javascript
function toggleAuditTrace() {
  const el = $('audit-trace');
  const btn = $('btn-toggle-trace');
  el.classList.toggle('hidden');
  if (btn) btn.innerHTML = el.classList.contains('hidden') ? '&#9654;' : '&#9660;';
}

async function loadAuditTrace() {
  const trace = await fetchJSON('/api/trace');
  if (trace?.log) $('audit-trace').textContent = trace.log;
}
```

- [ ] **Step 4: Remove old `toggleTrace` references**

The old `toggleTrace()` function and the audit trace fetch from `renderHistory()` (line 924-925) will be removed when `renderHistory()` is rewritten in Task 8. No action needed here — just note the dependency.

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(ui): relocate audit trace from History to Validate tab"
```

---

## Task 8: History Tab — JS Rewrite

**Files:**
- Modify: `static/app.js` — rewrite `renderHistory()` (lines 851-926)

This is the largest single task. The new `renderHistory()` builds: summary bar, escalation matrix, run strip, and run log.

- [ ] **Step 1: Add colour map and helper constants**

In `static/app.js`, find the severity colour helpers near `_buildHeatmap` (around line 834). Add above `renderHistory()` (before line 851):

```javascript
// ── History Matrix Helpers ────────────────────────────────────────────
const MATRIX_COLORS = {
  CRITICAL: 'rgba(255,123,114,0.95)',
  HIGH:     'rgba(255,123,114,0.85)',
  MEDIUM:   'rgba(255,166,87,0.80)',
  LOW:      'rgba(227,179,65,0.75)',
  MONITOR:  'rgba(121,192,255,0.55)',
  CLEAR:    '#1a2a1a',
  NO_DATA:  '#21262d',
};
const MATRIX_SEV_LABEL = { CRITICAL: '#ff7b72', HIGH: '#ff7b72', MEDIUM: '#ffa657', LOW: '#e3b341' };

function _matrixCellColor(status, severity) {
  if (!status || status === 'no_data') return MATRIX_COLORS.NO_DATA;
  const s = (status || '').toLowerCase();
  if (s === 'clear') return MATRIX_COLORS.CLEAR;
  if (s === 'monitor') return MATRIX_COLORS.MONITOR;
  return MATRIX_COLORS[severity] || MATRIX_COLORS.MEDIUM;
}

function _fmtShortDate(ts) {
  if (!ts) return '?';
  const d = new Date(ts);
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[d.getMonth()]} ${d.getDate()}`;
}
```

- [ ] **Step 2: Rewrite `renderHistory()`**

Replace the entire `renderHistory()` function (lines 851-926) with:

```javascript
async function renderHistory() {
  const [history, runs] = await Promise.all([
    fetchJSON('/api/history'),
    fetchJSON('/api/runs'),
  ]);

  const regionData = history?.regions || {};
  const drift = history?.drift || {};
  const allRuns = runs || [];

  // Build run index: array of {folder, date, regionMap}
  const runIndex = allRuns.map(run => {
    const m = run.manifest || {};
    const ts = m.run_timestamp || run.name;
    const regionMap = {};
    REGIONS.forEach(r => {
      const pts = regionData[r] || [];
      const match = pts.find(p => p.run_folder === run.name);
      if (match) regionMap[r] = match;
    });
    return { folder: run.name, ts, regionMap, window: m.window_used || '7d' };
  });

  // ── Summary bar ──
  const totalRuns = runIndex.length;
  const dateRange = totalRuns ? `${_fmtShortDate(runIndex[0].ts)} – ${_fmtShortDate(runIndex[runIndex.length-1].ts)}` : '';
  const persistCount = REGIONS.filter(r => {
    const pts = regionData[r] || [];
    const escalated = pts.filter(p => p.status === 'escalated').length;
    return escalated > pts.length / 2;
  }).length;
  const improvingCount = REGIONS.filter(r => {
    const pts = regionData[r] || [];
    if (pts.length < 2) return false;
    const last2 = pts.slice(-2);
    return last2[0].status === 'escalated' && last2[1].status !== 'escalated';
  }).length;
  const clearCount = REGIONS.filter(r => {
    const pts = regionData[r] || [];
    return pts.length > 0 && pts.every(p => p.status === 'clear');
  }).length;

  let summaryHtml = `<span>${totalRuns} runs · ${dateRange}</span>`;
  if (persistCount) summaryHtml += `<span style="color:#ff7b72">· ${persistCount} persistently escalated</span>`;
  if (improvingCount) summaryHtml += `<span style="color:#3fb950">· ${improvingCount} improving</span>`;
  if (clearCount) summaryHtml += `<span style="color:#3fb950">· ${clearCount} stable clear</span>`;
  $('history-summary').innerHTML = summaryHtml;

  // ── Escalation matrix ──
  if (!totalRuns) {
    $('history-matrix').innerHTML = '<p style="color:#6e7681;font-size:11px">Run the pipeline to build history.</p>';
    $('history-run-strip').innerHTML = '';
    $('history-run-log').innerHTML = '';
    return;
  }

  // Disambiguate same-day dates
  const dateLabels = runIndex.map((r, i) => {
    const base = _fmtShortDate(r.ts);
    const dupes = runIndex.filter((x, j) => j <= i && _fmtShortDate(x.ts) === base);
    return dupes.length > 1 ? `${base}${String.fromCharCode(96 + dupes.length)}` : base;
  });

  const isLatest = (i) => i === runIndex.length - 1;
  const colW = Math.max(20, Math.min(36, Math.floor(600 / totalRuns)));

  let matrixHtml = `<div style="display:grid;grid-template-columns:164px repeat(${totalRuns}, ${colW}px);gap:2px;align-items:center">`;
  // Header row
  matrixHtml += '<div></div>';
  dateLabels.forEach((label, i) => {
    const style = isLatest(i)
      ? 'color:#8b949e;font-weight:600;font-size:8px;text-align:center'
      : 'color:#6e7681;font-size:8px;text-align:center';
    matrixHtml += `<div style="${style}">${label}</div>`;
  });

  // Region rows
  REGIONS.forEach(r => {
    const pts = regionData[r] || [];
    const driftInfo = drift[r];
    const driftText = driftInfo && driftInfo.consecutive_runs >= 2
      ? `${driftInfo.current_scenario} ×${driftInfo.consecutive_runs} →`
      : '';
    const latest = pts.length ? pts[pts.length - 1] : null;
    const vacr = latest?.vacr_usd ? `$${(latest.vacr_usd / 1e6).toFixed(1)}M` : '—';
    const escRatio = pts.length ? `${pts.filter(p => p.status === 'escalated').length}/${pts.length}` : '';
    const statusColor = latest?.status === 'escalated' ? (MATRIX_SEV_LABEL[latest.severity] || '#ffa657') : latest?.status === 'monitor' ? '#79c0ff' : '#3fb950';

    matrixHtml += `<div style="padding:4px 8px">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="color:${statusColor};font-weight:600;font-size:10px">${r}</span>
        ${driftText ? `<span style="font-size:8px;color:#e3b341">${esc(driftText)}</span>` : ''}
      </div>
      <div style="font-size:8px;color:#6e7681">${vacr} · ${escRatio} escalated</div>
    </div>`;

    runIndex.forEach((run, i) => {
      const cell = run.regionMap[r];
      const status = cell?.status || 'no_data';
      const severity = cell?.severity || '';
      const bg = _matrixCellColor(status, severity);
      const border = status === 'clear' ? 'border:1px solid #21262d;' : '';
      const latestBorder = isLatest(i) ? 'border:1px solid #58a6ff;' : '';
      const scenario = cell?.primary_scenario || '';
      const cellVacr = cell?.vacr_usd ? `$${(cell.vacr_usd / 1e6).toFixed(1)}M` : '';
      const title = `${dateLabels[i]} · ${severity || status} · ${scenario} · ${cellVacr}`;
      matrixHtml += `<div style="height:20px;background:${bg};border-radius:2px;cursor:pointer;${border}${latestBorder}" title="${esc(title)}" onclick="selectHistoryRun(${i})"></div>`;
    });
  });
  matrixHtml += '</div>';

  // Legend
  const legendItems = [
    ['CRITICAL', MATRIX_COLORS.CRITICAL], ['HIGH', MATRIX_COLORS.HIGH],
    ['MEDIUM', MATRIX_COLORS.MEDIUM], ['LOW', MATRIX_COLORS.LOW],
    ['MONITOR', MATRIX_COLORS.MONITOR], ['CLEAR', MATRIX_COLORS.CLEAR],
    ['No data', MATRIX_COLORS.NO_DATA],
  ];
  matrixHtml += `<div style="display:flex;gap:12px;border-top:1px solid #21262d;padding-top:8px;margin-top:8px">`;
  legendItems.forEach(([label, color]) => {
    const extra = label === 'CLEAR' ? 'border:1px solid #21262d;' : '';
    matrixHtml += `<div style="display:flex;align-items:center;gap:4px;font-size:8px;color:#6e7681"><div style="width:10px;height:10px;border-radius:2px;background:${color};${extra}"></div>${label}</div>`;
  });
  matrixHtml += '</div>';
  $('history-matrix').innerHTML = matrixHtml;

  // ── Run strip (default: latest) ──
  window._historyRunIndex = runIndex;
  window._historyDateLabels = dateLabels;
  window._historyRegionData = regionData;
  selectHistoryRun(runIndex.length - 1);

  // ── Run log ──
  const DOT_COLORS = {
    CRITICAL: '#ff7b72', HIGH: '#ff7b72', MEDIUM: '#ffa657', LOW: '#e3b341',
    MONITOR: '#79c0ff', CLEAR: '#3fb950', NO_DATA: '#21262d',
  };
  const dotLegend = REGIONS.map(r => `<span style="font-size:9px;color:#8b949e">${r}</span>`).join(' · ');
  const recentRuns = runIndex.slice().reverse();
  const visibleCount = 3;
  const runRows = recentRuns.map((run, i) => {
    const opacity = i < 1 ? 1 : i < 3 ? 0.7 : 0.5;
    const dateColor = i < 1 ? '#e6edf3' : i < 3 ? '#8b949e' : '#484f58';
    const dots = REGIONS.map(r => {
      const cell = run.regionMap[r];
      const sev = cell?.status === 'escalated' ? (cell.severity || 'MEDIUM') : cell?.status === 'monitor' ? 'MONITOR' : cell?.status === 'clear' ? 'CLEAR' : 'NO_DATA';
      return `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${DOT_COLORS[sev] || DOT_COLORS.NO_DATA};opacity:${opacity}"></span>`;
    }).join('');
    return `<div style="display:grid;grid-template-columns:1fr auto;padding:4px 0;${i >= visibleCount ? 'display:none;' : ''}" class="run-log-row">
      <span style="font-size:10px;color:${dateColor}">${_fmtShortDate(run.ts)} · ${run.window} window</span>
      <span style="display:flex;gap:4px">${dots}</span>
    </div>`;
  }).join('');

  $('history-run-log').innerHTML = `
    <div style="font-size:8px;color:#6e7681;margin-bottom:6px">dots: ${dotLegend}</div>
    <div id="run-log-rows">${runRows}</div>
    ${recentRuns.length > visibleCount ? `<div style="font-size:9px;color:#484f58;margin-top:6px;cursor:pointer" onclick="document.querySelectorAll('.run-log-row').forEach(r=>r.style.display='grid');this.style.display='none'">${recentRuns.length} runs total · showing ${visibleCount} most recent — click to expand</div>` : ''}
  `;
}

function selectHistoryRun(idx) {
  const runIndex = window._historyRunIndex;
  const dateLabels = window._historyDateLabels;
  if (!runIndex || !runIndex[idx]) return;
  const run = runIndex[idx];
  const isLatestRun = idx === runIndex.length - 1;
  const label = isLatestRun ? 'latest run · click any cell to inspect' : 'click any cell to inspect';

  const items = REGIONS.map(r => {
    const cell = run.regionMap[r];
    if (!cell || cell.status === 'no_data') return `<span style="color:#484f58">${r} no data</span>`;
    const sColor = cell.status === 'escalated' ? (MATRIX_SEV_LABEL[cell.severity] || '#ffa657') : cell.status === 'monitor' ? '#79c0ff' : '#3fb950';
    const info = cell.status === 'escalated'
      ? `${cell.primary_scenario || '?'} · $${((cell.vacr_usd || 0) / 1e6).toFixed(1)}M`
      : cell.status;
    return `<span><span style="color:${sColor};font-weight:600">${r}</span> <span style="color:#8b949e">${esc(info)}</span></span>`;
  }).join(' &nbsp;·&nbsp; ');

  $('history-run-strip').innerHTML = `
    <div style="font-size:9px;color:#6e7681;margin-bottom:6px">${dateLabels[idx]} — ${run.window} window (${label})</div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;font-size:10px">${items}</div>
  `;
}
```

- [ ] **Step 3: Remove old helper functions that are no longer needed**

Remove `_buildSparkline` (lines 814-832), `_buildHeatmap` (lines 834-842), and `_velArrow` (lines 844-849) ONLY if they are not used elsewhere. Search for usages:

Run: `grep -n '_buildSparkline\|_buildHeatmap\|_velArrow' static/app.js`

If they are ONLY used in the old `renderHistory()`, remove them. If used elsewhere (e.g., Overview tab), keep them.

- [ ] **Step 4: Verify the app loads without JS errors**

Start the server: `uv run python -m uvicorn server:app --port 8000`
Open `http://localhost:8000`, click the History tab. Verify:
1. No console errors
2. Matrix renders if history data exists
3. Clicking a cell updates the run strip

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): History tab — escalation matrix, run strip, run log"
```

---

## Task 9: Trends Tab — JS Rewrite

**Files:**
- Modify: `static/app.js` — rewrite `renderTrends()` (lines 934-1017)

- [ ] **Step 1: Rewrite `renderTrends()`**

Replace the entire `renderTrends()` function (lines 934-1017) with:

```javascript
async function renderTrends() {
  const container = $('trends-content');
  if (!container) return;
  container.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:20px 0">Loading threat landscape...</div>';

  const [trends, landscape] = await Promise.all([
    fetch('/api/trends').then(r => r.ok ? r.json() : {}).catch(() => ({})),
    fetch('/api/threat-landscape').then(r => r.ok ? r.json() : {}).catch(() => ({})),
  ]);

  const hasLandscape = landscape && landscape.status !== 'no_data' && landscape.analysis_window;
  const hasTrends = trends && trends.status !== 'no_data' && trends.regions;

  if (!hasLandscape && !hasTrends) {
    container.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:20px 0">No threat landscape data yet — run the pipeline to generate analysis.</div>';
    return;
  }

  const window_ = hasLandscape ? landscape.analysis_window : {};
  const sufficiency = window_.data_sufficiency || 'limited';
  const runCount = window_.runs_included || trends?.run_count || 0;
  const dateRange = window_.from && window_.to ? `${window_.from} – ${window_.to}` : '';
  const generatedAt = hasLandscape ? landscape.generated_at : '';

  // ── Header bar ──
  const limitedBadge = sufficiency === 'limited'
    ? `<span style="background:#2d2208;border:1px solid #d29922;color:#d29922;padding:2px 8px;border-radius:2px;font-size:9px">Limited data — ${window_.runs_with_full_sections || 0}/${runCount} runs with full attribution</span>`
    : '';
  const genLabel = generatedAt
    ? `Last generated: ${new Date(generatedAt).toLocaleString()}`
    : 'Not yet generated';

  let html = `<div style="background:#080c10;border-bottom:1px solid #21262d;padding:10px 16px;margin:-20px -24px 16px -24px;display:flex;align-items:center;justify-content:space-between">
    <div style="display:flex;gap:12px;align-items:center;font-size:10px;color:#8b949e">
      <span>${runCount} runs · ${dateRange}</span>
      ${limitedBadge}
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      <span style="font-size:8px;color:#6e7681">${genLabel}</span>
      <button onclick="runThreatLandscape(this)" style="font-size:10px;color:#3fb950;background:#1a3a1a;border:1px solid #238636;padding:4px 14px;border-radius:2px;cursor:pointer">&#8635; Generate Quarterly Brief</button>
    </div>
  </div>`;

  // ── Section 1: Compound Risks ──
  html += `<div style="margin-bottom:24px">
    <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">CROSS-REGIONAL COMPOUND RISKS</div>`;

  const compoundRisks = hasLandscape ? (landscape.compound_risks || []) : [];
  if (sufficiency === 'limited' || !compoundRisks.length) {
    html += `<div style="padding:12px;background:#161b22;border:1px solid #21262d;border-radius:4px;color:#6e7681;font-size:10px">Insufficient data to identify compound risks — analysis available after 5+ runs with attribution data.</div>`;
  } else {
    compoundRisks.forEach(cr => {
      const levelColor = cr.risk_level === 'HIGH' ? '#ff7b72' : cr.risk_level === 'MEDIUM' ? '#ffa657' : '#e3b341';
      html += `<div style="border-left:3px solid #ff7b72;background:#160808;border-radius:0 4px 4px 0;padding:10px 14px;margin-bottom:8px">
        <div style="font-size:8px;color:#8b949e;margin-bottom:4px">${cr.risk_level} · ${(cr.regions||[]).join(' + ')} · ${cr.corroborating_runs} corroborating runs</div>
        <div style="font-size:10px;color:#e6edf3;line-height:1.6">${esc(cr.description)}</div>
      </div>`;
    });
  }
  html += '</div>';

  // ── Section 2: Threat Actors ──
  html += `<div style="margin-bottom:24px">
    <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">THREAT ACTORS</div>`;

  const actors = hasLandscape ? (landscape.threat_actors || []) : [];
  if (sufficiency === 'limited' || !actors.length) {
    html += `<div style="border:1px solid #21262d;border-radius:4px;overflow:hidden">
      <div style="background:#161b22;padding:5px 12px;font-size:8px;color:#484f58;text-transform:uppercase;display:grid;grid-template-columns:130px 1fr 80px 80px 50px">
        <span>Actor</span><span>Objective</span><span>Regions</span><span>Activity</span><span>Conf.</span>
      </div>
      <div style="padding:12px;color:#6e7681;font-size:10px;font-style:italic">Attribution data accumulating — table will populate after 5+ runs.</div>
    </div>`;
  } else {
    html += `<div style="border:1px solid #21262d;border-radius:4px;overflow:hidden">
      <div style="background:#161b22;padding:5px 12px;font-size:8px;color:#484f58;text-transform:uppercase;display:grid;grid-template-columns:130px 1fr 80px 80px 50px">
        <span>Actor</span><span>Objective</span><span>Regions</span><span>Activity</span><span>Conf.</span>
      </div>`;
    actors.forEach(a => {
      const isUnknown = !a.name;
      const bg = isUnknown ? 'background:#0d1117;opacity:0.7;' : '';
      const nameStyle = isUnknown ? 'color:#6e7681;font-style:italic' : 'color:#e6edf3;font-weight:600';
      const trendColor = a.activity_trend === 'escalating' ? '#ff7b72' : a.activity_trend === 'declining' ? '#3fb950' : '#6e7681';
      html += `<div style="display:grid;grid-template-columns:130px 1fr 80px 80px 50px;padding:7px 12px;border-top:1px solid #21262d;font-size:10px;${bg}">
        <span style="${nameStyle}">${esc(a.name || 'Unattributed')}</span>
        <span style="color:${isUnknown ? '#6e7681;font-style:italic' : '#c9d1d9'}">${esc(a.objective || '')}</span>
        <span style="color:#8b949e">${(a.regions||[]).join(', ')}</span>
        <span style="color:${trendColor}">${a.activity_trend || '—'}</span>
        <span style="color:#6e7681">${a.confidence || '—'}</span>
      </div>`;
    });
    html += '</div>';
  }
  html += '</div>';

  // ── Section 3: Scenario Persistence ──
  html += `<div style="margin-bottom:24px">
    <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">SCENARIO PERSISTENCE</div>`;

  const scenarios = hasLandscape ? (landscape.scenario_lifecycle || []) : [];
  if (!scenarios.length) {
    html += '<div style="color:#6e7681;font-size:10px">No scenario data available.</div>';
  } else {
    const totalRuns = runCount || 1;
    scenarios.forEach(sc => {
      const pillBg = sc.stage === 'persistent' ? '#2d0a0a' : sc.stage === 'emerging' ? '#2d2208' : '#161b22';
      const pillBorder = sc.stage === 'persistent' ? '#ff7b72' : sc.stage === 'emerging' ? '#d29922' : '#6e7681';
      const pillColor = pillBorder;
      const barPct = Math.round((sc.run_count / totalRuns) * 100);
      html += `<div style="margin-bottom:10px">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="background:${pillBg};border:1px solid ${pillBorder};color:${pillColor};font-size:7px;padding:1px 5px;border-radius:8px;text-transform:uppercase">${sc.stage}</span>
          <span style="color:#e6edf3;font-size:10px">${esc(sc.name)}</span>
          <span style="margin-left:auto;font-size:8px;color:#6e7681">${sc.run_count}/${totalRuns} · ${(sc.regions||[]).join(', ')}</span>
        </div>
        <div style="background:#21262d;height:5px;border-radius:2px;margin-top:4px"><div style="background:${pillBorder};height:5px;border-radius:2px;width:${barPct}%"></div></div>
      </div>`;
    });
  }
  html += '</div>';

  // ── Section 4: Intelligence Gaps ──
  const gaps = hasLandscape ? (landscape.intelligence_gaps || []) : [];
  if (gaps.length) {
    html += `<div style="margin-bottom:24px">
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">INTELLIGENCE GAPS</div>
      <div style="border:1px solid #30363d;border-radius:4px;overflow:hidden">`;
    gaps.forEach(gap => {
      const isMaturity = (gap.description || '').toLowerCase().includes('accumulating') || (gap.description || '').toLowerCase().includes('maturity');
      const badgeBg = isMaturity ? '#161b22' : '#2d2208';
      const badgeBorder = isMaturity ? '#30363d' : '#d29922';
      const badgeColor = isMaturity ? '#6e7681' : '#d29922';
      html += `<div style="display:flex;gap:12px;padding:8px 12px;border-bottom:1px solid #21262d">
        <span style="background:${badgeBg};border:1px solid ${badgeBorder};color:${badgeColor};font-size:8px;padding:2px 6px;border-radius:2px;white-space:nowrap;height:fit-content">${esc(gap.region || 'ALL')}</span>
        <div>
          <div style="font-size:9px;color:#c9d1d9">${esc(gap.description)}</div>
          <div style="font-size:8px;color:#6e7681;margin-top:2px">${esc(gap.impact || '')}</div>
        </div>
      </div>`;
    });
    html += '</div></div>';
  }

  // ── Section 5: Board Talking Points ──
  const talkingPoints = hasLandscape ? (landscape.board_talking_points || []) : [];
  if (talkingPoints.length) {
    html += `<div style="margin-bottom:24px">
      <div style="font-size:9px;letter-spacing:0.1em;text-transform:uppercase;color:#6e7681;border-bottom:1px solid #21262d;padding-bottom:6px;margin-bottom:10px">BOARD TALKING POINTS</div>`;
    talkingPoints.forEach(tp => {
      const isPositive = tp.type === 'POSITIVE SIGNAL';
      const accent = isPositive ? '#3fb950' : '#58a6ff';
      const borderAccent = isPositive ? '#238636' : '#1f6feb';
      html += `<div style="border:1px solid ${borderAccent};border-left:3px solid ${accent};padding:8px 12px;border-radius:0 4px 4px 0;margin-bottom:8px">
        <div style="font-size:8px;color:${accent};text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px">${esc(tp.type || '')}</div>
        <div style="font-size:10px;color:#c9d1d9;line-height:1.6">${esc(tp.text || '')}</div>
      </div>`;
    });
    html += '</div>';
  }

  // ── Footer ──
  html += `<div style="font-size:9px;color:#484f58;margin-top:8px">
    ${hasLandscape ? `Threat landscape: ${sufficiency} data · ${runCount} runs` : ''}
    ${hasTrends ? ` · Trend analysis: ${trends.run_count || 0} runs` : ''}
    ${generatedAt ? ` · Generated ${new Date(generatedAt).toLocaleString()}` : ''}
  </div>`;

  container.innerHTML = html;
}

async function runThreatLandscape(btn) {
  btn.disabled = true;
  btn.innerHTML = '&#8635; Generating...';
  try {
    const r = await fetch('/api/run-threat-landscape', { method: 'POST' });
    const data = await r.json();
    if (data.status === 'already_running') {
      btn.innerHTML = '&#8635; Already running...';
    }
  } catch {
    btn.innerHTML = '&#8635; Failed';
  }
  // Re-enable after delay — the agent may take minutes
  setTimeout(() => { btn.disabled = false; btn.innerHTML = '&#8635; Generate Quarterly Brief'; }, 5000);
}
```

- [ ] **Step 2: Remove old Trends helper functions**

Remove `buildTrendSparkline` (within old renderTrends, around line 950-961) and `buildScenarioBars` (around line 963-971). These are local functions inside the old `renderTrends` scope — they go away when the function is replaced.

- [ ] **Step 3: Verify the app loads without JS errors**

Start the server, open `http://localhost:8000`, click the Trends tab. Verify:
1. No console errors
2. Header bar renders with run count
3. If no `threat_landscape.json` exists, shows "No threat landscape data" message
4. Generate button is present and clickable

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): Trends tab — threat landscape view with compound risks, actors, gaps"
```

---

## Task 10: Cleanup & Final Verification

**Files:**
- Modify: `static/app.js` — remove dead code

- [ ] **Step 1: Search for orphaned references**

Run these searches:
```bash
grep -n 'history-charts\|run-history-list\|toggleTrace' static/app.js
grep -n 'buildTrendSparkline\|buildScenarioBars\|heatmapHtml\|talkingPoints.*ciso_talking' static/app.js
```

Remove any remaining references to old element IDs or functions that no longer exist.

- [ ] **Step 2: Verify all tabs work end-to-end**

Start the server, open `http://localhost:8000`. Check each tab:
1. **Overview** — loads normally, no errors
2. **Reports** — loads normally
3. **History** — matrix renders (or "Run pipeline" message if no data)
4. **Trends** — threat landscape view renders (or empty state)
5. **Validate** — scenarios table + audit trace collapsible at bottom
6. **Sources** — loads normally
7. **Config** — loads normally

- [ ] **Step 3: Verify no JS errors in browser console**

Open DevTools Console. Switch between all tabs. Confirm zero errors.

- [ ] **Step 4: Commit cleanup**

```bash
git add static/app.js static/index.html
git commit -m "chore: remove dead History/Trends code after redesign"
```

---

## Dependency Graph

```
Task 1 (upstream fix) ──┐
                         ├── Task 3 (agent def) ── Task 5 (pipeline wiring)
Task 2 (stop hook) ─────┘
                                    Task 4 (server endpoints) ── Task 9 (Trends JS)
Task 6 (History HTML) ── Task 8 (History JS)
Task 7 (Validate audit trace)
Task 10 (cleanup) ── depends on all above
```

**Independent tracks that can run in parallel:**
- Track A: Tasks 1, 2, 3, 5 (pipeline)
- Track B: Tasks 4, 9 (server + Trends UI)
- Track C: Tasks 6, 8 (History UI)
- Track D: Task 7 (Validate)
- Track E: Task 10 (after all)
