# Session F: Report Format Wiring — CISO + Board + RSM Quick Wins

**Goal:** Wire `brief_headlines` + `source_metadata` into all three stakeholder report formats, and add the three quick wins from the brainstorm priority table: RSM cross-regional watch, "why clear" footnotes, global summary opener.

**Why:** These are the items that survived critique as unambiguously good. Low risk, use existing data, improve every stakeholder output without structural reorganization.

**Scope boundary:** Report generation tools + RSM agent only. Do NOT touch dashboard/UI (Session E), do NOT change the pipeline or analysts (Sessions A/C).

**Depends on:** Session C (source-split execution — `brief_headlines` must exist in sections.json) and Session A (pipeline works, global_report.json is produced).

---

## Files in scope

```
tools/export_ciso_docx.py                — headline subheadings + "why clear" footnotes + global summary opener
tools/report_builder.py                  — headline on board region cards
tools/rsm_input_builder.py               — brief_headlines + cross-regional watch data
.claude/agents/rsm-formatter-agent.md    — consume brief_headlines + cross-regional watch
```

## Files NOT in scope

```
static/                        → Session E
tools/extract_sections.py      → Session C
.claude/agents/regional-analyst-agent.md → Session C
tests/                         → Session B
```

---

## Tasks (from brainstorm priority table)

### 1. RSM cross-regional watch block
- In `rsm_input_builder.py`: read `global_report.json` → `cross_regional_patterns`
- Add `cross_regional_watch` field to RSM payload per region
- In `rsm-formatter-agent.md`: add instruction to render cross-regional watch section

### 2. "Why clear" footnotes in CISO brief
- In `export_ciso_docx.py`: for MONITOR/CLEAR regions, read `gatekeeper_decision.json` for `seerist_absent` + `collection_quality.json` for `collection_lag.detected`
- Render one-line footnote per non-escalated region: "AME — MONITOR (Seerist data absent, OSINT signals did not reach escalation threshold)" or "LATAM — CLEAR (no signals from either source, collection quality normal)"

### 3. Global summary opener in CISO brief
- In `export_ciso_docx.py`: read `global_report.json` → `executive_summary`
- Render as the opening section before per-region detail
- Fallback: if `global_report.json` absent, skip (don't break the brief)

### 4. Wire brief_headlines into CISO
- Tasks 4 from source-split plan — use `brief_headlines` as section subheadings

### 5. Wire brief_headlines into Board
- Task 5 from source-split plan — `so_what_headline` on board region cards

### 6. Wire brief_headlines into RSM
- Task 6 from source-split plan — headlines as alert section openers

---

**Success criteria:** 
- CISO docx opens with global summary, has "why clear" footnotes, uses analyst headlines as section subheadings
- Board region cards show `so_what_headline`
- RSM briefs include cross-regional watch block and use headlines as openers
