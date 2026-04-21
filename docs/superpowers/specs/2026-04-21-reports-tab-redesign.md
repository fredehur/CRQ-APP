# Reports Tab Redesign — Design Spec

**Date:** 2026-04-21 (v3 — added versioning/history layer)
**Status:** Approved, ready for implementation plan
**Context:** Brief PDF pipeline shipped v1.0 (Board, CISO, RSM) on 2026-04-21. The Reports tab is now misaligned with the deliverable — it renders its own in-browser versions of each brief in parallel with the PDFs, creating drift and ~800 lines of maintenance surface that will rot.

## Goal

Rebuild the Reports tab as a **card-grid launcher** for seven PDFs (CISO · Board · 5 RSM regions). Each card shows enough visual and temporal context for skim-QA at a glance; the full QA read happens in a new browser tab using the native PDF viewer.

## User & job-to-be-done

**Primary user:** the analyst QA'ing briefs before they go out.

**Job-to-be-done:** skim-level QA — look at the cover thumbnail and freshness, open the PDF in a real viewer (native browser tab), skim top-to-bottom, download, send externally.

**Not solving:**
- Deep claim-level QA with inline source traceability.
- In-browser distribution (send happens outside the tool).
- Diff-against-prior-cycle views.
- Exec-consumes-briefs-in-browser (the earlier in-browser renders were a wrong bet).

## Architecture

The Reports tab becomes a flat card grid. The existing `rpt-shell` (200px rail + flex content) is deleted — it was useful when each audience had custom in-browser content; with one PDF per audience, it's navigation overhead for no gain.

```
┌──────────────────────────────────────────────────────────┐
│ REPORTS                                                  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│  │ [thumb]    │  │ [thumb]    │  │ RSM        │          │
│  │            │  │            │  │ (5 cards)  │          │
│  │ CISO       │  │ BOARD      │  │            │          │
│  │ Today 04:12│  │ Today 04:12│  │            │          │
│  │ [P][R][↓]  │  │ [P][R][↓]  │  │            │          │
│  └────────────┘  └────────────┘  └────────────┘          │
│                                                          │
│  RSM — 5 regions                                         │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                      │
│  │APAC│ │AME │ │LATA│ │MED │ │NCE │                      │
│  │ …  │ │ …  │ │ …  │ │ …  │ │ …  │                      │
│  └────┘ └────┘ └────┘ └────┘ └────┘                      │
└──────────────────────────────────────────────────────────┘
```

**Top row** — CISO and Board (one card each).

**Bottom row** — five RSM region cards grouped under a subheader.

**Each card** — cover-page thumbnail, audience name, freshness label (relative date + UTC time), optional stale/error badge, a **version menu** ("Latest · Today 04:12 ▾" that opens the prior-versions list), and three buttons: **Preview** (opens PDF in new tab), **Regenerate**, **Download**. RSM cards additionally show a **Narrate** button (separate from Regenerate, because narration is an expensive AI call that produces new content). Selecting a prior version in the menu swaps the thumbnail and repoints Preview/Download to that specific version's file.

## Components

### 1. `AudienceCard`
Self-contained card for one audience (or one RSM region).

Input props:
- `id` — e.g. `ciso`, `board`, `rsm-med`
- `title` — display name
- `latest_meta` — `{version_ts, pipeline_run_id, stale, generated_by, narrated}` for the Latest version (or `null` if no versions exist yet)
- `canNarrate` — boolean, true only for RSM

Renders:
- Thumbnail image for the currently-viewed version (lazy-loaded, falls back to a neutral placeholder when no PDF yet)
- Title + relative freshness label derived from the viewed version's `version_ts`
- Stale badge when Latest's `stale === true` **and** the card is viewing Latest (prior versions never show the badge)
- Buttons: Preview, Regenerate, Download, (Narrate if `canNarrate`)
- Inline error strip when regenerate/narrate fails

Local state per card: in-flight (disables buttons + shows spinner on that card), error (shows strip). Card state never leaks to other cards.

### 2. `ThumbnailGenerator` (server-side)
A small addition to the PDF render path in `tools/briefs/renderer.py`: after Playwright creates the PDF, take an element screenshot of the first `.page` (the cover) via `await page.locator('section.page').first.screenshot(path=thumbnail_path)`, resized to ~480px wide (~40–80 KB). The renderer writes PDF + PNG to caller-provided paths (tmp dir); `storage.record_version()` then moves both files into the archive layout. One Playwright session produces both artifacts.

