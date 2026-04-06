# Master Build Plan — Output Alignment + Source Quality Boundary Fix
**Date:** 2026-04-05
**Status:** Ready to build
**Supersedes:** `2026-04-05-output-alignment-plan.md` + `2026-04-05-source-quality-boundary-fix.md`
**These two plans are combined here with correct execution order, dependency wiring, and the missing `source_quality` fix.**

---

## What This Builds

Two complementary fixes that must run in order:

**Plan A — Source Quality Boundary Fix**
Moves `source_quality` computation out of the analyst agent (where it violates the boundary rule) into deterministic code. An LLM should not count URLs or classify tiers — code should.

**Plan B — Output Alignment**
Refactors all exporters (PDF, PPTX, CISO docx, RSM brief) to draw from a single canonical extraction layer in `report_builder.py`. Exporters become pure renderers. `RegionEntry` gains all pre-extracted intelligence sections — including `source_quality` from Plan A.

**Why this order:** Plan A populates `source_quality` in `data.json`. Plan B reads it into `RegionEntry` and exposes it to all exporters. Plan B without Plan A means `source_quality` is never populated.

---

## Root Causes Being Fixed

### Root cause 1 — Boundary violation in M4
`regional-analyst-agent.md` was instructed to scan signal file URLs, classify them into tiers (A/B/C), count uniques, and write `source_quality` to `data.json`. This is 100% deterministic work — URL pattern matching and arithmetic. Code territory. An agent doing this will eventually hallucinate a count with no stack trace.

**Fix:** Remove from agent. Add `enrich_region_data()` function in `update_source_registry.py`. Code runs after analyst exits, before CISO export.

### Root cause 2 — Three exporters, three content pipelines
`export_ciso_docx.py` contains all the real intelligence extraction logic (sentence splitting, threat actor detection, impact filtering, citation processing). `report_builder.py` does thin `board_bullets` extraction (4 first sentences). PDF and PPTX render that thin data and produce one-sentence-per-quadrant output. They also say "CISO Edition" on the cover.

**Fix:** Move all extraction logic into `report_builder.py`. Exporters become pure renderers.

### Root cause 3 — RSM brief has implicit fallbacks
`rsm-formatter-agent.md` declares 6 inputs. 3 are frequently absent (`seerist_signals.json`, `region_delta.json`, `audience_config.json`). The agent guesses what to do. Fallback routing is code territory — the agent should receive clean inputs and write.

**Fix:** Create `tools/rsm_input_builder.py` — code-owned fallback handler. Agent spec gets typed contract.

---

## Decisions Locked

| Decision | Choice |
|---|---|
| Board PDF | Full CISO mirror — same 7 sections, HTML→PDF |
| Board PPTX | One slide per escalated region, condensed. Framing first, design polish later. |
| RSM brief v1 | Works with existing OSINT data. No Seerist dependency. Explicit fallback in code. |
| VaCR in RegionEntry | Removed. VaCR is not intelligence. Not in the extraction layer. |
| Exec report | Not in scope. CISO report is canonical. Exec gets the same output. |
| source_quality in RegionEntry | Added. Populated by Plan A code, exposed to all exporters via Plan B. |
| PPTX design polish | Future session — brainstorm with `data/pptx_prompt_vault.md` |

---

## Plan A — Source Quality Boundary Fix

### A-1: Remove source_quality from analyst agent

**File:** `.claude/agents/regional-analyst-agent.md`

Remove:
- The "Deriving `source_quality` counts" section (URL scanning, tier classification rules, counting instructions)
- `source_quality` from the self-validation checklist
- Any instruction to write `source_quality` to `data.json`

The agent retains all intelligence work: prose, escalation rationale, cluster naming, scenario judgment, signal type. It does not touch source metrics.

### A-2: Add `enrich_region_data()` to `update_source_registry.py`

Three deterministic functions added at bottom of file:

