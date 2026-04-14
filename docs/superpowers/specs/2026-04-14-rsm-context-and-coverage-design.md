# RSM Context & Coverage — Design Spec

**Date:** 2026-04-14
**Status:** Design approved by user, awaiting implementation plan
**Supersedes (extends):** [docs/superpowers/specs/2026-03-20-rsm-intelligence-brief.md](2026-03-20-rsm-intelligence-brief.md)

---

## 1. Goal

Make the Regional Security Manager (RSM) brief good enough that an ex-military RSM in any of AeroGrid's five regions would actually want to read it — every morning. Specifically:

1. **Fully utilize Seerist** — every field the collector pulls is mapped to a place in the brief or formally parked
2. **Layer OSINT physical signals** alongside Seerist (currently only OSINT cyber is consumed)
3. **Anchor every signal to the AeroGrid site context** — personnel, criticality, dependencies, customer impact — so the brief answers "am I exposed and how" not "what happened in my region"
4. **Add a daily push cadence** so RSMs don't have to log into Seerist every morning
5. **Visual coherence with CISO/Board** through shared status labels and the `brief_headlines.{why,how,so_what}` spine — but RSM stays markdown SITREP, not docx/PDF

The intelligence production core (gatekeeper → analyst → builder → validator → board PPTX/CISO docx) is **untouched**. The RSM path is a parallel branch that shares signal collection and adds its own input builder, agent prompt, and delivery loop.

---

## 2. Persona & success test

**Who:** Regional Security Manager. One per region (APAC, AME, LATAM, MED, NCE). Ex-military. Deep regional knowledge. Reads briefs on email/Teams. Owns physical security of AeroGrid personnel and sites in their region. Cyber-aware but physical security is the primary lens.

**Success test (the one that matters):** An RSM in MED gets the morning brief, scrolls once, and within 30 seconds knows: *"Is anything happening near my Casablanca farm or my Malaga hub, how close, how many of my people are exposed, and what should I do today?"* — without opening another tool.

**Failure modes this spec solves:**

| Today | After this spec |
|---|---|
| Brief lists regional events but doesn't say which sites are in the blast radius | New AEROWIND EXPOSURE section anchors every relevant event to a named site with km distance |
| Seerist collects `verified_events`, `breaking_news`, `analysis_reports`, `risk_ratings`, `poi_alerts` — agent uses none of them | Every Seerist field mapped or formally parked (Section 5) |
| OSINT physical signals not pulled — only OSINT cyber | New `osint_physical_collector.py` |
| Weekly cadence only — RSM has to log into Seerist between Mondays | Daily push at 06:00 local, empty days emit a logged stub |
| No personnel counts, no criticality, no cascade impact | Canonical site registry with all of these |
| Two overlapping site files (`company_profile.json` + `aerowind_sites.json`) | Single canonical `aerowind_sites.json` |

---

## 3. Architecture & data flow

### Boundary: agent vs code

Per `agent-team-blueprint/docs/agent-boundary-principles.md` — agents own reasoning, code owns correctness.

| Step | Owner | Why |
|---|---|---|
| Pull Seerist payload | Code | Deterministic API call |
| Pull OSINT physical | Code | Mirrors existing cyber collector |
| Compute event→site distances | Code | Pure haversine |
| Compute cascading dependency impact | Code | Graph traversal |
| Rank events by proximity × severity | Code | Deterministic sort |
| Decide which signals to surface in the brief | **Agent** | Judgment under ambiguity |
| Write SITUATION + ASSESSMENT + WATCH LIST + consequence lines | **Agent** | Language + judgment |
| Assemble PHYSICAL/CYBER/EARLY WARNING/AEROWIND EXPOSURE skeleton | Code | Template injection from structured data |
| Trigger flash on threshold | Code | Threshold logic |
| Decide what to do on empty day | Code | If zero new signals → emit stub, never invoke agent |
| Send email/Teams | Code | I/O |

### Per-region orientation

The unit of work is **`(region, cadence)`**. Five regions × three cadences (daily / weekly / flash) = up to 15 independent jobs per pipeline run. The dispatcher fans them out in parallel (asyncio.gather pattern, identical to existing CRQ orchestration).

