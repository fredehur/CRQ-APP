# Trends & History Tab Redesign — Design Spec
**Date:** 2026-04-06
**Status:** Approved for implementation planning
**Scope:** Trends tab (pipeline + UI), History tab (UI only), Validate tab (audit trace relocation)
**Files changed:** `static/index.html`, `static/app.js`, `server.py`, `.claude/agents/`, `output/pipeline/`
**Deferred:** CISO Quarterly Brief as Audience Hub card (separate spec — requires this spec to ship first)

---

## 1. Context & Decisions

### Why this redesign
- **Trends tab** is a flat dump with no information hierarchy. Executive talking points, heatmap, cross-regional risk, and per-region cards all render at the same visual weight.
- **History tab** mixes three unrelated concerns: region performance charts, an archived runs list, and a raw audit trace log.
- **Audit trace** is a developer/ops tool in a consumer-facing tab.
- Neither tab realises the "threat landscape" purpose — longitudinal adversary pattern tracking — that a senior analyst and CISO actually need.

### Approach selected
**Full solution (C):** New `threat-landscape-agent` pipeline phase + Trends UI rebuild + History UI rebuild. No half-measures. The design should be right the first time.

### Downstream consideration
The `threat_landscape.json` output and its API endpoint (`GET /api/threat-landscape`) must be clean structured JSON, consumable by an external Microsoft dashboard without HTML scraping.

---

## 2. Pipeline Changes

### 2a. Upstream fix — `threat_actor` in `data.json` (PREREQUISITE)

**Problem:** `sections.json` (which contains `threat_actor`) exists in only 4 of 12 archived runs. Without this fix, the threat-landscape-agent launches with sparse attribution data.

**Fix:** Extend `regional-analyst-agent.md` to also write `threat_actor` to `data.json` — the same value it already writes to `sections.json`.

**Change:** Add `"threat_actor": "<clean actor name or null>"` to the `data.json` schema in the regional analyst output instructions. This is a one-field addition; the agent already has the value.

**This must ship at the same time as the threat-landscape-agent — not after.**

### 2b. New agent — `threat-landscape-agent`

**File:** `.claude/agents/threat-landscape-agent.md`
**Model:** `sonnet`
**Runs:** After `global-builder-agent` in the `/run-crq` pipeline (new Phase 5b, before CISO docx export)

**Inputs (reads from):**
- `output/runs/*/regional/*/data.json` — all archived runs, all regions. Fields used: `primary_scenario`, `severity`, `dominant_pillar`, `vacr_exposure_usd`, `threat_actor`, `timestamp`, `status`
- `output/runs/*/regional/*/sections.json` — where available. Fields used: `threat_actor`, `adversary_bullets`, `watch_bullets`
- **Does NOT read `report.md`** — unstructured extraction compounds hallucination risk

**Output:** `output/pipeline/threat_landscape.json` (atomic write via `.tmp` rename)

**Output schema:**
```json
{
  "generated_at": "<ISO 8601 UTC>",
  "analysis_window": {
    "from": "<YYYY-MM-DD>",
    "to": "<YYYY-MM-DD>",
    "runs_included": 12,
    "runs_with_full_sections": 4,
    "data_sufficiency": "limited | adequate | strong"
  },
  "threat_actors": [
    {
      "name": "<clean actor name>",
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

**Data sufficiency rules:**
- `"limited"`: fewer than 5 runs with `threat_actor` populated in `data.json`. `adversary_patterns` and `compound_risks` must be empty arrays. `intelligence_gaps` must include the data maturity gap.
- `"adequate"`: 5–9 runs with attribution. All sections populated.
- `"strong"`: 10+ runs with attribution. Full analysis.

**Agent persona rules (inherit from pipeline):**
- Zero technical jargon. No CVEs, IPs, hashes, MITRE references.
- Frame all risk in terms of impact on turbine production and service delivery continuity.
- Unknown actors must appear in `threat_actors[]` with `name: null` and an `intelligence_gaps` entry — do not omit them.
- Do not fabricate patterns not evidenced in the data files.

**Stop hook:** `.claude/hooks/validators/threat-landscape-auditor.py`
- Validates required fields present
- Confirms `adversary_patterns` and `compound_risks` are empty arrays when `data_sufficiency = "limited"`
- Checks no MITRE/CVE/TTP jargon in any text field
- Checks `quarterly_brief` has all 6 subfields non-empty when `data_sufficiency ≠ "limited"`

**New API endpoint:** `GET /api/threat-landscape` → reads and serves `output/pipeline/threat_landscape.json`. Returns `{"status": "no_data"}` if file absent.

---

## 3. History Tab Redesign (UI only)

**Files:** `static/index.html`, `static/app.js`

### 3a. Layout

Single scrollable view. No sub-tabs.

**Structure top-to-bottom:**
1. Summary bar (full-width, `background: #080c10`, `border-bottom: 1px solid #21262d`)
2. Escalation matrix (hero)
3. Run strip (expands on cell click, defaults to latest run)
4. Run log (compact, below matrix)

