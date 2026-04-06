# Task Assignment — Output Alignment + Source Quality Build
**Master plan:** `../2026-04-05-master-build-plan.md`

## Session Split

| Task | File | Session | Can Start | Blocks |
|---|---|---|---|---|
| Task 1 | `task-1-source-quality-boundary-fix.md` | Session A | Now | Task 2 |
| Task 2 | `task-2-report-builder-enrichment.md` | Session A | After Task 1 | Task 3 |
| Task 3 | `task-3-pdf-pptx-renderers.md` | Session B | After Task 2 | — |
| Task 4 | `task-4-rsm-fallback-contract.md` | Session B | Now (independent) | — |

## Execution Order

```
Session A:  Task 1 → Task 2  (sequential)
Session B:  Task 4            (start now, no blockers)

After Session A completes Task 2:
Session B:  Task 3            (PDF + PPTX renderers)

After all tasks complete:
Validation: cross-check all output against master-build-plan.md done criteria
```

## What Each Task Does

- **Task 1** — Removes source_quality from analyst agent. Adds `enrich_region_data()` to `update_source_registry.py`. Wires Phase 5.
- **Task 2** — Moves extraction logic from `export_ciso_docx.py` into `report_builder.py`. Enriches `RegionEntry` with 8 new fields. Makes ciso_docx a pure renderer.
- **Task 3** — Rewrites `report.html.j2` (PDF) and `export_pptx.py` (PPTX) to use 7-section intelligence layout. Removes "CISO Edition". Pure rendering — reads from `RegionEntry` fields.
- **Task 4** — Creates `tools/rsm_input_builder.py` (code-owned fallback handler). Updates `rsm-formatter-agent.md` with typed skill contract.

## Handoff Signals

- Task 1 → Task 2: "Task 1 complete. `enrich_region_data()` available. `data.json` will have `source_quality` after analyst runs."
- Task 2 → Task 3: "Task 2 complete. `RegionEntry` has `intel_bullets`, `adversary_bullets`, `impact_bullets`, `watch_bullets`, `action_bullets`, `threat_actor`, `signal_type_label`, `source_quality`."