### 3. `RelativeDate` helper
Pure function `formatRelative(iso_utc) → string`. Examples:
- Same UTC day as now → `"Today · HH:MM UTC"`
- Previous UTC day → `"Yesterday · HH:MM UTC"`
- Older → `"Mon DD · HH:MM UTC"`

### 4. `OtherFormatsMenu` (per card)
A `▾` icon-button rendered at the end of the action row when an audience has secondary formats. CISO has this (DOCX). Board and RSM currently don't.

### 5. `VersionMenu` (per card)
A compact dropdown next to the freshness label.
- **Closed state, viewing Latest:** `"Latest · <relative date · UTC time> ▾"`
- **Closed state, viewing a prior version:** `"<relative date · UTC time> ▾"` with a subtle "Viewing older version · return to Latest" affordance.
- **Open state:** lists all versions newest-first (including Latest, marked); each row shows relative date + UTC time + narrated indicator if applicable.

Selecting a row:
- Sets the card's "viewing" version (client state, per card).
- Swaps the thumbnail `src` to that version's thumbnail.
- Repoints Preview/Download anchors to include `?version=<ts>`.
- Clicking "Latest" returns to the top.

Regenerate and Narrate always produce a new version at the top of the list; the menu refreshes and the card jumps back to viewing Latest.

## Data flow

Three paths.

### Render initial view
1. Reports tab mounts → GET `/api/briefs/` returns the full list of audiences, each with `{id, title, canNarrate, latest_meta}` where `latest_meta` is `{version_ts, pipeline_run_id, stale, generated_by, narrated}` for the Latest version.
2. Client renders one `AudienceCard` per entry; each card calls `GET /api/briefs/{id}/versions` lazily on first expand of its VersionMenu (or eagerly if that turns out to feel too slow — reassess after first usage).
3. Each card sets its thumbnail `<img src="/api/briefs/{id}/thumbnail?version=<ts>">` pointing at the Latest version's `version_ts`.

This replaces the hardcoded client-side `AUDIENCE_REGISTRY` for the Reports tab's internal use. (The registry stays as a thin client cache but is populated from the server response.)

### Preview
`<a href="/api/briefs/{id}/pdf?version=<ts>" target="_blank" rel="noopener">Preview</a>` — opens the currently-viewed version in a new browser tab. Omitting `?version=` resolves to Latest.

### Regenerate
1. Click → card's Regenerate button disables, spinner shows.
2. `POST /api/briefs/{id}/regenerate` with empty body.
3. Server calls the shared internal render function, writes PDF + thumbnail to `tmp/`, then `record_version()` atomically inserts the row, moves files to archive, and prunes old versions per retention policy.
4. On 200: response contains the new version's meta. Card appends the new version to the top of its list, jumps back to viewing Latest, refreshes thumbnail, clears stale badge.
5. On non-2xx: inline error strip. Archive is untouched — rollback semantics described in Storage section.

### Narrate (RSM only)
Same as Regenerate but with `POST /api/briefs/rsm/{region}/regenerate` body `{narrate: true}`. The new version's row has `narrated = 1`. Error handling identical.

### View prior version
1. User opens VersionMenu on a card, selects a prior entry.
2. Client updates card's "viewing" state to that `version_ts`.
3. Thumbnail, Preview, and Download anchors are repointed with `?version=<ts>`.
4. Nothing changes server-side.

### Download
`<a href="/api/briefs/{id}/pdf?version=<ts>" download>Download</a>` — same URL as Preview with the `download` attribute.

### Stale detection
- For CISO and Board, `pipeline_run_id` is the global pipeline run. `stale = current_global_run_id > rendered_run_id`.
- For RSM, `pipeline_run_id` is per-region. `GET /api/briefs/rsm/{region}/meta` returns the region-specific run; `stale = current_region_run_id > rendered_region_run_id`.
- Stale is evaluated against the **Latest** version of the audience, not the currently-viewed version. Viewing an older version never shows a stale badge — it just shows "Viewing older version" context.
- The server computes `stale` and returns it as a bool in the meta object. The client just renders the badge, no logic.

## Storage & retention

Designed for **eternal archive** from day one — the initial deployment keeps the last 5 versions per audience, but the storage schema and query paths place no upper bound. Flipping to unlimited retention is a single config change (`BRIEFS_RETENTION=0`) — no schema migration, no code change.

### Backend: SQLite + filesystem

**Database** — `data/briefs.db` (new SQLite file, following the existing `data/sources.db` pattern). Schema:

