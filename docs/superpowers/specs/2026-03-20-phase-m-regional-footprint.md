# Phase M — Regional Footprint Context Layer

**Date:** 2026-03-20
**Status:** Design approved, awaiting implementation plan
**Phase:** M (follows Phase L — RSM Intelligence Brief)

---

## Overview

The pipeline currently reasons against a thin, global `company_profile.json` (4 fields). Agents infer what AeroGrid cares about rather than knowing it. This spec adds `data/regional_footprint.json` — per-region structural facts about AeroGrid's physical presence, crown jewels, supply chain, and stakeholders — injected into the pipeline as pre-formatted text before agents run.

**Three purposes, one file:**
1. **Analysis quality** — agents cite specific sites, headcount, contracts in the "so what" section
2. **Triage calibration** — gatekeeper uses site criticality to calibrate escalation threshold
3. **Phase L foundation** — stakeholders field seeds RSM routing (which RSM covers which region, how to reach them)

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Injection mechanism | Pre-assembled `context_block.txt` via `build_context.py` | Auditable, consistent formatting, follows filesystem-as-state pattern |
| Agent coverage | Gatekeeper (lightweight) + analyst (full) | Gatekeeper needs criticality signal; analyst needs full detail for "so what" |
| Global builder | No direct footprint — gets it via analyst briefs | Avoids double-citing; analysts bake footprint into briefs |
| Data population | Pre-populated with realistic AeroGrid mock data | Demo-ready from day one; Config tab UI for edits |
| UI approach | Hybrid — key fields + freetext notes | Summary/headcount/RSM email as dedicated inputs; sites/contracts/deps as freetext |
| Expiry/review | None enforced | Footprint is structural — changes when business changes, not on a cadence |

---

## Data Schema

### `data/regional_footprint.json`

