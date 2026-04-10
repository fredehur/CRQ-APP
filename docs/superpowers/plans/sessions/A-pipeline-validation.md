# Session A: Pipeline Validation

**Goal:** Run the full pipeline end-to-end with the new dual-collector Seerist architecture and fix whatever breaks.

**Why first:** The Seerist integration (16 tasks) rewrote the entire collection layer — new collectors (`osint_collector.py`, `seerist_collector.py`), new signal filenames (`osint_signals.json` replaces `geo_signals.json` + `cyber_signals.json`), restructured analyst agent, new stop hooks (Gate 3 + Gate 4). No clean end-to-end run yet. Everything else builds on unverified ground.

**Scope boundary:** Pipeline execution + bug fixes only. Do NOT touch test files, do NOT redesign anything, do NOT work on dashboard/UI. If you find a structural issue, document it and move on.

---

## Files in scope

```
.claude/commands/run-crq.md          — orchestrator (may need phase sequence fixes)
.claude/commands/crq-region.md       — single-region runner
tools/osint_collector.py             — new unified OSINT collector
tools/seerist_collector.py           — new Seerist collector
tools/collection_gate.py             — updated with seerist_strength
tools/extract_sections.py            — updated extraction
tools/pipeline_runner.py             — Phase 0 init
tools/scenario_mapper.py             — may need signal filename updates
.claude/agents/gatekeeper-agent.md   — updated with seerist_absent
.claude/agents/regional-analyst-agent.md — updated reading order
.claude/hooks/validators/regional-analyst-stop.py — Gates 1-4
data/mock_osint_fixtures/            — restructured fixtures
output/                              — all pipeline output
```

## Files NOT in scope

```
tests/                  → Session B
static/                 → Session E
tools/export_*.py       → Session C/F
tools/rsm_*.py          → Session F
docs/                   → not a build session
```

---

## Steps

1. Clean working tree — commit or stash modified output files and untracked artifacts
2. Run `/run-crq` in mock mode
3. For each failure: diagnose, fix, re-run the failing phase
4. After all phases pass: verify output files exist and have correct schema
   - `output/regional/{region}/osint_signals.json` (not geo_signals/cyber_signals)
   - `output/regional/{region}/seerist_signals.json`
   - `output/regional/{region}/collection_quality.json` (with `seerist_strength` + `collection_lag`)
   - `output/regional/{region}/gatekeeper_decision.json` (with `seerist_absent`)
   - `output/regional/{region}/claims.json` (escalated regions — with `convergence_assessment` + `bullets`)
   - `output/regional/{region}/sections.json` (escalated regions)
   - `output/pipeline/global_report.json`
5. Run `/crq-region APAC` separately to verify single-region path
6. Commit all fixes

**Success criteria:** `/run-crq` completes all 7 phases with zero failures. All stop hooks pass. Output schema matches the new dual-collector architecture.
