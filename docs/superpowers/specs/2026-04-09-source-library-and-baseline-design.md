# Source Library + Analyst Baseline + Run Summary — Design Spec

**Date:** 2026-04-09
**Status:** Approved (brainstorming + second-pass critique complete; ready for plan generation)
**Scope:** Risk Register tab cleanup, Source Audit → Source Library rename + restructure, analyst baseline per scenario, validation run summary card.
**Boundary:** Pure code work. Zero new agents. Existing Sonnet recommendation + Haiku extraction agents stay unchanged.

---

## 1. Architecture Overview

Three changes, one design:

1. **Source Audit → Source Library** — rename the existing tab and restructure it around two sub-tabs (OSINT, Benchmarks) that surface the two distinct source pools the pipeline draws from.
2. **Analyst Baseline** — a new optional per-scenario block in the register file where the analyst stores their own vetted impact/probability figures, sourced from references they curated. Baseline becomes a third opinion (alongside VaCR and OSINT) in every dimension card.
3. **Run Summary Card** — a deterministic post-validation summary written into `register_validation.json` and rendered at the top of the Risk Register tab. Answers "what changed since last run, where did evidence come from, where are the gaps?"

### File map

| File | Change |
|---|---|
| `tools/register_validator.py` | Add `build_run_summary()` post-pass; thread baseline through Sonnet recommendation prompt; emit `analyst_baseline` and `run_summary` in output |
| `data/registers/{id}.json` | Schema addition: optional `analyst_baseline` block per scenario |
| `output/validation/register_validation.json` | Gains top-level `run_summary` block |
| `data/validation_sources.json` | Schema addition: optional `provenance: "vendor" \| "analyst"` field |
| `data/sources.db` | No schema changes |
| `server.py` | New endpoints: `/api/source-library/osint`, `/api/source-library/benchmarks`, `PATCH /api/registers/{id}/scenarios/{idx}/baseline` |
| `static/index.html` | Remove bottom Source Registry panel from Risk Register tab; add run summary card slot; rename nav `Source Audit` → `Source Library`; add sub-tab markup |
| `static/app.js` | Delete 6 dead source-registry functions; add `renderRunSummary()`, baseline editor, sub-tab switcher, coverage matrix renderer |

No new files. No new tables. No new agents.

### Source pool clarification

The system has two distinct source pools that have always been muddled in the UI:

| Pool | File | Used by | Scope |
|---|---|---|---|
| OSINT sources | `data/sources.db` | Regional analyst reports (collectors → analysts → reports) | Global, region-tagged |
| Benchmark sources | `data/validation_sources.json` | Risk register validation (Phase 1 site-search + recommendation context) | Global, scenario-tagged |

Source Library surfaces both, but with different scoping defaults:
- **OSINT sub-tab:** global, filterable by region/tier/pillar/lifecycle
- **Benchmarks sub-tab:** scoped to active register by default, with "Show all" toggle

---

## 2. Source Library Tab Structure

### Tab rename

`Source Audit` → `Source Library` in main nav. Existing `loadSources()` / `renderSources()` code stays as the foundation; restructured around it, not replaced.

### Sub-tab layout

```
┌─ Source Library ─────────────────────────────────────┐
│  [ OSINT (142) ]  [ Benchmarks (7) ]                 │
│  ─────────────                                       │
│  ...content for active sub-tab...                    │
└──────────────────────────────────────────────────────┘
```

