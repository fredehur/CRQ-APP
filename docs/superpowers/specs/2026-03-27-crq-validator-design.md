# CRQ Validator — Design Spec
_2026-03-27_

## Problem

CRQ database VaCR figures (e.g. "$22M for ransomware in AME manufacturing") are treated as
immutable ground truth from the enterprise CRQ application. But ground truth drifts. Industry
benchmarks — DBIR, IBM Cost of a Data Breach, Dragos ICS/OT, insurance market reports — update
annually and quarterly. Without a systematic check, stale numbers go undetected.

This feature adds a **CRQ Validation layer**: a weekly harvester that searches for new benchmark
publications, a Haiku extractor that pulls financial figures and scenario tags, and a comparator
that diffs our VaCR figures against external benchmarks. Output surfaces as a persistent dashboard
panel. All flags are advisory — nothing writes back to the CRQ database automatically.

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Validation granularity | Per scenario type (not per region) | Benchmarks are global; region differentiation comes later |
| Cadence | Weekly harvester + event-triggered comparator | Most sources are annual/quarterly; daily is noise |
| Auto-write | Never | VaCR is immutable ground truth — flags are advisory only |
| Dashboard | Persistent panel, all 9 scenarios always visible | Clear signals are as valuable as alerts |
| Source quality gate | Admiralty ≥ B2 only surfaces in flags | Prevents low-quality sources from polluting the signal |
| SEC 8-K filings | Parked for v2 | High value, high parsing complexity |

---

## Architecture

```
tools/
  source_harvester.py      ← weekly: fetches content from known registry (tiered fetch)
  source_discoverer.py     ← weekly: search-driven discovery of unknown sources → candidates
  benchmark_extractor.py   ← Haiku: extracts $ figures + scenario tags from text
  crq_comparator.py        ← deterministic diff of VaCR vs. benchmarks → flags

data/
  validation_sources.json  ← curated source registry (human-controlled — promote from candidates)

output/
  validation_cache/        ← extracted benchmarks keyed by source_id + date (immutable once written)
  validation_candidates.json  ← discovered sources awaiting human review (promote or dismiss)
  validation_flags.json    ← dashboard reads this (rewritten on each comparator run)
  validation_flags.md      ← human-readable summary
```

The validator runs independently of the main CRQ pipeline. Scheduled via `tools/scheduler.py`,
also triggerable manually. Comparator also fires if `data/mock_crq_database.json` hash changes.

### Tiered Fetch Strategy (source_harvester.py)

```
Tier A — Open summary pages
         WebFetch the source landing page → extract headline figures directly

Tier B — Press release / news coverage  (primary path for gated PDFs)
         Search: "{source name} {year} {scenario} cost manufacturing"
         Gets key figures from news coverage even when full report is paywalled

Tier C — Abstract/exec summary PDFs
         Search: "{source name} {year} filetype:pdf"
         Many reports publish free exec summaries even when full report requires registration
```

Same search pattern as the existing OSINT toolchain (Tavily/DDG). No scraping auth required.

### Discovery Loop (source_discoverer.py)

Generates search queries from scenario tags × sector tags × current year:

```
"manufacturing sector ransomware financial impact 2025"
"ICS OT cyber incident cost report 2025"
"wind energy cyber attack cost 2025"
"renewable energy sector data breach cost report"
... (one query per scenario × sector combination)
```

Haiku scores each result: does it contain verifiable $ figures + a matching scenario tag?
Qualifying results → `output/validation_candidates.json` for analyst review.

**Discovery never auto-promotes to the trusted registry.** Analyst promotes or dismisses.
Newly promoted sources start at reliability C until confirmed accurate across two publication cycles.

---

## Source Registry — `data/validation_sources.json`

