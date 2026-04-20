# Context Tab Architecture — Session Brief

**Status:** Not started. Hand-off from 2026-04-20 RSM weekly brainstorm.
**Next step:** Run `superpowers:brainstorming` in a new session using this doc as the seed.

---

## Why this exists

The RSM weekly INTSUM design (separate spec, in progress) depends on richer per-site context than `data/aerowind_sites.json` carries today. Rather than bolt context changes into the RSM spec, we're splitting it out: Context is a cross-cutting concern that feeds every output (Overview, CISO brief, Board report, RSM weekly/daily/flash) — it deserves its own design.

The RSM spec will declare what fields it needs; this workstream commits to delivering them through a consolidated editable surface.

## Current state (as of 2026-04-20)

Context today is fragmented across multiple file-only sources:

- `data/company_profile.json` — company profile, sectors, risk appetite
- `data/aerowind_sites.json` — canonical site registry (region, personnel, name)
- `data/master_scenarios.json` — scenario catalog
- Settings tab has a "footprint" section that partially surfaces some of this

No single place for an RSM or country lead to edit the intelligence context their region runs on. No regionalization in the UI. No schema coherence across sources.

## Scope of this workstream

1. **Design the Context tab** — new top-level tab in the app. Absorbs Settings → footprint.
2. **Regionalize it** — region selector (APAC / AME / LATAM / MED / NCE) with a global layer on top. Matches the Reports → RSM Briefs pattern.
3. **Consolidate the schema** — one canonical shape for company, sites, people, scenarios. Decide what stays file-backed vs. what moves to a DB/editable store.
4. **Map context → agents → outputs (the feedback loop)** — for every agent in the pipeline (gatekeeper, regional analyst, global builder, RSM formatter, source librarian), document:
   - **Inputs:** which context fields the agent reads, which Seerist/OSINT fields it reads, and how it joins them (proximity, attack-type match, perpetrator watchlist, etc.)
   - **Outputs:** what the agent produces that lands in each downstream deliverable (Overview source boxes, CISO brief, Board report, RSM weekly/daily/flash, Risk Register reading list)
   - **Context tuning knobs:** which context fields, if changed, would meaningfully change that agent's output (tier, relevant_seerist_categories, threat_actors_of_interest, etc.)
   - **Anti-join gaps:** dimensions Seerist reports along that we have no context field for — these are improvement candidates.
   - Deliverable: a context-flow matrix — rows = agents, columns = context fields consumed / produced / downstream outputs. Living document that drives the implementation plan.
5. **Audit the full pipeline** — map every output to the context fields it reads. Document the data contract each output depends on. (This is the output-side view; task 4 is the agent-side view. Together they cover input → agent → output.)
6. **Define the edit flow** — who edits what, how changes propagate to generated outputs, whether edits are versioned.
7. **Permissions hook (design only)** — structure the data model so per-region edit access can be gated later, even if auth isn't built now.

## Decisions already made (2026-04-20 brainstorm)

- **Dedicated "Context" tab**, not an extension of Settings. "Footprint" framing is too narrow — tier, criticality drivers, downstream dependencies are editorial context, not footprint.
- **Regionalized UI** with a global layer above (company profile, risk appetite, master scenarios live globally; sites, people, standing notes live per-region).
- **Settings stays lean** — app config only (API keys, run cadence, export prefs, telemetry). No intelligence inputs.
- **Context fields must align with the dimensions Seerist (and other data sources) report along** so the agent can do joins like "is this event close to our site?" and "does this attack type match our asset type?"
- **Proposed sub-sections inside Context tab:**
  - Company (global) — profile, sectors, risk appetite
  - Sites (regional) — per-site registry
  - People (regional) — personnel overlays if not on site records
  - Scenarios (global) — master scenario catalog

## Migration principle — additive, not replacing

`data/aerowind_sites.json` is already consumed by several modules: `tools/poi_proximity.py`, `tools/seerist_collector.py`, `tools/threshold_evaluator.py`, `tools/rsm_input_builder.py`, `tools/build_context.py`, `tools/generate_sites.py`, and `.claude/hooks/validators/rsm-brief-context-checks.py`. These access **flat** keys (`site["lat"]`, `site["lon"]`, `site["poi_radius_km"]`, `site["criticality"]`, `site["personnel_count"]`, `site["expat_count"]`, `site["feeds_into"]`, `site.get("previous_incidents")`, `site.get("notable_dates")`, `site["site_lead"]`, etc.).

