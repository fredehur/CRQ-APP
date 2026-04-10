# /session-b — Test Suite Cleanup

Run `/prime-dev` first if not already loaded this conversation.

You are starting **Session B: Test Suite Cleanup**. Your goal is to make the test suite trustworthy — every test either passes or is deliberately skipped with a documented reason.

Read the full session plan:

```
docs/superpowers/plans/sessions/B-test-suite-cleanup.md
```

**Context:** `test_report_builder.py` imports a deleted function. Server tests fail on renamed signal files. Threshold evaluator tests reference missing files. Playwright UI tests may need browser install. The suite is noisy enough that new regressions hide behind old debt.

**Scope boundary:** Tests only. Fix broken imports, update assertions to match new schemas, skip or remove tests for deleted features. Do NOT change production code to make tests pass — if a test reveals a real bug, document it for Session A.

**First step:** Run `PYTHONPATH=. uv run pytest tests/ -v --tb=short 2>&1 | tail -40` and categorize each failure.

**Success criteria:** `PYTHONPATH=. uv run pytest tests/ -v` shows all green (or deliberate skips with `@pytest.mark.skip(reason="...")`).

Confirm with: "Session B loaded — test suite cleanup. Running full suite now."
