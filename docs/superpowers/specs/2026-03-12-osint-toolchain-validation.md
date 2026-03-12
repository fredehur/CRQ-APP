# Spec Validation Report: Phase D-1 OSINT Tool Chain

## Verdict: APPROVED

## Checks
- [PASS] Completeness: All required sections present — Mission, Stack, Deliverables, Acceptance Criteria, Constraints, Context Files, Data Schemas, Architecture, Task Breakdown.
- [PASS] Correctness: `cyber_signals.json` schema (`summary`, `threat_vector`, `target_assets`) matches the existing mock feed shape exactly. `geo_signals.json` adds `dominant_pillar` which is currently a top-level feed field — acceptable since D-2 will update the gatekeeper to read from these files instead. `scenario_map.json` is new data not currently consumed, so no compatibility issue.
- [PASS] Consistency: Task Breakdown inputs/outputs match the Deliverables list. Dependencies are correct: Task 1 (fixtures) blocks Task 2 (search), Task 2 blocks Tasks 3+4 (collectors), Tasks 3+4 block Task 5 (mapper). All output file paths are consistent across sections.
- [PASS] Constraints: Constraints are tight — no modifying existing tools, no reading from mock feeds, no hardcoded output, no new deps for mock mode, no wiring into agents yet. Good separation of D-1 (build tools) from D-2 (wire in).
- [PASS] Acceptance Criteria: All 6 criteria are machine-checkable — run command, check file exists, validate JSON keys, check exit code.
- [PASS] Mock/live seam: Clean — `osint_search.py` is the only file that knows about mock vs live. Collectors call it as subprocess and parse stdout. Swapping to Tavily requires changing only the search primitive.

## Issues Found

1. **MEDIUM** — `osint_search.py` fixture routing is underspecified. The CLI signature is `osint_search.py REGION QUERY [--mock]`, and mock mode loads `data/mock_osint_fixtures/{region}_{geo|cyber}.json`. But there is no mechanism described for how a free-text QUERY maps to the correct fixture file (`_geo` vs `_cyber`). The Architecture section shows `geo_collector.py` passing queries like `"{region} geopolitical risk wind energy"` — but how does the search primitive know to load the `_geo` fixture vs `_cyber` fixture from that query string alone? **Suggested fix:** Either (a) add an optional `--type geo|cyber` flag to `osint_search.py` for fixture selection in mock mode, or (b) specify that mock mode uses keyword matching on the query string (e.g., "geopolitical" maps to `_geo`, "cyber" maps to `_cyber`), or (c) document that mock mode ignores the query and returns the same fixture for both calls per region (less realistic but simpler). The Builder needs this clarified to implement correctly.

2. **LOW** — `dominant_pillar` placement differs between current feed and spec. In the current mock feed, `dominant_pillar` is a top-level field alongside `geo_signals`. In the spec, `dominant_pillar` is a key inside `geo_signals.json`. This is fine for D-1 (tools are standalone), but the D-2 spec will need to account for this schema migration when updating the gatekeeper. No action needed now, but worth noting for D-2 planning.

3. **LOW** — `scenario_map.json` includes `financial_rank` as an integer 1-9, but `master_scenarios.json` only has 9 scenarios. Acceptance criterion 3 validates `top_scenario` exists in the master list, but does not validate that `financial_rank` matches the actual rank from `master_scenarios.json` for that scenario. **Suggested fix:** Add an acceptance criterion: "`financial_rank` in `scenario_map.json` must equal the `financial_rank` of the matched scenario in `master_scenarios.json`."

## Summary

Spec is well-structured and implementation-ready. The one MEDIUM issue (fixture routing in mock mode) needs a one-sentence clarification so Builders know how `osint_search.py --mock` selects the right fixture file from a free-text query. The two LOW issues are minor and can be addressed in D-2 planning.
