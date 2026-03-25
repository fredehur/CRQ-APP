# Phase N Blueprint — Trends, Review Gate, Audience Cards

## Mission

Add longitudinal trend intelligence, analyst review workflow, and audience-specific card generation to the CRQ platform. These four capabilities close the gap between "pipeline produces a report" and "the whole org consumes actionable intelligence tailored to their role." The Trends Synthesis Agent gives the CISO historical context; the Review Gate gives analysts editorial control; Audience Cards give Sales, Ops, and Executives distilled framings they can act on immediately.

## Stack

- **Backend**: Python 3 + FastAPI (existing `server.py`), `uv` package manager
- **Sub-agent**: Sonnet model via `.claude/agents/` (trends synthesis only)
- **LLM tool**: Haiku via `anthropic` Python SDK (audience card generation)
- **Validator**: Python stop-hook script following `json-auditor.py` pattern
- **Frontend**: Vanilla JS (`static/app.js`), inline SVG charts, existing Tailwind CSS CDN + custom classes from `static/index.html`
- **No new frameworks, no new JS libraries, no new Python packages** (anthropic SDK already available via existing Haiku usage patterns in `deep_research.py`)

## Deliverables

### New Files

| Path | Description |
|---|---|
| `.claude/agents/trends-synthesis-agent.md` | Sonnet sub-agent — reads archived data, writes `trend_analysis.json` |
| `.claude/hooks/validators/trend-analysis-auditor.py` | JSON schema validator for `trend_analysis.json` (stop hook) |
| `tools/generate_audience_cards.py` | Haiku tool — reads `report.md` + `data.json`, writes `audience_cards.json` |
| `output/trend_analysis.json` | Longitudinal trend synthesis (written by agent each run) |
| `output/regional/{region}/review_status.json` | Review gate state per region (written by PUT endpoint) |
| `output/regional/{region}/audience_cards.json` | Three audience framings per escalated region |

### Modified Files

| Path | What Changes |
|---|---|
| `server.py` | Add 4 endpoints: `GET /api/trends`, `GET /api/review/{region}`, `PUT /api/review/{region}`, `GET /api/audience/{region}` |
| `static/index.html` | Add "Trends" nav tab + `<div id="tab-trends">` container; add audience cards panel markup in overview tab; CSS for new components |
| `static/app.js` | Add `renderTrends()`, update `_doSwitchTab` for trends tab, add review badge/button to right panel, add audience cards rendering |
| `.claude/commands/run-crq.md` | Add Phase 2.5 — delegate to `trends-synthesis-agent` after `trend_analyzer.py` |

## Output Schemas

### `output/trend_analysis.json`

```json
{
  "generated_at": "2026-03-24T10:00:00Z",
  "run_count": 7,
  "regions": {
    "APAC": {
      "severity_trajectory": ["HIGH","HIGH","HIGH","HIGH","HIGH","HIGH","HIGH"],
      "scenario_frequency": {"System intrusion": 7},
      "escalation_count": 7,
      "escalation_rate": 1.0,
      "dominant_pillar_history": ["Geopolitical","Geopolitical","Cyber","Geopolitical","Geopolitical"],
      "velocity_trend": "stable",
      "assessment": "APAC has been escalated in all 7 runs with system intrusion as the persistent scenario."
    }
  },
  "cross_regional": {
    "patterns": ["AME and APAC both show persistent escalation across all runs."],
    "compound_risk": "Two regions maintain continuous escalation posture."
  },
  "ciso_talking_points": [
    "AME ransomware exposure ($22M VaCR) has been flagged in every run since March 9.",
    "No region has improved from escalated to clear in the observation window.",
    "MED insider misuse scenario is the lowest-severity escalation but shows no signs of resolution."
  ]
}
```

### `output/regional/{region}/review_status.json`

```json
{
  "reviewer": "analyst@aerogrid.com",
  "timestamp": "2026-03-24T10:30:00Z",
  "status": "published",
  "notes": "Confirmed with regional ops lead. Assessment accurate."
}
```

### `output/regional/{region}/audience_cards.json`

```json
{
  "generated_at": "2026-03-24T10:31:00Z",
  "region": "AME",
  "cards": {
    "sales": {
      "title": "Sales Talking Points",
      "bullets": [
        "Active ransomware threat targeting North American energy infrastructure.",
        "Customer conversations should acknowledge sector-wide risk posture.",
        "No direct impact on delivery timelines at this time."
      ]
    },
    "ops": {
      "title": "Operations Signal",
      "signal": "Ransomware campaigns targeting OT/SCADA in energy sector.",
      "action": "Verify backup integrity for turbine maintenance scheduling systems."
    },
    "executive": {
      "title": "Executive Summary",
      "vacr_exposure": 22000000,
      "scenario": "Ransomware",
      "financial_rank": 1,
      "assessment": "Highest financial exposure scenario at $22M VaCR. AME has been escalated in every pipeline run."
    }
  }
}
```