**Rule:** the Context tab's schema is **additive** — it extends the existing record with new fields but never renames, flattens, or drops existing ones. Every existing consumer continues to work without edits.

- Existing flat fields stay flat: `lat`, `lon`, `poi_radius_km`, `criticality`, `personnel_count`, `expat_count`, `country`, `region`, `type`, `subtype`, `shift_pattern`, `produces`, `dependencies`, `feeds_into`, `customer_dependencies`, `previous_incidents`, `notable_dates`, `site_lead`, `duty_officer`, `embassy_contact`.
- New fields listed below are **added alongside**.
- Where the RSM brief / Context tab UI needs a derived shape (nested `coordinates`, `tier` enum, `personnel` object, `last_incident`), it's computed from the stored flat fields — not replacing them.
- `criticality → tier` derivation: `crown_jewel → crown_jewel`, `major → primary`, `standard → secondary` (downgrade to `minor` explicitly per-site where appropriate — e.g., offices with ≤20 personnel).
- `lat + lon → coordinates`: computed property.
- `personnel_count + expat_count + new contractors_count → personnel`: computed struct.
- `previous_incidents[latest] → last_incident`: computed property.
- `poi_radius_km → seerist_poi_radius_km` (naming clarification): stored field stays `poi_radius_km`; callers referring to it by either name must resolve to the same value.
- `site_lead → country_lead`: both present. `country_lead` (new) can optionally be a richer record with email; `site_lead` (existing) retained for backward compatibility with current consumers.

The Context tab edits the full record. Consumers choose which shape to read from.

## Consolidated context schema

### Global layer (one org, one appetite)

**Company**
- `name`, `sectors[]`, `employee_count`, `countries_of_operation[]`
- `risk_appetite` — qualitative statement + quantitative bounds
- `strategic_priorities` — what the org considers mission-critical

**Master Scenarios** (register-linked)
- Scenario catalog as exists today in `data/master_scenarios.json` — moves into Context tab as editable surface, same schema.

**Cyber watchlist — global layer** (applies everywhere)
- `threat_actor_groups[]` — APTs, ransomware families, hacktivist collectives of org-wide interest. Each entry: name, aliases, motivation, typical TTPs, target sectors, target geographies.
- `sector_targeting_campaigns[]` — known active campaigns against energy / utilities / renewables / OT/ICS. Each entry: campaign name, actor, sectors hit, first observed, status.
- `cve_watch_categories[]` — CVE category tags relevant to AeroGrid stack (OT/ICS, SCADA, turbine control, grid management, identity, perimeter). Drives CVE/advisory filtering.
- `global_cyber_geographies_of_concern[]` — countries whose state-actor activity is org-wide relevant.

### Regional layer — Site registry

Per site, one record. Existing fields (flat, unchanged) + new fields (additive).

**Existing — flat, preserved for backward compatibility**
- `site_id`, `name`, `region`, `country`, `type`, `subtype`, `shift_pattern`, `criticality` (`crown_jewel | major | standard`)
- `lat`, `lon` — flat numbers
- `poi_radius_km` — flat integer
- `personnel_count`, `expat_count` — flat integers
- `produces`, `dependencies[]`, `feeds_into[]`, `customer_dependencies[]`
- `previous_incidents[]` — list of `{date, type, summary, outcome}`
- `notable_dates[]` — list of `{date, event, risk}`
- `site_lead` — `{name, phone}`
- `duty_officer` — `{name, phone}`
- `embassy_contact` — `{country_of_origin, contact, phone}`

**New — additive fields for the RSM brief pipeline and Context tab UI**

*Identity*
- `seerist_country_code` — ISO-3166 Alpha-2 (query key for Seerist). Often same as `country` but explicit for querying.
- `capital_distance_km` — cached, derivable from coords (optional)

*Criticality* (drives RSM block size + analysis depth)
- `tier` — `crown_jewel | primary | secondary | minor`. Initially derivable from `criticality` per the mapping above; explicit field lets a site be downgraded to `minor` where numeric size alone would overstate it.
- `criticality_drivers` — 1–2 sentences, *why* this site matters
- `downstream_dependency` — what breaks if it goes down (one line summary; complements `feeds_into` / `customer_dependencies` which remain as the graph)
- `asset_type` — `wind_farm | substation | ops_center | manufacturing | office | port` (complements existing `type`/`subtype`)
- `sector` — matches Seerist `sectors` config IDs (for verified-event filtering)
- `status` — `active | commissioning | decommissioned | planned`