Audit trace removed from this tab — relocated to Validate tab (see Section 5).

### 3b. Summary bar

Single flex row. Content:
- `N runs · [from date] – [to date]`
- `· N persistently escalated` (colour: `#ff7b72`)
- `· N improving` (colour: `#3fb950`) — only shown if count > 0
- `· N stable clear` (colour: `#3fb950`) — only shown if count > 0

"Persistently escalated" = escalated in >50% of runs.

### 3c. Escalation matrix

Grid: `grid-template-columns: 164px repeat(N, 1fr)` where N = run count.

**Column headers:**
- Font-size: 8px, colour: `#6e7681`
- Format: abbreviated date (`Mar 9`)
- Same-day disambiguation: append `a`, `b` suffix (`Mar 9a`, `Mar 9b`)
- Latest run column: colour `#8b949e`, font-weight 600

**Row labels (164px column):**
- Line 1: region name (status colour, font-weight 600, font-size 10px) + drift annotation (8px, `#e3b341` if active drift, else `#6e7681`)
- Line 2: VaCR trend arrow + latest figure + escalation ratio (8px, `#6e7681`)
- Drift annotation format: `System Intrusion ×5 →` (shows when same scenario repeats ≥2 consecutive runs)

**Cell spec:**
- Height: 20px minimum
- Border-radius: 2px
- Cursor: pointer
- `title` attribute: `[date] · [severity] · [scenario] · [VaCR]` (native tooltip — acceptable for this density)

**Cell colour map:**
| State | Colour | Opacity |
|-------|--------|---------|
| CRITICAL | `#ff7b72` | 0.95 |
| HIGH | `#ff7b72` | 0.85 |
| MEDIUM | `#ffa657` | 0.80 |
| LOW | `#e3b341` | 0.75 |
| MONITOR | `#79c0ff` | 0.55 |
| CLEAR | `#1a2a1a` bg + `#21262d` border | — |
| No data | `#21262d` | — |
| Latest run | add `border: 1px solid #58a6ff` | — |

**Legend:** Horizontal flex row below the matrix, `border-top: 1px solid #21262d`, `padding-top: 8px`. Shows all 7 states with colour swatch + label.

### 3d. Run strip

Appears immediately below the matrix. **Defaults to latest run on load** — does not require a click to populate.

Label row: `[DATE] — [WINDOW] (latest run · click any cell to inspect)`

Content: 5 inline items — `[REGION_COLOUR][REGION] [scenario · VaCR]` or `[REGION_COLOUR][REGION] clear/monitor`

On cell click: strip updates to show data for the clicked run's column.

### 3e. Run log

**Dot legend above the list** (not below): inline flex row labelled `dots:` with coloured region name labels in order APAC · NCE · MED · LATAM · AME.

Row layout: `grid-template-columns: 1fr auto`
- Left: `[date] · [window]` — colour fades for older runs (`#e6edf3` → `#8b949e` → `#484f58`)
- Right: 5 dots, one per region, coloured by that run's severity status. Dot size: 7px circle.

Show 3 most recent rows visible by default. Scrollable to full history.

Footer: `N runs total · showing 3 most recent`

---

## 4. Trends Tab Redesign

**Files:** `static/index.html`, `static/app.js`
**API:** `GET /api/trends` (existing, `trend_analysis.json`) + `GET /api/threat-landscape` (new)

Both endpoints fetched in parallel on tab load.

### 4a. Layout

Single scrollable view. Section order (information hierarchy):

1. Header bar
2. **Cross-Regional Compound Risks** ← headline finding, always first
3. Threat Actors
4. Scenario Persistence
5. Intelligence Gaps
6. Board Talking Points

The escalation heatmap is **removed from Trends** — it is now exclusively in the History tab. Duplication eliminated.

### 4b. Header bar

