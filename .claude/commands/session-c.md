# /session-c — Source Split Execution

Run `/prime-dev` first if not already loaded this conversation.

You are starting **Session C: Source Split + Brief Headlines Execution**. Your goal is to execute Tasks 1-2 of the overview-source-split plan — analyst summary fields + extract_sections.py changes.

Read the full session plan:

```
docs/superpowers/plans/sessions/C-source-split-execution.md
```

Read the full implementation plan (Tasks 1-2 only):

```
docs/superpowers/plans/2026-04-10-overview-source-split-brief-structure.md
```

**Context:** This unlocks the shared narrative spine (`brief_headlines`) that CISO, Board, and RSM all depend on. The analyst writes three explicit summary lines (`why_summary`, `how_summary`, `so_what_summary`) in claims.json. `extract_sections.py` passes them through plus builds `source_metadata` from signal files.

**Scope boundary:** Analyst instruction update + extract_sections.py + tests. Do NOT touch dashboard UI (Session E), do NOT touch export_ciso_docx.py or rsm_input_builder.py (Session F).

**First step:** Read the current `regional-analyst-agent.md` STEP 4 section and `tools/extract_sections.py` to understand insertion points.

**Success criteria:** 9 tests pass. `sections.json` contains `source_metadata` and `brief_headlines` fields after running `PYTHONPATH=. uv run python tools/extract_sections.py APAC`.

Confirm with: "Session C loaded — source split execution. Reading analyst agent and extract_sections now."