```json
{
  "sources": [
    {
      "id": "verizon-dbir",
      "name": "Verizon Data Breach Investigations Report",
      "url": "https://www.verizon.com/business/resources/reports/dbir/",
      "cadence": "annual",
      "admiralty_reliability": "A",
      "sector_tags": ["all"],
      "scenario_tags": ["ransomware", "system_intrusion", "web_app_attacks", "social_engineering"],
      "last_checked": null,
      "last_new_content": null
    },
    {
      "id": "ibm-cost-data-breach",
      "name": "IBM Cost of a Data Breach Report",
      "url": "https://www.ibm.com/reports/data-breach",
      "cadence": "annual",
      "admiralty_reliability": "A",
      "sector_tags": ["all", "manufacturing", "energy"],
      "scenario_tags": ["ransomware", "data_exfiltration", "insider_misuse"],
      "last_checked": null,
      "last_new_content": null
    },
    {
      "id": "dragos-ics-ot",
      "name": "Dragos ICS/OT Cybersecurity Year in Review",
      "url": "https://www.dragos.com/year-in-review/",
      "cadence": "annual",
      "admiralty_reliability": "A",
      "sector_tags": ["ics_ot", "energy", "manufacturing"],
      "scenario_tags": ["system_intrusion", "ransomware", "supply_chain"],
      "last_checked": null,
      "last_new_content": null
    },
    {
      "id": "mandiant-mtrends",
      "name": "Mandiant M-Trends",
      "url": "https://www.mandiant.com/m-trends",
      "cadence": "annual",
      "admiralty_reliability": "B",
      "sector_tags": ["all"],
      "scenario_tags": ["ransomware", "system_intrusion", "data_exfiltration"],
      "last_checked": null,
      "last_new_content": null
    },
    {
      "id": "claroty-xiot",
      "name": "Claroty State of XIoT Security",
      "url": "https://claroty.com/resources/reports",
      "cadence": "biannual",
      "admiralty_reliability": "B",
      "sector_tags": ["ics_ot", "manufacturing"],
      "scenario_tags": ["system_intrusion", "supply_chain"],
      "last_checked": null,
      "last_new_content": null
    },
    {
      "id": "marsh-cyber-insurance",
      "name": "Marsh Cyber Insurance Market Report",
      "url": "https://www.marsh.com/en/services/cyber-risk/insights.html",
      "cadence": "annual",
      "admiralty_reliability": "B",
      "sector_tags": ["all", "energy"],
      "scenario_tags": ["ransomware", "data_exfiltration", "business_email_compromise"],
      "last_checked": null,
      "last_new_content": null
    },
    {
      "id": "enisa-threat-landscape",
      "name": "ENISA Threat Landscape",
      "url": "https://www.enisa.europa.eu/topics/cyber-threats/enisa-threat-landscape",
      "cadence": "annual",
      "admiralty_reliability": "B",
      "sector_tags": ["all", "energy"],
      "scenario_tags": ["ransomware", "supply_chain", "social_engineering"],
      "last_checked": null,
      "last_new_content": null
    }
  ]
}
```

Admiralty reliability: **A** = no doubt about authenticity; **B** = known source, minor uncertainty; **C** = not reliable but not ruled out.

---

## Benchmark Extraction Schema

`output/validation_cache/{source_id}/{YYYY-MM-DD}.json`

```json
{
  "source_id": "ibm-cost-data-breach",
  "extracted_date": "2026-03-27",
  "publication_year": 2025,
  "admiralty": {"reliability": "A", "credibility": "1", "rating": "A1"},
  "benchmarks": [
    {
      "scenario_tag": "ransomware",
      "sector": "manufacturing",
      "cost_low_usd": 4200000,
      "cost_median_usd": 5130000,
      "cost_high_usd": 8700000,
      "note": "Manufacturing sector median — all ransomware incidents with confirmed financial impact",
      "raw_quote": "..."
    }
  ]
}
```

---

## Validation Flags Schema — `output/validation_flags.json`

```json
{
  "generated_at": "2026-03-27T06:00:00Z",
  "crq_db_hash": "abc123",
  "scenarios": [
    {
      "scenario": "Ransomware",
      "scenario_id": "S-001",
      "our_vacr_usd": 22000000,
      "verdict": "supported",
      "confidence_admiralty": "A1",
      "benchmark_range_usd": [4200000, 35000000],
      "benchmark_median_usd": 5130000,
      "deviation_pct": 329,
      "flagged_for_review": true,
      "review_reason": "VaCR is 329% above benchmark median — within plausible range for large manufacturing but warrants analyst review",
      "supporting_sources": [
        {
          "source_id": "ibm-cost-data-breach",
          "publication_year": 2025,
          "admiralty": "A1",
          "note": "Manufacturing sector median $5.13M"
        }
      ],
      "last_validated": "2026-03-27"
    }
  ],
  "no_data_scenarios": ["Denial of Service"],
  "stale_scenarios": []
}
```

