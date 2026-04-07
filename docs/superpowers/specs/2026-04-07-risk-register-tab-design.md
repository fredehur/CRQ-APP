# Risk Register Tab — Design Spec (IN PROGRESS)

> Status: COMPLETE — both sections approved. Ready for implementation planning.

## What We're Building

Two features unified under a renamed "Risk Register" tab (currently "Validate"):

1. **CRQ Database Editor** — inline CRUD for both regional scenarios (`mock_crq_database.json`) and master scenario types (`master_scenarios.json`)
2. **VaCR Intelligence Pipeline** — per-scenario agent that searches industry sources, finds evidence that the VaCR should move up or down, and presents findings with source + quote + direction + assessment (no automatic changes)

## Decisions Locked

- **Tab rename:** "Validate" → "Risk Register"
- **Approach:** A (lightweight — inline row expand, direct JSON file writes, no new DB)
- **Edit UX:** Inline expand — click row, fields open below, Save/Cancel
- **Intelligence pipeline output:** Agent presents signal + direction + source evidence. No automatic VaCR changes. User decides.
- **Scope:** Edit BOTH regional scenarios (company-specific VaCR per region) AND master scenario types (industry incident types)

## Section 1: Tab Structure & CRQ Database Editor (PRESENTED — pending approval)

### Tab Layout (top to bottom)

1. **Regional Scenarios panel** — 5-row table (one per region)
   - Columns: Region · Scenario Name · Department · Critical Assets · VaCR (USD)
   - Click row → inline expand: editable fields + Save/Cancel
   - Editable fields: scenario_name (text), department (text), critical_assets (comma-separated textarea → saved as array), value_at_cyber_risk_usd (number), region (select: APAC/AME/LATAM/MED/NCE)
   - Add row button for new regional scenario. Delete button on expanded row.
   - Critical assets: tag chips in view, comma-separated textarea in edit

2. **Master Scenarios panel** — 9-row table (incident types)
   - Columns: Incident Type · Freq Rank · Financial Rank · Event Freq % · Financial Impact %
   - Same inline expand pattern. Add/delete rows.

3. *(existing)* Scenario Validation / Registered Sources / Candidates / Audit Trace — unchanged, below a divider

**Pipeline integration note:** Edits to `mock_crq_database.json` are picked up automatically on the next `/run-crq` — no additional wiring needed. The pipeline reads the file directly in Phase 1.

### API Endpoints (new)

| Method | Path | Action |
|--------|------|--------|
| GET | `/api/risk-register/regional` | Returns `mock_crq_database.json` |
| PUT | `/api/risk-register/regional/{scenario_id}` | Update one regional scenario (keyed by scenario_id e.g. APAC-001) |
| POST | `/api/risk-register/regional` | Add new regional scenario (auto-generates scenario_id) |
| DELETE | `/api/risk-register/regional/{scenario_id}` | Remove a regional scenario |
| GET | `/api/risk-register/master` | Returns `master_scenarios.json` scenarios array |
| PUT | `/api/risk-register/master/{incident_type}` | Update one master scenario |
| POST | `/api/risk-register/master` | Add new master scenario |
| DELETE | `/api/risk-register/master/{incident_type}` | Remove a master scenario |

## Section 2: VaCR Intelligence Pipeline (APPROVED)

### `tools/vacr_researcher.py` (new)

Per-scenario research function:

1. **Input:** `incident_type`, `current_vacr_usd`, `sector` (energy/manufacturing)
2. **Search:** Web search `"{incident_type} cost {sector} 2024 2025"` against registered benchmark sources (Claroty, IBM CBR, Verizon DBIR, ENISA, Mandiant M-Trends, Marsh)
3. **Extract:** Haiku extracts cost figures from results — reuses `benchmark_extractor.py` extraction prompt
4. **Reason:** Sonnet compares evidence against current VaCR — direction + one-sentence assessment per source
5. **Output per scenario:**
   ```json
   {
     "incident_type": "Ransomware",
     "current_vacr_usd": 22000000,
     "direction": "↑|↓|→|?",
     "findings": [
       {
         "source": "IBM Cost of a Data Breach 2024",
         "quote": "Average ransomware cost in manufacturing: $4.73M",
         "figure_usd": 4730000,
         "direction": "↓",
         "assessment": "IBM CBR median is 4.6x below current VaCR — may be elevated for this sector"
       }
     ],
     "agent_summary": "Two of three sources suggest current VaCR is above industry median for manufacturing ransomware."
   }
   ```

### Storage

`output/pipeline/vacr_research.json` — archived per run automatically by `archive_run.py`.

### Server Endpoints (new)

| Method | Path | Action |
|--------|------|--------|
| POST | `/api/risk-register/research` | Trigger research for all 9 scenarios in parallel |
| GET | `/api/risk-register/research/stream` | SSE stream — emits one event per scenario as it completes |
| GET | `/api/risk-register/research` | Returns latest `vacr_research.json` |

**Parallelism:** `asyncio.gather()` — all 9 scenarios fire simultaneously (~30–45 sec total).

### UI

- "RUN RESEARCH" button next to "RUN VALIDATION" in the Risk Register tab header
- Progress line shows: `Researching: Ransomware... [3/9 complete]`
- Each scenario row in verdicts table gets an expand arrow once research is available
- Expanded row shows findings list: source badge · quoted figure · direction arrow (↑/↓/→) · agent assessment sentence
- Run All only in v1 — no per-scenario trigger

## Data Sources

- `data/mock_crq_database.json` — regional scenarios (region-keyed, one scenario per region)
- `data/master_scenarios.json` — master scenario types with frequency/financial stats
- `data/validation_sources.json` — registered benchmark sources
- `output/validation/flags.json` — current validation results (verdicts table)

## Existing Infrastructure to Reuse

- `tools/research_collector.py` — LLM-driven web search loop pattern
- `tools/benchmark_extractor.py` — Haiku extraction prompt (good prompt, wrong input — hits HTML listing pages instead of actual reports)
- `tools/source_harvester.py` — fetches and caches source content
- `_run_validation()` in `server.py` — SSE progress pattern for long-running runs