*People*
- `contractors_count` — flat integer, additive to existing `personnel_count` / `expat_count`
- `country_lead` — `{ name, email, phone }` (additive to existing `site_lead`; often identical with email added)

*Environment* (baseline backdrop — deltas read against this)
- `host_country_risk_baseline` — `low | elevated | high`
- `standing_notes` — free text, RSM-authored, carries week to week
- `last_incident` (derived, not stored) — computed as the most recent entry in `previous_incidents`

*Seerist join keys* (enable agent analysis, not just query)
- `relevant_seerist_categories[]` — subset of `{ terrorism, unrest, conflict, crime, transportation, health, disaster, travel, elections }` — which categories matter here
- `threat_actors_of_interest[]` — Seerist `perpetrators` IDs the agent should prioritize for this site
- `relevant_attack_types[]` — Seerist `attackTypes` IDs that match this site's exposure

*Cyber join keys* (optional per site — drives per-site cyber callouts)
- `ot_stack[]` — SCADA, turbine control, grid management tech the site runs (vendor + product + version). Skip if unknown. Enables CVE/advisory matching.
- `site_cyber_actors_of_interest[]` — optional per-site overrides on top of the global cyber watchlist (rare — use only if a site has specific exposure not reflected globally).

### Regional layer — Cyber watchlist (regional overlay)

Each region extends (not replaces) the global cyber watchlist with region-specific cyber concerns. The agent reads `global ∪ regional` when assessing cyber signal.

- `regional_threat_actor_groups[]` — actors primarily active in this region (e.g., MED-focused hacktivists, APAC state actors). Same schema as global.
- `regional_sector_targeting_campaigns[]` — campaigns observed against the region's energy sector specifically.
- `regional_cyber_geographies_of_concern[]` — countries whose cyber activity is relevant to this region (origin-of-threat for this region's sites).
- `regional_standing_notes` — free text, RSM-authored, carries week to week (e.g., "increased scanning of Moroccan energy sector since Q1").

### Regional layer — People (optional, if country_lead expands)

- Contact directory per region — country leads, alternate contacts, escalation paths
- Keeps site records lean if a single country lead covers multiple sites

## The two-way feed (context ↔ data)

**Context drives queries:**
- `coordinates` + `seerist_poi_radius_km` → `/v1/wod?pois=[[lon,lat,r]]`
- `seerist_country_code` → `/v2/pulse/country/{code}`, `/v2/auto-summary/{code}/country`, `/v1/wod/risk-rating/{code}`
- `sector` + `asset_type` → verified-event filters
- `tier` → query depth (crown jewel gets deep pull; minor gets Pulse only)

**Context enables analysis joins** — for each Seerist signal returned, the agent asks:
- `signal.geo` close to `site.coordinates`? → proximity hit
- `signal.attack_type` in `site.relevant_attack_types`? → pattern hit
- `signal.perpetrator` in `site.threat_actors_of_interest`? → actor hit
- `signal.category` in `site.relevant_seerist_categories`? → category hit

Rank signals by hit count + severity + freshness → top N land in the output.

**Alignment principle:**
> Every dimension Seerist reports along (geo, attack type, perpetrator, sector, category, sentiment, severity) should have a matching context field that lets the agent answer *"is this relevant to us?"* for each returned event.

## Open questions for the next session

- Does Context replace "Settings → footprint" entirely, or just the intelligence parts?
- File-backed vs. database? If DB, migration path from current JSON files.
- How do edits to context trigger regeneration of affected outputs (manual refresh vs. reactive vs. scheduled)?
- Are scenarios truly global, or do regions override/extend the global list?
- Do we version context edits (audit trail for who changed a site's tier and when)?
- How does the existing Risk Register tab relate — do sites eventually become first-class register assets?

## Dependencies / consumers to audit

Every output that currently reads context:

- Overview tab → source boxes (reads company profile, sector tags)
- CISO brief → company framing, risk appetite
- Board report → portfolio exposure, site counts
- RSM weekly/daily/flash → sites (region filter), personnel counts, site discipline enforcement
- Risk Register → scenarios, VaCR inputs
- Source Librarian → register context, intent yamls

The audit output should be a matrix: output × context-field → where it's used, whether it's critical, what breaks if the field is missing.

## Deliverables

- `docs/superpowers/specs/YYYY-MM-DD-context-tab-design.md` — full design spec
- Implementation plan (separate) after spec approval