**Per-region invariants:**

| Layer | Rule |
|---|---|
| Collectors | `seerist_collector.py REGION`, `osint_physical_collector.py REGION` — never aggregate |
| Proximity / cascade | Sites filtered to the region only; cross-region distances not computed |
| Input builder | Manifest is region-scoped; never reads `regional/{other_region}/` except for `cross_regional_watch` |
| Agent prompt | Hard parameter `REGION = "MED"`; stop hook asserts no out-of-region site names appear in the body |
| Output paths | `output/regional/{region}/rsm_brief_{region}_{date}.md` (existing) and `rsm_daily_{region}_{date}.md` (new) |
| Delivery | `audience_config.json` has one entry per `rsm_{region}` with their own recipient |
| Logging | `delivery_log.json` rows include `region` and `cadence` |

**The one cross-region surface:** `cross_regional_watch` from `global_report.json`, surfaced as a small inset in the WATCH LIST section (max 2 items). Weekly only — daily stays disciplined to the region.

### Dispatcher pattern (daily, weekly identical structure)

```
rsm_dispatcher.py --daily
  ├─ seerist_collector  × 5 regions ─┐
  ├─ osint_physical     × 5 regions ─┤  parallel (asyncio.gather)
  ├─ poi_proximity      × 5 regions ─┤
  ├─ rsm_input_builder  × 5 regions ─┤
  ├─ rsm-formatter       × 5 regions ─┤  parallel agent invocations
  └─ notifier (one delivery per region to per-region recipient)
       └─ delivery_log.json appended (proves daily ran on quiet days)
```

### New tools

#### `tools/osint_physical_collector.py REGION [--mock]`

Mirrors the existing cyber OSINT pattern. Tavily search + Firecrawl deep extraction for physical-pillar signals (unrest, conflict, terrorism, crime, travel, maritime, political, disaster). Writes `output/regional/{region}/osint_physical_signals.json` with the same shape as `osint_signals.json` but `pillar: "physical"`.

#### `tools/poi_proximity.py REGION`

Two clearly separated functions in one file:

**`compute_proximity(region) → events_by_site_proximity`**

Reads `seerist_signals.json` (events + verified_events + breaking_news + hotspots + poi_alerts) and `osint_physical_signals.json`. For every event, computes haversine distance to every site in the region. Returns a sorted matrix per site with events grouped by `within_radius` vs `outside_radius_but_relevant`.

**`compute_cascade(region) → cascading_impact_warnings`**

Reads the canonical `aerowind_sites.json` and the proximity matrix. For each site with an event inside its radius, traverses the `feeds_into` dependency graph and surfaces downstream sites that would be affected. Cycles are ignored. Multi-hop is supported but limited to depth 2.

Output: `output/regional/{region}/poi_proximity.json`:

```json
{
  "region": "MED",
  "computed_at": "2026-04-14T05:00:00Z",
  "events_by_site_proximity": [
    {
      "site_id": "med-casablanca-ops",
      "site": "Casablanca Wind Farm Operations",
      "personnel": 47,
      "expat": 8,
      "criticality": "major",
      "events_within_radius": [
        {
          "signal_id": "seerist:event:med-0042",
          "title": "Civil unrest, Rabat",
          "category": "Unrest",
          "severity": 3,
          "distance_km": 87,
          "source_count": 6,
          "verified": true
        }
      ],
      "events_outside_radius_but_relevant": []
    }
  ],
  "cascading_impact_warnings": [
    {
      "trigger_site_id": "apac-kaohsiung-mfg",
      "trigger_signal_id": "seerist:event:apac-0007",
      "downstream_site_ids": ["nce-hamburg-mfg"],
      "downstream_region": "NCE",
      "dependency": "Blade root supply for final assembly",
      "estimated_delay_days": 5
    }
  ]
}
```

Pure code, unit-testable, no LLM.

#### Extended: `tools/rsm_input_builder.py REGION CADENCE`