Flex row, `background: #080c10`, `border-bottom: 1px solid #21262d`.

- Left: `N runs · [from] – [to] · [window]`
- Conditional amber badge (when `data_sufficiency = "limited"`): `background: #2d2208; border: 1px solid #d29922; color: #d29922` — text: `Limited data — N/M runs with full attribution`
- Right: `Last generated: [date, time]` (8px, `#6e7681`) + `↻ Generate Quarterly Brief` button (green style)

**"Generate Quarterly Brief" button:**
- Triggers `POST /api/run-threat-landscape` (new endpoint, runs `threat-landscape-agent` on demand)
- While running: button shows `↻ Generating...`, disabled
- On complete: `last generated` timestamp updates
- "Not yet generated" shown if `threat_landscape.json` absent

### 4c. Cross-Regional Compound Risks

**Section header:** `CROSS-REGIONAL COMPOUND RISKS` (uppercase label + `border-bottom: 1px solid #21262d`)

Each compound risk:
- `border-left: 3px solid #ff7b72`
- `background: #160808`
- `border-radius: 0 4px 4px 0`
- Meta line (8px): `[RISK_LEVEL] · [REGIONS joined with +] · [N] corroborating runs`
- Body (10px, `#e6edf3`, `line-height: 1.6`): narrative text

When `data_sufficiency = "limited"`: render single muted card — `"Insufficient data to identify compound risks — analysis available after 5+ runs with attribution data."`

### 4d. Threat Actors

Table. `border: 1px solid #21262d; border-radius: 4px; overflow: hidden`.

**Columns:** `grid-template-columns: 130px 1fr 80px 80px 50px`
- Actor | Objective | Regions | Activity | Conf.

**Header row:** `background: #161b22`, 8px, `#484f58`, uppercase.

**Known actor row:** standard colours — name `#e6edf3` bold, objective `#c9d1d9`, regions `#8b949e`, trend colour-coded (`#ff7b72` escalating / `#3fb950` declining / `#6e7681` stable or unknown), confidence `#6e7681`.

**Unknown/unattributed actor row:** `background: #0d1117; opacity: 0.7` — name `#6e7681` italic, objective `#6e7681` italic pointing to Intelligence Gaps section.

When `data_sufficiency = "limited"`: show single row with dim italic text — `"Attribution data accumulating — table will populate after 5+ runs."`

### 4e. Scenario Persistence

For each scenario in `scenario_lifecycle[]`:

**Row layout:**
- Line 1 (flex, align-items center): `[STAGE_PILL]` `[scenario name]` `[run_count/total · regions]` (right-aligned, 8px, `#6e7681`)
- Line 2: progress bar (`background: #21262d; height: 5px; border-radius: 2px`) — fill width = `run_count / total_runs * 100%`

**Stage pill:**
- PERSISTENT: `background: #2d0a0a; border: 1px solid [scenario_colour]; color: [scenario_colour]; font-size: 7px; padding: 1px 5px; border-radius: 8px; text-transform: uppercase`
- EMERGING: amber palette (`#2d2208 / #d29922`)
- DECLINING: muted grey (`#161b22 / #6e7681`)

Scenario colour = severity of the scenario's latest occurrence (uses same colour map as matrix cells).

### 4f. Intelligence Gaps

`border: 1px solid #30363d; border-radius: 4px; overflow: hidden`.

Each gap row (flex, `gap: 12px`):
- Left: region badge — `background: #2d2208; border: 1px solid #d29922; color: #d29922` for actionable gaps; `background: #161b22; border: 1px solid #30363d; color: #6e7681` for data maturity gaps
- Right: description (9px, `#c9d1d9`) + impact line (8px, `#6e7681`)

**No pipeline filenames in any gap description.** Refer to "attribution data" not "sections.json".

### 4g. Board Talking Points

**Section header:** `BOARD TALKING POINTS`

Each talking point:
- `border: 1px solid [accent]; border-left: 3px solid [accent]; padding: 8px 12px; border-radius: 0 4px 4px 0`
- Accent determined by type: risk/escalation → `#1f6feb / #58a6ff` (blue), positive → `#238636 / #3fb950` (green)
- Type label (8px, accent colour, uppercase, `letter-spacing: 0.06em`) above text body
- Body (10px, `#c9d1d9`, `line-height: 1.6`)