**`_compute_source_quality(conn, region, run_id)` → SQL + arithmetic**
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

**`_enrich_cluster_sources(conn, region)` → URL + tier lookup**

For each cluster source `name` in `signal_clusters.json`:
- Lookup matching row in `sources_registry` by `name` (exact first, domain fuzzy second)
- If matched: add `url` and `credibility_tier` to the source object
- If unmatched (generic label like "Tavily Research", no registry entry): `url: null`, `credibility_tier: null`, log as unresolved
- Write enriched clusters back to `output/regional/{region}/signal_clusters.json`

**`_set_cited_flags(conn, region, run_id)` → SQL UPDATE (M5 work pulled forward)**

For each URL found in enriched cluster sources:
- Match to `source_id` in `sources_registry`
- `UPDATE source_appearances SET cited=1 WHERE source_id=? AND run_id=? AND region=?`

**`_validate_source_quality(data)` → schema gate**
```python
def _validate_source_quality(data):
    sq = data.get("source_quality")
    assert sq is not None, "source_quality missing from data.json"
    assert all(isinstance(sq.get(k), int) for k in ["tier_a", "tier_b", "tier_c", "total"])
    assert sq["total"] == sq["tier_a"] + sq["tier_b"] + sq["tier_c"]
```
Fails hard if validation fails — pipeline stops, not silently broken.

**`enrich_region_data(region, run_id)` → orchestrator**

Calls the four functions above in order. Writes `source_quality` into `data.json`. Returns the result dict.

### A-3: Wire into pipeline (correct order)

**CRITICAL:** `update_source_registry.py` must run BEFORE `enrich_region_data`. The SQL query in `_compute_source_quality` reads from `source_appearances` — that table is populated by `update_source_registry.py`. Reversed order = all-zero source_quality with no error.

**File:** `.claude/commands/run-crq.md`
Move `update_source_registry.py` to run per-region (after analyst agent). Then add `enrich_region_data` call directly after it.

**File:** `server.py`
Pipeline order after analyst agent exits:
1. `update_source_registry.py` (populates source_appearances)
2. `enrich_region_data(region, run_id)` (reads source_appearances, writes source_quality)
3. `export_ciso_docx.py` (reads enriched data.json)

### Plan A — Files Changed

| File | Change |
|---|---|
| `.claude/agents/regional-analyst-agent.md` | Remove source_quality derivation block + checklist item |
| `tools/update_source_registry.py` | Add 4 functions + `enrich_region_data()` orchestrator |
| `.claude/commands/run-crq.md` | Add Phase 5 `enrich_region_data` call |
| `server.py` | Wire Phase 5 into pipeline |

---

## Plan B — Output Alignment

### B-1 (ST-1): Enrich `report_builder.py` — single extraction layer

**Move from `export_ciso_docx.py` into `report_builder.py`:**
- `_extract_threat_actor()` function
- `_intel_bullets()`, `_adversary_bullets()`, `_impact_bullets()`, `_watch_bullets()`, `_action_bullets()` functions
- `_signal_type_label()` function
- `_SCENARIO_ACTIONS` dict
- `_SIGNAL_TYPE_LABELS` dict
- `_STATE_ACTORS`, `_CRIMINAL_PAT` regex patterns

**Update `RegionEntry` dataclass — full target schema:**

```python
@dataclass
class RegionEntry:
    # identity
    name: str
    status: RegionStatus

    # metadata (existing)
    scenario_match: str | None
    admiralty: str | None
    velocity: str | None
    severity: str | None
    dominant_pillar: str | None
    signal_type: str | None
    confidence_label: str | None
    threat_characterisation: str | None
    top_sources: list[str] | None

    # raw pillar text (kept for reference, used by extraction functions)
    why_text: str | None
    how_text: str | None
    so_what_text: str | None

    # pre-extracted intelligence sections (NEW — from extraction functions)
    threat_actor: str | None          # extracted from why+how text
    signal_type_label: str | None     # mapped display label
    intel_bullets: list[str]          # sentences from why_text, max 3
    adversary_bullets: list[str]      # sentences from how_text, max 2
    impact_bullets: list[str]         # sentences from so_what_text, non-VaCR, max 2
    watch_bullets: list[str]          # tradecraft from how/so_what overflow
    action_bullets: list[str]         # scenario-mapped recommended actions

    # source quality (NEW — from Plan A, read from data.json)
    source_quality: dict | None       # {tier_a, tier_b, tier_c, total}

    # REMOVED: vacr — VaCR is not intelligence
    # REMOVED: board_bullets — deprecated, exporters use section fields above
```