Threads the new context blocks through the manifest:
- `poi_proximity.json` (full payload)
- `site_registry` (sites filtered to this region)
- `notable_dates` (region + per-site, filtered to next 7 days)
- `previous_incidents` (per-site historical entries)
- `cadence` parameter (`daily | weekly | flash`)

The manifest is the contract surface between code and the agent.

#### Extended: `.claude/agents/rsm-formatter-agent.md`

New cadence branching, site discipline rules, AEROWIND EXPOSURE consequence prompt, daily empty-stub short-circuit. See Section 6.

#### Extended: `.claude/hooks/validators/rsm-formatter-stop.py`

New deterministic checks (Section 6).

#### Extended: `data/audience_config.json`

New `daily` product type per `rsm_{region}` entry. See Section 7.

---

## 4. Site context — canonical registry

### Single canonical file: `data/aerowind_sites.json`

Replaces the `facilities` block in `data/company_profile.json`. The `crown_jewels`, `industry`, and `company_name` fields stay in `company_profile.json`.

### Schema (per site)

```json
{
  "site_id": "apac-kaohsiung-mfg",
  "name": "Kaohsiung Manufacturing Hub",
  "region": "APAC",
  "country": "TW",
  "lat": 22.62,
  "lon": 120.30,
  "type": "manufacturing",
  "subtype": "blade and nacelle assembly",

  "poi_radius_km": 50,

  "personnel_count": 320,
  "expat_count": 18,
  "shift_pattern": "24/7",

  "criticality": "crown_jewel",
  "produces": "Blade root sections, nacelle final assembly",
  "dependencies": [],
  "feeds_into": ["nce-hamburg-mfg"],

  "customer_dependencies": [
    {"customer": "Vestas", "product": "Q3 turbine delivery", "exposure": "high"}
  ],

  "previous_incidents": [
    {
      "date": "2024-08-14",
      "type": "labour",
      "summary": "Dockworker strike, 4-day disruption",
      "outcome": "resolved"
    }
  ],

  "site_lead": {"name": "Chen Wei-Ming", "phone": "+886-7-555-0142"},
  "duty_officer": {"name": "APAC Duty Desk", "phone": "+65-6555-0100"},
  "embassy_contact": {
    "country_of_origin": "DK",
    "contact": "Royal Danish Embassy Taipei",
    "phone": "+886-2-2718-2101"
  },

  "notable_dates": [
    {"date": "2026-04-30", "event": "Labour Day", "risk": "elevated unrest probability"}
  ]
}
```

### Field rationale

| Field | Source | Used in |
|---|---|---|
| `site_id` | New stable ID | Cross-references between proximity/cascade/feedback systems. Reserved for future RSM feedback loop |
| `region`, `country`, `lat`, `lon` | Existing | Filtering, distance computation |
| `type`, `subtype` | Existing + new | Type drives criticality default; subtype drives bullet specificity |
| `poi_radius_km` | Existing in `company_profile.json` only | Proximity filter — events within radius hit AEROWIND EXPOSURE |
| `personnel_count`, `expat_count` | New (mocked) | "47 personnel (8 expat)" inline |
| `shift_pattern` | New (mocked) | Agent qualifies "X people on-site at event time" |
| `criticality` (`crown_jewel` / `major` / `standard`) | New (mocked) | Drives bullet ordering — crown jewels listed first |
| `produces`, `feeds_into`, `dependencies` | New (mocked) | Cascade computation |
| `customer_dependencies` | New (mocked) | Cascade can name commercial impact |
| `previous_incidents` | New (mocked, small array) | Pattern-matching for the agent — "3rd incident in 12mo" |
| `site_lead`, `duty_officer`, `embassy_contact` | New (mocked) | Footer references — alert to action in one product |
| `notable_dates` | New (mocked) | Region-level + site-level calendar for risk windows |

### Mock generation strategy

- All sites in current `aerowind_sites.json` get the new fields populated
- Sites in `company_profile.json` not yet in `aerowind_sites.json` get added (deduped by lat/lon proximity)
- Personnel counts in realistic ranges per type: manufacturing 200-500, service 30-80, office 15-40, R&D 25-60
- Crown jewels assigned to ~20% of sites (major manufacturing plants holding OT/SCADA + IP)
- A separate `data/site_registry_audit.json` documents what was mocked vs sourced, so real values can replace mocks later without losing provenance