**Verdicts:**
- `supported` — VaCR within 2× benchmark range
- `challenged` — VaCR deviates >50% from benchmark median (flagged for review)
- `no_data` — no qualifying benchmark found for this scenario
- `stale` — most recent benchmark is >18 months old

**Flagging rule:** `flagged_for_review: true` when `verdict == "challenged"` OR deviation >200% (large enterprise scale-up may be legitimate but needs annotation).

---

## Comparator Logic

```
for each scenario in mock_crq_database.json:
    benchmarks = [b for b in cache if b.scenario_tag matches AND b.admiralty >= B2]
    if no benchmarks → verdict = "no_data"
    elif most recent benchmark > 18 months old → verdict = "stale"
    else:
        deviation = abs(our_vacr - benchmark_median) / benchmark_median
        if deviation > 0.5 → verdict = "challenged", flagged = true
        else → verdict = "supported"
```

The comparator is deterministic — no LLM involved. Haiku is only used in the extractor step.

---

## Dashboard Panel

**Location:** Below the existing regional threat cards, above the audit trace.

**Always visible.** Shows all 9 scenarios from the CRQ scenario register.

```
┌─ CRQ Validation ──────────────────────────────────────── Last run: 2026-03-27 ─┐
│                                                                                  │
│  Ransomware        $22M  ⚠ REVIEW    329% above IBM/DBIR median                │
│  System Intrusion  $18M  ✓ SUPPORTED  Within Dragos ICS/OT range               │
│  Data Exfiltration $12M  ✓ SUPPORTED  IBM A1 2025                              │
│  Insider Misuse     $4M  ✓ SUPPORTED  Verizon DBIR A1                          │
│  Supply Chain      $15M  — NO DATA    No qualifying benchmark found            │
│  ...                                                                             │
│                                                                                  │
│  Sources: 7 registered · 4 with data · Last DBIR: 2025 · Last IBM: 2025        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Colour coding: green (supported), amber (review), grey (no data / stale).
Clicking a scenario row expands to show all supporting sources with Admiralty ratings.

---

## Scheduler Integration

Add to `tools/scheduler.py` jobs:

```json
{
  "job": "crq-validator",
  "schedule": "weekly",
  "day": "sunday",
  "time": "02:00",
  "command": "uv run python tools/source_harvester.py && uv run python tools/crq_comparator.py"
}
```

Comparator also runs if `data/mock_crq_database.json` hash changes (checked on pipeline start).

---

## Out of Scope (v1)

- SEC 8-K cyber disclosure parsing — parked for v2
- Per-region validation — scenario-level only in v1
- Auto-update of CRQ numbers — never automatic, advisory only
- Email delivery of validation report — dashboard panel only in v1

---

## Files to Create

| File | Purpose |
|---|---|
| `data/validation_sources.json` | Curated source registry (seed with 7 sources above) |
| `tools/source_harvester.py` | Tiered fetch of known sources (WebFetch + search fallback) |
| `tools/source_discoverer.py` | Search-driven discovery of unknown sources → candidates |
| `tools/benchmark_extractor.py` | Haiku extraction of $ figures + scenario tags from text |
| `tools/crq_comparator.py` | Deterministic diff of VaCR vs. benchmarks → flags |
| `output/validation_cache/` | Extracted benchmarks per source per date (auto-created) |
| `output/validation_candidates.json` | Discovered sources awaiting human review |
| `output/validation_flags.json` | Output consumed by dashboard |
| `output/validation_flags.md` | Human-readable summary for analyst |

## Files to Modify

| File | Change |
|---|---|
| `tools/build_dashboard.py` | Add CRQ Validation panel reading `validation_flags.json` |
| `tools/scheduler.py` | Add `crq-validator` weekly job |
| `CLAUDE.md` | Add validator commands to the commands table |
