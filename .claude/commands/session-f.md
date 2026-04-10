# /session-f — Report Wiring

Run `/prime-dev` first if not already loaded this conversation.

You are starting **Session F: Report Format Wiring — CISO + Board + RSM Quick Wins**. Your goal is to wire `brief_headlines` into all three stakeholder formats and add three quick wins: RSM cross-regional watch, "why clear" footnotes, global summary opener.

Read the full session plan:

```
docs/superpowers/plans/sessions/F-report-wiring.md
```

Also read Tasks 4-6 of the source-split plan:

```
docs/superpowers/plans/2026-04-10-overview-source-split-brief-structure.md
```

And the brainstorm priority table (Round 2 section):

```
docs/superpowers/plans/2026-04-10-regional-structure-brainstorm.md
```

**Context:** These are the items that survived critique as unambiguously good — low risk, use existing data, improve every stakeholder output. `brief_headlines` must already exist in sections.json (Session C must be complete).

**Scope boundary:** Report generation tools + RSM agent only. Do NOT touch dashboard/UI (Session E), do NOT change the pipeline or analysts (Sessions A/C).

**Task order:**
1. RSM cross-regional watch block (pull from `global_report.json` → `cross_regional_patterns`)
2. "Why clear" footnotes in CISO (surface `seerist_absent` + `collection_lag` for non-escalated regions)
3. Global summary opener in CISO (add `global_report.json` exec summary as opening section)
4. Wire `brief_headlines` into CISO as section subheadings
5. Wire `brief_headlines` into Board region cards
6. Wire `brief_headlines` into RSM as alert openers

**Success criteria:** CISO docx opens with global summary, has "why clear" footnotes, uses analyst headlines. Board cards show `so_what_headline`. RSM includes cross-regional watch block.

Confirm with: "Session F loaded — report wiring. Reading export_ciso_docx.py and rsm_input_builder.py now."