### Migration

- Move `facilities` from `company_profile.json` to `aerowind_sites.json`
- Test `test_site_registry.py` asserts: every site has unique `site_id`; no duplicate (region, name) pairs; every region has ≥1 site; lat/lon valid; required fields present

---

## 5. Seerist field coverage map

Every Seerist field that `seerist_collector.py` pulls today, mapped to a place in the brief or formally parked.

| Seerist field | Brief section | Use | Owner | If absent |
|---|---|---|---|---|
| `situational.events` | PHYSICAL & GEOPOLITICAL | Filter by proximity to sites (≤ radius first, then "regional context" tail). `[CATEGORY][SEVERITY] {location} — {title}. Distance: {km}km from {site}. {operational_implication}` | Code filters by proximity, agent picks bullets | "No new physical events this period" |
| `situational.verified_events` | PHYSICAL & GEOPOLITICAL | High-confidence subset — bullets get `✓ verified` tag | Code tags, agent uses tag in Assessment language | Skip tag |
| `situational.breaking_news` | SITUATION header | If non-empty AND any item is within site radius, surface as one-line "DEVELOPING:" prefix above SITUATION | Code detects, agent rewrites prefix in voice | Skip prefix |
| `situational.news` | Background only | Used by agent for context — NOT quoted as bullets. Helps calibrate Assessment language ("widely reported" vs "early stage") | Agent reads, doesn't quote | Agent ignores |
| `analytical.pulse.countries` | SITUATION header (per-country line for multi-country regions) + EARLY WARNING (sub-category drift) | Each country's score, delta, sub-categories. "MED: Italy stable (62, +1), Morocco declining (54, −6)" | Code formats, agent picks worst items | "No pulse data" |
| `analytical.pulse.region_summary` | Header line | Worst country + avg delta + trend → existing PULSE field on the SITREP header | Code | Default to single-country logic |
| `analytical.hotspots` | EARLY WARNING (PRE-MEDIA) | Existing use. Add proximity tag from `poi_proximity.py` so anomalies show distance to nearest site | Code computes proximity, agent surfaces | "No pre-media anomalies" |
| `analytical.scribe` | ASSESSMENT context (NOT quoted) | Seerist analyst notes. Agent reads as input to the Assessment paragraph — never quoted directly. Disambiguates "we made this call" vs "Seerist analysts called this" | Agent | Agent skips |
| `analytical.wod_searches` | EARLY WARNING (secondary) | Search trend spikes. Surfaces only if a spike correlates with a region or site name. `▪ Search anomaly: "{term}" spiking — possible early indicator` | Code correlates, agent decides | Skip |
| `analytical.analysis_reports` | REFERENCES footer | Seerist long-form analyst reports. Listed in references with title + date. Agent may cite in Assessment | Code lists, agent optionally cites | Skip |
| `analytical.risk_ratings` | SITUATION header | Per-country risk rating. `RISK: Morocco HIGH (▲ from MED last period)` | Code | Skip line |
| `poi_alerts` | **NEW SECTION: AEROWIND EXPOSURE** | The most important new use. Each POI alert becomes a structured block: site name, distance, matching events, personnel exposed, criticality | Code populates, agent writes one-line consequence per block | "No site-specific alerts this period" |

### Parked fields

| Field | Why parked | Future re-use |
|---|---|---|
| `situational.news` (raw quoting) | Adds noise — Seerist analyst layer is better signal | Background context only |
| `analytical.scribe` (verbatim) | Style mismatch — Seerist analyst voice ≠ RSM voice | Internal context only |
| `wod_searches` (when uncorrelated) | Too noisy without correlation | Future trend dashboard |
| Cross-region pulse comparisons | Not part of RSM scope (regional, not global) | Already in CISO/board path via `cross_regional_watch` |

---

## 6. Brief structure

