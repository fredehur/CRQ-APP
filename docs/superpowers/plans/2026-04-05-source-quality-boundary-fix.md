# Source Quality — Boundary Fix Plan
**Date:** 2026-04-05
**Status:** Sketched — ready to build
**Depends on:** M1–M4 of `2026-04-01-sources-redesign.md` (all complete)

---

## Context

M4 of the sources redesign was implemented by updating the `regional-analyst-agent` prompt to instruct the agent to compute `source_quality` — scanning signal file URLs, classifying them into tiers (A/B/C) by URL pattern matching, counting uniques, and writing the result to `data.json`.

This violates the agent boundary principles.

**The rule:** *Agents own reasoning. Code owns correctness. If you can write a unit test for it, code should own it.*

URL pattern matching (`if ".gov" in url → Tier A`) and counting are 100% deterministic. An LLM doing this will occasionally produce wrong counts with zero stack trace — no exception, just a bad report.

The same violation applies to Fix B (`signal_clusters.json` source enrichment with `{url, credibility_tier}`) and the M5 `cited=1` flag — both are URL matching, both are code territory.

---

## What Was Built in M4 (current state)

- `regional-analyst-agent.md` prompt updated with a "Deriving `source_quality` counts" block — instructs the agent to scan signal files, classify URLs, count per tier, and write to `data.json`
- `source_quality` is in the agent self-validation checklist
- `signal_clusters.json` cluster sources are `{name, headline}` only — no `url`, no `credibility_tier` (Fix B not done)
- `data.json` does NOT currently have `source_quality` in any live run output — field is absent

---

## What Is Wrong (the boundary violation)

| Task | Current owner | Correct owner | Why |
|---|---|---|---|
| Classify URL into Tier A/B/C | Agent (prompt instruction) | Code | URL pattern match — 100% deterministic, unit-testable |
| Count unique sources per tier | Agent (prompt instruction) | Code | Arithmetic — agents hallucinate numbers |
| Write `source_quality` to `data.json` | Agent | Code | Derived from DB query, not from reasoning |
| Enrich cluster sources with `{url, tier}` | Not done yet | Code | URL lookup against `sources_registry` — deterministic |
| Set `cited=1` in `source_appearances` | Not done yet (M5) | Code | URL match in clusters — deterministic |

---

## The Fix

### 1. Remove source_quality work from the analyst agent

**File:** `.claude/agents/regional-analyst-agent.md`

Remove:
- The "Deriving `source_quality` counts" section (URL scanning, tier classification rules, counting instructions)
- `source_quality` from the self-validation checklist
- Any instruction to write `source_quality` to `data.json`

The agent retains all intelligence work: prose, escalation rationale, cluster naming, scenario judgment, signal type classification. It does not touch source metrics.

---

### 2. New code function: `enrich_region_data(region, run_id)`

**File:** `tools/update_source_registry.py` (add as new function at bottom)

This function runs after the analyst agent exits, before the CISO export. It does three deterministic tasks:

**Task A — Compute `source_quality` (SQL + arithmetic)**

```python
def _compute_source_quality(conn, region, run_id):
    cur = conn.execute("""
        SELECT credibility_tier, COUNT(DISTINCT source_id)
        FROM source_appearances
        WHERE region = ? AND run_id = ?
        GROUP BY credibility_tier
    """, (region, run_id))
    counts = {row[0]: row[1] for row in cur.fetchall()}
    return {
        "tier_a": counts.get("A", 0),
        "tier_b": counts.get("B", 0),
        "tier_c": counts.get("C", 0),
        "total": sum(counts.values())
    }
```

Write result into `output/regional/{region}/data.json["source_quality"]`.

**Task B — Enrich `signal_clusters.json` sources with `{url, credibility_tier}`**

For each cluster source `name`:
- Lookup matching row in `sources_registry` by `name` (exact match first, then domain fuzzy)
- If matched: add `url` and `credibility_tier` to the source object
- If unmatched (generic name like "Tavily Research" or no registry entry): log as unresolved, leave `url: null`, `credibility_tier: null`
- Write enriched clusters back to `output/regional/{region}/signal_clusters.json`

**Task C — Set `cited=1` in `source_appearances` (pulls M5 work forward)**

For each URL found in enriched cluster sources:
- Match to `source_id` in `sources_registry`
- `UPDATE source_appearances SET cited=1 WHERE source_id=? AND run_id=? AND region=?`
- This is a SQL UPDATE — deterministic, zero LLM

---

### 3. Schema quality gate (currently absent)

After `enrich_region_data` runs, validate `data.json` before proceeding to CISO export:

```python
def _validate_source_quality(data):
    sq = data.get("source_quality")
    assert sq is not None, "source_quality missing from data.json"
    assert all(isinstance(sq.get(k), int) for k in ["tier_a", "tier_b", "tier_c", "total"])
    assert sq["total"] == sq["tier_a"] + sq["tier_b"] + sq["tier_c"]
```