Pill-style sub-tab toggle. Counts come from data. **OSINT is the default** landing view (highest-traffic — analysts checking what fed today's reports).

---

## 3. OSINT Sub-tab

### Purpose

"What sources fueled the regional analyst reports, and how trustworthy/productive have they been?"

### Source pool

`sources.db` → `sources_registry` WHERE `collection_type='osint'`. Global, never scoped to a register (these sources don't belong to registers — they belong to regional analyst reports).

### Filters

- Region: All | APAC | AME | LATAM | MED | NCE
- Tier: All | A | B | C
- Pillar: All | Geo | Cyber | Both
- Lifecycle: All | Active | Stale | Blocked
- Search box (name / domain substring)

### Effectiveness signals — what we compute

A source is *effective* when the regional analyst actually cited it in a report. Five signals matter, all derived from existing tables.

**Run identity definition (resolves region segmentation):** OSINT runs are region-segmented in `sources.db`, so "this run" needs an unambiguous global definition. Adopted rule:

- `current_run_ts` = `MAX(run_timestamp)` across ALL rows in `source_appearances` (the most recent regional run, regardless of which region it was)
- `previous_run_ts` = `MAX(run_timestamp)` across all rows older than the most recent **distinct day** of `current_run_ts` (so two same-day reruns count as one logical run)
- "≤3 runs ago" = appears in any of the 3 most recent distinct `(run_timestamp::date)` values, regardless of region

This trades regional precision for a simple global header. Per-region drilldown is available in the row-expand panel.

| Signal | Definition |
|---|---|
| **Cited rate** | `cited_count / appearance_count` (Python guards divide-by-zero → returns `null` when `appearance_count == 0`) |
| **Lifecycle** | `active` if source appears in any of the 3 most recent distinct run-days; else `stale`; `blocked` overrides both when `blocked=1` |
| **Region footprint** | `DISTINCT region` over all of source's `source_appearances` rows |
| **Pillar split** | `DISTINCT pillar` collapsed to `geo` / `cyber` / `both` |
| **Run delta** | `count(appearances WHERE run_date = current_run_ts::date) − count(appearances WHERE run_date = previous_run_ts::date)`; positive = source gained activity, negative = source quieted |

### Table columns

| # | Source | Tier | Type | Pillar | Regions | Runs | Cited % | Last seen | Δ vs prev | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Reuters | A | news | Both | APAC,MED | 12 | 78% | 2026-04-09 | ↑ +2 | Active |

Default sort: `cited_rate DESC, appearance_count DESC`. Click column header to re-sort. Row click → expand inline appearance history (per-run, per-region, per-pillar).

**Lifetime vs per-run columns:** `Runs`, `Cited %`, `Regions`, `Last seen` are **lifetime** aggregates (full history of the source in `source_appearances`). `Δ vs prev` and `Status` are **per-run** (computed against current/previous run per the run-identity rule above). The table caption must make this distinction explicit so sorting semantics aren't mis-read.

**First-run handling:** on the very first validation run after deployment there is no previous run. `current_run_id` is set normally, `previous_run_id` is `null`, and `run_delta` is `null` for every source (UI renders as `—`).

### Endpoint contract

**`GET /api/source-library/osint`**

Query params (all optional): `region`, `tier`, `pillar`, `lifecycle`, `search`

Response:
```json
{
  "total": 142,
  "filtered": 38,
  "current_run_id": "2026-04-09T08:14:22Z",
  "previous_run_id": "2026-04-08T15:02:11Z",
  "sources": [
    {
      "id": 47,
      "name": "Reuters",
      "domain": "reuters.com",
      "tier": "A",
      "type": "news",
      "pillar": "both",
      "regions": ["APAC", "MED"],
      "appearance_count": 87,
      "cited_count": 68,
      "cited_rate": 0.78,
      "first_seen": "2026-02-14",
      "last_seen": "2026-04-09",
      "lifecycle": "active",
      "run_delta": 2,
      "blocked": false
    }
  ]
}
```

### Computation map

| Field | Computed via |
|---|---|
| `tier`, `type`, `name`, `domain`, `blocked` | direct read from `sources_registry` |
| `pillar` | `DISTINCT source_appearances.pillar` collapsed to `geo`/`cyber`/`both` |
| `regions` | `DISTINCT source_appearances.region` |
| `appearance_count`, `cited_count` | `COUNT(*)` and `COUNT WHERE cited=1` |
| `cited_rate` | Python (handles divide-by-zero) |
| `first_seen`, `last_seen` | `MIN`/`MAX` on `run_timestamp` |
| `lifecycle` | derived per the run-identity rule above |
| `run_delta` | per the run-identity rule above; integer (may be negative) |

One SQL query with grouping + Python post-pass. Server-side filtering applies query params before serializing.

---

## 4. Benchmarks Sub-tab

### Purpose

"What sources back the risk register validation, and which scenarios do they cover?"

### Source pool

`data/validation_sources.json` (vendor reports + any analyst-curated sources flagged with `provenance: "analyst"`).

### Header bar

```
Benchmarks (7) ─ Register: ⓘ Wind Power Plant ▾  ─  [ Source list ]  [ Coverage matrix ]  ─  [ Show all 7 ]
```

- **Register dropdown** shares state with `activeRegister` from Risk Register tab (single source of truth)
- **View toggle:** Source list (default) ⇄ Coverage matrix
- **Show all toggle:** OFF by default; ON ignores active-register filter **for the source list view only**. The Coverage matrix view is **always** scoped to the active register (a global cross-register matrix would be hundreds of rows × 7 sources and is not a useful view).

### Source list view

Filtering: default shows only sources whose `scenario_tags` ∩ `register.scenario_tags` is non-empty. Toggle ON shows all 7.

Columns:

| # | Source | Reliability | Edition | Cadence | Sectors | Scenarios in this register | Last checked | Cited in current run |
|---|---|---|---|---|---|---|---|---|
| 1 | Verizon DBIR | A | 2024 | annual | all | Ransomware, Insider misuse | 2026-04-07 | Ransomware (2026-04-09) |

- **Scenarios in this register** — when toggle OFF: `scenario_tags ∩ register.scenario_tags`. When toggle ON: renders the source's raw `scenario_tags` (the column semantically becomes "Scenario tags covered"). The column header label is swapped in the client when the toggle flips.
- **Cited in current run** = scenarios where this source's `id` appears in evidence in `output/validation/register_validation.json` for the active register's most recent run. `register_validation.json` is overwritten each run, so historical citation is **not** queryable from this file alone. Cell format: comma-separated scenario names, with the run date in parentheses once at the end. Empty if the source was not used in the current run.
- Row click → expand to show which scenarios used the source in the current run with verdict

Sources with `provenance: "analyst"` get a small badge to distinguish them from vendor reports. **Provenance default:** sources without an explicit `provenance` field are treated as `"vendor"` at read time. No data migration needed; existing 7 sources will lazy-default.

### Coverage matrix view

```
                       Verizon  IBM   Dragos  Mandiant  Claroty  Marsh  ENISA   Coverage
Ransomware                ✓      ✓      ✓        ✓                  ✓      ✓      6/7
System intrusion          ✓             ✓        ✓        ✓                ✓      5/7
Insider misuse            ✓      ✓                                                2/7
Accidental disclosure            ✓               ✓                  ✓             3/7
DoS attack                                                                   ✓    1/7  ⚠
Scam or fraud             ✓                                          ✓             2/7
Phishing                                                                           0/7  ⚠
                          ─       ─      ─        ─        ─       ─      ─
Coverage                  4/7    3/7    2/7      3/7      1/7     3/7    4/7
```

- Rows = scenarios from active register
- Columns = the 7 benchmark sources
- Cell = ✓ if source's `scenario_tags` includes the scenario tag (set intersection)
- Right column "Coverage" = sources backing this scenario; ⚠ when ≤ 1
- Bottom row "Coverage" = how many active register scenarios each source supports
- Empty cells = visual gap signals

### Cell click behavior

- ✓ cell (source was cited in current run) → "Verizon DBIR was used for Ransomware in the current run. Verdict: SUPPORT (2026-04-09)"
- ✓ cell (source is tagged but not cited in current run) → "Verizon DBIR is tagged for Ransomware but was not cited in the current run."
- Empty cell → "No benchmark covers `<scenario>` for `<source>`. Suggested action: tag this source if it covers the scenario."
- ⚠ scenario row → "Only 1 source backs `<scenario>`. Validation confidence will be LOW until you add more."

Historical counts ("used in N runs") are intentionally absent — see the historical-citation-depth limitation in Section 8.

### Gap detection — pure code

```python
def coverage_matrix(register, sources):
    matrix = {}
    for scenario in register["scenarios"]:
        scenario_tag = scenario["search_tag"]
        row = {src["id"]: scenario_tag in src["scenario_tags"] for src in sources}
        matrix[scenario_tag] = row
    return matrix
```

Set intersection. No agent. No "kind of covers" judgment — that's exactly what `scenario_tags` is for.

### Endpoint contract

**`GET /api/source-library/benchmarks?register=<id>&show_all=<bool>`**

```json
{
  "register_id": "wind_power_plant",
  "register_name": "Wind Power Plant",
  "scenarios": ["Ransomware", "System intrusion", "Insider misuse", "DoS attack", "Phishing"],
  "sources": [
    {
      "id": "verizon-dbir",
      "name": "Verizon DBIR",
      "url": "...",
      "reliability": "A",
      "edition_year": 2024,
      "cadence": "annual",
      "sector_tags": ["all"],
      "scenario_tags": ["System intrusion", "Ransomware", "Insider misuse", "Scam or fraud"],
      "provenance": "vendor",
      "covered_scenarios": ["Ransomware", "Insider misuse", "System intrusion"],
      "last_checked": "2026-04-07",
      "cited_in_current_run": [
        {"register_id": "wind_power_plant", "scenario": "Ransomware", "run_id": "2026-04-09T14:22:08Z"}
      ]
      // NOTE: when show_all=false, entries in cited_in_current_run are filtered to the active
      // register only. When show_all=true, entries from every register's most recent run are
      // included (but coverage_summary is still omitted — see below).
    }
  ],
  "matrix": {
    "Ransomware":      {"verizon-dbir": true, "ibm-cost-data-breach": true},
    "System intrusion":{"verizon-dbir": true},
    "Phishing":        {"verizon-dbir": false}
  },
  "coverage_summary": {
    "scenarios_with_zero_sources": ["Phishing"],
    "scenarios_with_one_source":  ["DoS attack"],
    "uncovered_count": 1,
    "thinly_covered_count": 1
  }
}
```

**`coverage_summary` scoping rule:** All counts in `coverage_summary` are computed **after** the active-register filter is applied. They reflect gaps for *this register*, never global benchmark coverage. When `show_all=true` is passed, `coverage_summary` is omitted from the response (it's not meaningful without a register scope).

### Benchmark source CRUD endpoints

The baseline picker (Section 5) and the "+ Add source" button on the Benchmarks sub-tab both need to write new entries to `validation_sources.json`. Rather than inventing a new route, we **reuse** the existing endpoints that already back the old Risk Register bottom panel and repoint them:

| Action | Endpoint | Notes |
|---|---|---|
| Add new benchmark source | `POST /api/validation/sources` | Existing route. Body: `{id, name, url, reliability, edition_year, cadence, sector_tags, scenario_tags, provenance}`. Server defaults `provenance="analyst"` when omitted (new sources added via UI are analyst-curated by definition). |
| Delete benchmark source | `DELETE /api/validation/sources/{id}` | Existing route. Must check no active register's `analyst_baseline.*.source_ids` references it — if referenced, return 409 with the list of referring scenarios and let the client decide (delete anyway / cancel). |
| List candidates | `GET /api/validation/candidates` | Existing route. Surfaced by Source Library → Benchmarks as a dismissible "Candidates" section. |
| Promote candidate | `POST /api/validation/candidates/{id}/promote` | Existing route. |
| Dismiss candidate | `DELETE /api/validation/candidates/{id}` | Existing route. |

No new endpoints introduced. Section 7 already keeps these alive server-side; Unit 4 repoints the UI consumers.

---

## 5. Analyst Baseline

### Concept

When the analyst does their own research and finds sources with their own impact/probability values, those numbers need a home in the system. The baseline is **the analyst's own opinion**, anchored to sources they curated, treated as a **third opinion** alongside VaCR (immutable from CRQ app) and OSINT (auto-extracted).

### Decisions

- **Third opinion, not anchor.** VaCR remains the immutable input per CLAUDE.md boundary. The Sonnet recommendation reasons about how the three numbers relate.
- **Optional.** Never blocks a validation run. When absent, dimension cards collapse the baseline row and behave exactly as today.

### Two layers

When an analyst does their own validation work, two distinct things are produced:

#### Layer 1: Source → Benchmarks library (global, reusable)

Any source vetted by hand goes into `validation_sources.json` alongside vendor reports — same shape, same fields, with `provenance: "analyst"` flag. It then appears in:
- Source Library → Benchmarks sub-tab (with badge)
- Coverage matrix automatically (because it has `scenario_tags`)
- Validator's Phase 1 site-search pool

Reusable across every register.

#### Layer 2: Figures → Per-scenario baseline (register-scoped)

Each scenario in a register gets an optional `analyst_baseline` block:

```json
{
  "scenario": "Ransomware",
  "vacr": { ... },
  "search_tag": "ransomware energy",
  "analyst_baseline": {
    "fin": {
      "value_usd": 4200000,
      "low_usd": 1800000,
      "high_usd": 7500000,
      "source_ids": ["my-internal-2026-q1", "verizon-dbir"],
      "notes": "Mid-case anchored to 2025 Q4 internal incident response cost",
      "updated": "2026-04-09",
      "updated_by": "analyst"
    },
    "prob": {
      "annual_rate": 0.12,
      "low": 0.08,
      "high": 0.18,
      "evidence_type": "frequency_rate",
      "source_ids": ["dragos-ics-ot"],
      "notes": "Energy sector base rate from 2024 Dragos report",
      "updated": "2026-04-09",
      "updated_by": "analyst"
    }
  }
}
```

Lives in the register file (e.g. `data/registers/wind_power_plant.json`). Register-scoped because *this scenario in this register* is what the figures apply to.

### How it flows through the validator

When `register_validator.py` runs:

```
For each scenario:
  1. Run OSINT search (existing two-phase Tavily pipeline)
  2. Haiku extracts figures from snippets
  3. Aggregate auto-extracted figures into an "OSINT range"
  4. Read scenario.analyst_baseline if present
  5. Compute verdict with two anchors:
     - VaCR (immutable)
     - Analyst baseline (high-confidence, when present)
  6. Compare OSINT range against both
  7. Sonnet recommendation prompt receives all three: VaCR, baseline, OSINT
```

The Sonnet recommendation gets richer context: *"VaCR says $5M, analyst baseline says $4.2M [$1.8–7.5M], OSINT supports $3–6M. Baseline and OSINT consistent; VaCR within both ranges."*

**Sonnet recommendation prompt addition (concrete):** the existing `_RECOMMENDATION_PROMPT` in `register_validator.py` already takes `vacr`, `fin_result`, `prob_result`, `fin_confidence`, `prob_confidence`, `prob_evidence_type`. The baseline addition adds three optional fields to the prompt template:

```
ANALYST BASELINE (optional, may be null):
  fin:  {baseline_fin_summary}    # e.g., "$4.2M [low $1.8M, high $7.5M], 2 sources"
  prob: {baseline_prob_summary}   # e.g., "0.12/yr [0.08–0.18], frequency_rate, 1 source"
  alignment_fin:  {baseline_fin_alignment}    # "aligned" | "diverged" | "n/a"
  alignment_prob: {baseline_prob_alignment}   # "aligned" | "diverged" | "n/a"

If a baseline is present, your recommendation MUST acknowledge it explicitly:
- If baseline aligns with OSINT: cite the analyst's number as a corroborating signal
- If baseline diverges from OSINT: name the divergence and which range you weight higher (with reason)
- Never silently override the baseline — the analyst put it there deliberately
```

`{baseline_fin_summary}`, `{baseline_prob_summary}`, and the two `alignment_*` values are computed by code (see "Alignment definition" below) and substituted before the prompt is sent. When `analyst_baseline` is null, all four fields are rendered as `"none"` and the new instructions become a no-op.

**Alignment definition (resolves `baseline_aligned_with_osint`):**

| Condition | Result |
|---|---|
| No baseline for the dimension | `n/a` |
| No OSINT range available (insufficient evidence) | `n/a` |
| Baseline `[low, high]` and OSINT `[low, high]` overlap (i.e., `max(b_low, o_low) ≤ min(b_high, o_high)`) | `aligned` |
| Otherwise | `diverged` |

A scenario counts toward `baseline_usage.baseline_aligned_with_osint` only when **both** `alignment_fin` and `alignment_prob` are `aligned` (or one is `aligned` and the other is `n/a`). It counts toward `baseline_diverged_from_osint` when at least one dimension is `diverged`. Pure code, no agent.

### UI — baseline editor

In the Risk Register tab → click scenario → detail panel, below the existing description editor, add a collapsible block:

```
┌─ Analyst Baseline ──────────────────────────────────┐
│  Impact (USD)                                        │
│    Mid: [4,200,000]   Low: [1,800,000]  High: [...] │
│    Sources: [+ Add from library]  • Verizon DBIR    │
│             • my-internal-2026-q1                    │
│    Notes: [Mid-case anchored to 2025 Q4 incident]   │
│                                                      │
│  Probability (annual)                                │
│    Mid: [0.12]   Low: [0.08]   High: [0.18]         │
│    Evidence type: ◉ frequency  ○ prevalence  ○ mixed│
│    Sources: [+ Add]  • Dragos ICS/OT                 │
│    Notes: [...]                                      │
│                                                      │
│  [ Save baseline ]                                   │
└──────────────────────────────────────────────────────┘
```

Default state: collapsed if no baseline saved, expanded if `analyst_baseline` exists.

`+ Add from library` opens a picker modal that lists everything in `validation_sources.json` so the analyst doesn't re-type source metadata — references by ID. **The picker also has an inline `+ Add new source` button** which opens the same source-creation form used by Source Library → Benchmarks. The baseline editor's form state is preserved while the modal is open (held in component state, not refetched). After save, the new source's `id` is auto-selected in the picker so the analyst can finish their baseline edit without leaving the scenario detail panel.

**Orphan reference handling:** if `analyst_baseline.fin.source_ids` (or `prob.source_ids`) contains an `id` that no longer exists in `validation_sources.json` (analyst deleted the source from the library), the editor renders the orphan as a strikethrough chip with a red `(missing)` tag. The validator treats orphans as warnings, not errors — the baseline is still consumed, but the run summary's `errors` array gets a `baseline_orphan_source` entry per orphan. The analyst can click the chip to remove it.

### UI — baseline row in dimension cards

When `valScenario.analyst_baseline?.[dim]` exists, insert a row above the OSINT range:

```
┌─ IMPACT ─────────────────────────────────┐
│  Verdict: SUPPORTS  ┃  OT DATA           │
│                                          │
│  VaCR (CRQ app):   $5,000,000            │
│  Baseline (you):   $4.2M [$1.8–7.5M] ◆   │
│  OSINT range:      $3.1M – $6.4M         │
│                                          │
│  Sources used: 7   ┃   Cited: Verizon... │
└──────────────────────────────────────────┘
```

The ◆ marker = "your number". The validator never overwrites it; only the analyst can.

### Three distinct things, three distinct homes

| Concept | Lives in | Scope | Editable from |
|---|---|---|---|
| Vendor benchmark sources | `validation_sources.json` (`provenance: "vendor"`) | Global | Source Library → Benchmarks |
| Analyst-curated sources | `validation_sources.json` (`provenance: "analyst"`) | Global | Source Library → Benchmarks |
| Analyst figures for a scenario | `register.scenarios[i].analyst_baseline` | Per-register, per-scenario | Risk Register → scenario detail |

### Endpoint contract

**`PATCH /api/registers/{register_id}/scenarios/{scenario_index}/baseline`**

Body: `analyst_baseline` block as defined above (or `null` to clear it).

**Server-side validation rules** (any failure → 422 with field-specific error):

| Rule | Applies to |
|---|---|
| If `fin` present, `low_usd ≤ value_usd ≤ high_usd` | fin block |
| If `prob` present, `low ≤ annual_rate ≤ high` and all in `[0, 1]` | prob block |
| `value_usd`, `low_usd`, `high_usd` must be non-negative numbers | fin block |
| `evidence_type` must be one of `frequency_rate`, `prevalence_survey`, `mixed`, `expert_estimate`, `unknown` | prob block |
| `source_ids` may be empty; entries that don't resolve in `validation_sources.json` are accepted but flagged as orphans on read (not blocked at write — analyst may want to add the source after saving) | both blocks |
| `notes` length ≤ 1000 chars | both blocks |
| At least one of `fin` or `prob` must be present (otherwise client should send `null` to clear) | top level |

`updated` and `updated_by` are server-stamped, not client-provided. Returns the full updated scenario object.

---

## 6. Run Summary Card

### What it answers

After every validation run, an analyst opening the Risk Register tab should see, in one glance:
- *What changed since last run?*
- *Did anything get more or less supported?*
- *Where did new evidence come from?*
- *Where did we draw a blank?*

A scoreboard. Not an essay. No agent prose.

### Where it lives

**Storage:** new top-level `run_summary` block inside `output/validation/register_validation.json`. Co-located with the data it summarizes — single source of truth.

**Single-register constraint:** `register_validator.py` validates exactly one register per invocation today, and `run_summary` codifies that. `register_id` is a singular string, not a list. If multi-register runs are ever introduced, the schema needs to change to `runs: [{register_id, ...}]`. Out of scope for this spec — flagged for future revisitation.

**UI:** Risk Register tab, above the matrix, full-width, collapsible. Default state: expanded after a fresh run, collapsed otherwise (last state remembered in `localStorage`).

### `run_summary` JSON shape

```json
{
  "run_summary": {
    "run_id": "2026-04-09T14:22:08Z",
    "previous_run_id": "2026-04-08T09:11:47Z",
    "register_id": "wind_power_plant",
    "register_name": "Wind Power Plant",
    "duration_seconds": 142,

    "scenarios": {
      "total": 7,
      "validated": 7,
      "skipped": 0
    },

    "verdicts": {
      "current":  { "support": 4, "challenge": 1, "insufficient": 2 },
      "previous": { "support": 3, "challenge": 1, "insufficient": 3 },
      "deltas": [
        { "scenario": "Ransomware", "dim": "fin",  "from": "insufficient", "to": "support",   "direction": "improved" },
        { "scenario": "DoS attack", "dim": "prob", "from": "support",      "to": "challenge", "direction": "weakened" }
      ]
    },

    "sources": {
      "queried": 47,
      "matched": 19,
      "new_this_run": [
        { "id": 218, "name": "CISA ICS Advisory", "tier": "A", "scenarios": ["System intrusion"] }
      ],
      "dropped_this_run": [
        { "id": 144, "name": "old-blog.example.com", "reason": "blocked" }
      ],
      "by_tier": { "A": 11, "B": 6, "C": 2 }
    },

    "evidence": {
      "fin_extracted":  14,
      "prob_extracted": 9,
      "fin_after_iqr_filter":  11,
      "prob_after_iqr_filter": 8,
      "outliers_removed": 4
    },

    "coverage_gaps": [
      { "scenario": "Phishing", "issue": "no benchmark sources tagged" },
      { "scenario": "Supply chain compromise", "issue": "only 1 source — confidence LOW" }
    ],

    "baseline_usage": {
      "scenarios_with_baseline": 3,
      "baseline_aligned_with_osint": 2,
      "baseline_diverged_from_osint": 1
    },

    "errors": []
  }
}
```

### Where each field is computed

| Field | Computed by | How |
|---|---|---|
| `run_id` | `register_validator.py` | `datetime.utcnow().isoformat() + "Z"` at start of `main()` |
| `previous_run_id` | `register_validator.py` | Read prior `register_validation.json.run_summary.run_id` before overwriting; `null` if file absent or lacks `run_summary` |
| `duration_seconds` | `register_validator.py` | `time.monotonic()` bracket around the scenario loop, rounded to the nearest second, emitted as int |
| `verdicts.current` | scenario results | Tally |
| `verdicts.previous` | from prior file | Tally; `null` on first run |
| `verdicts.deltas` | join on `(scenario, dim)` | Diff; empty list on first run |
| `sources.queried` | `register_validator.py` | Count of **unique benchmark source IDs submitted to Phase 1 Tavily site-search** across all scenarios in the run (de-duped — if Verizon DBIR is queried for 5 scenarios, it counts once) |
| `sources.matched` | `register_validator.py` | Count of **unique source IDs whose Phase 1 results contributed at least one non-empty snippet to Haiku extraction** (i.e., the source actually yielded evidence). `matched ≤ queried` is invariant. |
| `sources.new_this_run` | sources cited this run not in prior file | Set diff on `cited` source IDs; empty list on first run |
| `sources.dropped_this_run` | sources in prior, absent now | Set diff + check `blocked` flag; empty list on first run |
| `sources.by_tier` | `register_validator.py` | Tally of `tier` across the `matched` set (not `queried`) |
| `evidence.*` | counters incremented during phase 1+2 | In-loop — **see instrumentation note below** |
| `coverage_gaps` | post-pass | Scan results for `verdict=insufficient` + source count ≤ 1 (matches Section 4 ⚠ rule) |
| `baseline_usage` | post-pass | Per Section 5 alignment definition. Note: `scenarios_with_baseline ≥ baseline_aligned_with_osint + baseline_diverged_from_osint` — the remainder are scenarios with a baseline where **both** dimensions resolved to `n/a` (baseline present but no alignment signal possible, e.g. OSINT returned insufficient evidence). |
| `errors` | exception capture | Append-on-fail; orphan baseline source refs append `baseline_orphan_source` entries |

**Verdict enum case:** JSON uses lowercase (`"support"`, `"challenge"`, `"insufficient"`) in `run_summary`. The existing scenario-level `verdict` field in `register_validation.json` should be the source of truth — Builder A must confirm its case convention before writing the summary and, if the existing field is uppercase, normalise to lowercase inside `build_run_summary()` only. UI uppercases for display.

100% deterministic. Single Python function `build_run_summary(current_results, previous_path)` called at the end of `main()`.

**Instrumentation note for Builder A:** the validator does **not** currently track `fin_extracted`, `prob_extracted`, `fin_after_iqr_filter`, `prob_after_iqr_filter`, or `outliers_removed` as named counters. These need to be added as part of Unit 1. Recommended approach: a `RunCounters` dataclass (or simple dict) instantiated at the top of `main()`, mutated inside `validate_scenario()` and the IQR filter functions, then snapshotted into the `evidence` block. Builder A must verify the counter increments match the figure flow at every collection point — this is a validator-checked invariant: `fin_after_iqr_filter ≤ fin_extracted` always, same for prob.

### Card layout

```
┌─ Last validation run ────────── 2026-04-09 14:22  (2m 22s)  ▾ ─┐
│                                                                 │
│  VERDICTS    SUPPORT  4 (+1)   CHALLENGE  1 (–)   INSUF.  2 (–1)│
│                                                                 │
│  SOURCES     19 matched  ·  +1 new (CISA ICS)  ·  –1 dropped    │
│              Tier A: 11   Tier B: 6   Tier C: 2                 │
│                                                                 │
│  EVIDENCE    Fin: 11/14 figures  ·  Prob: 8/9  ·  4 outliers cut│
│                                                                 │
│  GAPS        ⚠ Phishing — no benchmark sources                  │
│              ⚠ Supply chain — only 1 source                     │
│                                                                 │
│  BASELINE    3 scenarios  ·  2 aligned  ·  1 diverged           │
│                                                                 │
│  CHANGES     ↑ Ransomware (fin):  insufficient → SUPPORT        │
│              ↓ DoS attack (prob): support → CHALLENGE           │
│                                                                 │
│  [ View source library ]  [ Re-run validation ]                 │
└─────────────────────────────────────────────────────────────────┘
```

- `(+N)` / `(–N)` are deltas from previous run
- `↑ Ransomware` click → scrolls matrix to that row + opens detail
- ⚠ gap click → jumps to Source Library → Benchmarks → coverage matrix → that scenario row
- `View source library` → switches to Source Library tab
- Collapsed state shows just header: `Last run 2026-04-09 14:22 — 4 SUPPORT, 1 CHALLENGE, 2 INSUF · 2 changes · 2 gaps`

### Endpoint contract

No new endpoint. `/api/register-validation/results` already returns the file — extending it adds `run_summary` automatically. UI fetches it on Risk Register tab activation.

---

## 7. Risk Register Tab Cleanup

### What gets removed

**`static/index.html` lines 1098–1125** — entire bottom Source Registry panel:
- `toggleSourceRegistry()` toggle button
- `val-sources` div + add-source form
- `val-candidates` div + accept/reject buttons
- Two-column grid wrapper

**`static/app.js` lines 2858–3052** — six dead functions:
- `toggleSourceRegistry`
- `loadValSources`
- `submitAddSource`
- `deleteValSource`
- `loadValCandidates`
- `promoteCandidate`
- `dismissCandidate`

**`server.py`** — keep validation source/candidate endpoints alive (Phase 2 may still want them) but mark with `# served by Source Library tab as of 2026-04-09`. UI consumers repointed to new endpoints.

**State variables** in `app.js` global state — drop `valSources`, `valCandidates`, `sourceRegistryOpen`.

### What gets added

**1. Run summary card slot** — directly below `register-bar`:

```html
<div id="register-bar">...</div>
<div id="rr-run-summary-card" class="rr-run-summary"></div>  <!-- NEW -->
<div id="rr-matrix">...</div>
```

`renderRunSummary(summary)` called as part of register-load. Empty summary → render nothing.

**2. Analyst baseline editor** — below `descriptionEditor` in `_renderScenarioDetail`. Collapsible block as designed in Section 5.

**3. Baseline row in dimension cards** — `_renderRegValDimension` extension as designed in Section 5.

### Where things relocate

| Old location (Risk Register tab) | New location |
|---|---|
| Bottom panel: Sources list | Source Library → Benchmarks → Source list |
| Bottom panel: Add source form | Source Library → Benchmarks → "+ Add source" modal |
| Bottom panel: Candidates queue | Source Library → Benchmarks → Candidates section |
| Source Audit tab | Renamed → Source Library tab; sources content → OSINT sub-tab |

The Risk Register tab becomes register-focused: matrix on top, run summary above it, scenario detail panel on the right with baseline editor. Nothing about source management lives there anymore.

### Final layout

```
┌─ Risk Register ─────────────────────────────────────────────────┐
│  ▣ Active: Wind Power Plant · 7 scenarios · Switch ▾             │
│                                                                  │
│  ┌─ Last validation run ─ 2026-04-09 14:22 ─ ▾ ─┐               │
│  │ VERDICTS  4 SUPPORT (+1)  1 CHALLENGE  2 INS │               │
│  └──────────────────────────────────────────────┘               │
│                                                                  │
│  ┌─────────────────────────┬──────────────────────────────────┐ │
│  │  Scenario matrix         │  Scenario detail                  │ │
│  │  (existing 4-column)     │   - Description (editable)        │ │
│  │                          │   - Analyst Baseline (collapsible)│ │
│  │                          │   - IMPACT card (with baseline)   │ │
│  │                          │   - PROBABILITY card              │ │
│  │                          │   - Analyst Note (Sonnet)         │ │
│  └─────────────────────────┴──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Data Flows + Computation Map

### End-to-end flow

```
                            ┌──────────────────────────┐
                            │  User actions in UI      │
                            └────────────┬─────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ▼                                ▼                                ▼
┌─────────────────┐         ┌─────────────────────┐         ┌──────────────────────┐
│ Edit baseline   │         │ Trigger validation  │         │ Open Source Library  │
│ on a scenario   │         │ run                 │         │ tab                  │
└────────┬────────┘         └──────────┬──────────┘         └──────────┬───────────┘
         │ PATCH                       │                               │ GET
         ▼                             ▼                               ▼
┌─────────────────┐         ┌─────────────────────┐         ┌──────────────────────┐
│ /api/registers  │         │ register_validator  │         │ /api/source-library  │
│  /{id}/         │         │  .py main()         │         │  /osint              │
│  scenarios/     │         │                     │         │ /api/source-library  │
│  {idx}/baseline │         │ 1. Load register    │         │  /benchmarks         │
└────────┬────────┘         │ 2. Phase 1 OSINT    │         └──────────┬───────────┘
         │ writes           │ 3. Phase 2 OSINT    │                    │ reads
         ▼                  │ 4. Haiku extract    │                    ▼
┌─────────────────┐         │ 5. IQR filter       │         ┌──────────────────────┐
│ data/registers/ │ ◀───────┤ 6. Read baseline    │         │ sources.db           │
│  {id}.json      │  reads  │    from register    │         │ validation_sources   │
│                 │         │ 7. Verdict compute  │ ◀───────┤  .json               │
│ scenarios[i].   │         │    (VaCR vs base    │  reads  │ register_validation  │
│ analyst_baseline│         │     vs OSINT)       │         │  .json               │
└─────────────────┘         │ 8. Sonnet recom-    │         └──────────────────────┘
                            │    mendation        │
                            │ 9. build_run_       │
                            │    summary()        │
                            └──────────┬──────────┘
                                       │ writes
                                       ▼
                            ┌──────────────────────────┐
                            │ output/validation/       │
                            │  register_validation.json│
                            │                          │
                            │ + run_summary {...}      │
                            │ + scenarios[]            │
                            │   .analyst_baseline      │
                            │   .recommendation        │
                            └──────────────────────────┘
                                       │
                                       │ read by
                                       ▼
                            ┌──────────────────────────┐
                            │ Risk Register tab UI     │
                            └──────────────────────────┘
```

### Single source of truth audit

| Datum | Authoritative file | Read by | Never derived elsewhere |
|---|---|---|---|
| VaCR | `data/registers/{id}.json` | validator, UI | ✅ |
| Analyst baseline | `data/registers/{id}.json` per scenario | validator, UI | ✅ |
| Vendor benchmark sources | `data/validation_sources.json` | validator (Phase 1), Source Library Benchmarks | ✅ |
| OSINT source registry | `data/sources.db` | regional collectors, Source Library OSINT | ✅ |
| Validation results | `output/validation/register_validation.json` | UI | ✅ |
| Run summary | `output/validation/register_validation.json` → `run_summary` | UI | ✅ |
| Coverage matrix | computed on-demand | nobody (never persisted) | ✅ |
| OSINT effectiveness signals | computed on-demand from sources.db | nobody (never persisted) | ✅ |

The coverage matrix and OSINT effectiveness signals are always computed live, never stored. Edits to `validation_sources.json` or `sources.db` are reflected immediately without a re-run.

**Known limitation — historical citation depth:** `register_validation.json` is overwritten each validation run, so "which sources were cited" is only queryable for the **current run**. Historical citation patterns (e.g., "Verizon DBIR has been cited in 4 of the last 6 runs") would require either (a) archiving validation runs to `output/runs/` and scanning them, or (b) introducing a `validation_appearances` table mirroring `source_appearances`. Both are out of scope for this spec — the Benchmarks sub-tab uses `Cited in current run` only and the column header makes that explicit. Flagged for future work.

---

## 9. Boundary Check (against agent-design-principles + agent-boundary-principles)

Core rule: **Agents own reasoning. Code owns correctness.**

| Component | Type of work | Owner | Status |
|---|---|---|---|
| `run_summary` aggregation | Counting, diffing, JSON I/O | CODE (`register_validator.py`) | Pure |
| Verdict deltas (prev vs current) | Set ops + comparison | CODE | Pure |
| OSINT effectiveness signals | SQL aggregation | CODE (server endpoint) | Pure |
| Benchmark coverage matrix | Set intersection | CODE (server endpoint) | Pure |
| Baseline editor + PATCH | Form validation, JSON write | CODE | Pure |
| Source classification (`asset_specific`/`company_scale`/`general`) | Language judgment | AGENT — already Haiku, unchanged | Correct |
| `recommendation` text per scenario | Synthesis + caveats + tone | AGENT — already Sonnet, unchanged | Correct |
| Sub-tab UI, run summary card, view toggles | DOM rendering | CODE (vanilla JS) | Pure |

**No new agents.** Every new component is deterministic. Existing Haiku context-tagging and Sonnet recommendation stay exactly where they are.

**No boundary violations.** Sonnet recommendation is not asked to "summarize the run" or "compute deltas" (would push reasoning onto code). Code does not invent verdict text or judge sources (would push correctness onto agents).

**Tool Permission Model respected.** New server endpoints run in the FastAPI process (orchestrator-owned). No background agents introduced.

---

## 10. Build Sequence

Five buildable units, ordered by dependency. Builder/Validator pairings noted (CLAUDE.md Engineering Protocol).

### Unit 1 — Validator backend (`register_validator.py`)
- **Builder A (Sonnet):** (1) Add `RunCounters` instrumentation in `main()` and increment at every figure-collection / IQR-filter point. (2) Add `build_run_summary()` post-pass that reads prior `register_validation.json` before overwrite, computes deltas, applies the alignment rules from Section 5, returns the `run_summary` block. (3) Thread `analyst_baseline` through `validate_scenario()` — read from register file, compute alignment per dimension, inject baseline summary + alignment fields into the Sonnet recommendation prompt template per Section 5. **Verify the actual prompt symbol name first** (`search_symbols` / `grep` for `_RECOMMENDATION_PROMPT` — the spec asserts this name but Builder A must confirm before editing; if it's different, adapt and note the real name in the PR). (4) Write `analyst_baseline` to scenario result schema as a passthrough field. (5) Append orphan source warnings to `run_summary.errors`. (6) Confirm the existing scenario-level verdict case convention and normalise to lowercase inside `build_run_summary()` if necessary (per Section 6 "Verdict enum case" rule).
- **Validator (Sonnet):** Read back the schema, run validator on a wind-power fixture **with** a hand-crafted baseline on at least one scenario and an intentional orphan source ID on another. Confirm: `run_summary` matches contract from Section 6; `RunCounters` invariants hold (`fin_after_iqr_filter ≤ fin_extracted`); orphan flagged in `errors`; alignment rule produces expected `aligned`/`diverged`/`n/a` values.
- **Blocks:** Unit 2.

### Unit 2 — Server endpoints (`server.py`)
- **Builder B (Sonnet):** Add `/api/source-library/osint` (with run-identity rule from Section 3), `/api/source-library/benchmarks` (with active-register scoping + `show_all` rule from Section 4 + `coverage_summary` scoping rule), `PATCH /api/registers/{id}/scenarios/{idx}/baseline` (with all validation rules from Section 5 + server-stamped `updated`/`updated_by`). Confirm `/api/register-validation/results` automatically returns `run_summary` after Unit 1. Add a tiny `provenance_default()` helper that returns `"vendor"` when the field is missing — used everywhere benchmark sources are read.
- **Validator (Sonnet):** Hit each endpoint with curl. Verify JSON shapes match Sections 3, 4, 5, 6. Test PATCH 422 paths (low > high, prob outside [0,1], missing both fin and prob). Test orphan source_id is accepted on PATCH (200, not 422).
- **Depends on:** Unit 1.

### Unit 3 — Source Library tab (`static/index.html`, `static/app.js`)
- **Builder C (Sonnet):** Rename `Source Audit` → `Source Library` in nav. Add OSINT/Benchmarks sub-tab markup. **Refactor the existing `loadSources()` / `renderSources()` into `loadSourceLibraryOSINT()` / `renderSourceLibraryOSINT()` — preserve the existing pagination, search, and row-expand behaviour; only remap the endpoint to `/api/source-library/osint` and adapt the row schema for the new columns.** Implement `loadSourceLibraryBenchmarks()`, `renderCoverageMatrix()`, sub-tab switcher, view toggle, `+ Add new source` modal. **The modal MUST be exposed globally as `window.openAddBenchmarkSourceModal(opts)` so Unit 4's baseline picker can call it** — this is the coupling contract. The "Show all" toggle must hide the matrix view (or grey out the toggle on the matrix view) per Section 4 scoping rule. Swap the "Scenarios in this register" column header to "Scenario tags covered" when `show_all=true`.
- **Validator (Sonnet):** Switch tabs, confirm OSINT default, filters work, Benchmarks toggles between Source list and Coverage matrix, gap cells flag correctly. Verify `show_all=true` does NOT change the matrix scope and swaps the column header correctly. Verify `window.openAddBenchmarkSourceModal` is defined on `window` after the tab module loads (console check).
- **Depends on:** Unit 2.
- **Blocks:** Unit 4 (baseline picker depends on the shared modal).

### Unit 4 — Risk Register tab cleanup + run summary card (`static/index.html`, `static/app.js`)
- **Builder D (Sonnet):** Delete bottom panel + 6 dead JS functions. Add `<div id="rr-run-summary-card">`. Implement `renderRunSummary()` (collapsed/expanded state in `localStorage`, click-to-scroll-to-scenario for delta rows, click-to-jump-to-coverage-matrix for gap rows). Add baseline editor block to scenario detail panel — collapsible, holds form state across modal opens. The picker's `+ Add new source` button calls `window.openAddBenchmarkSourceModal({ onSave: (newSourceId) => ... })` which Unit 3 provides; Builder D may assume this function exists because Unit 3 ships first. If it is unexpectedly absent at runtime, the `+ Add new source` affordance must feature-detect and hide gracefully. Implement `saveBaseline()` with client-side range-validation matching server rules. Extend `_renderRegValDimension` with baseline row + `◆` marker. Render orphan source IDs as strikethrough chips with click-to-remove.
- **Validator (Sonnet):** Open the tab, confirm bottom panel gone, run summary renders against fixture data with all six rows (verdicts, sources, evidence, gaps, baseline, changes). Baseline edits persist via PATCH and round-trip on reload. Orphan chip renders correctly. Click handlers fire correctly (delta → scroll, gap → jump). Opening `+ Add new source` from the picker calls into Unit 3's modal successfully.
- **Depends on:** Unit 2, Unit 3.

### Unit 5 — End-to-end smoke test (orchestrator)
Run a full validation against the wind power register fixture. Verify:
- `register_validation.json` contains `run_summary`
- Risk Register tab shows the card
- Baseline edit round-trips through PATCH
- Coverage matrix highlights the right gaps
- OSINT effectiveness page loads under 200ms

### Parallelism map

```
Unit 1 (validator backend)
    └──> Unit 2 (server endpoints)
              └──> Unit 3 (Source Library UI)
                        └──> Unit 4 (Risk Register UI + baseline editor) ──> Unit 5 (smoke test)
```

**Sequential, not parallel.** Unit 3 must land before Unit 4 because Unit 4's baseline picker calls `window.openAddBenchmarkSourceModal()` — a global that only exists once Unit 3's Source Library tab module has loaded. The original plan had Units 3 and 4 parallel; that was a defect caught in review. If the coupling becomes painful later, extract the shared modal into a separate shared-components module (not scoped here).

Each builder is a Sonnet agent in a TeamCreate team, validators are separate Sonnet agents. Opus orchestrates, runs all Bash itself.

**Parallelism recovery:** Unit 2 can itself be split into "endpoints only" (blocks 3) and "PATCH + validation rules" (blocks 4), allowing Unit 3 to start earlier. Left as an optimisation for the plan writer, not a mandate.

---

## 11. What does NOT change

- No agent definitions touched
- No new tables in `sources.db`
- No new files in `data/`
- No changes to `regional-analyst-agent`, `gatekeeper-agent`, `global-builder-agent`, `rsm-formatter-agent`
- No changes to OSINT collectors
- No changes to the CRQ app boundary (VaCR still immutable input)
- No deleted endpoints (only repointed UI consumers)

---

## 12. Known limitations (acknowledged, out of scope)

These are intentional simplifications. Each is documented inline at the relevant section but listed here for visibility:

1. **Historical citation depth.** `register_validation.json` is overwritten each run, so the Benchmarks "Cited in current run" column reflects only the most recent run for the active register. Multi-run citation history would need archived runs or a new appearances table. (Section 8)
2. **Single register per validation run.** `run_summary.register_id` is singular. If multi-register runs are introduced, `run_summary` schema must change to a list. (Section 6)
3. **OSINT run identity is global, not per-region.** "Last 3 runs" counts the 3 most recent distinct run-days across all regions, so a source last seen in APAC 5 days ago is "stale" even if APAC hasn't run since. Per-region drilldown is available in row-expand. (Section 3)
4. **Orphan baseline source refs are warnings, not errors.** The validator consumes the baseline anyway and emits `baseline_orphan_source` entries to `run_summary.errors`. The analyst is expected to clean up via the editor. (Section 5)
5. **`coverage_summary` is suppressed when `show_all=true`.** Cross-register coverage counts have no useful interpretation. (Section 4)
6. **Unit 3 and Unit 4 are sequential, not parallel.** Unit 4's baseline picker depends on a global `window.openAddBenchmarkSourceModal()` defined by Unit 3. Parallelism recoverable by splitting Unit 2 or extracting a shared-components module; left as an optional optimisation for the plan writer. (Section 10)
7. **Benchmark source CRUD reuses existing `/api/validation/sources` routes.** No new POST/DELETE endpoints are introduced; Unit 4 repoints UI consumers to the existing routes with `provenance` defaulted to `"analyst"` for UI-added sources. (Section 4)

## 13. Open questions for review

None at design time — all clarifying questions resolved during brainstorming, all first- and second-pass critique gaps folded in. Spec ready for plan generation.