## Acceptance Criteria

| ID | Criterion | Checkable |
|---|---|---|
| AC-1 | `output/trend_analysis.json` exists after `/run-crq`, parses as valid JSON | `python -c "import json; json.load(open('output/trend_analysis.json'))"` |
| AC-2 | `trend-analysis-auditor.py` validates schema (required keys: `regions`, `ciso_talking_points`, `cross_regional`) | `uv run python .claude/hooks/validators/trend-analysis-auditor.py output/trend_analysis.json trends` exits 0 |
| AC-3 | `GET /api/trends` returns 200 with JSON body containing `regions` key | curl check |
| AC-4 | Trends tab renders severity line chart SVG, scenario frequency bars, escalation heatmap, CISO cards | Manual visual check |
| AC-5 | `PUT /api/review/{region}` with `{"reviewer":"x","status":"published"}` creates `review_status.json` and triggers audience card generation | curl check + file existence |
| AC-6 | `GET /api/review/{region}` returns current review status or `{"status":"draft"}` default | curl check |
| AC-7 | `GET /api/audience/{region}` returns audience cards JSON or empty object | curl check |
| AC-8 | Overview tab shows "DRAFT"/"PUBLISHED" badge on escalated region cards | Manual visual check |
| AC-9 | Overview tab shows audience cards panel when region is escalated + published | Manual visual check |
| AC-10 | `run-crq.md` Phase 2.5 wires trends-synthesis-agent after trend_analyzer.py | `grep "trends-synthesis-agent" .claude/commands/run-crq.md` |
| AC-11 | No new Python packages added to `pyproject.toml` | Diff check |
| AC-12 | No new JS frameworks/libraries added to `index.html` | Diff check |

## Constraints

1. **No new JS frameworks or chart libraries.** SVG charts must be hand-drawn inline (polyline for severity trajectory, rect for bars, rect grid for heatmap). Follow existing `renderHistory` sparkline pattern in `app.js`.
2. **No new Python packages.** Use `anthropic` SDK already available. Use stdlib `json`, `os`, `sys`, `pathlib` for tools.
3. **Follow existing tab CSS pattern.** New Trends tab uses `.nav-tab` class, `#tab-trends` div, same padding/overflow pattern as `#tab-history`.
4. **Follow existing agent frontmatter pattern.** Only valid keys: `name`, `description`, `tools`, `model`, `hooks`.
5. **Follow existing validator pattern.** `trend-analysis-auditor.py` uses same circuit-breaker retry file pattern as `json-auditor.py`. Returns `sys.exit(0)` on pass, `sys.exit(2)` on fail.
6. **Non-blocking review gate.** Briefs are visible immediately after pipeline. Review gate adds badge + publish action. No pipeline changes for review.
7. **Audience cards generated on publish only.** The PUT `/api/review/{region}` endpoint calls `generate_audience_cards.py` as a subprocess when `status == "published"`.
8. **Jargon-free.** Audience cards must follow the same geopolitical analyst persona. No CVEs, no SOC language, no technical jargon.
9. **Atomic writes.** All JSON writes use tmp-file + `os.replace()` pattern per existing codebase convention.

## Context Files

### Builder-A (Backend: Agent + Tools + Endpoints)

| File | Why |
|---|---|
| `.claude/agents/global-builder-agent.md` | Agent frontmatter + prompt pattern to replicate |
| `.claude/hooks/validators/json-auditor.py` | Validator pattern to replicate |
| `tools/trend_analyzer.py` | Reads same archived data; understand output shape |
| `tools/build_history.py` | Reads same `output/runs/*/regional/*/data.json`; understand traversal |
| `output/history.json` | Understand existing longitudinal data shape |
| `server.py` | Add 4 new endpoints; follow existing patterns |
| `.claude/commands/run-crq.md` | Wire Phase 2.5 after Phase 2 |
| `data/company_profile.json` | Audience cards need company context for Haiku prompt |
| `CLAUDE.md` | Geopolitical persona rules, jargon constraints |

### Builder-B (Frontend: Trends Tab + Review UI + Audience Cards UI)

| File | Why |
|---|---|
| `static/index.html` | Add nav tab, tab container, audience cards panel, CSS |
| `static/app.js` | Add `renderTrends()`, review badge, audience cards render, update `_doSwitchTab` |
| `output/history.json` | Understand data shape for charts |
| `server.py` (read-only) | Know the endpoint contracts to call |
| `CLAUDE.md` | UI conventions, color scheme, CSS class patterns |

## Task Breakdown

