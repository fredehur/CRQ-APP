# Session C: Source Split + Brief Headlines Execution

**Goal:** Execute Tasks 1-2 of `2026-04-10-overview-source-split-brief-structure.md` — analyst summary fields + extract_sections.py changes. This unlocks the shared narrative spine that CISO, Board, and RSM all depend on.

**Why:** `brief_headlines` is the prerequisite for every downstream report improvement — CISO headline openers, Board summary cards, RSM alert openers. Small scope, no dependencies on other sessions.

**Scope boundary:** Analyst instruction update + extract_sections.py + tests. Do NOT touch dashboard UI (Session E), do NOT touch export_ciso_docx.py or rsm_input_builder.py (Session F).

**Full plan:** `docs/superpowers/plans/2026-04-10-overview-source-split-brief-structure.md` — Tasks 1 and 2 only.

---

## Files in scope

```
.claude/agents/regional-analyst-agent.md              — add why/how/so_what_summary to claims output
tools/extract_sections.py                             — add _build_source_metadata() + _extract_brief_headlines()
tests/test_extract_sections_source_split.py           — new test file (9 tests)
```

## Files NOT in scope

```
static/                    → Session E (dashboard)
tools/export_ciso_docx.py  → Session F (report wiring)
tools/report_builder.py    → Session F
tools/rsm_input_builder.py → Session F
```

---

## Steps

1. Task 1: Add `why_summary`, `how_summary`, `so_what_summary` to analyst agent claims.json instruction
2. Task 2: Write failing tests → implement `_build_source_metadata()` + `_extract_brief_headlines()` → run tests → verify integration with `extract()` writing to disk
3. Run `PYTHONPATH=. uv run python tools/extract_sections.py APAC` and confirm `source_metadata` + `brief_headlines` appear in sections.json
4. Commit

**Success criteria:** 9 tests pass. `sections.json` contains `source_metadata` and `brief_headlines` fields after running extract_sections.