### New section: AEROWIND EXPOSURE

Sits **second**, immediately after SITUATION. Answers the persona test directly. Rendered identically in daily and weekly cadences.

```
█ AEROWIND EXPOSURE
▪ Casablanca Wind Farm Operations [CROWN_JEWEL · 47 personnel, 8 expat]
   ├─ Civil unrest, Rabat — 87km, severity HIGH, ✓ verified, 6 sources
   ├─ Strike action, Port of Casablanca — 3km, severity HIGH, ✓ verified, 4 sources
   └─ Consequence: Inbound nacelle component shipments delayed; dependency
      cascades to Hamburg final assembly (5d delay assessed).

▪ Malaga Service Hub [STANDARD · 18 personnel]
   └─ No new events within radius this period.
```

The agent writes only the `Consequence:` line. Everything else is deterministic from `poi_proximity.py` + the site registry.

### Weekly INTSUM template (extended from existing spec)

```
AEROWIND // {REGION} INTSUM // WK{iso_week}-{year}
PERIOD: {from} – {to} | PRIORITY SCENARIO: {scenario} #{rank} | PULSE: {prev}→{curr} ({delta}) | ADM: {admiralty}
RISK: {country_a} {rating_a} ({trend}) · {country_b} {rating_b} ({trend})    ← from risk_ratings, optional line, omit if absent

█ SITUATION
DEVELOPING: {one-line breaking_news prefix — only if breaking_news non-empty AND within site radius, else omit}
{One sentence: overall posture. What changed since last INTSUM.}

█ AEROWIND EXPOSURE
{Site blocks per Section 6 above.}

█ PHYSICAL & GEOPOLITICAL
{Existing format. Includes ✓ verified tags from verified_events.}

█ CYBER
{Existing format.}

█ EARLY WARNING (PRE-MEDIA)
{Existing format. Includes proximity tags from poi_proximity.py.}

█ ASSESSMENT
{2-4 sentences. Existing reasoning logic.}

█ WATCH LIST — WK{next}
{3-5 items. Cross-regional watch inset (max 2) appended at the bottom.}

REFERENCES
{Numbered list of Seerist analysis_reports + cited OSINT sources.}

---
Reply: ACCURATE · OVERSTATED · UNDERSTATED · FALSE POSITIVE | AeroGrid Intelligence // {REGION} RSM
```

### Daily template — non-empty

```
AEROWIND // {REGION} DAILY // {date}Z
PULSE: {curr} ({arrow} {delta_24h}) | ADM: {adm} | NEW: {n_events} EVT · {n_hotspots} HOT · {n_cyber} CYB
RISK: {country_a} {rating_a} ({trend})    ← optional line, omit if no risk_ratings change

█ SITUATION
DEVELOPING: {one-line breaking_news prefix — only if breaking_news non-empty AND within site radius, else omit}
{One sentence — what changed in the last 24h. No history, no narrative.}

█ AEROWIND EXPOSURE
{Site blocks ONLY for sites with new events inside their radius in the last 24h.}

█ PHYSICAL & GEOPOLITICAL — LAST 24H
{Event bullets — new only. If none: "No new events."}

█ CYBER — LAST 24H
{Cyber bullets — new only. If none: "No new signals."}

█ EARLY WARNING — NEW
{Hotspots first detected in last 24h. If none: "No new anomalies."}

█ TODAY'S CALL
{1-2 sentences. What does this mean for today specifically? Operational, not strategic.
 Replaces ASSESSMENT in the daily product.}

---
Reply: ACKNOWLEDGED · INVESTIGATING · FALSE POSITIVE | AeroGrid Intelligence // {REGION} RSM
```

### Daily template — empty stub

```
AEROWIND // {REGION} DAILY // {date}Z
PULSE: {curr} ({arrow} {delta_24h}) | ADM: {adm} | NEW: 0 EVT · 0 HOT · 0 CYB

▪ No new physical events past 24h
▪ No new cyber signals
▪ No pre-media anomalies
▪ No site-specific alerts

Automated check ran {timestamp}. Nothing to escalate. Next check 24h.

---
Reply: ACKNOWLEDGED | AeroGrid Intelligence // {REGION} RSM
```

