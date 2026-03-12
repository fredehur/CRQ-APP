# Design Spec: Phase D-1 OSINT Tool Chain

**Date:** 2026-03-12
**Status:** Draft
**Project:** CRQ Geopolitical Intelligence Pipeline — AeroGrid Wind Solutions

---

## Mission

Build a 4-tool OSINT signal collection layer that replaces static mock feed signals with dynamically generated geo and cyber signal files. In mock mode the logic runs against fixture data; in live mode only the search primitive changes. The gatekeeper and regional analyst agents consume the output files instead of reading raw feed JSONs.

---

## Stack

- Language: Python 3.12
- Package manager: uv
- Search backends: fixture files (mock), DuckDuckGo HTML scrape (free fallback), Tavily API (drop-in upgrade)
- Output format: JSON files on disk (filesystem as state)
- No new dependencies required for mock mode

---

## Deliverables

- [ ] `tools/osint_search.py` — raw search primitive, returns `[{title, summary, source, date}]`; accepts `--type geo|cyber` flag for fixture selection in mock mode
- [ ] `tools/geo_collector.py` — geo signal collector, writes `output/regional/{region}/geo_signals.json`
- [ ] `tools/cyber_collector.py` — cyber signal collector, writes `output/regional/{region}/cyber_signals.json`
- [ ] `tools/scenario_mapper.py` — scenario mapper, writes `output/regional/{region}/scenario_map.json`
- [ ] `data/mock_osint_fixtures/{region}_geo.json` (5 files) — raw search result fixtures for geo queries
- [ ] `data/mock_osint_fixtures/{region}_cyber.json` (5 files) — raw search result fixtures for cyber queries

---

## Acceptance Criteria

1. `uv run python tools/geo_collector.py APAC --mock` writes `output/regional/apac/geo_signals.json` with keys `summary`, `lead_indicators`, `dominant_pillar`
2. `uv run python tools/cyber_collector.py APAC --mock` writes `output/regional/apac/cyber_signals.json` with keys `summary`, `threat_vector`, `target_assets`
3. `uv run python tools/scenario_mapper.py APAC --mock` writes `output/regional/apac/scenario_map.json` with keys `top_scenario`, `confidence`, `financial_rank`, `rationale`
4. `uv run python tools/osint_search.py APAC "wind turbine supply chain" --mock --type geo` prints a valid JSON array of `[{title, summary, source, date}]` to stdout; exits 0
5. All 5 regions produce valid output files with no errors
6. Swapping `--mock` for a live Tavily key requires only changing `osint_search.py` — no downstream code changes
7. `financial_rank` in `scenario_map.json` matches the actual `financial_rank` of the `top_scenario` in `data/master_scenarios.json`

---

## Constraints

- DO NOT hardcode signal output in the collectors — the normalization logic must run even in mock mode
- DO NOT read from `data/mock_threat_feeds/{region}_feed.json` in any new tool — feeds remain as VaCR/severity source only
- DO NOT add new Python package dependencies for mock mode
- DO NOT modify existing tools (`regional_search.py`, `geopolitical_context.py`, `threat_scorer.py`)
- DO NOT wire the new tools into `gatekeeper-agent.md` or `run-crq.md` yet — that is Phase D-2
- DO NOT generate statistics not present in `data/master_scenarios.json`

---

## Context Files

Builders must read these before writing any code:

- `data/mock_threat_feeds/apac_feed.json` — reference for existing signal shape
- `data/master_scenarios.json` — scenario list that `scenario_mapper.py` cross-references
- `data/company_profile.json` — AeroGrid crown jewels, used to filter asset-relevant signals
- `tools/regional_search.py` — existing tool pattern to follow for CLI arg style
- `tools/geopolitical_context.py` — existing tool pattern to follow for output style
- `CLAUDE.md` — project conventions, Disler protocol

---

## Data Schemas

### Fixture files — `data/mock_osint_fixtures/{region}_{type}.json`

Raw search results, shaped like a real DDG/Tavily API response:

```json
[
  {
    "title": "string",
    "summary": "string",
    "source": "string (domain or outlet name)",
    "date": "YYYY-MM-DD"
  }
]
```

Each fixture file contains 4–6 articles relevant to the region and signal type (geo or cyber).

### `geo_signals.json`

