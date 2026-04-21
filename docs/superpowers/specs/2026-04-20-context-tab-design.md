# Context Tab — Design Spec (v2)

**Date:** 2026-04-20
**Status:** Draft — pending user review
**Seed:** `docs/superpowers/plans/2026-04-20-context-tab-architecture-brief.md`
**Supersedes:** v1 of this spec (commit `9e05fc0`) — rewritten after self-critique.

---

## Purpose

Give RSMs, country leads, and the CISO a single editable surface for intelligence context — company profile, site records, cyber watchlists, and regional standing notes. Today this context is fragmented across read-only JSON and a narrow Footprint sub-tab under Config. The Context tab consolidates it.

The Context tab is three kinds of surface, not one:

| Surface kind | Applies to | Starting state |
|---|---|---|
| **Editor** — modify already-populated records | Sites, Company profile | Pre-populated (sites by Phase 5; company_profile already exists) |
| **Capture** — build content that doesn't exist yet | Global Cyber Watchlist, Regional Cyber Overlay | Empty on first visit; user fills in |
| **Migration** — take over from a legacy surface | Regional Profile (absorbs Footprint) | Already has summary/notes/headcount; some fields re-homed |

Being honest about this up front matters — it changes what the UX must do. Editors need orderly field discipline; capture surfaces need low friction for adding rows; migrations need to preserve legacy consumers.

---

## Scope

### In scope (v1)

1. New `Context` top-level tab in the main nav.
2. Region-first navigation: `Global | APAC | AME | LATAM | MED | NCE` (same pattern as the region selector already in use on the Reports tab — a horizontal button strip that swaps the panel content below).
3. Four UI surfaces (defined in § UI surfaces).
4. Four backing JSON files (three existing, one new — defined in § Data model).
5. API: PUT-replace on every endpoint. No merge logic in handlers.
6. Footprint sub-tab removal from Config. `regional_footprint.json` retained as the backing file.
7. Context-flow matrix produced during implementation (schema fixed here, cells filled by the plan).

### Deferred

- Pipeline regeneration wiring on edit (manual `/run-crq` remains the model)
- Auth / per-region permissions
- Edit versioning / audit trail
- Concurrent-edit conflict resolution (v1 is last-writer-wins, explicitly)
- Field-level semantic validation (ISO-3166 codes, valid Seerist category IDs)
- Inline map for `lat/lon`
- Bulk import/export

### Explicitly excluded

- **Scenarios.** `data/master_scenarios.json` is empirical industry baseline statistics — reference data, not intelligence context. Register-level scenarios are already editable in the Risk Register tab. A Scenarios panel would duplicate an existing editor with no added surface.

---

## Data model

One section per backing file. Describes the on-disk shape independent of UI.

### `data/company_profile.json` (existing)

Full-document shape, edited as one record. Fields:

- `name` (string)
- `employee_count` (integer)
- `sectors[]` (array of strings)
- `countries_of_operation[]` (array of strings)
- `risk_appetite` (string — qualitative)
- `strategic_priorities` (string — qualitative)

### `data/aerowind_sites.json` (existing, extended by Phase 5)

Array of site records under `sites[]`. Per record — existing flat keys are preserved unchanged; Phase 5 adds the new keys alongside.

**Preserved (existing consumers depend on these):**
`site_id`, `name`, `region`, `country`, `lat`, `lon`, `type`, `subtype`, `poi_radius_km`, `personnel_count`, `expat_count`, `shift_pattern`, `criticality`, `produces`, `dependencies[]`, `feeds_into[]`, `customer_dependencies[]`, `previous_incidents[]`, `notable_dates[]`, `site_lead`, `duty_officer`, `embassy_contact`

**Added by Phase 5 (see brief for rationale):**
`seerist_country_code`, `capital_distance_km`, `tier`, `criticality_drivers`, `downstream_dependency`, `asset_type`, `sector`, `status`, `contractors_count`, `country_lead`, `host_country_risk_baseline`, `standing_notes`, `relevant_seerist_categories[]`, `threat_actors_of_interest[]`, `relevant_attack_types[]`, `ot_stack[]`, `site_cyber_actors_of_interest[]`