The empty stub is generated by `rsm_input_builder.py` directly — the agent is **not invoked** when zero new signals exist. This is a code path, not a prose path.

### Cadence-aware agent prompt

Single agent, single prompt, cadence parameter:

| Cadence | Sections agent writes | Sections skipped |
|---|---|---|
| `daily` | SITUATION (1 sentence), AEROWIND EXPOSURE consequences, TODAY'S CALL (1-2 sentences) | ASSESSMENT, WATCH LIST, REFERENCES, cross_regional_watch |
| `weekly` | SITUATION, AEROWIND EXPOSURE consequences, ASSESSMENT, WATCH LIST | none — full brief |
| `flash` | Existing flash format | n/a |

### Site discipline rules (anti-hallucination)

The prompt states explicitly:

> You may reference only the following sites in this brief: `[Casablanca Wind Farm Operations, Palermo Offshore Ops, Malaga Service Hub]`. You may NOT name any other AeroGrid site, anywhere in the brief, including in cascading impact references. If a `cascading_impact_warnings` entry references a downstream site outside this region, summarise the cascade as "downstream site in {other_region}" — do NOT name it.

> When writing AEROWIND EXPOSURE consequences, you may NOT invent or modify personnel/expat counts. The structured block injected by `poi_proximity.py` is authoritative. If a count is missing, write "personnel exposure unknown" — never guess.

### Stop hook checks (`rsm-formatter-stop.py` extended)

| Check | Asserts | Exit |
|---|---|---|
| Section presence | All cadence-appropriate headers present | 2 |
| Jargon audit | No CVEs, IPs, hashes, SOC vocab, budget advice | 2 |
| Site name discipline | Every AeroGrid site name in the brief is in the region's allowed-site list | 2 |
| Personnel count match | Every personnel/expat number matches `aerowind_sites.json` exactly | 2 |
| No cross-region body | Brief body never names another region except in the cross_regional_watch inset | 2 |
| Daily-empty short-circuit | If cadence=daily AND zero new signals, brief is the stub format and nothing more | 2 |
| AEROWIND EXPOSURE consequence length | Each consequence line ≤ 2 sentences | 2 |
| No quoted Seerist scribe text | Brief contains no verbatim text matching `analytical.scribe[].text` | 2 |

Each check is a deterministic function. Exit 0 if all pass, exit 2 with failure list if not. Agent reruns on exit 2.

---

## 7. `audience_config.json` — daily product

New `daily` product type per `rsm_{region}` entry:

```json
{
  "rsm_med": {
    "label": "MED Regional Security Manager",
    "formatter_agent": "rsm-formatter-agent",
    "regions": ["MED"],
    "products": {
      "daily": {
        "cadence": "daily",
        "time_local": "06:00",
        "timezone": "Africa/Casablanca",
        "always_emit": true
      },
      "weekly_intsum": {
        "cadence": "monday",
        "time_local": "07:00",
        "timezone": "Africa/Casablanca"
      },
      "flash": {
        "threshold": {
          "hotspot_score_min": 0.85,
          "site_proximity_km": 100,
          "event_severity_min": 4,
          "categories": ["Conflict", "Terrorism", "Unrest"]
        }
      }
    },
    "delivery": {
      "channel": "email",
      "recipients": ["rsm-med@aerowind.com"]
    }
  }
}
```

`always_emit: true` means even empty days produce a brief (the stub form). `delivery_log.json` row is appended either way, so the RSM trusts the daily ran.

---

## 8. Test plan

### Unit tests (code, no LLM)