```json
{
  "summary": "string (2-3 sentences, board-level language)",
  "lead_indicators": ["string", "string", "string"],
  "dominant_pillar": "Geopolitical | Cyber | Regulatory"
}
```

### `cyber_signals.json`

```json
{
  "summary": "string (2-3 sentences, board-level language)",
  "threat_vector": "string",
  "target_assets": ["string", "string"]
}
```

### `scenario_map.json`

```json
{
  "top_scenario": "string (must match a scenario name in master_scenarios.json)",
  "confidence": "high | medium | low",
  "financial_rank": "integer (1-9, from master_scenarios.json)",
  "rationale": "string (single sentence)"
}
```

---

## Architecture

```
osint_search.py REGION QUERY --type geo|cyber [--mock]
    --type: selects fixture file in mock mode (geo → {region}_geo.json, cyber → {region}_cyber.json)
    --mock: loads data/mock_osint_fixtures/{region_lower}_{type}.json
    --live: calls Tavily API (requires TAVILY_API_KEY env var); --type used as search domain hint
    stdout: JSON array [{title, summary, source, date}]

geo_collector.py REGION [--mock]
    calls: osint_search.py REGION "{region} geopolitical risk wind energy" --type geo [--mock]
    calls: osint_search.py REGION "{region} trade tensions manufacturing" --type geo [--mock]
    normalizes: extracts summary + lead_indicators from article titles/summaries
    infers: dominant_pillar from signal keywords
    writes: output/regional/{region_lower}/geo_signals.json

cyber_collector.py REGION [--mock]
    calls: osint_search.py REGION "{region} cyber threat industrial control systems" --type cyber [--mock]
    calls: osint_search.py REGION "{region} OT security wind energy" --type cyber [--mock]
    normalizes: extracts summary + threat_vector + target_assets
    writes: output/regional/{region_lower}/cyber_signals.json

scenario_mapper.py REGION [--mock]
    reads: output/regional/{region_lower}/geo_signals.json
    reads: output/regional/{region_lower}/cyber_signals.json
    reads: data/master_scenarios.json
    maps: signal keywords → scenario match + financial_rank
    writes: output/regional/{region_lower}/scenario_map.json
```

**Key invariant:** `osint_search.py` is the only file that knows about mock vs. live. Collectors always call it as a subprocess and parse its stdout. This is the seam where live search will be plugged in.

---

## Task Breakdown

### Task 1: Fixture files
- **Skills:** none
- **Input:** `data/mock_threat_feeds/apac_feed.json` (reference shape), `data/company_profile.json`
- **Output:** `data/mock_osint_fixtures/{region}_{geo,cyber}.json` — 10 files total
- **Criteria:** Each file is valid JSON, array of 4–6 objects, each with `title`, `summary`, `source`, `date`
- **Blocked by:** nothing

### Task 2: `osint_search.py`
- **Skills:** none
- **Input:** `data/mock_osint_fixtures/`, `tools/regional_search.py` (pattern reference)
- **Output:** `tools/osint_search.py`
- **Criteria:** `uv run python tools/osint_search.py APAC "query" --mock` prints valid JSON array to stdout; exits 0
- **Blocked by:** Task 1

### Task 3: `geo_collector.py`
- **Skills:** none
- **Input:** `tools/osint_search.py`, `data/company_profile.json`
- **Output:** `tools/geo_collector.py`
- **Criteria:** `uv run python tools/geo_collector.py APAC --mock` writes valid `geo_signals.json`; all 5 regions pass
- **Blocked by:** Task 2

### Task 4: `cyber_collector.py`
- **Skills:** none
- **Input:** `tools/osint_search.py`, `data/company_profile.json`
- **Output:** `tools/cyber_collector.py`
- **Criteria:** `uv run python tools/cyber_collector.py APAC --mock` writes valid `cyber_signals.json`; all 5 regions pass
- **Blocked by:** Task 2

### Task 5: `scenario_mapper.py`
- **Skills:** none
- **Input:** `tools/geo_collector.py`, `tools/cyber_collector.py`, `data/master_scenarios.json`
- **Output:** `tools/scenario_mapper.py`
- **Criteria:** `uv run python tools/scenario_mapper.py APAC --mock` writes valid `scenario_map.json`; `top_scenario` exists in `master_scenarios.json`; all 5 regions pass
- **Blocked by:** Tasks 3 and 4