```json
{
  "APAC": {
    "summary": "Primary manufacturing region. 60% of global turbine output. Highest operational sensitivity.",
    "headcount": 3200,
    "sites": [
      {"name": "Kaohsiung Manufacturing Hub", "country": "TW", "type": "manufacturing", "criticality": "primary"},
      {"name": "Singapore Regional HQ",       "country": "SG", "type": "headquarters",  "criticality": "high"},
      {"name": "Tokyo Service Centre",         "country": "JP", "type": "service",       "criticality": "medium"}
    ],
    "crown_jewels": ["Series 7 production line", "SCADA network TW-01", "OT predictive maintenance stack"],
    "supply_chain_dependencies": ["Taiwanese semiconductor components", "Korean rare earth supply"],
    "key_contracts": ["TEPCO 5yr turbine supply agreement", "Vestas APAC logistics JV"],
    "notes": "",
    "stakeholders": [
      {"role": "APAC Regional Ops Lead", "email": "apac-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "APAC RSM",               "email": "rsm-apac@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  },
  "AME": {
    "summary": "Primary North American operations. Wind farm service hub and growing manufacturing presence.",
    "headcount": 2100,
    "sites": [
      {"name": "Houston Operations Centre",    "country": "US", "type": "headquarters",  "criticality": "high"},
      {"name": "Monterrey Assembly Plant",     "country": "MX", "type": "manufacturing", "criticality": "high"},
      {"name": "Toronto Service Hub",          "country": "CA", "type": "service",       "criticality": "medium"}
    ],
    "crown_jewels": ["Wind farm telemetry network NA-01", "Predictive maintenance IP"],
    "supply_chain_dependencies": ["US steel imports", "Canadian logistics network"],
    "key_contracts": ["NextEra Energy 3yr maintenance contract", "Ontario Wind Power service agreement"],
    "notes": "",
    "stakeholders": [
      {"role": "AME Regional Ops Lead", "email": "ame-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "AME RSM",               "email": "rsm-ame@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  },
  "LATAM": {
    "summary": "Growing service and maintenance presence. No primary manufacturing. Emerging wind market.",
    "headcount": 680,
    "sites": [
      {"name": "São Paulo Regional Office",   "country": "BR", "type": "service",      "criticality": "medium"},
      {"name": "Santiago Service Centre",     "country": "CL", "type": "service",      "criticality": "medium"}
    ],
    "crown_jewels": ["Regional service contracts", "Field technician network"],
    "supply_chain_dependencies": ["Brazilian logistics partners"],
    "key_contracts": ["Enel Chile wind maintenance 2yr", "Neoenergia turbine service Brazil"],
    "notes": "",
    "stakeholders": [
      {"role": "LATAM Regional Ops Lead", "email": "latam-ops@aerowind.com", "notify_on": ["escalated"]},
      {"role": "LATAM RSM",               "email": "rsm-latam@aerowind.com", "notify_on": ["escalated"]}
    ]
  },
  "MED": {
    "summary": "Manufacturing and service hub for Southern Europe and North Africa. Offshore wind growth market.",
    "headcount": 1400,
    "sites": [
      {"name": "Tarragona Manufacturing Plant", "country": "ES", "type": "manufacturing", "criticality": "high"},
      {"name": "Athens Service Centre",         "country": "GR", "type": "service",       "criticality": "medium"},
      {"name": "Casablanca Logistics Hub",      "country": "MA", "type": "service",       "criticality": "medium"}
    ],
    "crown_jewels": ["Offshore blade assembly process", "Mediterranean service network"],
    "supply_chain_dependencies": ["Spanish steel supply", "North African logistics corridor"],
    "key_contracts": ["Iberdrola offshore maintenance 4yr", "ENEL MED service contract"],
    "notes": "",
    "stakeholders": [
      {"role": "MED Regional Ops Lead", "email": "med-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "MED RSM",               "email": "rsm-med@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  },
  "NCE": {
    "summary": "Largest European presence. Mature wind market. Key R&D and engineering functions.",
    "headcount": 2800,
    "sites": [
      {"name": "Hamburg Engineering HQ",       "country": "DE", "type": "headquarters",  "criticality": "high"},
      {"name": "Gdansk Manufacturing Plant",   "country": "PL", "type": "manufacturing", "criticality": "high"},
      {"name": "Copenhagen R&D Centre",        "country": "DK", "type": "r_and_d",       "criticality": "high"},
      {"name": "Oslo Service Hub",             "country": "NO", "type": "service",       "criticality": "medium"}
    ],
    "crown_jewels": ["Core turbine aerodynamic IP", "R&D roadmap and prototype designs", "OT/SCADA networks EU-01/EU-02"],
    "supply_chain_dependencies": ["German precision engineering components", "Nordic offshore logistics"],
    "key_contracts": ["Ørsted offshore wind 5yr maintenance", "Vattenfall EU service agreement"],
    "notes": "",
    "stakeholders": [
      {"role": "NCE Regional Ops Lead", "email": "nce-ops@aerowind.com",  "notify_on": ["escalated"]},
      {"role": "NCE RSM",               "email": "rsm-nce@aerowind.com",  "notify_on": ["escalated", "monitor"]}
    ]
  }
}
```

**`criticality` values:** `primary` / `high` / `medium` — used by gatekeeper for triage calibration.

---

## Tool: `tools/build_context.py`

**CLI:**
```bash
uv run python tools/build_context.py APAC
# Writes: output/regional/apac/context_block.txt
# Prints: Context block written: output/regional/apac/context_block.txt
# Exit 0
```

**Output format (`context_block.txt`):**
```
[REGIONAL FOOTPRINT — APAC]
Summary: Primary manufacturing region. 60% of global turbine output.
Headcount: 3,200

Sites:
  - Kaohsiung Manufacturing Hub (TW) — manufacturing, PRIMARY
  - Singapore Regional HQ (SG) — headquarters, HIGH
  - Tokyo Service Centre (JP) — service, MEDIUM

Crown Jewels: Series 7 production line | SCADA network TW-01 | OT predictive maintenance stack
Supply Chain Dependencies: Taiwanese semiconductor components | Korean rare earth supply
Key Contracts: TEPCO 5yr turbine supply agreement | Vestas APAC logistics JV

Notes:
{notes field verbatim, omitted if empty}
```

**Gatekeeper summary** (separate function `build_gatekeeper_summary(data)`):
```
APAC footprint: 3,200 staff | Sites: Kaohsiung (manufacturing, PRIMARY), Singapore (HQ, HIGH), Tokyo (service, MEDIUM)
```

**Error behaviour:**
- Unknown region → stderr + exit 1
- Missing `regional_footprint.json` → stderr + exit 1
- Region key absent from file → writes empty `context_block.txt` + exit 0

---

## Pipeline Wiring

### `run-crq.md` — Phase 0