**`tier` ↔ `criticality` relationship.** Both fields exist. `criticality` is the legacy enum (`crown_jewel | major | standard`) read by existing consumers. `tier` is the newer enum (`crown_jewel | primary | secondary | minor`) read by the RSM brief pipeline. They serve different readers and are allowed to drift. The UI shows both fields; editing one does **not** cascade to the other. The spec accepts drift because coupling them would require touching every legacy consumer. A default derivation (`crown_jewel→crown_jewel`, `major→primary`, `standard→secondary`) is used once at Phase 5 population time; thereafter both are independently edited and neither is authoritative.

**`capital_distance_km`.** Computed once at Phase 5 population time from `lat/lon` against a countries-capitals table. Stored. UI treats it as read-only. No runtime recomputation.

### `data/regional_footprint.json` (existing, extended)

Object keyed by region code. Per region:

**Preserved (legacy consumers):**
`summary`, `headcount`, `notes`, `stakeholders[]`

**Added for v1:**
- `regional_summary` (string — aliased to `summary` at read time for legacy consumers; see migration note below)
- `standing_notes` (string — aliased to `notes`)
- `regional_threat_actor_groups[]` (array of objects — same shape as global)
- `regional_sector_targeting_campaigns[]`
- `regional_cyber_geographies_of_concern[]` (array of strings)
- `regional_standing_notes` (string — distinct from site-level `standing_notes`; describes region-wide cyber tempo)

**Migration note — `summary` / `notes` / `headcount`:**
- `summary` and `notes` are renamed in the UI to `regional_summary` and `standing_notes` but the file keeps writing both names on save. Legacy consumers (`build_context.py`, tests) continue to read `summary` / `notes` until they're migrated in a later pass. Double-write is a small cost, not worth a larger refactor.
- `headcount` stays in the file as a stored field. It is **no longer user-editable** in the new UI. On every regional save, the server recomputes `headcount = sum(site.personnel_count) + sum(site.expat_count)` across sites in the region and writes the computed value. `contractors_count` is not rolled in (preserves legacy "headcount = employees" semantics). `tools/build_context.py` continues reading `regional_footprint.headcount` unchanged.

### `data/cyber_watchlist.json` (new)

Full-document shape:

```
{
  "threat_actor_groups": [
    { "name": str, "aliases": [str], "motivation": str,
      "target_sectors": [str], "target_geographies": [str] }
  ],
  "sector_targeting_campaigns": [
    { "campaign_name": str, "actor": str, "sectors": [str],
      "first_observed": str, "status": str }
  ],
  "cve_watch_categories": [str],
  "global_cyber_geographies_of_concern": [str]
}
```

First visit: file does not exist. Server returns empty scaffold on GET. Server creates file on first PUT.

### `data/master_scenarios.json` and `data/registers/*.json`

Not touched by this workstream. Scenarios are edited in the Risk Register tab.

---

## UI primitives

Two primitives used across the tab. Defined once here; referenced by name in § UI surfaces.

### Tag List

For flat-string arrays (`sectors[]`, `countries_of_operation[]`, `cve_watch_categories[]`, etc.).

```
┌─────────────────────────────────────────────────────┐
│ [ energy ×] [ renewables ×] [ offshore wind ×]      │
│                                                     │
│ + Add tag:  [________________________]  (Enter)     │
└─────────────────────────────────────────────────────┘
```

- Existing tags: pill + `×` button. Click `×` removes.
- Input field at the bottom. Enter commits a new tag. Empty Enter is a no-op.
- No sorting, no dedup enforcement beyond warning on exact duplicate.

### Record List

For arrays of objects (`threat_actor_groups[]`, `previous_incidents[]`, `notable_dates[]`, `ot_stack[]`).

```
┌──────────────────────────────────────────────────────┐
│ ▸ Volt Typhoon (APT40 · China-linked)      [Edit ×]  │
│ ▸ FIN7 (ransomware · target: energy)       [Edit ×]  │
│                                                      │
│ [ + Add row ]                                        │
└──────────────────────────────────────────────────────┘
```

- Collapsed row = single-line summary (the first 1-2 fields).
- Expand (▸ → ▾) reveals an inline mini-form with all record fields as labeled inputs.
- `+ Add row` appends an empty record and auto-expands it.
- `×` prompts "Remove this entry?" confirm dialog.

