# Session B: Test Suite Cleanup

**Goal:** Make the test suite trustworthy — every test either passes or is deliberately skipped with a documented reason. No silent failures masking real regressions.

**Why:** `test_report_builder.py` imports a deleted function. Server tests fail on renamed signal files. Threshold evaluator tests reference missing files. The suite is noisy enough that new regressions hide behind old debt. This must be clean before more structural changes.

**Scope boundary:** Tests only. Fix broken imports, update assertions to match new schemas, skip or remove tests for deleted features. Do NOT change production code to make tests pass — if a test reveals a real bug, document it for Session A.

**Depends on:** Session A (pipeline validation) should run first so production code is stable.

---

## Files in scope

```
tests/test_report_builder.py              — broken import (_extract_board_bullets deleted)
tests/test_server.py                      — failing on renamed signal files / changed API responses
tests/test_server_source_library_osint.py — failing endpoint tests
tests/test_threshold_evaluator.py         — failing on missing files / changed schema
tests/test_ui.py                          — Playwright errors (may need browser install)
```

## Files NOT in scope

```
tools/               → Session A
static/              → Session E
.claude/agents/      → not a test session
output/              → not a test session
```

---

## Steps

1. Run full test suite: `PYTHONPATH=. uv run pytest tests/ -v --tb=short 2>&1 | tail -40`
2. Categorize each failure:
   - **Stale import** — test references deleted function/file → fix or remove test
   - **Schema drift** — test expects old field names (geo_signals vs osint_signals) → update assertions
   - **Missing infrastructure** — Playwright not installed, server not running → add skip marker
   - **Real bug** — test reveals actual production issue → document, don't fix here
3. Fix each category
4. Re-run full suite — target: zero failures, zero errors
5. Commit

**Success criteria:** `PYTHONPATH=. uv run pytest tests/ -v` shows all green (or deliberate skips with `@pytest.mark.skip(reason="...")`)