```sql
CREATE TABLE IF NOT EXISTS brief_versions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  audience_id      TEXT NOT NULL,          -- 'ciso', 'board', 'rsm-med', etc.
  version_ts       TEXT NOT NULL,          -- ISO 8601 UTC, e.g. '2026-04-21T04:12:00Z'
  pipeline_run_id  TEXT,                   -- null if produced outside a pipeline run
  pdf_path         TEXT NOT NULL,          -- relative path under output/deliverables/archive/
  thumbnail_path   TEXT NOT NULL,
  narrated         INTEGER NOT NULL DEFAULT 0,  -- 1 for RSM narrate=True
  generated_by     TEXT NOT NULL,          -- 'manual' | 'pipeline' | 'cron'
  metadata_json    TEXT,                   -- free-form JSON (e.g., region for RSM, brief length, etc.)
  UNIQUE(audience_id, version_ts)
);
CREATE INDEX IF NOT EXISTS idx_audience_ts
  ON brief_versions(audience_id, version_ts DESC);
```

**Files** — PDFs and thumbnails land under a versioned archive directory, not overwritten:

```
output/deliverables/archive/
├── ciso/
│   ├── 2026-04-21T04-12-00Z.pdf
│   ├── 2026-04-21T04-12-00Z.png
│   ├── 2026-04-18T14-03-00Z.pdf
│   └── 2026-04-18T14-03-00Z.png
├── board/
│   └── …
├── rsm-med/
│   └── …
```

(Filename colons replaced with hyphens for Windows compatibility. `version_ts` in the DB is canonical ISO 8601; the filename derivation is a one-line helper.)

Nothing lands at `output/deliverables/{id}.pdf` anymore — the "latest" resolution goes through the database. This removes symlinks, coexisting-file confusion, and stale overwrites.

### Retention policy

- Config constant in `tools/briefs/storage.py`: `RETENTION_PER_AUDIENCE = int(os.getenv("BRIEFS_RETENTION", "5"))`.
- `0` or negative = unlimited.
- After every `INSERT` into `brief_versions`, call `prune(audience_id)`:
  1. Query the N+1th oldest version for the audience (if retention is unlimited, skip).
  2. DELETE all rows older than that.
  3. `os.remove` the corresponding PDF + thumbnail files.
  4. Transaction-safe: if file removal fails, row is rolled back so the DB and filesystem stay in sync.

### Query paths

- **Latest version for audience X:**
  ```sql
  SELECT * FROM brief_versions WHERE audience_id = ?
  ORDER BY version_ts DESC LIMIT 1;
  ```
- **All versions for audience X (for VersionMenu):**
  ```sql
  SELECT version_ts, pipeline_run_id, narrated, generated_by
  FROM brief_versions WHERE audience_id = ?
  ORDER BY version_ts DESC;
  ```
- **Specific version:**
  ```sql
  SELECT * FROM brief_versions
  WHERE audience_id = ? AND version_ts = ?;
  ```

### Writing a new version

Atomic flow in `tools/briefs/storage.py::record_version(...)`:
1. Render PDF + thumbnail to a `tmp/` path first.
2. Begin SQLite transaction; INSERT the row.
3. Move tmp files to their archive paths (atomic on same filesystem).
4. Commit transaction.
5. Call `prune(audience_id)`.
6. On any failure between 1–4: rollback DB, clean tmp files, surface error to caller.

### Why SQLite + filesystem instead of blobs

- PDFs range 200KB–2MB — not trivial to stream from blob columns in Python/SQLite without memory tradeoffs. Filesystem is lighter and maps cleanly to `FileResponse`.
- Existing deploy has `data/sources.db` — no new infrastructure pattern.
- Migrating to Postgres later (for multi-user/multi-tenant) is a DSN swap; the schema is standard SQL.

## States

Three states per card.

### 1. No brief PDF yet
Thumbnail area shows a neutral placeholder ("No brief yet"). Freshness label is absent. Preview and Download buttons are disabled. Regenerate (and Narrate for RSM) is enabled only if pipeline data exists; otherwise disabled with tooltip "Run pipeline first."

### 2. Brief exists + stale
All buttons enabled. Freshness label shows the rendered timestamp plus a `⚠ Stale` badge next to it.

### 3. Regenerate/Narrate failed
Inline error strip below the card body (red-left border) with server error message. Thumbnail, freshness, and buttons all stay as they were before the failed action. Strip has a `×` dismiss button and auto-clears on next successful action.

## Scope of change

### Deleted from `static/app.js`
- `renderCisoView`, `renderBoardGlobalView`, `renderBoardRegionalView`, `renderRsmInReports`, `_hubGenerate`
- The `renderReports` / `renderReportsRail` / `renderAudienceContent` / `selectAudience` functions — replaced by a new `renderReports` that emits the card grid
- Any private helpers of the deleted functions that become dead code