Both primitives participate in dirty state (any add/remove/edit marks the containing surface dirty).

---

## UI surfaces

The tab has a top-level region selector strip. The surfaces below vary by selection.

```
Region selector:  [ Global ]  [ APAC ]  [ AME ]  [ LATAM ]  [ MED ]  [ NCE ]
```

**Global view** renders two surfaces. **Regional view** renders three surfaces.

| Surface | Shown when | Primitive type | Backing data | Starting state | Can add/remove rows? |
|---|---|---|---|---|---|
| Company | Global | Single form | `company_profile.json` | Populated | N/A (scalars) |
| Global Cyber Watchlist | Global | Tag Lists + Record Lists | `cyber_watchlist.json` | **Empty** (capture) | Yes |
| Sites | Regional | List + detail form | `aerowind_sites.json` | Populated (Phase 5) | **No** (edit existing only) |
| Regional Profile | Regional | Single form | `regional_footprint.json[region]` | Populated (legacy) | N/A |
| Regional Cyber Overlay | Regional | Tag Lists + Record Lists | `regional_footprint.json[region]` | **Empty** (capture) | Yes |

### Company (Global)

Single form card, always expanded. Fields: `name` (text), `employee_count` (number), `sectors[]` (Tag List), `countries_of_operation[]` (Tag List), `risk_appetite` (textarea), `strategic_priorities` (textarea). One Save button.

### Global Cyber Watchlist (Global)

Four sub-sections:
- `threat_actor_groups[]` → Record List (name, aliases[Tag List], motivation, target_sectors[Tag List], target_geographies[Tag List])
- `sector_targeting_campaigns[]` → Record List (campaign_name, actor, sectors[Tag List], first_observed, status)
- `cve_watch_categories[]` → Tag List
- `global_cyber_geographies_of_concern[]` → Tag List

One Save button at the bottom for the whole watchlist.

### Sites (Regional)

Split layout. Left: compact list of sites in the selected region. Each row shows name, `tier` badge, `personnel_count`. A small orange dot marks sites with unsaved edits (see § Dirty state).

Right: detail editor for the selected site, grouped into collapsible field groups. All groups collapsed by default except Identity and Criticality.

| Group | Fields |
|---|---|
| Identity | `name`, `country`, `type`, `subtype`, `asset_type`, `status`, `seerist_country_code` |
| Location | `lat`, `lon`, `poi_radius_km` (editable); `capital_distance_km` (read-only, greyed) |
| Criticality | `tier` (select), `criticality` (select), `criticality_drivers` (textarea), `downstream_dependency` (text) |
| People | `personnel_count`, `expat_count`, `contractors_count`, `shift_pattern`, `site_lead` (name+phone), `duty_officer` (name+phone), `embassy_contact`, `country_lead` (name+email+phone) |
| Operations | `produces`, `dependencies[]` (Tag List), `feeds_into[]` (Tag List), `customer_dependencies[]` (Record List), `previous_incidents[]` (Record List), `notable_dates[]` (Record List) |
| Environment | `host_country_risk_baseline` (select), `standing_notes` (textarea) |
| Seerist Joins | `relevant_seerist_categories[]` (Tag List — multi-select from enum), `threat_actors_of_interest[]` (Tag List), `relevant_attack_types[]` (Tag List) |
| Cyber | `ot_stack[]` (Record List: vendor, product, version), `site_cyber_actors_of_interest[]` (Tag List) |

Save button at the bottom of the detail column. Cannot add or delete sites in v1 — that's a provisioning task.

### Regional Profile (Regional)

Single form card. Fields:
- `regional_summary` (textarea)
- `standing_notes` (textarea)
- Read-only display: `headcount` (e.g. `3,200 employees`) and `contractors` (e.g. `48 contractors`) — both computed from site records at GET time.

### Regional Cyber Overlay (Regional)

Four sub-sections:
- `regional_threat_actor_groups[]` → Record List
- `regional_sector_targeting_campaigns[]` → Record List
- `regional_cyber_geographies_of_concern[]` → Tag List
- `regional_standing_notes` → textarea