| File | Tests |
|---|---|
| `tests/test_poi_proximity.py` | `compute_proximity()` returns correct distance (haversine known cases), filters events to region, sorts by proximity, handles empty event list, handles missing site coords |
| `tests/test_dependency_cascade.py` | `compute_cascade()` traces single-hop and multi-hop dependencies, ignores cycles, returns empty for sites with no `feeds_into`, names downstream sites in other regions correctly |
| `tests/test_rsm_input_builder.py` | Manifest contains all required blocks per cadence, optional fallbacks fire when files absent, manifest is region-scoped (no cross-contamination), CADENCE param branches the manifest correctly |
| `tests/test_site_registry.py` | Every site has unique `site_id`, every region has ≥1 site, no duplicate (region, name) pairs, all required fields present, lat/lon valid ranges |
| `tests/test_rsm_formatter_stop.py` | Each new stop-hook check passes on a known-good brief, fails on a brief with: invented site name, wrong personnel count, cross-region body, quoted scribe text, daily-non-stub on empty signal day |
| `tests/test_osint_physical_collector.py` | Tavily/Firecrawl integration mirrors existing cyber collector tests in `--mock` mode |

### Integration tests

| File | Tests |
|---|---|
| `tests/test_rsm_dispatcher_daily.py` | Full daily dispatch in `--mock --region MED` produces brief at expected path, stub format on empty signal day, full format on populated day, delivery_log row written |
| `tests/test_rsm_dispatcher_weekly.py` | Full weekly dispatch in `--mock --region APAC` produces brief with all sections, AEROWIND EXPOSURE block populated for sites with events in radius |
| `tests/test_rsm_parallel_fanout.py` | All 5 regions × cadence=daily run in parallel, no cross-region contamination in any brief, all 5 deliveries logged |

### Stop-hook validation tests

| Scenario | Expected |
|---|---|
| Brief invents a site not in registry | Exit 2, named in failure list |
| Brief states "47 personnel" but registry says 320 | Exit 2 |
| Daily brief writes ASSESSMENT section | Exit 2 (cadence violation) |
| Daily empty stub → brief contains "█ ASSESSMENT" | Exit 2 |
| Brief in MED references "Hamburg" outside cross_regional_watch | Exit 2 |
| Brief quotes Seerist scribe text verbatim | Exit 2 |

### Mock fixture parity

- All 5 regions get updated `{region}_seerist.json` mock fixtures with `verified_events`, `analysis_reports`, `risk_ratings`, `poi_alerts` populated
- `aerowind_sites.json` has all new fields populated for every site
- `tests/test_mock_fixture_parity.py` asserts every Seerist field used in the agent prompt is present (or explicitly null) in every regional mock fixture

### Smoke test

`uv run python tools/rsm_dispatcher.py --daily --mock` — runs all 5 regions, asserts 5 brief files written, 5 delivery_log rows appended, exit 0.

---

## 9. Build order

15 tasks. Critical path bolded.

```
M-1   Site registry consolidation                                      ~1.5h
      Merge company_profile.facilities + aerowind_sites.json into
      single canonical aerowind_sites.json with all new fields.
      Mock plausible values. test_site_registry.py.

M-2   Update mock seerist fixtures                                     ~1h
      Populate verified_events, analysis_reports, risk_ratings,
      poi_alerts in all 5 region fixtures.
      test_mock_fixture_parity.py.

M-3   poi_proximity.py (compute_proximity + compute_cascade)           ~2h  ★
      Pure haversine + dependency graph traversal.
      depends on: M-1
      test_poi_proximity.py + test_dependency_cascade.py

M-4   osint_physical_collector.py                                      ~1.5h
      Tavily + Firecrawl with --mock fallback.
      test_osint_physical_collector.py

M-5   audience_config.json — daily product schema                      ~30min
      Add daily cadence + delivery for each rsm_{region}.

M-6   rsm_input_builder.py extension                                   ~1.5h  ★
      New manifest blocks: poi_proximity, site_registry, notable_dates,
      previous_incidents, cadence parameter.
      depends on: M-1, M-2, M-3, M-4, M-5
      test_rsm_input_builder.py

M-7   rsm-formatter-agent.md prompt rewrite                            ~2h  ★
      Cadence branching, site discipline rules, AEROWIND EXPOSURE
      template, daily empty stub short-circuit.
      depends on: M-6
      Manual review against principles.

M-8   rsm-formatter-stop.py extended checks                            ~1.5h  ★
      Site name, personnel count, cross-region, daily-stub, scribe
      quote, consequence length checks.
      depends on: M-7
      test_rsm_formatter_stop.py

M-9   rsm_dispatcher.py — daily mode                                   ~1.5h  ★
      --daily flag, parallel fan-out across 5 regions, empty-stub path.
      depends on: M-6, M-7, M-8
      test_rsm_dispatcher_daily.py

M-10  rsm_dispatcher.py — weekly mode integration                      ~1h
      Reuse existing weekly logic, route through new input_builder.
      depends on: M-9
      test_rsm_dispatcher_weekly.py

M-11  delivery_log.json schema + notifier.py daily integration         ~1h
      Append-only JSONL, region + cadence fields.
      Verify empty-stub deliveries logged.
      depends on: M-9

M-12  Parallel fan-out integration test                                ~1h  ★
      All 5 regions × daily, no contamination.
      depends on: M-9, M-10, M-11
      test_rsm_parallel_fanout.py

M-13  End-to-end smoke test in --mock                                  ~30min
      Manual: dispatcher --daily --mock, dispatcher --weekly --mock.

M-14  Documentation                                                    ~1h
      Update CLAUDE.md + README RSM section. Note Task 11 follow-on.

M-15  (Follow-on, separate plan) Context propagation to CISO + board   parked
      Brainstormed separately — not built in this round.
```

