# Dashboard UI Alignment — Implementation Plan
**Date:** 2026-04-05
**Spec:** `docs/superpowers/specs/2026-04-05-dashboard-alignment-design.md`
**Status:** Ready to build

---

## Team structure

- **Orchestrator: Opus** — coordinate, validate final output
- **Builder A: Sonnet** — Tasks 1–2 (agent + validator)
- **Builder B: Sonnet** — Task 3 (server endpoint) + Task 4 (report_builder migration)
- **Builder C: Sonnet** — Task 5 (dashboard app.js)
- **Validator: Sonnet** — Task 6 (cross-check all done criteria)

**Execution order:**
```
Phase 1 (sequential): Builder A — Tasks 1+2 (agent writes sections.json → validator gate exists)
Phase 2 (parallel):   Builder B — Tasks 3+4 | Builder C — Task 5
Phase 3 (sequential): Validator — Task 6
```

Builder B Task 4 (report_builder migration) is gated on Task 1 completing — it reads `sections.json` which must exist before extraction functions can be removed.
Builder C (Task 5) can run in parallel with B — it only needs the endpoint path, not the data.

---

## Task 1 — Agent: add sections.json output

**Builder A**
**depends_on:** `_SCENARIO_ACTIONS` dict in `tools/report_builder.py` (lines 156–173), `regional-analyst-agent.md`
**feeds_into:** Task 4 (report_builder reads sections.json), Task 3 (endpoint serves it), Task 6 (validator checks it)
**context:** The agent currently writes 5 artifacts. sections.json is the 6th — machine-readable structured output for the dashboard and exporters. The agent already knows these values when writing report.md; it just hasn't been asked to emit them separately.

### Files to modify

**`.claude/agents/regional-analyst-agent.md`**

1. Add **Step 8 — Write sections.json** after the existing Step 7 (update data.json):

```
## STEP 8 — WRITE SECTIONS.JSON

After updating data.json, write `output/regional/{region_lower}/sections.json`.

This is the machine-readable version of your brief — used by the dashboard and exporters.
Write it using the Write tool.

Schema:
{
  "region": "{REGION uppercase}",
  "generated_at": "<ISO 8601 UTC — same timestamp as data.json>",
  "threat_actor": "<primary actor named in brief, or empty string if none>",
  "signal_type_label": "<one of: Confirmed Incident | Emerging Pattern | Confirmed Incident + Emerging Pattern>",
  "status_label": "<ESCALATED — GEO-LED or ESCALATED — CYBER-LED based on dominant_pillar>",
  "intel_bullets": ["<2–3 key findings from Why paragraph>"],
  "adversary_bullets": ["<1–2 observed activity lines from How paragraph>"],
  "impact_bullets": ["<1–2 AeroGrid-specific consequences from So What — no VaCR, no financial figures>"],
  "watch_bullets": ["<2–3 concrete watch indicators from So What closing>"],
  "action_bullets": ["<2–3 recommended actions from scenario lookup below>"]
}

signal_type_label mapping:
  Event  → "Confirmed Incident"
  Trend  → "Emerging Pattern"
  Mixed  → "Confirmed Incident + Emerging Pattern"

status_label mapping:
  dominant_pillar = Cyber → "ESCALATED — CYBER-LED"
  dominant_pillar = Geo   → "ESCALATED — GEO-LED"
  dominant_pillar = Mixed → "ESCALATED — CYBER-LED"  (default to cyber-led for mixed)

action_bullets lookup (use scenario_match from Step 2):
  "Ransomware":
    - "Verify offline backup integrity and tested recovery time for OT/SCADA environments."
    - "Confirm IT/OT network segmentation is enforced — no lateral path from corporate to operational systems."
  "System intrusion":
    - "Audit third-party and supply chain access credentials for privileged systems."
    - "Review hardware integrity for recently sourced components in affected manufacturing sites."
  "Insider misuse":
    - "Review privileged access logs for anomalous data movement on crown jewel systems."
    - "Confirm data loss prevention alerts are active and monitored."
  "Accidental disclosure":
    - "Verify data classification controls are applied to sensitive IP repositories."
    - "Review cloud sharing permissions for engineering and R&D assets."
  (no match) → derive 2 generic actions from the scenario description in master_scenarios.json

Only write sections.json for ESCALATED regions. Do not write it for CLEAR or MONITOR.
```

2. Add to **Self-Validation Checklist**:
```
- [ ] sections.json written with all 5 bullet arrays non-empty and threat_actor/signal_type_label populated
```

### Done criteria (Task 1)
- Step 8 present in agent spec with full schema, mappings, and lookup table
- Self-validation checklist item added
- No change to any other step in the agent spec

---

## Task 2 — Validator: sections-validator.py

