# Source Audit Tab — Redesign Spec
**Date:** 2026-04-06
**Status:** Approved for implementation

---

## Goal

Make the Source Audit tab useful for an analyst auditing intelligence source quality — not just a registry dump. Every row should be scannable at a glance; bulk operations should be one action; source credibility should be visible without expanding rows.

---

## Features (6 approved)

### 1. Keyword search bar
A text input anchored left in the filter bar. Filters client-side across `name`, `domain`, and `url` fields on every keystroke. No server roundtrip needed — sources are already loaded.

- Placeholder: `"Search publications, domains..."`
- Blue focus border (`#388bfd`) to signal it's the primary control
- Position: left side of filter bar, flex:1, max-width 260px
- Stats summary (`108 sources · 34 cited · 6 junk`) moves to right side, separated by a 1px divider

**Interaction with server filters:** The existing region/tier/type/cited/hide_junk filters still trigger a server fetch (`GET /api/sources?...`). Keyword search operates as a client-side post-filter on the fetched array — it does NOT re-fetch. `applySourceSearch(query, sources)` takes the already-loaded array and returns a filtered subset. Called inside `renderSourceRegistryTable()` after fetch completes.

### 2. Merged "Usage" column
Replaces the separate `Appearances` and `Citation rate` columns with a single `Usage` column showing:
```
[count]  [progress bar]  [pct%]
  14     ████░░░░░░        70%
```
- Bar width: 55px, height: 4px, border-radius: 2px
- Bar + percentage colour: green >60%, amber 20–60%, grey <20%
- Count: always `#8b949e`
- Benchmark sources: show `— benchmark anchor` italic in this column (no bar, not applicable)
- Freed column space goes to `flex:2` publication name column

**Parent row aggregation:** `sum(cited_count) / sum(appearance_count)` across all child members. Not the first member's value.

### 3. Citation + freshness colour signals
Applied on every parent row without expanding:

**Citation bar colour thresholds:**
- Green (`#3fb950`): cited_count / appearance_count > 60%
- Amber (`#e3b341`): 20–60%
- Grey (`#6e7681`): < 20%

**Freshness colour on `last_seen` date:**
- Green (`#3fb950`): within 14 days
- Amber (`#e3b341`): 15–42 days
- Red (`#f85149`) + `font-weight:600`: older than 42 days
- Null/missing `last_seen`: render `—` in `#484f58`, no colour signal

### 4. Tier override (click badge → dropdown)
The tier badge (`A ▾`, `B ▾`, `C ▾`) is clickable. Click opens an inline dropdown below the badge showing A / B / C options coloured by tier. Selecting a tier:
- `POST /api/sources/{id}/tier` with `{ tier: "A" }`  
- Updates `credibility_tier` in `sources_registry`
- Re-renders the row (no full table reload)

**Scope of change:** Clicking tier on a parent row changes **all child URLs** from that publication to the same tier (loop over member IDs). Clicking on an individual child row changes only that URL. Parent badge shows the representative (first member) tier.

New server endpoint: `POST /api/sources/{id}/tier` — body `{ tier: string }`, validates A/B/C, updates DB.

Dropdown styling:
- Background: `#161b22`, border: `1px solid #388bfd`, border-radius: 4px
- A row: `#3fb950`, B row: `#e3b341`, C row: `#6e7681`
- Closes on outside click

### 5. Prominent links with pill-action buttons
In child rows (expanded), each URL gets:
- Domain + path as a blue link (`#79c0ff`), `target="_blank"`, `title="{full url}"`
- URL text truncated: `overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 280px`
- Favicon via `https://www.google.com/s2/favicons?domain={domain}&sz=16`, 12×12px, `onerror="this.style.display='none'"`
- `↗` pill button: opens URL in new tab (bordered, 9px, `#484f58`)
- `copy` pill button: copies full URL to clipboard via `navigator.clipboard.writeText(url)`. On success: button text changes to `✓` for 1000ms then reverts to `copy`. No feedback on failure (silent).

Pill button style: `border: 1px solid #21262d; border-radius: 2px; padding: 0 4px; font-size: 9px; line-height: 16px; cursor: pointer`

Favicons also shown on parent rows for publication recognition at a glance.

### 6. Bulk flag with select-all
**Checkboxes:** Added as first column (24px wide) on both parent and child rows.

**Select-all:** Checkbox in column header selects/deselects all currently visible rows.

**Bulk action bar:** Conditionally rendered between the filter bar and column header. Hidden when nothing is selected, visible when ≥1 checkbox is checked.
- Left border: `2px solid #e3b341`
- Background: `#161b22`
- Shows: `N selected` (amber) + `Flag as junk` button (red) + `Clear` button (grey)
- Flagging uses `Promise.all()` — parallel calls to `POST /api/sources/{id}/flag` with `{ junk: true }` for all selected IDs. Re-renders table after all resolve.

**Checkbox state:** Tracked in `state.selectedSourceIds = new Set()`. Parent checkbox checked = all child IDs added to set. Individual child checkbox toggles that ID only. Select-all header checkbox adds/removes all currently visible source IDs.

**No "Flag all" button on parent rows** — removed. The bulk flag via action bar (check parent row → flag) covers this case with one extra click and is less confusing.

---

## Layout changes summary

| Column | v1 | v2 |
|---|---|---|
| Checkbox | — | 24px (NEW) |
| Publication | flex:2 min 160px | flex:2 min 180px |
| Type | 100px | 100px |
| Tier | 50px | 55px |
| Citation rate | 110px | — (REMOVED) |
| Appearances | 90px | — (REMOVED) |
| Usage (merged) | — | 150px (NEW) |
| Last seen | 80px | 80px |
| Actions | 80px | 90px |

---

## New API endpoint

```
POST /api/sources/{id}/tier
Body: { "tier": "A" | "B" | "C" }
Response: { "ok": true }
```

Updates `credibility_tier` in `sources_registry`. Returns 400 if tier not in A/B/C.

---

## Files to change

| File | Change |
|---|---|
| `static/app.js` | `renderSourceRegistryTable()` — new columns, citation bar, freshness, checkboxes, bulk bar, tier dropdown, pill buttons. `renderSources()` — keyword search filter. New: `flagAllSources()`, `overrideTier()`, `copyUrl()`, `applySourceSearch()` |
| `static/index.html` | Add `<input id="src-search">` to filter bar HTML (filter controls are HTML, not JS-rendered). Remove separate cited/hide-junk checkboxes from layout if they move inline. |
| `server.py` | Add `POST /api/sources/{id}/tier` endpoint |

---

## Out of scope
- Source sparklines / longitudinal trends (M5, time-gated)
- Region heatmap per source
- CSV export
- Group-by-region view
- Audit note / comment field