### Deleted from `static/index.html` CSS
- Rail chrome: `.rpt-shell`, `.rpt-rail*`, `.rpt-rail-item*`, `.rpt-rail-subitem*`, `.rpt-rail-name`, `.rpt-rail-fmt`, `.rpt-live-badge`, `.rpt-plan-badge`, `.rpt-content`, `.rpt-action-bar*`
- Custom render chrome: `.rpt-section*`, `.rpt-cards`, `.rpt-card*`, `.rpt-decision*`, `.rpt-tp*`, `.rpt-watch*`, `.rpt-region-selector`, `.rpt-region-btn*`

### Added in `static/index.html` CSS
- `.rpt-grid` — CSS grid for the cards
- `.rpt-audience-card` — card shell with thumbnail slot, body, action row
- `.rpt-thumb` — thumbnail image + placeholder styles
- `.rpt-freshness` — relative date label
- `.rpt-stale-badge`, `.rpt-error-strip` — status elements
- `.rpt-card-btn` — unified card button style (Preview, Regenerate, Narrate, Download, ▾)

### Changes to `AUDIENCE_REGISTRY`
- The client-side hardcoded registry is reduced to a fallback; the canonical source is the server's `GET /api/briefs/` response.
- Drop `renderer`, `generate`, `subviews`, and `sales` (future) entries.
- Board no longer has subviews (there's one board PDF; the old Global/Regional Exec split was UI-only).
- RSM's 5 regions are returned as 5 entries (`rsm-apac`, `rsm-ame`, `rsm-latam`, `rsm-med`, `rsm-nce`).

### New in `server.py`
All endpoints route through `tools/briefs/storage.py` (new) for DB access; none touch the filesystem directly.

- `GET /api/briefs/` — list of audiences with `latest_meta`.
- `GET /api/briefs/{id}/meta` — Latest version meta. Accepts optional `?version=<ts>` for a specific version.
- `GET /api/briefs/{id}/versions` — list of all versions for the audience (newest first).
- `GET /api/briefs/{id}/pdf` — Latest PDF. Accepts `?version=<ts>`.
- `GET /api/briefs/{id}/thumbnail` — Latest PNG. Accepts `?version=<ts>`.
- `POST /api/briefs/{id}/regenerate` with optional `{narrate: bool}` body — renders, records a new version, prunes per retention.

### New modules
- `tools/briefs/storage.py` — owns SQLite connection, schema migration, `record_version()`, `list_versions()`, `get_latest()`, `get_specific()`, `prune()`, `RETENTION_PER_AUDIENCE` config.
- `data/briefs.db` — created on first server startup if absent (`CREATE TABLE IF NOT EXISTS`).

### Modified in `tools/briefs/renderer.py`
- `render_pdf(...)` extended to accept a `thumbnail_path` argument and produce the cover-page PNG alongside the PDF in the same Playwright session.
- Neither the PDF nor the PNG is written to a final destination by the renderer — paths are caller-provided (typically a tmp dir). `storage.record_version()` is responsible for moving both files into the archive layout atomically.

### Explicitly out of scope
- PPTX board endpoint / backend (legacy, not exposed in UI).
- CISO DOCX endpoint (stays reachable via "Other formats ▾" on the CISO card).
- History tab (`#tab-history`) merge — separate concern.
- Pipeline agents, brief data loaders, templates — v1.0, don't touch.
- Non-Chromium browsers.

## Testing

### New storage tests (`tests/briefs/test_storage.py`)
1. `record_version()` writes a row and moves files atomically; subsequent `get_latest()` returns the new row.
2. `prune()` with `RETENTION_PER_AUDIENCE=3` and 5 existing rows → keeps newest 3, deletes 2 PDFs and 2 thumbnails from disk.
3. `prune()` with `RETENTION_PER_AUDIENCE=0` → no-op, all rows retained.
4. `list_versions()` returns newest-first, one row per version, with expected fields.
5. `get_specific(audience_id, version_ts)` returns the right row; missing → None.
6. Failure during file move rolls back the DB insert (no orphan row, no orphan file).
7. Concurrent `record_version()` calls for the same audience get distinct `version_ts` and don't clobber files (use a monotonic timestamp helper, not wall-clock-only).

### New server tests (`tests/test_briefs_api.py`)
1. `GET /api/briefs/` returns audiences with `latest_meta`; empty archives resolve to `latest_meta=null` and 200.
2. `GET /api/briefs/ciso/meta` returns Latest meta; `?version=<ts>` returns that version's meta; unknown version → 404.
3. `GET /api/briefs/rsm-med/versions` returns the full list, newest-first.
4. `GET /api/briefs/ciso/pdf?version=<ts>` serves the correct file; Latest is served when `?version` is absent.
5. `GET /api/briefs/ciso/thumbnail?version=<ts>` serves PNG bytes.
6. `POST /api/briefs/ciso/regenerate` — invokes render (mock Playwright), inserts a new version, prior version still accessible via `?version=`.
7. `POST /api/briefs/rsm-med/regenerate` with `{narrate: true}` — new row has `narrated = 1`; narrate flag reaches `load_rsm_data` (mock Anthropic).
8. Stale computation — after N regenerations followed by a new pipeline run, only Latest's stale flips; prior versions are not flagged stale (they're historical by definition).
9. Error paths — unknown audience → 404; pipeline data missing for CISO → 4xx with descriptive body.

