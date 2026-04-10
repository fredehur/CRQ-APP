# /session-d — End-to-End Pipeline Review

Run `/prime-dev` first if not already loaded this conversation.

You are starting **Session D: End-to-End Pipeline Review**. Your goal is a read-only diagnostic — walk every data path from raw collection to stakeholder output, map transformations, find gaps.

Read the full session plan:

```
docs/superpowers/plans/sessions/D-pipeline-review.md
```

Also read the brainstorm context:

```
docs/superpowers/plans/2026-04-10-regional-structure-brainstorm.md
```

**Context:** The brainstorm proposes structural changes to how regions tie into CISO/Board/RSM formats. Before making those changes, we need to understand what the pipeline actually does today. This session produces the diagnostic that informs Sessions E and F.

**Scope boundary:** Read-only. Do NOT change any code. Read files, trace data flows, produce a written findings document.

**Key questions to answer:**
1. For each field in final outputs (CISO docx, board PDF, RSM brief) — where does it come from? Where is data lost?
2. Where do CISO, Board, and RSM consume the same data from different files?
3. Which intermediate files have quality gates (stop hooks) and which pass through unchecked?
4. Trace a Seerist hotspot anomaly from `seerist_signals.json` to CISO brief — where does it appear? Where is it lost?
5. What does `global_report.json` produce that never reaches any stakeholder output?

**Output:** Write findings to `docs/superpowers/specs/2026-04-pipeline-review-findings.md`.

Confirm with: "Session D loaded — pipeline review. Starting trace at Phase 0."
