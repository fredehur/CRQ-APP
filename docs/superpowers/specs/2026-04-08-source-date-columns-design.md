# Source Date Columns — Design Spec

**Date:** 2026-04-08
**Status:** Approved
**Scope:** Add "First Seen" and "Published" date columns to the Source Audit table

---

## Problem

The Source Audit table has no date context. Analysts cannot tell when a source first entered the pipeline (`first_seen`) or when the source article was published (`published_at`). Both fields exist in the database and are partially wired — `published_at` is rendered as a ghost column in `app.js` with no matching header in `index.html`, and `first_seen` is not rendered at all.

---

## Solution

Three small edits across three files:

1. **`server.py`** — add `first_seen` to the `/api/sources` response dict
2. **`static/index.html`** — fix header row: add `Published` header, rename `Last Seen` → `First Seen`
3. **`static/app.js`** — update row renderer: label the existing `published_at` cell correctly (width stays 90px), replace `last_seen` cell with `first_seen` (same freshness colour logic)

---

## Column Layout (after change)

| Column | Width | Source field | Notes |
|--------|-------|-------------|-------|
| ☐ | 24px | — | Checkbox |
| Publication | flex:2 min 180px | name/url | Existing |
| Type | 100px | source_type | Existing |
| Tier | 55px | credibility_tier | Existing |
| Usage | 150px | appearance_count / cited_count | Existing |
| Published | 90px | published_at | Already rendered, now has header |
| First Seen | 80px | first_seen | Replaces last_seen |
| Actions | 90px+70px | — | Existing |

`Published` shows `—` when null (many sources lack a publication date — normal).
`First Seen` uses the existing `_freshnessStyle()` colour logic (same as `last_seen` used to).

---

## Data Flow

```
sources_registry.first_seen  →  GET /api/sources  →  s.first_seen  →  table cell
sources_registry.published_at → GET /api/sources  →  s.published_at → table cell (already flowing)
```

`first_seen` is populated by `update_source_registry.py` at pipeline Phase 6 — it is set on first upsert and never overwritten.

---

## Out of Scope

- Sorting by date columns (future)
- `last_seen` removal from DB or API (keep in response for potential future use — just stop displaying it)
- Date formatting beyond `slice(0,10)` (ISO date prefix is readable enough)