**`export_ciso_docx.py` after ST-1:**
- Remove all extraction functions (now in report_builder)
- Import extraction results from `RegionEntry` fields directly
- Becomes a pure renderer — all section content comes from `entry.intel_bullets`, `entry.adversary_bullets`, etc.
- Citation processing (`_process_citations`, `SourceRegistry`) stays in ciso_docx — it's rendering logic specific to docx format

### B-2 (ST-2): Board PDF — full CISO mirror

**File:** `tools/templates/report.html.j2`

Remove 2×2 `.bullets-grid` layout entirely. Replace per-region page with 7-section layout:

```
Cover page
  Title: "Cyber Risk Intelligence Brief"  ← remove "CISO Edition"
  Status strip: ESCALATED / MONITOR / CLEAR counts
  Date · Pipeline ID · CONFIDENTIAL

Global Posture page
  Executive summary (4-part structure from global_report.json)
  Escalated regions table: Region / Scenario / Confidence / Velocity / Severity

Per-region page (one per escalated region)
  Header: {region name} — {full region name}   [{ESCALATED — GEO-LED}]
  Meta row: Scenario · Threat Actor · Signal Type
  ── Intel Findings ──────────────────────────
    • {intel_bullets[0]}
    • {intel_bullets[1]}  (if present)
    • {intel_bullets[2]}  (if present)
  ── Observed Adversary Activity ─────────────
    • {adversary_bullets[0]}
    • {adversary_bullets[1]}  (if present)
  ── Impact for AeroGrid ─────────────────────
    • {impact_bullets[0]}
    • {impact_bullets[1]}  (if present)
  ── Watch For — Adversary Tradecraft ────────
    • {watch_bullets[0..]}
  ── Recommended Actions ─────────────────────
    • {action_bullets[0..]}
  Footer: velocity · threat characterisation · sources

Appendix page
  Monitor regions with rationale
  Clear regions
  Run metadata
```

CSS changes: remove `.bullets-grid`, `.bullet-cell.*` classes. Add `.section-heading`, `.intel-list` styles.

### B-3 (ST-3): Board PPTX — condensed one-slide-per-region

**File:** `tools/export_pptx.py`

**Cover slide:**
- Remove "CISO Edition" subtitle line
- Title stays: "Global Cyber Risk Intelligence Brief"

**Region slide — replace 2×2 grid with vertical intelligence structure:**

```
Header band (navy):
  Left: {REGION} — {scenario_match}
  Right: severity chip
  Sub: [{status_label}] · Threat Actor: {threat_actor} · {signal_type_label} · Confidence: {confidence_label}

Body (5 labelled rows, each 1 bullet):
  INTEL FINDINGS      {intel_bullets[0]}
  ADVERSARY ACTIVITY  {adversary_bullets[0]}
  IMPACT FOR AEROGRID {impact_bullets[0]}
  WATCH FOR           {watch_bullets[0]}
  RECOMMENDED ACTION  {action_bullets[0]}

Footer:
  {velocity} · {threat_characterisation} · Sources: {top_sources joined}

Speaker notes (full depth):
  Intel Findings: {intel_bullets joined}
  Adversary Activity: {adversary_bullets joined}
  Impact for AeroGrid: {impact_bullets joined}
  Watch For: {watch_bullets joined}
  Recommended Actions: {action_bullets joined}
```

