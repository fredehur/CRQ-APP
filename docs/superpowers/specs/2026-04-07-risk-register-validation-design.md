# Risk Register Validation — Design Spec

**Date:** 2026-04-07
**Status:** Approved
**Scope:** Multi-register support + VaCR source validation pipeline

---

## Overview

The CRQ pipeline currently runs against a single fixed company profile and VaCR dataset (AeroGrid Enterprise). This feature adds:

1. **Multi-register support** — multiple named risk registers, each representing a different business context (e.g., full enterprise vs. wind power plant only), UI-managed
2. **Register validation pipeline** — a dedicated `/validate-register` command that hunts for quantitative sources (monetary figures + probability percentages) and maps them to each scenario's VaCR figures, producing a per-scenario verdict

The geopolitical intelligence pipeline is **untouched**. Register validation is a separate pipeline with a separate agent and separate output.

---

## Data Model

### Register file — `data/registers/{register_id}.json`

```json
{
  "register_id": "wind_power_plant",
  "display_name": "Wind Power Plant",
  "company_context": "Wind power plant operator. No manufacturing. Primary assets: turbines, grid connections, OT/SCADA control systems.",
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
    }
  ]
}
```

**Field notes:**
- `search_tags` — LLM-generated from scenario name + description. Drive the validator's source search. User can edit/add.
- `figure_source` / `probability_source` — dropdown: `internal_estimate`, `industry_report`, `actuarial_model`, `broker_quote`. Tells the validator what counts as genuinely new evidence (e.g., if source is already `industry_report`, finding another one of the same type has lower incremental value).
- `last_validated_at` — updated each time `/validate-register` completes. Used by UI to show staleness.

### Active register pointer — `data/active_register.json`

```json
{ "register_id": "wind_power_plant" }
```

Single-field file. Read by the pipeline at runtime. Set via app UI. The existing `mock_crq_database.json` is **not migrated** — it remains the mock VaCR for the intelligence pipeline. Registers are a parallel, independent data structure.

---

## Validation Pipeline

### Command: `/validate-register`

Orchestrator-owned. Runs against the active register.

**Sequence:**

```
1. Load data/active_register.json → get register_id
2. Load data/registers/{register_id}.json → scenarios + search_tags
3. For each scenario (parallel):
   a. Query sources.db WHERE tags overlap search_tags AND has_quantitative_data = TRUE
      → existing_sources with figures
   b. Fresh web research targeting quantitative sources only
      → filter: must contain USD figure OR probability percentage
      → discard narrative-only sources silently
      → new_source candidates
4. register-validator-agent
   → reads both result sets per scenario
   → computes benchmark_range per dimension
   → produces verdict + improvement candidates
5. Write output/validation/register_validation.json
6. Update last_validated_at on the register file
```

**Source filter rule (strict):** A source that contains no dollar figure and no probability percentage does not exist. Narrative-only sources are silently dropped at collection time, not flagged.

### Agent: `register-validator-agent`

- Model: `sonnet`
- Tools: `Read`, `Write`
- Input: per-scenario result sets (existing + new sources)
- Output: `output/validation/register_validation.json`
- Stop hook: schema validator on output JSON

**Verdict logic per dimension:**
- `supports` — benchmark range contains or overlaps the VaCR figure (within 25%)
- `challenges` — benchmark range differs by >25% from VaCR figure
- `insufficient` — fewer than 2 quantitative sources found

---

## Output Format

### `output/validation/register_validation.json`

```json
{
  "register_id": "wind_power_plant",
  "validated_at": "2026-04-07T14:02:00Z",
  "scenarios": [
    {
      "scenario_id": "WP-001",
      "scenario_name": "Wind Farm OT Ransomware",
      "financial": {
        "vacr_figure_usd": 8000000,
        "verdict": "challenges",
        "benchmark_range_usd": [12000000, 18000000],
        "existing_sources": [
          {
            "name": "IBM Cost of a Data Breach 2024",
            "figure_usd": 14500000,
            "figure_type": "sector_average",
            "sector": "energy",
            "url": "https://..."
          }
        ],
        "new_sources": [
          {
            "name": "Dragos Year in Review 2023",
            "figure_usd": 17200000,
            "figure_type": "ot_incident_median",
            "sector": "energy_ot",
            "url": "https://...",
            "improvement_note": "OT-specific figure — more precise than general energy sector average"
          }
        ],
        "recommendation": "Figure is below all 3 benchmarks. OT-specific data (Dragos) suggests $17.2M. Consider revising upward."
      },
      "probability": {
        "vacr_probability_pct": 12.0,
        "verdict": "supports",
        "benchmark_range_pct": [10.5, 14.2],
        "existing_sources": [...],
        "new_sources": [],
        "recommendation": "Figure is within benchmark range across 2 sources. No revision indicated."
      }
    }
  ]
}
```

