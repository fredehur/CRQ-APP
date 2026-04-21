# Context Tab — Design Spec

**Date:** 2026-04-20
**Status:** Draft — pending user review
**Seed:** `docs/superpowers/plans/2026-04-20-context-tab-architecture-brief.md`

---

## Purpose

Give RSMs, country leads, and the CISO a single editable surface for the intelligence context every agent and output depends on — company profile, site records, cyber watchlists, and per-region standing notes. Today this context is fragmented across file-only JSON and a narrow "Footprint" sub-tab under Config. The Context tab consolidates it.

By the time this spec ships, `data/aerowind_sites.json` already carries the full `SiteContext` field set (populated by hand in Phase 5). This workstream is therefore **editor UI over already-populated data**, not schema invention.

## Scope fence

### In scope (v1)

1. New `Context` top-level tab, sibling to Overview / Reports / Risk Register / etc.
2. Region-first navigation: `Global | APAC | AME | LATAM | MED | NCE`.
3. Four editable surfaces:
   - **Global — Company** (one card)
   - **Global — Cyber Watchlist** (four sub-arrays)
   - **Regional — Sites** (list + detail split panel)
   - **Regional — Profile + Cyber Overlay** (free text + three sub-arrays)
4. CRUD API surface over existing JSON files, atomic tmp-file swap writes, additive-only for sites.
5. Context-flow matrix — documentation artifact at `docs/context-flow-matrix.md`.
6. Footprint sub-tab removal from Config; `regional_footprint.json` retained as the backing file.

### Deferred (later specs)

- Edits → pipeline regeneration wiring (manual re-run remains v1 model)
- Auth / per-region edit permissions (structure-only, no enforcement)
- Versioning / edit audit trail
- People as a separate sub-section (`country_lead` stays as a site field)
- Sites becoming first-class Risk Register assets
- Scenarios editing (already handled by the Risk Register tab — see "Scenarios overlap" below)

### Scenarios overlap — decision to exclude

The brief listed a Scenarios sub-section pointing at `data/master_scenarios.json`. On inspection, that file holds empirical industry baseline statistics (frequency %, financial impact %) — it is reference data, not intelligence context, and is rarely edited. The editable scenario instances live in `data/registers/*.json` and already have an editor (Risk Register tab, `PATCH /api/registers/{register_id}/scenarios/{scenario_id}`). A Scenarios panel in Context would duplicate that editor with no added surface. **Scenarios are excluded from v1.**

## Information architecture

Tab placement in the main nav:

```
Overview | Reports | Trends | History | Risk Register | Source Library | Context | Pipeline | Run Log
```

Inside the Context tab:

```
┌──────────────────────────────────────────────────────────────────┐
│ [ Global ]  [ APAC ]  [ AME ]  [ LATAM ]  [ MED ]  [ NCE ]       │ ← region strip
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   [region-specific panels render here]                           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Global view** shows: Company panel, Global Cyber Watchlist panel.

**Regional view** (any of APAC/AME/LATAM/MED/NCE) shows: Sites (list + detail), Regional Profile, Regional Cyber Watchlist overlay.

Region is the primary governance boundary — editing context for a region is the dominant task, so it sits at the top level. This mirrors Reports → RSM Briefs.

## Global view

### Company panel

Single card, always expanded. Backed by `data/company_profile.json`. Fields:

| Field | Control |
|---|---|
| `name` | text |
| `employee_count` | number |
| `sectors[]` | tag list (add/remove) |
| `countries_of_operation[]` | tag list |
| `risk_appetite` | textarea (qualitative) |
| `strategic_priorities` | textarea |

Single Save button. `PUT /api/context/company` replaces the full document.

### Global Cyber Watchlist panel

Backed by `data/cyber_watchlist.json` (new file). Four sub-arrays, each rendered as a row list with inline add/remove. Single Save for the whole document.

| Array | Row fields |
|---|---|
| `threat_actor_groups[]` | name, aliases[], motivation, target_sectors[], target_geographies[] |
| `sector_targeting_campaigns[]` | campaign_name, actor, sectors[], first_observed, status |
| `cve_watch_categories[]` | tag list (flat strings — OT/ICS, SCADA, turbine-control, grid-management, identity, perimeter) |
| `global_cyber_geographies_of_concern[]` | tag list (country codes or names) |

## Regional view

### Sites panel (list + detail)

Split layout:

```
┌─────────────────────────┬─────────────────────────────────────────┐
│ Site list (selected)    │ Site detail editor                      │
│   • Kaohsiung  [CJ]     │  ▸ Identity                             │
│   • Taipei     [PR]     │  ▸ Location                             │
│   • Shanghai   [SC]     │  ▸ Criticality                          │
│   • Tokyo      [MN]     │  ▸ People                               │
│                         │  ▸ Operations                           │
│                         │  ▸ Environment                          │
│                         │  ▸ Seerist Joins                        │
│                         │  ▸ Cyber                                │
│                         │                                         │
│                         │                              [ Save ]   │
└─────────────────────────┴─────────────────────────────────────────┘
```

**Left column** — compact site list for the current region. Each row: site name, tier badge (`crown_jewel / primary / secondary / minor`), personnel count. Click selects.

**Right column** — detail editor, scrollable, collapsible field groups:

| Group | Fields |
|---|---|
| Identity | `name`, `country`, `type`, `subtype`, `asset_type`, `status`, `seerist_country_code` |
| Location | `lat`, `lon`, `poi_radius_km` (editable); `capital_distance_km` (read-only) |
| Criticality | `tier`, `criticality`, `criticality_drivers` (textarea), `downstream_dependency` (text) |
| People | `personnel_count`, `expat_count`, `contractors_count`, `shift_pattern`, `site_lead {name, phone}`, `duty_officer {name, phone}`, `embassy_contact`, `country_lead {name, email, phone}` |
| Operations | `produces`, `dependencies[]`, `feeds_into[]`, `customer_dependencies[]`, `previous_incidents[]`, `notable_dates[]` |
| Environment | `host_country_risk_baseline` (select: low / elevated / high), `standing_notes` (textarea) |
| Seerist Joins | `relevant_seerist_categories[]` (multi-select), `threat_actors_of_interest[]` (tag list), `relevant_attack_types[]` (tag list) |
| Cyber | `ot_stack[]` (row editor: vendor + product + version), `site_cyber_actors_of_interest[]` (tag list) |

Save button at the bottom of the detail panel. `PUT /api/context/sites/{site_id}` writes the merged record back into `data/aerowind_sites.json`.

No add/delete in v1 — editing existing records only. The registry is created and grown outside the UI (provisioning scripts + Phase 5 population).

### Regional Profile panel

Backed by `data/regional_footprint.json[region]`. Fields:

| Field | Control |
|---|---|
| `regional_summary` | textarea |
| `standing_notes` | textarea |
| `headcount` (derived) | read-only — computed as `sum(personnel_count) + sum(expat_count)` across sites in region. `contractors_count` is **not** rolled into this number — it is tracked separately on site records for agent use and shown alongside headcount as a second figure (e.g. `headcount: 640 · contractors: 48`). This preserves the legacy Footprint semantics of "headcount = employees" while still surfacing contractor totals. |

The legacy Footprint fields `summary` and `notes` map to `regional_summary` and `standing_notes` respectively. `rsm_email` is dropped — nothing downstream consumed it. `headcount` becomes derived because the editable value drifted from the site records that actually back the pipeline.

### Regional Cyber Watchlist panel

Collapsed by default (most regions have no entries yet). Four fields:

| Field | Control |
|---|---|
| `regional_threat_actor_groups[]` | row list (same schema as global) |
| `regional_sector_targeting_campaigns[]` | row list (same schema as global) |
| `regional_cyber_geographies_of_concern[]` | tag list |
| `regional_standing_notes` | textarea |

**Single Save button for the whole regional record.** A Save control sits at the bottom of the combined Regional Profile + Regional Cyber Watchlist area (not one per panel). Clicking it fires a single `PUT /api/context/regional/{region}` with the merged payload (profile fields + cyber overlay arrays). This keeps writes atomic at the file level — the two panels are visually separate but edit the same backing document. Dirty state applies to the combined area; either panel becoming dirty enables the shared Save button.

## Edit semantics

Explicit Save on every panel. Dirty indicator on the panel header once a field changes. Save button enables only when dirty. On success the panel refetches and clears dirty state. On failure an inline error banner appears above the Save button (same pattern as current Sources/Footprint panels).

No auto-save. Context edits are authoritative inputs to agents — accidental keystrokes should not silently change agent behavior between runs.

## API surface

All endpoints live under `/api/context/*`. All writes use the atomic tmp-file swap pattern already in `server.py` (write to `.tmp`, then rename).

| Method | Path | Backing file | Semantics |
|---|---|---|---|
| `GET` | `/api/context/company` | `data/company_profile.json` | Returns full document |
| `PUT` | `/api/context/company` | `data/company_profile.json` | Full replace |
| `GET` | `/api/context/cyber-watchlist` | `data/cyber_watchlist.json` | Returns full doc; empty scaffold if file missing |
| `PUT` | `/api/context/cyber-watchlist` | `data/cyber_watchlist.json` | Full replace; creates file if missing |
| `GET` | `/api/context/sites?region=X` | `data/aerowind_sites.json` | Returns sites filtered by region |
| `PUT` | `/api/context/sites/{site_id}` | `data/aerowind_sites.json` | Per-site merge; additive only |
| `GET` | `/api/context/regional/{region}` | `data/regional_footprint.json` | Returns `footprint[region]` |
| `PUT` | `/api/context/regional/{region}` | `data/regional_footprint.json` | Replaces regional sub-document |

### Additive-only merge for sites

`PUT /api/context/sites/{site_id}` enforces the additive-migration invariant at the server layer. The handler:

1. Loads the site record from `data/aerowind_sites.json`.
2. Verifies the submitted payload does not **drop** any key already present in the stored record. If a key is missing from the payload, its stored value is preserved. (Setting a value to `null` / `""` / `[]` explicitly is allowed and distinct from omitting it.)
3. Applies submitted key→value pairs over the stored record.
4. Writes the full site array back via atomic swap.

This guarantees existing consumers (`poi_proximity.py`, `seerist_collector.py`, `threshold_evaluator.py`, `rsm_input_builder.py`, `build_context.py`, `generate_sites.py`, `rsm-brief-context-checks.py`) keep reading flat keys unchanged regardless of how the UI evolves.

### Error cases

| Case | Response |
|---|---|
| File missing (`cyber_watchlist.json`) on GET | 200 with empty scaffold `{threat_actor_groups: [], sector_targeting_campaigns: [], cve_watch_categories: [], global_cyber_geographies_of_concern: []}` |
| File missing on PUT | File created |
| Unknown `site_id` on PUT | 404 |
| Unknown region on GET/PUT | 400 |
| JSON decode failure in submitted body | 400 |
| Atomic write fails | 500, stored file untouched |

## Footprint retirement

- Remove `cfg-nav-footprint` nav entry from `static/index.html:1118`
- Remove `cfg-tab-footprint` panel from `static/index.html:1190-1192`
- Remove `loadFootprint`, `renderFootprint`, `toggleFpRegion`, `markFpDirty`, `saveFpRegion` from `static/app.js:2494-2575`
- Remove `.fp-*` CSS if unused elsewhere
- Remove the `/api/footprint` GET/PUT endpoints from `server.py:390-432` once the new `/api/context/regional/{region}` is wired
- `data/regional_footprint.json` is retained as the backing file for the new regional endpoint, extended with new fields (cyber overlay arrays, `regional_summary`, `standing_notes`)

No migration script is needed — the additive extension of `regional_footprint.json` happens naturally when the new endpoint first saves data.

## Context-flow matrix

Deliverable: `docs/context-flow-matrix.md`. Structure:

| Agent | Context fields read | Produces | Lands in |
|---|---|---|---|
| `gatekeeper-agent` | `sites.tier`, `sites.criticality`, `sites.sector`, `company.sectors` | Admiralty rating, scenario match | Regional `data.json` |
| `regional-analyst-agent` | `sites.*`, `company.*`, `regional_standing_notes`, `relevant_seerist_categories`, `threat_actors_of_interest` | Three-pillar brief | `sections.json` |
| `global-builder-agent` | `company.*`, all regional briefs | Global report | `global_report.json` |
| `rsm-formatter-agent` | per-region `sites.*`, `standing_notes`, cyber watchlist (global ∪ regional) | Weekly / daily / flash | `output/deliverables/` |
| `source-librarian` | `company_profile`, register scenarios | Reading list | Risk Register tab |

The matrix is a doc-only artifact — the spec commits the structure, the implementation plan populates the cells with line-level references.

## File inventory

| Status | File | Role after v1 |
|---|---|---|
| Existing | `data/company_profile.json` | Edited via Context → Company |
| Existing | `data/aerowind_sites.json` | Edited via Context → Sites (per-record) |
| Existing | `data/regional_footprint.json` | Edited via Context → Regional Profile + Cyber Overlay; Footprint sub-tab removed |
| New | `data/cyber_watchlist.json` | Edited via Context → Global Cyber Watchlist |
| Unchanged | `data/master_scenarios.json` | Not editable in Context (reference data) |
| Unchanged | `data/registers/*.json` | Edited via Risk Register tab |

## Frontend implementation notes

- Follow existing `static/app.js` pattern — plain ES modules, Tailwind utility classes, no framework dependency.
- New tab rendered in `static/index.html` alongside existing tab panels; new block wired into the `switchTab()` switch.
- State namespace: `contextState = { region, company, cyberWatchlist, sitesByRegion, regionalByRegion, dirty: {...} }`.
- One shared dirty-indicator util (reuse pattern from `markFpDirty`).
- Use existing severity/tier badge styles from the Risk Register and Overview tabs — do not introduce new visual tokens.

## Out of scope (explicit non-goals)

- No live pipeline regeneration on edit. Edits take effect on the next manual `/run-crq` or `/crq-region <REGION>` run.
- No field-level validation beyond basic type coercion (numbers stay numbers, arrays stay arrays). Semantic validation (e.g. `seerist_country_code` is a valid ISO-3166 code) is a later enhancement.
- No bulk import / export in v1.
- No inline map visualisation for `lat/lon`. A later enhancement.
- No creation of new sites / new scenarios / new watchlist entries beyond the row-list add/remove affordance already described. Site creation remains a provisioning-script task outside the UI.

## Success criteria

1. `Context` tab appears in main nav; selecting it shows the region strip and renders the Global view by default.
2. Switching region loads that region's Sites list + Regional Profile panel without a page reload.
3. Editing a field on any panel enables Save; clicking Save persists the change to disk and the panel refreshes to show the saved value.
4. Existing consumers of `data/aerowind_sites.json`, `data/company_profile.json`, `data/regional_footprint.json` continue to work unchanged — no flat-key renames, no additions to the stop-hook validator's rejection set.
5. Footprint sub-tab is gone from Config; the Config tab shows only the Intelligence Sources sub-panel.
6. `docs/context-flow-matrix.md` exists and covers all five agents.
7. `PUT /api/context/sites/{site_id}` refuses to drop existing keys — verified by an integration test that submits a partial payload and asserts omitted keys survive.