### New client tests (`tests/test_reports_tab.py` via Playwright automation)
1. Reports tab mounts, fetches `/api/briefs/`, renders one card per audience.
2. Preview button has `target="_blank"` and the correct href (including `?version=` for non-Latest).
3. Regenerate button click triggers POST to the correct endpoint with empty body; card's thumbnail src updates on response; VersionMenu gains a new top entry.
4. Narrate button visible only on RSM cards; click triggers POST with `{narrate: true}`.
5. Stale badge renders when the server returns `stale: true` on Latest; never renders when viewing a prior version.
6. VersionMenu lists all versions newest-first; selecting a prior version swaps thumbnail + repoints Preview/Download; clicking "Latest" returns to the top.
7. Error strip appears on regenerate failure and dismisses on `×`.

### Manual acceptance
- Eyeball the grid on a fresh pipeline run. Confirm thumbnails look right and freshness labels match. Click Preview on each card, confirm new-tab PDFs render.

### Not tested in this redesign
- PDF content (covered by `tests/briefs/`, 63 tests, unchanged).
- Deleted in-browser render paths (no code to test).

## Migration notes

1. The old Board subviews (Global, Regional Exec) disappear. If a separate regional-exec brief is needed later, it gets its own backend generator and its own entry in `/api/briefs/`.
2. The CSS deletions are aggressive but safe — every class removed is verified unused outside the deleted JS functions.
3. The thumbnail + archive features mean each render writes files under `output/deliverables/archive/`; verify this path is gitignored (likely already is — `output/` usually is).
4. The client-side `AUDIENCE_REGISTRY` stays as a fallback/schema definition, but its `renderer`/`generate`/`subviews`/`sales` fields go.
5. **Backfill:** existing PDFs at `output/deliverables/{board,ciso,rsm}_mock_test.pdf` won't appear in the archive DB. On first startup, run a one-time backfill that ingests those files (if present) as `generated_by='manual'`, `version_ts` from file mtime, so the archive isn't empty on day one.
6. **Retention is a config knob, not a bake-in.** Default is 5 via `BRIEFS_RETENTION=5` env var. Setting `BRIEFS_RETENTION=0` switches to eternal retention with no code change.

## Success criteria

1. Reports tab loads a card grid with 7 cards (CISO, Board, 5 RSM regions), each showing a thumbnail, a relative freshness label, and a VersionMenu.
2. Preview button opens the selected version's PDF in a new browser tab; the native PDF viewer loads with full controls (search, zoom, print).
3. Regenerate inserts a new row in `brief_versions`, writes PDF + thumbnail to the archive, prunes per retention, and the card refreshes without a full page reload.
4. Narrate is visible only on RSM cards, separate from Regenerate, produces a row with `narrated=1`, and threads through to `load_rsm_data(..., narrate=True)`.
5. Per-region stale detection works: running pipeline for MED marks only the MED card's Latest stale, not others, and prior versions are never flagged stale.
6. Relative date labels read as "Today / Yesterday / Mon DD" with UTC time.
7. VersionMenu lists prior versions newest-first; selecting a prior version swaps thumbnail + repoints Preview/Download without hitting the server beyond the file fetches.
8. With `BRIEFS_RETENTION=5` (default), a sixth regenerate of the same audience prunes the oldest version from both DB and disk. With `BRIEFS_RETENTION=0`, no pruning occurs.
9. First-run backfill ingests any pre-existing PDFs in `output/deliverables/` into the archive DB so the UI is populated on day one.
10. All deleted functions (`renderCisoView`, etc.) are fully removed from `static/app.js`; no dead CSS rules remain.
11. All new server + storage + client tests pass. All existing `tests/briefs/` (63) still pass.