**Appendix slide:** unchanged

### B-4 (ST-4): RSM brief — resilient fallback contract

**File:** `.claude/agents/rsm-formatter-agent.md`

Replace implicit 6-input list with typed contract:

```
Required inputs (pipeline always produces these):
  geo_signals.json      → PHYSICAL & GEO section
  cyber_signals.json    → CYBER section
  data.json             → admiralty, primary_scenario, financial_rank

Optional inputs (use fallback if absent):
  seerist_signals.json  → if absent: use geo_signals.json for PHYSICAL & GEO
  region_delta.json     → if absent: SITUATION = "No comparative data for this period."
                                     EARLY WARNING = "No pre-media anomalies detected this period."
  aerowind_sites.json   → if absent: refer to "AeroGrid regional operations" generically
  audience_config.json  → if absent: address to "Regional Security Manager"
```

Quality gate addition: "Brief must be structurally complete — all section headers present — even if 3 optional inputs are absent."

**New file:** `tools/rsm_input_builder.py`

Code-owned fallback handler. Called by orchestrator before rsm-formatter-agent runs.

```python
"""
tools/rsm_input_builder.py
Assembles RSM agent input manifest with explicit fallbacks.
Code owns the fallback routing. Agent owns the writing.

Returns dict: {path_or_fallback per input, fallback_flags: {input: bool}}
"""
```

For each optional input:
- Check if file exists
- If exists: return real path
- If absent: return fallback path + set `fallback_flags[input] = True`

Passed to rsm-formatter-agent as a clean manifest — agent never decides what to do when a file is missing.

### Plan B — Files Changed

| File | Change | Sub-task |
|---|---|---|
| `tools/report_builder.py` | Add 8 new `RegionEntry` fields (7 sections + source_quality). Move extraction logic from ciso_docx. Remove `vacr`, `board_bullets`. | ST-1 |
| `tools/export_ciso_docx.py` | Remove extraction functions. Read from `RegionEntry` fields. Pure renderer. | ST-1 |
| `tools/templates/report.html.j2` | Replace 2×2 grid with 7-section layout. Fix cover title. | ST-2 |
| `tools/export_pptx.py` | Fix cover. Replace region slide with vertical bullets + speaker notes. | ST-3 |
| `.claude/agents/rsm-formatter-agent.md` | Typed contract with explicit fallback per optional input. | ST-4 |
| `tools/rsm_input_builder.py` | NEW. Code-owned fallback handler. | ST-4 |

---

## Architecture Principles Applied

### Boundary rule

| Task | Owner | Where |
|---|---|---|
| Classify URL into Tier A/B/C | **Code** | `_compute_source_quality()` in update_source_registry.py |
| Count sources per tier | **Code** | `_compute_source_quality()` — SQL + arithmetic |
| Write `source_quality` to data.json | **Code** | `enrich_region_data()` |
| Enrich cluster sources with url + tier | **Code** | `_enrich_cluster_sources()` |
| Set `cited=1` in source_appearances | **Code** | `_set_cited_flags()` |
| Fallback routing for missing RSM inputs | **Code** | `rsm_input_builder.py` |
| Extract sentences from pillar text | **Code** | `report_builder.py` extraction functions |
| Detect threat actor from text | **Code** | `_extract_threat_actor()` in report_builder.py |
| Write intelligence prose | **Agent** | regional-analyst-agent |
| Write RSM brief | **Agent** | rsm-formatter-agent |
| Render HTML / PPTX / DOCX sections | **Code** | Pure renderer exporters |

### Skill contract — RSM formatter after this build

| Field | Value |
|---|---|
| Purpose | Format weekly INTSUM and flash alerts for ex-military RSMs from pipeline intelligence data |
| Inputs (required) | geo_signals.json, cyber_signals.json, data.json |
| Inputs (optional) | seerist_signals.json, region_delta.json, aerowind_sites.json, audience_config.json |
| Outputs | rsm_brief_{region}_{date}.md, rsm_flash_{region}_{datetime}.md |
| Quality gate | All section headers present even with optional inputs absent. Stop hook: rsm-formatter-stop.py |