**Builder A** (same builder, sequential after Task 1)
**depends_on:** Task 1 (agent spec defines what sections.json must contain)
**feeds_into:** pipeline stop hook chain — runs after grounding-validator.py
**context:** Every agent output needs a deterministic quality gate. This is the gate for sections.json. Pattern is identical to grounding-validator.py — region discovery, guard check, retry machinery, exit codes.

### File to create

**`.claude/hooks/validators/sections-validator.py`**

```python
"""
Sections validator — deterministic check of sections.json integrity.
Runs as stop hook after regional-analyst-agent exits.

Guard: reads output/regional/*/gatekeeper_decision.json to find the region.
If decision != "ESCALATE", exit 0 immediately (no sections.json expected).

Checks:
1. sections.json exists for ESCALATED region
2. Valid JSON
3. All required keys present: intel_bullets, adversary_bullets, impact_bullets,
   watch_bullets, action_bullets, threat_actor, signal_type_label
4. intel_bullets, adversary_bullets, impact_bullets are non-empty lists

Retry pattern: output/.retries/sections-validator.retries
Max 3 retries then force-approve with warning logged to system_trace.log.
Exit codes: 0 = pass/skip, 1 = fail (triggers agent retry)
"""
```

Model the retry machinery, region discovery, and logging exactly after `grounding-validator.py`. Region discovery: find latest `sections.json` by mtime in `output/regional/*/sections.json`.

### Wire as stop hook

Add to `.claude/agents/regional-analyst-agent.md` frontmatter hooks:
```yaml
hooks:
  Stop:
    - type: command
      command: "uv run python .claude/hooks/validators/regional-analyst-stop.py"
    - type: command
      command: "uv run python .claude/hooks/validators/grounding-validator.py"
    - type: command
      command: "uv run python .claude/hooks/validators/sections-validator.py"
```

### Done criteria (Task 2)
- `sections-validator.py` exists with all 4 checks implemented
- Retry machinery matches grounding-validator pattern (max 3, force-approve with warning)
- Wired as 3rd stop hook in agent frontmatter
- `uv run python .claude/hooks/validators/sections-validator.py` exits 0 on a valid run

---

## Task 3 — Server: GET /api/region/{region}/sections