**Total: ~16h focused work.** Critical path (★): M-1 → M-3 → M-6 → M-7 → M-8 → M-9 → M-12 ≈ 11h sequential. M-2, M-4, M-5 run in parallel against M-1/M-3.

---

## 10. Future task — context propagation to CISO + board (Task 11, parked)

The context layer built here (personnel, criticality, dependencies, cascading impact, customer dependencies, previous incidents) is just as valuable upstream:

- **CISO weekly brief**: today says "$22M VaCR exposure in AME." With the new context: "$22M VaCR exposure in AME — Houston (47 personnel, customer: ExxonMobil Q3 turbine delivery on the line)."
- **Board PPTX**: today's threat slides say "System intrusion — APAC." With cascading impact: "System intrusion — APAC — disrupts blade root supply to Hamburg final assembly, downstream delay 5d."
- **Reports tab cards**: each region card could show "47 personnel, 1 crown-jewel site, 2 cascading dependencies."

This is **explicitly out of scope for this build**. Each consumer (CISO, board, reports tab) gets its own brainstorm + plan when the data layer is proven in RSM. The only thing this spec does for them is establish the canonical site registry and the proximity/cascade computation as shared infrastructure they can read from.

---

## 11. What does not change

- `run-crq.md` orchestrator
- `gatekeeper-agent.md`
- `regional-analyst-agent.md`
- `global-builder-agent.md`
- `global-validator-agent.md`
- `tools/export_ciso_docx.py`
- `tools/export_pptx.py` (board)
- `dashboard.html`, `board_report.pdf`, `ciso_brief.docx` outputs
- All existing pipeline collectors (`geo_collector.py`, `cyber_collector.py`, etc.)
- The existing weekly INTSUM template structure (sections are extended, not rewritten)
- The flash alert format

The RSM context + coverage work is additive to the intelligence production core.

---

## 12. Future extensions (Tier 3, parked beyond Task 11)

- Open incidents register per site — items the RSM has flagged and not closed; brief surfaces "Day 14 of 30 — still open" automatically
- Scenario playbook matching against `master_scenarios.json` — "this matches Scenario 7"
- Travel/VIP register — board members, customers, executives traveling near hot zones
- Last-week feedback closure — RSM replies ACCURATE/OVERSTATED feeding into calibration
- Pre-mortem one-liner per site — "If this site goes offline 7d, what breaks?"
- Two-pass agent design — first pass ranks/selects, second pass writes prose
- Local-language OSINT routing — Arabic sources weighted higher for MED, Mandarin for APAC China
- Weather/climate context tagging per site
- Per-RSM feedback loop calibrating threshold sensitivity

These are noted so the data layer reserves what it needs (e.g., `signal_id` is stable per run already, anticipating the feedback loop) without building any of it now.