If validation fails → raise exception, pipeline stops. Do not silently produce a CISO report without quality data.

---

### 4. Pipeline execution order

```
Phase 1:  research_collector.py (OSINT collection)
Phase 2:  youtube_collector.py
Phase 3:  scenario_mapper.py → gatekeeper-agent
Phase 4:  regional-analyst-agent (prose + clusters + data.json — no source_quality)
Phase 5:  enrich_region_data()     ← NEW (code gate, not agent)
Phase 6:  update_source_registry.py (existing registry population)
Phase 7:  export_ciso_docx.py      ← reads enriched data.json with source_quality
Phase 8:  global-builder-agent
```

Phase 5 must complete and pass the schema gate before Phase 7 runs. The CISO export, region card badge, and evidence panel all read `source_quality` from `data.json` — no agent is involved in that chain.

---

## Files to Change

| File | Change | Size |
|---|---|---|
| `.claude/agents/regional-analyst-agent.md` | Remove source_quality derivation block + checklist item | Small |
| `tools/update_source_registry.py` | Add `enrich_region_data()` + `_compute_source_quality()` + `_validate_source_quality()` | Medium |
| `.claude/commands/run-crq.md` | Add Phase 5 `enrich_region_data` call between analyst and CISO export | Small |
| `server.py` | Wire `enrich_region_data` into pipeline Phase 5 | Small |

No new files. No new agents. No schema changes to the DB.

---

## What the Analyst Agent Prompt Looks Like After

The agent still writes:
- `report.md` — full prose brief
- `data.json` — all existing fields (primary_scenario, severity, admiralty, rationale, signal_type, etc.)
- `signal_clusters.json` — cluster names, pillars, convergence scores, source names + headlines

It no longer:
- Scans URLs
- Classifies tiers
- Counts anything
- Writes `source_quality`

The self-validation checklist loses one item. The prompt gets shorter and more focused.

---

## Dependency on Output Alignment Plan

This plan must run **before** `2026-04-05-output-alignment-plan.md` ST-1 (Builder A).

Output Alignment's ST-1 enriches `RegionEntry` in `report_builder.py`. `RegionEntry` must carry `source_quality` through to Board PDF and PPTX so those exporters can render tier data without reading `data.json` directly.

**Add one field to `RegionEntry` in ST-1:**

```python
source_quality: dict | None  # {"tier_a": 3, "tier_b": 8, "tier_c": 1, "total": 12}
```

`report_builder.py` reads `data.json["source_quality"]` (written by `enrich_region_data()`) and sets this field. Board PDF footer and PPTX speaker notes then read it from `RegionEntry` — no direct `data.json` access in the exporters.

**Correct build order (merged across both plans):**

```
Step 1 — Source Quality fix (this plan, no blockers):
  1a. Remove source_quality from analyst agent prompt
  1b. Add enrich_region_data() to update_source_registry.py
  1c. Wire Phase 5 in server.py + run-crq.md

Step 2 — Output Alignment ST-1 (depends on Step 1):
  Builder A: report_builder.py + RegionEntry incl. source_quality field
  export_ciso_docx.py → pure renderer

Step 3 — Output Alignment ST-2/ST-3/ST-4 (parallel, depend on ST-1):
  Builder B: report.html.j2 + export_pptx.py
  Builder C: rsm-formatter-agent.md + rsm_input_builder.py

Step 4 — Validator: cross-check all against both plan docs
```

---

## Downstream consumers (unchanged interface)

Once `enrich_region_data` populates `source_quality` in `data.json`, all downstream reads flow through `RegionEntry`:

- **Region card badge** in app: reads `data.json["source_quality"]` → renders `"8A · 5B · 2C"`
- **Board PDF footer**: reads `RegionEntry.source_quality` → renders tier counts per region page
- **Board PPTX speaker notes**: reads `RegionEntry.source_quality` → includes tier summary
- **CISO docx reference list**: reads cluster sources `credibility_tier` → renders `[A] Reuters — url`
- **Evidence panel** in brief view: reads enriched `signal_clusters.json` → tier badges + URLs
- **M5 longitudinal**: `cited=1` already set in `source_appearances` → Trends annotation ready

---

## Why This Is the Right Boundary

Per `agent-boundary-principles.md`:

> *"An agent that does arithmetic is an agent that will eventually hallucinate a number."*
> *"If you can write a unit test for it, code should own it."*

The tier classification rule (`".gov" → A`) is a unit test. The count is arithmetic. The URL match is a dictionary lookup. None of these require judgment. Moving them to code makes the pipeline deterministic and debuggable — when `source_quality` is wrong, there is a stack trace, not a hallucinated count.

The agent is freed to do what only an agent can do: reason about signals, construct narrative, apply language discipline.