**Builder B**
**depends_on:** nothing (endpoint is a file pass-through — sections.json doesn't need to exist yet)
**feeds_into:** Task 5 (dashboard fetches from this endpoint)
**context:** Thin pass-through endpoint. No compute. Reads file, returns JSON. Pattern matches existing `/api/region/{region}/clusters` endpoint in server.py.

### File to modify

**`server.py`** — add after the existing `/api/region/{region}/clusters` endpoint:

```python
@app.get("/api/region/{region}/sections")
async def get_region_sections(region: str):
    path = OUTPUT_DIR / "regional" / region.lower() / "sections.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
```

### Done criteria (Task 3)
- Endpoint exists and returns correct JSON for a region that has sections.json
- Returns `{}` gracefully when sections.json absent
- `curl http://localhost:8000/api/region/apac/sections` returns valid JSON

---

## Task 4 — report_builder.py: read sections.json, remove extraction

**Builder B** (after Task 3 — same session, sequential)
**depends_on:** Task 1 complete (agent spec defines sections.json schema) + sections.json files present in output/regional/*/
**feeds_into:** all exporters (PDF/PPTX/DOCX already read from RegionEntry fields — no exporter changes needed)
**context:** report_builder.py currently calls _intel_bullets(), _adversary_bullets() etc. to extract section content by parsing prose. After sections.json exists, these become dead code. This task replaces the extraction calls with a file read and removes the extraction functions.

### File to modify

**`tools/report_builder.py`**

In the `build()` function, for ESCALATED regions, replace:
```python
threat_actor   = _extract_threat_actor(why_text, how_text)
sig_type_label = _signal_type_label(d.get("signal_type"))
intel_b        = _intel_bullets(why_text)
adversary_b    = _adversary_bullets(how_text)
impact_b       = _impact_bullets(so_what_text)
watch_b        = _watch_bullets(how_text, so_what_text)
action_b       = _action_bullets(d.get("primary_scenario"))
```

With:
```python
sections = _load_sections(base, region_name)
threat_actor   = sections.get("threat_actor") or ""
sig_type_label = sections.get("signal_type_label") or _signal_type_label(d.get("signal_type"))
intel_b        = sections.get("intel_bullets") or []
adversary_b    = sections.get("adversary_bullets") or []
impact_b       = sections.get("impact_bullets") or []
watch_b        = sections.get("watch_bullets") or []
action_b       = sections.get("action_bullets") or []
```

Add helper:
```python
def _load_sections(base: Path, region: str) -> dict:
    path = base / "regional" / region.lower() / "sections.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
```

The `or` fallbacks ensure existing runs without sections.json don't break — they fall back to empty lists gracefully. `sig_type_label` falls back to the existing `_signal_type_label()` call so non-sections runs still work.

**Remove these functions** (dead code once sections.json is live):
- `_intel_bullets()`
- `_adversary_bullets()`
- `_impact_bullets()`
- `_watch_bullets()`
- `_action_bullets()`
- `_extract_threat_actor()`
- `_STATE_ACTORS` list
- `_CRIMINAL_PAT` regex
- `_SCENARIO_ACTIONS` dict (moved to agent spec)
- `_signal_type_label()` — keep for the fallback above, mark DEPRECATED

Also remove: `_parse_pillars()` and `why_text`/`how_text`/`so_what_text` extraction since the raw pillar text is no longer needed for bullet extraction. Keep `why_text`/`how_text`/`so_what_text` on `RegionEntry` for reference — just stop populating them from file parsing if sections.json covers all consumers.

**Gating rule:** Only remove extraction functions after confirming `uv run python tools/report_builder.py` passes with sections.json present.

### Done criteria (Task 4)
- `build()` reads from `_load_sections()` for all 7 section fields
- All 7 extraction functions removed
- `_SCENARIO_ACTIONS`, `_STATE_ACTORS`, `_CRIMINAL_PAT` removed
- `uv run python tools/report_builder.py` exits 0
- `uv run python tools/build_dashboard.py` exits 0

---

## Task 5 — Dashboard: right panel + synthesis bar + trends label

**Builder C**
**depends_on:** Task 3 (endpoint path `/api/region/{region}/sections` confirmed)
**feeds_into:** dashboard user experience
**context:** Three changes to static/app.js. The right panel currently fetches raw markdown from /api/region/{region}/report. Replace with structured 5-section render. Synthesis bar currently shows a raw text paragraph. Replace with 4-part structured layout. One label rename in renderTrends().

### File to modify

**`static/app.js`**

#### Change 1 — Replace renderBriefSection() and _fetchBrief()

Replace the `renderBriefSection()` function with:

```javascript
function renderBriefSection(region, d) {
  const contentId = `brief-sections-${region}`;
  return `<div id="${contentId}">
    <div style="color:#6e7681;font-size:11px">Loading...</div>
  </div>
  <div id="evidence-panel-${region}" style="margin-top:8px;border-top:1px solid #21262d;padding-top:8px">
    <button class="evidence-toggle" id="evidence-toggle-${region}" onclick="toggleEvidence('${region}')" style="background:none;border:none;color:#6e7681;font-size:10px;cursor:pointer;padding:0;font-family:inherit">▶ Source Evidence</button>
    <div class="evidence-list" id="evidence-list-${region}" style="display:none;margin-top:6px;padding-left:4px"></div>
  </div>`;
}
```

Replace `_fetchBrief()` with:

```javascript
function _fetchBrief(region) {
  fetch(`/api/region/${region}/sections`)
    .then(r => r.json())
    .then(data => {
      const el = document.getElementById(`brief-sections-${region}`);
      if (!el) return;
      if (!data || !data.intel_bullets) {
        el.innerHTML = `<p style="color:#6e7681;font-size:11px">Brief not available for this run.</p>`;
        return;
      }
      el.innerHTML = _renderSections(data);
    })
    .catch(() => {
      const el = document.getElementById(`brief-sections-${region}`);
      if (el) el.innerHTML = `<p style="color:#6e7681;font-size:11px">Brief not available.</p>`;
    });
  _fetchEvidence(region);
}

function _renderSections(s) {
  const sections = [
    { key: 'intel_bullets',     label: 'INTEL FINDINGS',              color: '#1f6feb' },
    { key: 'adversary_bullets', label: 'OBSERVED ADVERSARY ACTIVITY', color: '#388bfd' },
    { key: 'impact_bullets',    label: 'IMPACT FOR AEROGRID',         color: '#3fb950' },
    { key: 'watch_bullets',     label: 'WATCH FOR',                   color: '#e3b341' },
    { key: 'action_bullets',    label: 'RECOMMENDED ACTIONS',         color: '#ff7b72' },
  ];
  return sections.map(sec => {
    const bullets = s[sec.key] || [];
    if (!bullets.length) return '';
    const items = bullets.map(b => `<div style="margin-bottom:4px;color:#c9d1d9;font-size:11px;line-height:1.5">${esc(b)}</div>`).join('');
    return `
<div style="border-left:2px solid ${sec.color};padding-left:8px;margin-bottom:10px">
  <div style="font-size:9px;letter-spacing:0.08em;color:${sec.color};margin-bottom:4px">${sec.label}</div>
  ${items}
</div>`;
  }).join('');
}
```

Also update the `contextStrip` in `renderRightPanel()` to include threat actor and status label from sections data. Fetch sections eagerly when a region is selected and cache in `state.regionSections[region]`.

#### Change 2 — Update synthesis bar

In `renderOverview()` (the function that populates `#synthesis-brief`, `#global-priority`, `#status-counts` etc.), replace the raw `synthesis-brief` paragraph with structured elements:

```javascript
// Status counts — derive from state.regionData
const counts = { escalated: 0, monitor: 0, clear: 0 };
REGIONS.forEach(r => {
  const s = (state.regionData[r]?.status || 'clear').toLowerCase();
  if (s === 'escalated') counts.escalated++;
  else if (s === 'monitor') counts.monitor++;
  else counts.clear++;
});

const countsHtml = `
  <span style="color:#ff7b72;font-size:10px;font-weight:600">${counts.escalated} ESCALATED</span>
  <span style="color:#6e7681;font-size:10px"> · </span>
  <span style="color:#e3b341;font-size:10px">${counts.monitor} WATCH</span>
  <span style="color:#6e7681;font-size:10px"> · </span>
  <span style="color:#3fb950;font-size:10px">${counts.clear} CLEAR</span>`;

// Headline from global_report exec_summary (first sentence of HEADLINE part)
const headline = state.globalReport?.exec_summary
  ? extractHeadline(state.globalReport.exec_summary)
  : 'Run pipeline to generate global synthesis.';

$('synthesis-brief').innerHTML = `
  <div style="font-size:11px;color:#c9d1d9;margin-bottom:4px">${esc(headline)}</div>
  <div style="display:flex;align-items:center;gap:6px">${countsHtml}</div>`;
```

Add helper:
```javascript
function extractHeadline(execSummary) {
  // exec_summary starts with "HEADLINE: ..." — extract first sentence
  const match = execSummary.match(/HEADLINE[:\s]+([^\.]+\.)/i);
  return match ? match[1].trim() : execSummary.split('.')[0].trim() + '.';
}
```

#### Change 3 — Trends label rename

In `renderTrends()`, find and replace:
```javascript
// Before:
'CISO Talking Points'
// After:
'Executive Talking Points'
```

### Done criteria (Task 5)
- Right panel shows 5 labelled sections with coloured left borders for escalated regions
- Right panel shows "Brief not available" gracefully for CLEAR/MONITOR
- Synthesis bar shows headline + colour-coded status counts
- Synthesis bar fallback works when global_report.json absent
- "CISO Talking Points" → "Executive Talking Points" in Trends tab
- No JS console errors

---

## Task 6 — Validation

**Validator: Sonnet**
**depends_on:** Tasks 1–5 complete
**context:** Cross-check all 10 done criteria from the spec.

Read these files and check each criterion:
1. `.claude/agents/regional-analyst-agent.md` — Step 8 present, checklist item added, SCENARIO_ACTIONS lookup table present
2. `.claude/hooks/validators/sections-validator.py` — exists, 4 checks implemented, wired in frontmatter
3. `output/regional/*/sections.json` — exists for escalated regions (run `/run-crq` in mock mode if needed)
4. `server.py` — `/api/region/{region}/sections` endpoint exists
5. `static/app.js` — `_renderSections()` function present, synthesis bar updated, trends label changed
6. Run `uv run python tools/report_builder.py` and `uv run python tools/build_dashboard.py` — both exit 0
7. Verify extraction functions removed from report_builder.py

Report APPROVED or REWRITE with specific failures.

---

## Execution notes

- Builder A and Builder C have no shared files — they can start simultaneously if desired, but Builder A must complete before Builder B Task 4.
- `static/index.html` requires no changes.
- `export_ciso_docx.py`, `export_pptx.py`, `report.html.j2` require no changes — they already read from RegionEntry fields which report_builder populates.
- The `or []` fallbacks in Task 4 mean existing pipeline output without sections.json degrades gracefully — no hard breakage on old runs.

---

## Done criteria (full list from spec)

- [ ] `regional-analyst-agent.md` has Step 8 with schema, mappings, and SCENARIO_ACTIONS lookup
- [ ] `sections-validator.py` exists and wired as 3rd stop hook
- [ ] Mock pipeline run produces `sections.json` for all escalated regions
- [ ] `GET /api/region/{region}/sections` returns correct JSON
- [ ] Dashboard right panel shows 5 labelled sections for escalated regions
- [ ] Dashboard right panel shows "Brief not available" for CLEAR/MONITOR
- [ ] Global synthesis bar shows headline + colour-coded status counts
- [ ] "CISO Talking Points" → "Executive Talking Points" in Trends tab
- [ ] `report_builder.py` reads from `sections.json` (extraction functions removed)
- [ ] Validator confirms all criteria pass
