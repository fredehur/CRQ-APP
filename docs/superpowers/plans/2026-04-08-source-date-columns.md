# Source Date Columns — Implementation Plan

**Goal:** Add "Published" and "First Seen" columns to the Source Audit table, surfacing when a source article was published and when it first appeared in the pipeline.

**Architecture:** Three small edits — `server.py` adds `first_seen` to the API response, `index.html` adds the `Published` header and renames `Last Seen` → `First Seen`, `app.js` replaces the `last_seen` cell with `first_seen`. The `published_at` cell already exists in `app.js` but had no matching header; this fix aligns them.

**Tech Stack:** FastAPI (`server.py`) / vanilla JS (`static/app.js`) / HTML (`static/index.html`)

---

## File Map

| File | Action | Change |
|------|--------|--------|
| `server.py` | Modify line ~1548 | Add `first_seen` field to `/api/sources` response dict |
| `static/index.html` | Modify lines 1148–1151 | Add `Published` header, rename `Last Seen` → `First Seen` |
| `static/app.js` | Modify lines 3588–3589 | Replace `last_seen` cell with `first_seen`; label widths unchanged |

---

## Task 1: `server.py` — expose `first_seen` in API response

**Files:**
- Modify: `server.py:1536-1552`

The `/api/sources` endpoint returns a list of dicts. `first_seen` is in the DB but not returned. Add it.

- [ ] **Step 1: Open `server.py` and find the return block of `/api/sources`**

Located at approximately line 1536. It currently reads:

```python
return [
    {
        "id": r["id"],
        "url": r["url"],
        "name": r["name"],
        "domain": r["domain"],
        "published_at": r["published_at"] if "published_at" in r.keys() else None,
        "source_type": r["source_type"],
        "credibility_tier": r["credibility_tier"],
        "collection_type": r["collection_type"] if "collection_type" in r.keys() else "osint",
        "appearance_count": r["appearance_count"],
        "cited_count": r["cited_count"],
        "last_seen": r["last_seen"],
        "junk": r["junk"],
    }
    for r in rows
]
```

- [ ] **Step 2: Add `first_seen` to the return dict**

Replace the return block with:

```python
return [
    {
        "id": r["id"],
        "url": r["url"],
        "name": r["name"],
        "domain": r["domain"],
        "published_at": r["published_at"] if "published_at" in r.keys() else None,
        "first_seen": r["first_seen"] if "first_seen" in r.keys() else None,
        "source_type": r["source_type"],
        "credibility_tier": r["credibility_tier"],
        "collection_type": r["collection_type"] if "collection_type" in r.keys() else "osint",
        "appearance_count": r["appearance_count"],
        "cited_count": r["cited_count"],
        "last_seen": r["last_seen"],
        "junk": r["junk"],
    }
    for r in rows
]
```

- [ ] **Step 3: Verify the API returns first_seen**

With the server running (`uv run python server.py` on port 8001):

```bash
curl -s "http://localhost:8001/api/sources?limit=1" | python -m json.tool | grep first_seen
```

Expected: `"first_seen": "2026-04-06T..."` or `"first_seen": null`

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat(api): expose first_seen in /api/sources response"
```

---

## Task 2: `static/index.html` — fix column headers

**Files:**
- Modify: `static/index.html:1148-1151`

The current header row has no `Published` column header (ghost column) and shows `Last Seen` instead of `First Seen`.

- [ ] **Step 1: Find and replace the header row block**

Current (lines ~1146–1151):

```html
      <span style="flex:2;min-width:180px">Publication</span>
      <span style="width:100px;flex-shrink:0">Type</span>
      <span style="width:55px;flex-shrink:0">Tier</span>
      <span style="width:150px;flex-shrink:0">Usage</span>
      <span style="width:80px;flex-shrink:0">Last Seen</span>
      <span style="width:90px;flex-shrink:0">Actions</span>
```

Replace with:

```html
      <span style="flex:2;min-width:180px">Publication</span>
      <span style="width:100px;flex-shrink:0">Type</span>
      <span style="width:55px;flex-shrink:0">Tier</span>
      <span style="width:150px;flex-shrink:0">Usage</span>
      <span style="width:90px;flex-shrink:0">Published</span>
      <span style="width:80px;flex-shrink:0">First Seen</span>
      <span style="width:90px;flex-shrink:0">Actions</span>
```

Note: widths match the row renderer — `Published` is 90px (matching the existing `published_at` cell), `First Seen` is 80px (matching the existing cell that will show `first_seen`).

- [ ] **Step 2: Verify in browser**

Open Source Audit tab. Header row should now read:
`Publication | Type | Tier | Usage | Published | First Seen | Actions`

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): add Published header, rename Last Seen -> First Seen in Source Audit"
```

---

## Task 3: `static/app.js` — update row renderer

**Files:**
- Modify: `static/app.js:3588-3589`

The row renderer already has a `published_at` cell (90px) and a `last_seen` cell (80px). Replace `last_seen` with `first_seen`.

- [ ] **Step 1: Find the two date cells in the row renderer**

Current (lines ~3588–3589):

```javascript
    <span style="width:90px;flex-shrink:0;font-size:10px;color:${s.published_at ? '#8b949e' : '#484f58'}">${s.published_at ? s.published_at.slice(0,10) : '\u2014'}</span>
    <span style="width:80px;flex-shrink:0;font-size:10px;${_freshnessStyle(s.last_seen)}">${s.last_seen ? s.last_seen.slice(0,10) : '\u2014'}</span>
```

- [ ] **Step 2: Replace `last_seen` with `first_seen`**

```javascript
    <span style="width:90px;flex-shrink:0;font-size:10px;color:${s.published_at ? '#8b949e' : '#484f58'}">${s.published_at ? s.published_at.slice(0,10) : '\u2014'}</span>
    <span style="width:80px;flex-shrink:0;font-size:10px;${_freshnessStyle(s.first_seen)}">${s.first_seen ? s.first_seen.slice(0,10) : '\u2014'}</span>
```

The only change is `s.last_seen` → `s.first_seen` in both the style call and the display. `_freshnessStyle()` takes any ISO date string — no changes needed there.

- [ ] **Step 3: Verify in browser**

Reload the Source Audit tab. Each source row should show:
- `Published` column: article publication date or `—`
- `First Seen` column: date the source first appeared in the pipeline, colour-coded by age

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): show first_seen instead of last_seen in Source Audit rows"
```

---

## Self-Review

**Spec coverage:**
- ✅ `first_seen` added to API — Task 1
- ✅ `Published` header added — Task 2
- ✅ `Last Seen` renamed to `First Seen` in header — Task 2
- ✅ Row renderer updated to show `first_seen` — Task 3
- ✅ `published_at` cell already existed, now has matching header — Tasks 2+3

**Placeholder scan:** No TBDs, all code blocks complete, exact line references given.

**Type consistency:** `s.first_seen` used consistently in Task 3; `"first_seen"` key used consistently in Task 1 server response.