---

## Full Execution Order

```
PHASE 1 — Plan A (sequential, foundational)

  A-1: Update regional-analyst-agent.md
       → Remove source_quality derivation block

  A-2: Update update_source_registry.py
       → Add enrich_region_data() + 4 sub-functions

  A-3: Wire Phase 5 into run-crq.md + server.py

  [Plan A complete — source_quality now lives in data.json, populated by code]

PHASE 2 — Plan B ST-1 (sequential, must precede B-2/B-3)

  B-ST-1: Update report_builder.py + export_ciso_docx.py
          → RegionEntry gains 8 new fields (including source_quality)
          → export_ciso_docx.py becomes pure renderer

  [ST-1 complete — all exporters can now read RegionEntry section fields]

PHASE 3 — Plan B ST-2/ST-3/ST-4 (parallel)

  B-ST-2: Rewrite report.html.j2  (run_in_background: true)
  B-ST-3: Update export_pptx.py   (run_in_background: true)
  B-ST-4: Update rsm-formatter-agent.md + create rsm_input_builder.py  (run_in_background: true)

PHASE 4 — Validation (sequential)

  Validator: cross-check all changes against Done Criteria
  Orchestrator: accept or loop builders
  TeamDelete
```

---

## Team Structure

- **Orchestrator: Opus** — coordinate, contracts, validate. Does not write code.
- **Builder A: Sonnet** — Plan A (A-1, A-2, A-3)
- **Builder B: Sonnet** — Plan B ST-1 (report_builder.py + export_ciso_docx.py)
- **Builder C: Sonnet** — Plan B ST-2 + ST-3 (report.html.j2 + export_pptx.py)
- **Builder D: Sonnet** — Plan B ST-4 (rsm-formatter-agent.md + rsm_input_builder.py)
- **Validator: Sonnet** — cross-check all builders against this spec

Builders A and B run sequentially. Builders C and D run in parallel after B completes.

---

## What Is NOT in Scope

- Dashboard alignment (follows naturally from RegionEntry fields — separate session)
- PPTX visual design polish (brainstorm with `data/pptx_prompt_vault.md` — future session)
- Seerist API integration (Phase 2 — separate plan)
- Board vs. CISO split into separate audience reports (future — post CISO Phase 1 handoff)
- M5 longitudinal trends heatmap (time-gated, needs 3+ runs with source_quality populated)

---

## Done Criteria

**Plan A:**
- [ ] `regional-analyst-agent.md` has no URL scanning, tier classification, or source_quality writing
- [ ] `update_source_registry.py` has `enrich_region_data()` with 4 sub-functions
- [ ] `_validate_source_quality()` raises exception if source_quality missing or arithmetic wrong
- [ ] Phase 5 wired in `run-crq.md` and `server.py`
- [ ] `data.json` contains `source_quality: {tier_a, tier_b, tier_c, total}` after a run

**Plan B:**
- [ ] `report_builder.py` exposes all 8 new `RegionEntry` fields (7 sections + source_quality)
- [ ] `export_ciso_docx.py` reads from `RegionEntry` fields, contains no extraction logic
- [ ] Board PDF per-region page has 7 intelligence sections
- [ ] Board PDF cover says "Cyber Risk Intelligence Brief" (no "CISO Edition")
- [ ] Board PPTX region slide has vertical bullet structure + speaker notes
- [ ] Board PPTX cover has correct title
- [ ] `rsm_input_builder.py` handles fallback for all 4 optional inputs
- [ ] `rsm-formatter-agent.md` has typed contract with explicit fallback per optional input
- [ ] Validator confirms all output against this spec
- [ ] Pipeline run produces all outputs without error