**Key distinction:** `existing_sources` = already in `sources.db`. `new_sources` = discovered in this run, not yet in registry. New sources are improvement candidates.

---

## Database Changes

`sources.db` — two new columns on `sources_registry`:

| Column | Type | Description |
|---|---|---|
| `has_quantitative_data` | `BOOLEAN DEFAULT FALSE` | True if source contains a USD figure or probability % |
| `quantitative_figure` | `TEXT` | The extracted figure(s), e.g. `"$14.5M sector average"` |
| `source_tags` | `TEXT` | JSON array of tags, e.g. `["ransomware","energy_operator"]`. Populated at upsert time. |

Step 3a queries: `WHERE has_quantitative_data = TRUE AND source_tags` overlaps scenario `search_tags` (JSON intersection in SQLite). `source_tags` is populated by `update_source_registry.py` using the same LLM tag-suggestion endpoint used in the register form.

---

## UI

### Persistent register bar

Slim bar below the main nav, always visible:

```
▣  Active: Wind Power Plant  ·  Switch Register ▾
```

Clicking "Switch Register" opens a compact drawer.

### Register drawer (compact list)

- Header: "RISK REGISTERS" label + "+ New" button
- Active register highlighted with ACTIVE badge, scenario count, last validated date
- Other registers: name, scenario count, validation status, "Set Active" button
- Footer: "+ Add register" link

### Validation results (Source Audit tab)

Per-scenario layout with two expandable rows each:

- **Header row:** scenario name + verdict badges ($ CHALLENGES · % SUPPORTS)
- **Financial row:** VaCR figure → benchmark range → verdict pill → source count. Click to expand.
- **Probability row:** same pattern.
- **Expanded state:** source list — existing sources in default style, new sources highlighted in purple with ★ NEW badge + improvement_note. Recommendation block at bottom.

### New Register form

Fields per scenario:
- **Risk ID** — free text (e.g., WP-001)
- **Scenario Name** — free text
- **Description** — free text (feeds LLM tag generation)
- **Financial Impact (USD)** — number
- **Probability (%)** — number
- **Search Tags** — LLM-suggested pills (from name + description), editable. "Re-suggest" button.

Tag generation: triggered automatically when both name and description are filled. Calls a lightweight LLM endpoint (`POST /api/registers/suggest-tags`) with the scenario name + description, returns tag array. Tags shown as removable pills. User can add custom tags.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/registers` | List all registers with metadata |
| `POST` | `/api/registers` | Create new register |
| `PUT` | `/api/registers/{id}` | Update register |
| `DELETE` | `/api/registers/{id}` | Delete register |
| `POST` | `/api/registers/active` | Set active register `{ "register_id": "..." }` |
| `GET` | `/api/registers/active` | Get active register |
| `POST` | `/api/registers/suggest-tags` | LLM tag suggestion `{ "name": "...", "description": "..." }` → `{ "tags": [...] }` |
| `GET` | `/api/validation/register-results` | Latest validation results for active register |

---

## What Does NOT Change

- `mock_crq_database.json` — unchanged, still used by intelligence pipeline
- `company_profile.json` — unchanged, still used by regional-analyst-agent
- `master_scenarios.json` — unchanged, still the statistical baseline
- Geopolitical intelligence pipeline — untouched
- All existing agents — untouched

---

## Out of Scope (This Iteration)

- Regional granularity on registers (global only for now)
- Register versioning / history
- Automated figure update from validation results (analyst makes that call manually)
- Sharing registers across users