**Regional Profile and Regional Cyber Overlay share one Save button** (bottom of the combined area). Both panels write the same backing file, so they commit together as one atomic `PUT /api/context/regional/{region}`.

---

## Dirty state and navigation

One rule, stated once.

Every surface tracks dirty state independently. When a surface is dirty:
- Its Save button is enabled; otherwise disabled.
- A small orange dot appears next to its header.
- For the Sites surface specifically, the dot also appears next to the dirty site in the list column.

**Navigating away from unsaved changes:**

| Action | Behavior |
|---|---|
| Click another site in the same region while Sites surface is dirty | Confirm dialog: "Discard unsaved changes to {site_name}?" → Discard / Cancel |
| Switch region while any surface in current region is dirty | Confirm dialog: "You have unsaved changes in {region}. Discard?" → Discard / Cancel |
| Switch to a different top-level tab (Overview, Reports, etc.) while any Context surface is dirty | Confirm dialog as above |
| Reload the page | Browser's native `beforeunload` prompt (via `window.onbeforeunload`) |

No auto-save. Last-writer-wins on the server (no optimistic concurrency, no ETag checks in v1).

---

## API

All endpoints under `/api/context/*`. Every write is full-document PUT — the client loads the current record, edits it, submits the whole record. Server does not merge partial payloads; it validates type shape and writes atomically.

| Method | Path | Backing | Semantics |
|---|---|---|---|
| GET | `/api/context/company` | `company_profile.json` | Returns full doc |
| PUT | `/api/context/company` | `company_profile.json` | Full replace |
| GET | `/api/context/cyber-watchlist` | `cyber_watchlist.json` | Full doc; empty scaffold if file missing |
| PUT | `/api/context/cyber-watchlist` | `cyber_watchlist.json` | Full replace; creates file if missing |
| GET | `/api/context/sites?region=X` | `aerowind_sites.json` | Returns sites filtered by region |
| PUT | `/api/context/sites/{site_id}` | `aerowind_sites.json` | Replaces the single site record with the submitted record. Preserves `site_id` and `region` (server rejects requests that change them — 400). |
| GET | `/api/context/regional/{region}` | `regional_footprint.json` | Returns `footprint[region]` with computed `headcount`/`contractors` added |
| PUT | `/api/context/regional/{region}` | `regional_footprint.json` | Replaces regional sub-document. Server recomputes `headcount` from sites at write time and writes the legacy `summary` / `notes` aliases alongside the new `regional_summary` / `standing_notes` keys |

### Schema-additive rule

The existing-flat-keys invariant (`data/aerowind_sites.json` never renames or drops existing keys) is a **code-review invariant**, not an HTTP handler responsibility. Reviewers block PRs that rename flat keys; the handler itself does full-replace without per-request merge logic.

### Error cases

| Case | Response |
|---|---|
| File missing on GET (`cyber_watchlist.json` only — others must exist) | 200 with empty scaffold |
| File missing on PUT | File created |
| Unknown `site_id` on PUT | 404 |
| PUT body changes `site_id` or `region` | 400 |
| Unknown region on GET/PUT | 400 |
| JSON decode failure | 400 |
| Atomic write fails | 500; stored file untouched |

---

## Footprint retirement

Once the new regional endpoint is wired and the Context tab ships:

1. Remove `cfg-nav-footprint` entry and `cfg-tab-footprint` panel from `static/index.html` (~lines 1118, 1190-1192).
2. Remove `loadFootprint`, `renderFootprint`, `toggleFpRegion`, `markFpDirty`, `saveFpRegion` from `static/app.js` (~lines 2494-2575).
3. Remove `.fp-*` CSS if unused.
4. Remove `/api/footprint` GET/PUT from `server.py:390-432`.
5. `data/regional_footprint.json` stays. Its `summary` / `notes` keys are still written (aliased) so `build_context.py` keeps working.

No data migration script is required — the file is extended additively and the aliases keep legacy consumers reading unchanged values.

---

## Context-flow matrix

Produced as an implementation plan task. Lives at `docs/context-flow-matrix.md`. Committed schema:

| Column | Meaning |
|---|---|
| `agent` | Agent name (from `.claude/agents/`) |
| `context_fields_read` | List of `file:field` pairs the agent reads at runtime |
| `produces` | Names of outputs the agent writes |
| `downstream_consumers` | Deliverables that include this agent's output |
| `source_ref` | `path/to/file.py:line` where the read or write happens |

