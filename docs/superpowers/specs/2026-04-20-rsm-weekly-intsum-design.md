# RSM Weekly INTSUM — Design Spec

**Date:** 2026-04-20
**Status:** Draft — pending user review
**Scope:** Weekly INTSUM only. Daily + flash derivatives designed in a later session.

---

## Purpose

Deliver fast, high-quality regional intelligence to AeroGrid Regional Security Managers (RSMs) as a printed briefing pack, read in-person with country leads and site managers.

**Product promise:** *"The intelligence an RSM would have gathered themselves if they had 4 hours with Seerist — compressed into 10 minutes of reading."*

**Non-goal:** Decision-support or prescription. RSMs are expert professionals; they interpret and decide. Agents gather, correlate, and deliver — nothing more.

## Audience & Context

- **Primary reader:** Regional Security Manager (one per region — APAC, AME, LATAM, MED, NCE)
- **Secondary readers:** Country leads, site managers (present at the in-person briefing)
- **Read setting:** Printed PDF, sitting down, 10–15 minutes
- **Cadence:** Weekly (this spec). Daily + flash are derivatives designed later.

## Design Principles

1. **Intelligence delivery, not prescription.** No recommended actions, no decision asks, no "consequence if ignored."
2. **Physical is the center of gravity.** RSMs think in sites; cyber is a parallel strand that earns space only when it joins.
3. **Tier decides depth.** Crown-jewel sites always appear; minor sites earn space through joined evidence.
4. **Joins before volume.** Every Seerist/OSINT signal in the pack must clear a context join (proximity, attack type, actor, sector). Unjoined signal is noise.
5. **Visual rhythm over novelty.** Inherit CRQ Design System v1.0 from Board/CISO. Consistent grammar across all AeroGrid intelligence products.
6. **Scale with the week.** Pack length flexes with intelligence density. A quiet week is 3 pages; a hot week is 10.

## Context Dependency

This design consumes a consolidated per-site and regional context defined in `docs/superpowers/plans/2026-04-20-context-tab-architecture-brief.md`. The brief is the contract; implementation of the Context tab is a parallel workstream.

**Hard requirements this design places on context:**

- Per-site fields: `tier`, `coordinates`, `seerist_country_code`, `seerist_poi_radius_km`, `asset_type`, `sector`, `criticality_drivers`, `downstream_dependency`, `personnel`, `country_lead`, `host_country_risk_baseline`, `last_incident`, `standing_notes`, `relevant_seerist_categories`, `threat_actors_of_interest`, `relevant_attack_types`, `ot_stack` (optional)
- Regional cyber overlay: `regional_threat_actor_groups`, `regional_sector_targeting_campaigns`, `regional_cyber_geographies_of_concern`, `regional_standing_notes`
- Global layer: company profile, master scenarios, global cyber watchlist

If the Context tab is not shipped first, the RSM weekly runs off the existing `aerowind_sites.json` and stub watchlists until context catches up.

## Pack Structure

End-to-end order:

1. **Cover**
2. **p1 — Intelligence Summary**
3. **Crown-jewel + primary site blocks** (one each, variable length)
4. **Regional Cyber page**
5. **Secondary sites** (inline, header + 1–3 events each)
6. **Minor sites table** (single-row entries)
7. **Evidence appendix** (sectioned E/C)

### 1. Cover

Full briefing-pack cover — not minimal.

- Title: `AEROGRID // {REGION} WEEKLY INTSUM`
- Region (full name)
- Week of: `2026-04-20 → 2026-04-26`
- As-of timestamp: `Issued 2026-04-21 06:00Z`
- Prepared by: `AeroGrid Intelligence`
- Distribution list: named country leads addressed
- Classification band: `INTERNAL — AEROGRID SECURITY`
- Regional admiralty baseline: e.g., `B2`
- AeroGrid mark

### 2. p1 — Intelligence Summary

The one page that characterises the week.

Sections, top to bottom:

- **Headline line** — one sentence on the week's shape. Characterisation, not recommendation. *"Elevated unrest across MED maritime corridor; North Africa steady; Italy quiet."*
- **Baseline strip** — Pulse scores + forecast arrows for each country in the region; regional admiralty rating
- **Top events this week** — 5–8 items, ranked by relevance to AeroGrid sites (proximity + asset/attack join + actor watchlist match). Each item shows: what / where / when / severity / distance-to-nearest-site
- **Cyber strip** — 3–5 items (sector / actor / geography / CVE), ranked by fit to the region's context
- **Baselines moved** — any Pulse forecast or risk-rating change vs. last week. Fact only.
- **Reading guide** — site block list with page refs (acts as implicit TOC)

### 3. Site blocks — crown-jewel + primary

**Layout:** full-width header strip, two-column body below.

**Header strip (full width):**
- Site name
- Tier badge (pill — filled navy for crown_jewel, outlined for primary)
- Country
- Coordinates map thumbnail (small)
- Personnel count (total / expat / contractors)
- Country lead name

**Left column — Baseline:**
- Pulse score + forecast arrow
- Host-country risk rating
- `host_country_risk_baseline`
- Days since last incident
- `standing_notes` (RSM-authored)
- `criticality_drivers`

**Right column — This-week intelligence (ranked feed):**
- Proximity hits — events within `seerist_poi_radius_km`
- Pattern hits — `relevant_attack_types` / `relevant_seerist_categories` matches in country
- Actor hits — `threat_actors_of_interest` activity
- Calendar ahead — elections, anniversaries, high-severity future events

Each item: what / where / when / severity / distance / ref (`[E4]` etc.)

