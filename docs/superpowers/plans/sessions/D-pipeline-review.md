# Session D: End-to-End Pipeline Review

**Goal:** Walk the full path from raw OSINT/Seerist collection through every intermediate file, every agent, every stop hook, to each final stakeholder output. Map where data is transformed, where it's lost, where formats diverge unnecessarily, and where quality gates exist vs. where they're missing.

**Why:** The brainstorm doc (`2026-04-10-regional-structure-brainstorm.md`) proposes structural changes to how regions tie into output formats. Before making those changes, we need to understand what the pipeline actually does today — not what we think it does. This is the diagnostic.

**Scope boundary:** Read-only analysis. Do NOT change any code. Produce a written map of the pipeline with findings. This informs Sessions E and F.

**Depends on:** Session A (pipeline works end-to-end) should complete first so the review reflects the current working state.

---

## Files to trace (in pipeline order)

### Phase 0 — Init
```
tools/pipeline_runner.py → output/pipeline/run_config.json
```

### Phase 1 — Per-region fan-out
```
tools/osint_collector.py      → output/regional/{region}/osint_signals.json
tools/seerist_collector.py    → output/regional/{region}/seerist_signals.json
tools/youtube_collector.py    → output/regional/{region}/youtube_signals.json
tools/scenario_mapper.py      → output/regional/{region}/scenario_map.json
tools/collection_gate.py      → output/regional/{region}/collection_quality.json
.claude/agents/gatekeeper-agent.md → output/regional/{region}/gatekeeper_decision.json
.claude/agents/regional-analyst-agent.md → report.md + data.json + claims.json
tools/extract_sections.py     → sections.json + signal_clusters.json
```

### Phase 2-3 — Trend + Diff
```
tools/trend_analyzer.py       → output/pipeline/trend_brief.json
tools/report_differ.py        → cross-regional delta
```

### Phase 4 — Global synthesis
```
.claude/agents/global-builder-agent.md → output/pipeline/global_report.json
.claude/agents/global-validator-agent.md → APPROVED / REWRITE
```

### Phase 5 — Export
```
tools/build_dashboard.py      → output/pipeline/dashboard.html
tools/export_pdf.py           → output/deliverables/board_report.pdf
tools/export_pptx.py          → output/deliverables/board_report.pptx
tools/export_ciso_docx.py     → output/deliverables/ciso_brief.docx
```

### Phase 6-7 — Finalize + RSM
```
tools/write_manifest.py       → output/pipeline/run_manifest.json
tools/rsm_input_builder.py    → RSM input payloads
.claude/agents/rsm-formatter-agent.md → output/delivery/rsm/
```

---

## Questions to answer

1. **Data loss map:** For each field in the final outputs (CISO docx, board PDF, RSM brief), trace it back to its source. Where does a field disappear or get silently dropped?
2. **Format divergence:** Where do CISO, Board, and RSM consume the same data from different files or with different schemas? Can they share a single source?
3. **Quality gate coverage:** Which intermediate files are validated by stop hooks, and which pass through unchecked? Specifically: is `global_report.json` validated before `export_ciso_docx.py` reads it?
4. **Seerist → output path:** Trace a Seerist hotspot anomaly from `seerist_signals.json` all the way to the CISO brief and board PDF. Where does it appear? Where is it lost?
5. **`global_report.json` utilization:** The global builder produces `executive_summary`, `cross_regional_patterns`, `compound_risks`. Which of these actually reach any stakeholder output? Which are produced but never rendered?

**Output:** A written findings document — not a plan, not a spec. Just the map and the gaps.