Agents covered: `gatekeeper-agent`, `regional-analyst-agent`, `global-builder-agent`, `rsm-formatter-agent`, source librarian tools. One row per (agent, field) pair.

The spec commits only the schema. The plan produces the filled matrix by reading the code.

---

## Frontend implementation notes

- New tab block in `static/index.html` alongside existing `<div id="tab-*">` panels.
- Wire into `switchTab()`.
- New state namespace `contextState = { currentRegion, company, cyberWatchlist, sitesByRegion, regionalByRegion, dirty: { company: bool, cyberWatchlist: bool, regional: { APAC: bool, ... }, sites: { [site_id]: bool } } }`.
- **Loading lifecycle:** `currentRegion` defaults to `Global`. Global view fetches `company` and `cyberWatchlist` on first visit. Switching to a region fetches that region's sites and regional record. All fetched data is cached in-memory; a "Refresh" button on each surface forces refetch. No periodic polling.
- Reuse severity/tier badge CSS from Risk Register and Overview tabs. No new visual tokens.
- Tag List and Record List are implemented once as small rendering utilities and called by each surface.

---

## Test plan

Integration + UI smoke coverage for v1:

| Test | What it proves |
|---|---|
| `GET /api/context/company` returns current `company_profile.json` | Read path works for existing file |
| `PUT /api/context/company` round-trips — GET after PUT returns the posted body | Full-replace semantics |
| `GET /api/context/cyber-watchlist` with file missing returns empty scaffold | New-file fallback |
| `PUT /api/context/cyber-watchlist` creates the file | Capture-surface bootstrapping |
| `PUT /api/context/sites/{site_id}` with changed `site_id` in body → 400 | Identity key protection |
| `PUT /api/context/sites/{site_id}` for site with rich legacy fields → file preserves all legacy flat keys the payload included | Full-replace doesn't corrupt; schema-additive is respected by the client |
| `PUT /api/context/regional/APAC` recomputes `headcount` from APAC sites and writes it back | Headcount derivation works |
| `PUT /api/context/regional/APAC` writes both `summary` (legacy alias) and `regional_summary` | Alias double-write works |
| After editing `tier` in the UI and Save, re-running `/crq-region APAC --mock` produces a brief that reflects the new tier in gatekeeper scenario match | **End-to-end functional** — the whole loop works |
| Navigating away from a dirty site with the list-click triggers the confirm dialog | Dirty-state guard works |
| Footprint sub-tab is removed from Config, Config shows only Intelligence Sources | Legacy retirement |

---

## Success criteria

1. `Context` tab appears in main nav; default view is Global; Global shows Company + Global Cyber Watchlist.
2. Switching region loads that region's Sites list + Regional Profile + Regional Cyber Overlay without a page reload.
3. Every surface can be edited and saved; changes persist to disk and the panel refetches to show the saved value.
4. Existing consumers of `aerowind_sites.json`, `company_profile.json`, `regional_footprint.json` continue to read unchanged flat keys after the first Context edit — verified by `tools/build_context.py` still producing the same output for an unchanged region.
5. Footprint sub-tab is gone from Config; Config shows only Intelligence Sources.
6. `docs/context-flow-matrix.md` exists and has at least one row per agent.
7. **End-to-end:** editing a site's `tier` in the UI, saving, then running `/crq-region APAC --mock` produces a brief reflecting the new tier in the gatekeeper's scenario-match logic. This is the functional proof the Context tab actually controls agent behavior.

---

## Open decisions requiring user signoff

None at the spec level — all the pre-rewrite ambiguities are resolved in the text above. Open items for the implementation plan:

- Whether the `tier` enum options in the UI dropdown should include all four values (`crown_jewel / primary / secondary / minor`) regardless of current record value. Assumed yes.
- Whether `seerist_country_code` / `relevant_seerist_categories` etc. dropdowns should enumerate only the values Seerist actually supports (requires importing those enums from `tools/seerist_client.py`) or accept free text. Assumed free text for v1; enum tightening later.
- Whether a "Refresh" button per surface is a v1 polish item or a later enhancement.