Type labels come from `threat_landscape.json → board_talking_points[].type` — set explicitly by the agent, not derived by the frontend. Valid values: `SUSTAINED EXPOSURE`, `PERSISTENT PATTERN`, `COMPOUND RISK`, `POSITIVE SIGNAL`.

---

## 5. Validate Tab — Audit Trace Relocation

**Audit trace moved from History tab → Validate tab.**

In `#tab-validate` (or equivalent), add a collapsible section at the bottom:

```
border-top: 1px solid #21262d
padding-top: 14px
```

Header row: `AUDIT TRACE` label (uppercase, `#6e7681`) + toggle button (`▾ / ▸`)

On expand: `<pre id="audit-trace">` — same styles as current implementation (`background: #0d1117; border: 1px solid #21262d; font-size: 10px; color: #6e7681; overflow-x: auto; white-space: pre-wrap`).

Data source: `GET /api/trace` — unchanged.

Remove from History tab entirely.

---

## 6. New API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/threat-landscape` | GET | Serves `output/pipeline/threat_landscape.json`. Returns `{"status":"no_data"}` if absent. |
| `POST /api/run-threat-landscape` | POST | Triggers `threat-landscape-agent` on demand. Returns `{"status":"running"}` immediately, or `{"status":"already_running"}` if a run is in progress. Agent writes output when done. |

---

## 7. Implementation Notes

- `trend_analysis.json` and `threat_landscape.json` are separate files. The Trends tab fetches both in parallel — they are NOT merged. `trend_analysis.json` supplies `scenario_lifecycle` data only (via its `scenario_frequency` and `severity_trajectory` fields). Board talking points come exclusively from `threat_landscape.json → board_talking_points[]` — the existing `ciso_talking_points` strings in `trend_analysis.json` are not displayed in the redesigned UI.
- The `threat-landscape-agent` uses the same DISLER protocol as all other agents: zero preamble, filesystem as state, atomic JSON write.
- The `data_sufficiency` field gates the UI rendering — the frontend must check this field before rendering threat actors table, compound risks, and adversary patterns. Do not show empty tables.
- `GET /api/threat-landscape` is a new server endpoint in `server.py` — reads and serves the JSON file, same pattern as existing output endpoints.
- `POST /api/run-threat-landscape` runs the agent via `subprocess` (same pattern as existing run triggers) — non-blocking, returns immediately.
- The History matrix is rendered purely from `GET /api/history` data — no new endpoints needed.
- Escalation heatmap CSS classes (`.heatmap-grid`, `.heatmap-row`, `.heatmap-label`) remain in `index.html` for History tab use. They are removed from the Trends tab render function only.

---

## 8. Out of Scope

- CISO Quarterly Brief as Audience Hub card — deferred to next spec (requires this spec to ship first as prerequisite)
- Trends and History tab redesign of the run-crq pipeline scheduling — no changes to pipeline timing
- Adversary patterns UI section — omitted from v1 UI (data will be in JSON but not surfaced until data sufficiency is adequate; placeholder not needed)
- Trends/History mobile responsiveness — app is desktop-only
- Any changes to Config, Validate, or Sources tab beyond the audit trace relocation

---

## 9. Validation Checklist

- [ ] `threat_actor` field present in `data.json` output from `regional-analyst-agent`
- [ ] `threat-landscape-agent` writes valid `threat_landscape.json` on pipeline run
- [ ] Threat landscape auditor stop hook passes without error
- [ ] `GET /api/threat-landscape` returns correct JSON
- [ ] `POST /api/run-threat-landscape` triggers agent and returns `{"status":"running"}`
- [ ] History tab: matrix renders with correct colours for MONITOR (blue), CLEAR (dark green), no-data (dark), latest run (blue outline)
- [ ] History tab: run strip defaults to latest run on tab load
- [ ] History tab: clicking a matrix cell updates the run strip
- [ ] History tab: dot legend appears above run log list
- [ ] History tab: no audit trace present
- [ ] Trends tab: compound risks render first (below header)
- [ ] Trends tab: heatmap absent
- [ ] Trends tab: stage pills left-aligned on scenario persistence bars
- [ ] Trends tab: data_sufficiency "limited" → threat actors and compound risks show empty-state messages, not empty tables
- [ ] Trends tab: board talking points have type labels
- [ ] Trends tab: "Generate Quarterly Brief" button shows last-generated timestamp
- [ ] Validate tab: audit trace present and collapsible
- [ ] No JS errors across all tabs
- [ ] No regression in Config, Sources, or existing Validate content