After loading prior feedback, before OSINT fan-out:
```
For each region, run: uv run python tools/build_context.py {REGION}
```
All 5 regions. Fast — pure file I/O, no LLM. Failures are logged but non-fatal (agent proceeds without context).

The orchestrator also reads `regional_footprint.json` directly to construct `FOOTPRINT_SUMMARY` for each region's gatekeeper invocation.

### `regional-analyst-agent.md` — STEP 1 input list

Add as item 9:
```
9. output/regional/{region_lower}/context_block.txt (if present) —
   AeroGrid's physical footprint in this region: sites, headcount,
   crown jewels, supply chain dependencies, key contracts.
   Cite specific assets when describing business impact in the So What section.
   If absent, proceed without it — do not fabricate footprint data.
```

### `gatekeeper-agent.md` — TASK section

Orchestrator passes `FOOTPRINT_SUMMARY` as a prompt variable. One line added to gatekeeper TASK:
```
FOOTPRINT: {FOOTPRINT_SUMMARY}
Use site criticality to calibrate escalation threshold — a region with a PRIMARY
manufacturing site warrants a lower ESCALATE bar than a service-only presence.
```

---

## API

```
GET  /api/footprint             → returns full regional_footprint.json
PUT  /api/footprint/{region}    → updates one region entry (atomic write)
                                   validates region in KNOWN_REGIONS
                                   returns {ok: true}
```

---

## Config Tab UI — Footprint Panel

New panel in Config tab alongside Topics, Sources, Prompts, Agent.

Per-region collapsible sections. Each section:

```
┌─ APAC ──────────────────────────────────────────── [▼] ─┐
│ Summary      [____________________________________]      │
│ Headcount    [______]                                    │
│ RSM Email    [____________________]                      │
│                                                          │
│ Notes        [                                    ]      │
│              [ sites, contracts, deps, crown jewels ]    │
│              [                                    ]      │
│                                              [Save]      │
└──────────────────────────────────────────────────────────┘
```

- `summary` → `footprint[region].summary`
- `headcount` → `footprint[region].headcount`
- `rsm_email` → `footprint[region].stakeholders[role=RSM].email`
- `notes` → `footprint[region].notes` (appended verbatim to context_block.txt)

Dirty-state warning on tab navigation (same pattern as Topics/Sources).

---

## Tests: `tests/test_build_context.py`

8 tests, all unit-level:

| Test | Assertion |
|---|---|
| `test_valid_region_writes_file` | APAC → `context_block.txt` created at correct path |
| `test_output_contains_site_names` | Block includes site names from footprint |
| `test_output_contains_headcount` | Headcount rendered as formatted number (3,200) |
| `test_gatekeeper_summary_format` | `build_gatekeeper_summary()` returns correct one-liner with criticality |
| `test_unknown_region_exits_1` | `UNKNOWN` → exit 1, stderr message |
| `test_missing_footprint_file_exits_1` | No `regional_footprint.json` → exit 1 |
| `test_empty_region_writes_empty_block` | Region absent from file → empty `context_block.txt`, exit 0 |
| `test_notes_field_appended_verbatim` | Notes text appears unchanged in output block |

Same `monkeypatch` / `tmp_path` pattern as `test_build_history.py`.

---

## Build Order

```
M-1  data/regional_footprint.json (mock data, all 5 regions)         ~30 min
M-2  tools/build_context.py + tests/test_build_context.py            ~1 hour
M-3  Pipeline wiring: run-crq.md Phase 0 + analyst agent + gatekeeper ~45 min
M-4  server.py: GET/PUT /api/footprint endpoints                      ~30 min
M-5  Config tab: Footprint panel (UI + JS)                            ~1 hour
```

Total: ~3.75 hours

---

## What Does Not Change

- `run-crq.md` pipeline logic (only Phase 0 addition)
- `gatekeeper-agent.md` core triage logic (one line added to TASK section)
- `regional-analyst-agent.md` analysis logic (one item added to input list)
- All existing tools, OSINT collectors, signal files
- `data/company_profile.json` — footprint supplements it, does not replace it

---

## Future Extensions (not in scope for Phase M)

- Business events layer (`human_context.json` — time-bounded entries)
- RSM HUMINT submission (field notes from Regional Security Managers)
- Context quality loop (did the context change the analysis? rate it)
- `build_context.py` extended to merge footprint + business events + HUMINT into one block