### N-1: Trends Synthesis Agent + Validator
- **Owner**: Builder-A
- **Input**: `.claude/agents/global-builder-agent.md`, `.claude/hooks/validators/json-auditor.py`, `output/history.json`
- **Output**: `.claude/agents/trends-synthesis-agent.md`, `.claude/hooks/validators/trend-analysis-auditor.py`
- **Blocked-by**: None
- **Criteria**: Agent frontmatter valid. Auditor validates required keys (`regions`, `ciso_talking_points`, `cross_regional`, `generated_at`, `run_count`) and region sub-keys. Circuit-breaker pattern present.

### N-2: Wire Phase 2.5 into run-crq.md
- **Owner**: Builder-A
- **Input**: `.claude/commands/run-crq.md`
- **Output**: `.claude/commands/run-crq.md` (modified)
- **Blocked-by**: N-1
- **Criteria**: New "PHASE 2.5 — TREND SYNTHESIS" section after Phase 2. Delegates to `trends-synthesis-agent`. Passes `output/trend_brief.json` path. Logs `PHASE_COMPLETE`.

### N-3: Backend Endpoints
- **Owner**: Builder-A
- **Input**: `server.py`
- **Output**: `server.py` (modified)
- **Blocked-by**: None (parallel with N-1)
- **Criteria**: All 4 endpoints present. PUT `/api/review/{region}` spawns `generate_audience_cards.py` as subprocess on publish. Atomic write. Region validation. Returns correct defaults when files absent.

### N-4: Audience Card Generator Tool
- **Owner**: Builder-A
- **Input**: `data/company_profile.json`, `CLAUDE.md`
- **Output**: `tools/generate_audience_cards.py`
- **Blocked-by**: None (parallel with N-1 and N-3)
- **Criteria**: CLI `uv run python tools/generate_audience_cards.py {REGION}`. Reads `report.md` + `data.json`. Calls Haiku. `--mock` flag for testing. Atomic write. Jargon-free output. Exits 0/1.

### N-5: Trends Tab HTML Structure
- **Owner**: Builder-B
- **Input**: `static/index.html`
- **Output**: `static/index.html` (modified)
- **Blocked-by**: None
- **Criteria**: `.nav-tab` with `id="nav-trends"` between History and Config. `<div id="tab-trends">` with correct styling. CSS for `.trend-card`, `.talking-point-card`, `.heatmap-grid`, `.review-draft`, `.review-published`. No new external scripts.

### N-6: Trends Tab JavaScript
- **Owner**: Builder-B
- **Input**: `static/app.js`, trend_analysis.json schema (this blueprint)
- **Output**: `static/app.js` (modified)
- **Blocked-by**: N-5
- **Criteria**: `renderTrends()` fetches `/api/trends`. Renders severity trajectory (SVG polyline), scenario frequency (SVG bars), escalation heatmap (SVG rect grid), CISO talking-point cards. `_doSwitchTab` updated for 'trends'. Graceful no-data state.

### N-7: Review Badge + Publish Button
- **Owner**: Builder-B
- **Input**: `static/app.js`, `static/index.html`
- **Output**: `static/app.js` (modified), `static/index.html` (modified — CSS only)
- **Blocked-by**: N-6
- **Criteria**: Escalated region right panel shows DRAFT/PUBLISHED badge. Publish button calls PUT `/api/review/{region}`. On success refreshes badge and triggers audience cards fetch. Badge uses `.review-draft` / `.review-published` classes.

### N-8: Audience Cards Panel
- **Owner**: Builder-B
- **Input**: `static/app.js`, `static/index.html`
- **Output**: `static/app.js` (modified), `static/index.html` (modified — CSS only)
- **Blocked-by**: N-7
- **Criteria**: Published escalated region shows collapsible Audience Cards section. Three sub-cards (Sales bullets, Ops signal+action, Executive VaCR). Fetched from `/api/audience/{region}`. Empty state message when not published.

## Dependency Graph

```
N-1 (Agent+Validator)   N-3 (Endpoints)   N-4 (Audience Tool)   N-5 (HTML)
        |                                                              |
        v                                                              v
N-2 (Pipeline wire)                                             N-6 (Trends JS)
                                                                       |
                                                                       v
                                                                N-7 (Review UI)
                                                                       |
                                                                       v
                                                                N-8 (Audience UI)
```

**Parallel opportunities:**
- Builder-A: N-1 + N-3 + N-4 all start simultaneously
- Builder-B: N-5 starts simultaneously with all Builder-A tasks
- N-2 unblocks after N-1; N-6→N-7→N-8 sequential (same files)

**Cross-builder dependency:** None. Builder-B works from schema in this blueprint.

## Execution Order

| Phase | Builder-A | Builder-B |
|---|---|---|
| 1 (parallel) | N-1 + N-3 + N-4 | N-5 |
| 2 | N-2 | N-6 |
| 3 | done | N-7 |
| 4 | done | N-8 |