**Cyber callout (single line, block footer):**
- Only when a global/regional cyber event joins this site (actor on watchlist active in host country, CVE touching `ot_stack`, sector campaign in host country)
- Format: `CYBER: {one-line signal}. Ref C{n}.`

**Length:**
Variable. Full page if intelligence is rich; half page if the week is quiet baseline-only.

### 4. Stepped simplification down tiers

Each tier drops elements as it steps down:

- **Crown jewel:** header + baseline + full intelligence (proximity + pattern + actor + calendar) + cyber callout + evidence
- **Primary:** header + baseline + intelligence (proximity + pattern only) + evidence. Cyber callout only if it joins.
- **Secondary:** header + baseline strip + 1–3 events inline. No separate columns.
- **Minor:** table row only (see section 6).

### 5. Regional Cyber page

Mirrors the crown-jewel anatomy — the region's cyber treatment is structurally a site block.

**Header strip (full width):**
- Title: `CYBER — {REGION}`
- Regional admiralty for cyber signal
- Distinct accent mark (cyan rule line) to visually signal the switch from physical

**Left column — Baseline:**
- Sector posture (energy / utilities / renewables)
- Active regional campaigns count
- CVE watchlist count touching `cve_watch_categories`
- `regional_standing_notes`

**Right column — This-week cyber (four sub-sections as a ranked feed):**
- **Sector signal** — attacks on energy / wind / utilities globally this week
- **Actor activity** — APTs and groups from `global_cyber_watchlist ∪ regional_threat_actor_groups` active this week
- **Geography overlay** — cyber events in countries hosting our regional sites
- **Vulnerability signal** — CVEs and advisories affecting `ot_stack` or `cve_watch_categories`

### 6. Secondary sites (inline)

Inline block (not table, not full block). Header + 1–3 events.

Appears only if joined evidence exists this week. Otherwise the site rolls up into the minor-sites table below.

### 7. Minor sites table

Single page (or less) with one row per minor site in the region.

Columns: `site · country · pulse · forecast arrow · delta count · top-1 event headline (or "quiet")`

A minor site with a hot week gets promoted to secondary-style inline treatment and does not appear in the table.

### 8. Evidence appendix

Two sections: **Physical Evidence (E1–En)** and **Cyber Evidence (C1–Cn)**.

Per-entry fields (7):
1. Ref ID — `E4`, `C3`
2. Headline — one line
3. Source — publisher / outlet / Seerist feed
4. Admiralty rating
5. Timestamp
6. URL (optional — often ignored in print)
7. One-line "why it's here" — which site / pattern / actor it supports

## Document Chrome (every page except cover)

- Header left: `AEROGRID // {REGION} WEEKLY INTSUM`
- Header right: `Week of 2026-04-20 · Issued 2026-04-21 06:00Z`
- Footer left: `INTERNAL — AEROGRID SECURITY`
- Footer right: `Page X of Y · Reply: ACCURATE / OVERSTATED / FALSE POSITIVE`

The reply callback is chrome, not a separate page.

## Visual System

Inherits CRQ Design System v1.0 with no deviations:

- IBM Plex Sans typography
- Brand navy `#1B2D6E`
- Severity palette: CRITICAL `#d1242f`, HIGH `#cf6f12`, MEDIUM `#9a7300`, MONITOR `#0969da`
- Standard ink ramp
- Pill/badge treatment for tier badges
- Cyber section uses the same palette with a distinct accent rule (cyan) to mark the switch from physical

No new tokens, no new typography, no new grid rules. One design system across Board / CISO / RSM.

## Agent Behaviour (implementation-adjacent)

The RSM formatter agent produces the weekly by:

1. Reading per-site context from the Context tab (via loader)
2. Querying Seerist per site using context-driven parameters (`coordinates + seerist_poi_radius_km`, `seerist_country_code`, `sector`, `asset_type`, etc.)
3. Joining returned signals against context fields (`threat_actors_of_interest`, `relevant_seerist_categories`, `relevant_attack_types`)
4. Ranking joined signals by hit count + severity + freshness
5. Rendering per the pack structure above
6. Stop hooks validate site discipline, personnel counts, admiralty attribution, evidence-ref integrity

No decision recommendations. No scoring of sites. No prescriptive language. The agent's voice is that of a skilled analyst delivering correlated intelligence to a skilled consumer.

## Cadence Relationship (non-scope)

Daily and flash briefs will be designed as derivatives in a later session. They will share:
- Visual system (CRQ Design System v1.0)
- Site context schema
- Per-site cyber callout logic
- Evidence appendix structure

They will differ in:
- Length (1 page for daily; single card for flash)
- Scope (last 24h for daily; single event for flash)
- Chrome (tighter, less formal)

This spec does not specify daily or flash layouts.

## Regionalisation

One template. Five regional instantiations (APAC, AME, LATAM, MED, NCE). Structure is identical; content is drawn from the region's slice of the Context tab and the region's Seerist AoI. Cover and chrome swap in the region name.

## Open Questions for the Implementation Plan

- Rendering stack: reuse the Board/CISO pipeline (`tools/build_pdf.py` pattern with shared `brief_data.py` style) or separate renderer?
- Does the weekly pack generate at the same cadence as the Monday CRQ run, or on its own schedule?
- Who authors `standing_notes` and `regional_standing_notes` — RSM via the Context tab, or seeded by the agent and edited by the RSM?
- Map thumbnails in site headers — static assets at Context-entry time or rendered dynamically?
- PDF only, or PDF + PPTX (for in-session presentation to country leads)?

These are for the implementation plan, not the design spec.
