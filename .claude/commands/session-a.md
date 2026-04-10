# /session-a — Pipeline Validation

Run `/prime-dev` first if not already loaded this conversation.

You are starting **Session A: Pipeline Validation**. Your goal is to run the full pipeline end-to-end with the new dual-collector Seerist architecture and fix whatever breaks.

Read the full session plan:

```
docs/superpowers/plans/sessions/A-pipeline-validation.md
```

**Context:** The Seerist integration (16 tasks) rewrote the entire collection layer — new collectors (`osint_collector.py`, `seerist_collector.py`), new signal filenames (`osint_signals.json` replaces `geo_signals.json` + `cyber_signals.json`), restructured analyst agent, new stop hooks (Gate 3 + Gate 4). No clean end-to-end run yet with the new architecture.

**Scope boundary:** Pipeline execution + bug fixes only. Do NOT touch test files (Session B), do NOT touch dashboard/UI (Session E), do NOT redesign anything. If you find a structural issue, document it and move on.

**First step:** Clean working tree — commit or stash modified output files and untracked artifacts. Then run `/run-crq` in mock mode.

**Success criteria:** `/run-crq` completes all 7 phases with zero failures. All stop hooks pass. Output schema matches the new dual-collector architecture.

Confirm with: "Session A loaded — pipeline validation. Ready to run."
