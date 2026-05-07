# Reports Tab Redesign — Design Spec

**Date:** 2026-04-21 (v5 — pipeline run ID plumbing, orphan sweep, download filename)
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
- `versions` — newest-first list of `VersionRecord` (empty list if no versions yet)
- `canNarrate` — boolean, true only for RSM

Renders:
- Thumbnail image for the currently-viewed version (lazy-loaded, falls back to a neutral placeholder when no PDF yet)
- Title + relative freshness label derived from the viewed version's `version_ts`
- Stale badge when Latest's `stale === true` **and** the card is viewing Latest (prior versions never show the badge)
- Buttons: Preview, Regenerate, Download, (Narrate if `canNarrate`)
- Inline error strip when regenerate/narrate fails

Local state per card: in-flight (disables buttons + shows spinner on that card), error (shows strip). Card state never leaks to other cards.

### 2. `ThumbnailGenerator` (server-side)
Added to `tools/briefs/renderer.render_pdf(...)` — the existing shared render entry point. After Playwright creates the PDF:
```python
await page.locator('section.page').first.screenshot(path=thumbnail_path)
```
This takes an element screenshot of the cover page. To keep file size manageable without adding a PIL dependency, set Playwright viewport width to `480px` for the screenshot pass only (re-use the same browser context but a second page, or downscale via `clip`). Expect ~80–150 KB PNGs. The renderer writes PDF + PNG to caller-provided tmp paths; `storage.record_version()` moves both into the archive. One Playwright session produces both artifacts.

### 3. `RelativeDate` helper
Pure function `formatRelative(iso_utc) → string`. Examples:
- Same UTC day as now → `"Today · HH:MM UTC"`
- Previous UTC day → `"Yesterday · HH:MM UTC"`
- Older → `"Mon DD · HH:MM UTC"`

### 4. `OtherFormatsMenu` (per card)
A `▾` icon-button rendered at the end of the action row when an audience has secondary formats. CISO has this (DOCX). Board and RSM currently don't.

### 5. `VersionMenu` (per card)
The freshness label IS the dropdown trigger — not a separate element. Clicking the freshness label opens the menu.
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
1. Reports tab mounts → GET `/api/briefs/` returns the full list of audiences, each with `{id, title, canNarrate, latest_meta, versions}` where `versions` is the full newest-first list (typically ≤5 rows × 7 audiences ≈ 35 rows, a few KB of JSON — eager fetch, no lazy loading).
2. Client renders one `AudienceCard` per entry.
3. Each card sets its thumbnail `<img src="/api/briefs/{id}/thumbnail?version=<ts>">` pointing at the Latest version's `version_ts`.

This replaces the hardcoded client-side `AUDIENCE_REGISTRY` for the Reports tab's internal use. (The registry stays as a thin client cache but is populated from the server response.)

### Preview
`<a href="/api/briefs/{id}/pdf?version=<ts>" target="_blank" rel="noopener">Preview</a>` — opens the currently-viewed version in a new browser tab. Omitting `?version=` resolves to Latest.

### Regenerate
1. Click → card's Regenerate button disables, spinner shows.
2. `POST /api/briefs/{id}/regenerate` with empty body.
3. Server renders PDF + thumbnail to a tmp dir, then `storage.record_version()` moves both into the archive, writes the sidecar JSON, and prunes per retention policy.
4. On 200: response returns the new `VersionRecord` and the updated `versions` list. Card appends the new version to the top, jumps back to viewing Latest, refreshes thumbnail, clears stale badge.
5. On non-2xx: inline error strip; archive is untouched (sidecar-last ordering ensures no partial version).

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
- For RSM, `pipeline_run_id` is per-region. `stale = current_region_run_id > rendered_region_run_id`.
- If a version has `pipeline_run_id = null` (manual render, not tied to a pipeline run), `stale` is always `false` — manual renders are explicit snapshots, not candidates for staleness.
- Stale is evaluated against the **Latest** version of the audience only. Prior versions are never flagged stale — they're historical by definition.
- The server computes `stale` and returns it as a bool in the meta object. The client just renders the badge.

## Storage & archive

Filesystem-backed archive with sidecar JSON for metadata. Designed for a clean future migration to SQLite (or Postgres) when query needs grow beyond "list versions for audience X" — the `storage.py` module interface stays the same across backends.

### Layout

```
output/deliverables/archive/
├── ciso/
│   ├── 20260421T041200Z.pdf
│   ├── 20260421T041200Z.png
│   ├── 20260421T041200Z.json   ← sidecar metadata
│   ├── 20260418T140300Z.pdf
│   ├── 20260418T140300Z.png
│   └── 20260418T140300Z.json
├── board/
│   └── …
├── rsm-apac/
│   └── …
├── rsm-ame/
├── rsm-latam/
├── rsm-med/
└── rsm-nce/
```

One directory per `audience_id`. Three files per version, all sharing the same `{version_ts}` basename.

### Timestamp format

- Filenames: `YYYYMMDDTHHMMSSZ` (no colons, no hyphens) — sortable, OS-portable, compact.
- Sidecar JSON + API responses: ISO 8601 `YYYY-MM-DDTHH:MM:SSZ` — human-readable.
- Conversion is a one-line helper in each direction.

### Sidecar JSON

```json
{
  "audience_id": "rsm-med",
  "version_ts": "2026-04-21T04:12:00Z",
  "pipeline_run_id": "run-2026-04-21-0412",
  "narrated": true,
  "generated_by": "manual",
  "metadata": { "region": "MED" }
}
```

Sidecars are the source of truth for version metadata. Filesystem listing + parsing sidecars IS the index.

### `tools/briefs/storage.py` — module interface

The public interface is backend-agnostic — its internals can swap to SQLite later without changing any caller:

```python
def record_version(
    audience_id: str,
    pdf_tmp_path: Path,
    thumbnail_tmp_path: Path,
    pipeline_run_id: str | None,
    narrated: bool,
    generated_by: str,
    metadata: dict,
) -> VersionRecord: ...

def list_versions(audience_id: str) -> list[VersionRecord]: ...   # newest first
def get_latest(audience_id: str) -> VersionRecord | None: ...
def get_specific(audience_id: str, version_ts: str) -> VersionRecord | None: ...
def prune(audience_id: str) -> int: ...                           # returns count removed
```

`VersionRecord` is a frozen dataclass with the sidecar fields plus resolved `pdf_path` and `thumbnail_path`.

### Writing a new version (atomicity)

`record_version()`:
1. Validate tmp files exist and are non-empty.
2. Compute `version_ts = utc_now_iso()`; derive filename basename.
3. Move PDF and PNG from tmp → archive dir (two `os.replace` calls — atomic on same filesystem).
4. Write sidecar JSON last (signals "this version is complete"). Failure here deletes the moved files and re-raises.
5. Call `prune(audience_id)`.

Sidecar-written-last is the completeness marker: `list_versions()` ignores directories where a version's sidecar is missing (partial writes are skipped).

### Retention

- Config: `BRIEFS_RETENTION = int(os.getenv("BRIEFS_RETENTION", "5"))`, read once at module import. `0` or negative = unlimited.
- `prune(audience_id)` lists versions newest-first, keeps the first N, deletes the remainder (pdf + png + json, in that order so the sidecar goes last).
- Changing the env var requires a server restart — acceptable for a local-run tool.

### Orphan file sweep

If a render crashes between moving pdf/png and writing the sidecar, orphan files accumulate. `storage.sweep_orphans(audience_id)` scans an audience directory, removes `.pdf` / `.png` pairs that have no matching `.json` sidecar. It runs:
1. Once on server startup, for every known `audience_id`.
2. Opportunistically at the start of each `record_version()` call for the target audience (cheap — `os.listdir` on a small directory).

### Download filename

`FileResponse(archive_path)` defaults to the archive filename (`20260421T041200Z.pdf`) which is analyst-hostile. Endpoints that serve PDFs set `Content-Disposition: attachment; filename={audience}_{version_ts_human}.pdf` explicitly, where `version_ts_human` is the ISO 8601 date part + HHMM, e.g.:
- `ciso_2026-04-21_0412.pdf`
- `rsm-med_2026-04-18_1403.pdf`

`Preview` does not set `attachment`; the browser renders inline. `Download` does.

### URL `?version=` format

Always the compact form (`20260421T041200Z`) — matches filenames, no URL encoding needed. The server's `version_ts` helper converts to/from ISO 8601 at the API boundary; sidecars and API response bodies keep ISO 8601 for human readability.

### Future migration to SQLite (design note)

When query needs grow (e.g., cross-audience filtering, analytics queries), the filesystem archive migrates cleanly:
1. Keep the same `output/deliverables/archive/` file layout.
2. Swap `storage.py` internals to hit `data/briefs.db` instead of `os.listdir` + sidecar reads.
3. Write a one-time migrator that walks the archive and inserts a row per sidecar.
4. Callers (`server.py` routes, tests) don't change — the interface is the same.

The sidecar JSON schema is deliberately identical to the future SQL schema fields — no remapping at migration time.

## Pipeline run ID plumbing

Stale detection needs every version to know which pipeline run produced its input data. Two pieces:

### Data loaders return run IDs

The brief data loaders are extended to return `(data, pipeline_run_id)` instead of just `data`:

```python
def load_ciso_data(month: str) -> tuple[CisoBrief, str | None]: ...
def load_board_data(quarter: str) -> tuple[BoardBrief, str | None]: ...
def load_rsm_data(region: str, week_of: str | None = None, narrate: bool = False) -> tuple[RsmBrief, str | None]: ...
```

`pipeline_run_id` is `None` when the loader is reading a mock fixture or there's no live pipeline run backing the data (preserves current mock-mode behaviour).

Sources for the run id:
- **CISO, Board** → `output/pipeline/last_run_log.json` top-level `run_id` field (global pipeline run).
- **RSM** → per-region state. Each regional pipeline writes a `run_id` into its regional artifacts (e.g., `output/regional/{region}/meta.json` — create if not already present). Reading the regional run id is a `region_run_id(region)` helper.

### `tools/briefs/pipeline_state.py` (new, small)

Centralises pipeline-run-id resolution so loaders and the `/meta` endpoints agree on the source of truth:

```python
def global_run_id() -> str | None: ...
def region_run_id(region: str) -> str | None: ...
def current_run_id(audience_id: str) -> str | None:
    if audience_id.startswith("rsm-"):
        return region_run_id(audience_id.removeprefix("rsm-"))
    return global_run_id()
```

### Stale computation

`/meta` endpoints call `current_run_id(audience_id)` and compare against the version's stored `pipeline_run_id`:
- Both non-null + unequal → stale.
- Either null → not stale (manual render, or no current run recorded).
- Equal → not stale.

### Mock-mode behaviour

Running CLI with `--mock` produces versions with `pipeline_run_id = null`. These never go stale — consistent with their nature (fixtures, not live pipeline output).

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
- `tools/briefs/storage.py` — filesystem-backed archive with the interface described in "Storage & archive." No DB, no new dependencies. Future SQLite migration swaps the internals without changing callers.
- `tools/briefs/pipeline_state.py` — `global_run_id()`, `region_run_id(region)`, `current_run_id(audience_id)`. Sole source of truth for "what pipeline run is current for this audience."

### Modified in `tools/briefs/data/{ciso,board,rsm}.py`
- Return signature changes to `(data, pipeline_run_id)`. `pipeline_run_id` read via `pipeline_state.global_run_id()` (CISO/Board) or `pipeline_state.region_run_id(region)` (RSM); null in mock mode or when no run is recorded.
- All call sites (build_pdf CLI, FastAPI endpoints, tests that call loaders directly) updated to accept the new tuple. Existing `tests/briefs/` cases touching loaders get the minimum destructuring change.

### Modified in `tools/briefs/renderer.py`
- `render_pdf(...)` extended to accept a `thumbnail_path` argument and produce the cover-page PNG alongside the PDF in the same Playwright session.
- Paths are caller-provided (typically a tmp dir). `storage.record_version()` is responsible for moving both files into the archive layout atomically.

### Modified in regional pipeline
- Each regional pipeline run must write `run_id` into `output/regional/{region}/meta.json` (create the file if absent). The run id can reuse whatever the global pipeline already generates (ISO timestamp or ULID). One-line change in the regional runner.

### Modified in `tools/build_pdf.py` (CLI)
Current behaviour: writes to `--out` path, no archive. Updated behaviour:
- Default (no `--out`): render → `storage.record_version()` → file lands in archive, nothing more.
- With `--out PATH` (ad-hoc dev): render to the given path, **also** call `storage.record_version()` so the archive stays authoritative. The `--out` copy is a convenience; the archive always reflects the render.
- New `--no-archive` flag (escape hatch): render to `--out` only, skip the archive. Useful for one-off test renders that shouldn't pollute history.
- `--mock` and `--narrate` flags continue to work; both produce regular archive entries (mock versions have `pipeline_run_id=null`).

### Explicitly out of scope
- PPTX board endpoint / backend (legacy, not exposed in UI).
- CISO DOCX endpoint (stays reachable via "Other formats ▾" on the CISO card).
- History tab (`#tab-history`) merge — separate concern.
- Pipeline agents and brief templates — v1.0, don't touch. (The brief data loaders are touched, but narrowly: the return signature gains a `pipeline_run_id` alongside the existing data model.)
- Non-Chromium browsers.

## Testing

### New storage tests (`tests/briefs/test_storage.py`)
1. `record_version()` moves PDF + PNG into archive, writes sidecar, `get_latest()` returns the new version.
2. Sidecar-last ordering: if sidecar write fails, PDF/PNG are removed — no partial version lingers in listings.
3. `list_versions()` returns newest-first, skips directories where the sidecar is missing (partial writes ignored).
4. `get_specific(audience_id, version_ts)` returns the right record; missing → None.
5. `prune()` with `BRIEFS_RETENTION=3` and 5 versions → keeps newest 3, deletes 2 each of pdf/png/json from disk.
6. `prune()` with `BRIEFS_RETENTION=0` → no-op, everything retained.
7. Timestamp format helper converts `YYYYMMDDTHHMMSSZ` ↔ `YYYY-MM-DDTHH:MM:SSZ` round-trip.
8. `sweep_orphans()` deletes pdf/png pairs without sidecars; preserves all complete versions; runs cleanly on an empty directory.
9. `pipeline_run_id=null` produces a `VersionRecord` where `stale` computes to false regardless of current pipeline state.

### New pipeline-state tests (`tests/briefs/test_pipeline_state.py`)
1. `global_run_id()` returns the `run_id` field from `output/pipeline/last_run_log.json`; returns `None` when the file is missing.
2. `region_run_id('med')` returns the `run_id` from `output/regional/med/meta.json`; returns `None` when the file is missing.
3. `current_run_id('ciso')` / `current_run_id('board')` delegates to `global_run_id()`.
4. `current_run_id('rsm-med')` delegates to `region_run_id('med')`.
5. Unknown audience id → raises a `ValueError` (prevents silent misuse).

### Loader return-signature tests (update existing `tests/briefs/test_loaders.py`)
- `load_ciso_data(...)` returns `(CisoBrief, str | None)`; `pipeline_run_id` matches the global state when live; `None` in mock mode.
- Same for `load_board_data`, `load_rsm_data`.
- Existing assertions about the brief models continue to pass (destructure the tuple before asserting).

### New server tests (`tests/briefs/test_api.py`)
1. `GET /api/briefs/` returns all 7 audiences with `latest_meta` and `versions` list; empty archive → `latest_meta=null`, `versions=[]`, still 200.
2. `GET /api/briefs/ciso/pdf?version=<ts>` serves the right file; no `?version` → Latest; unknown version → 404.
3. `GET /api/briefs/ciso/pdf?version=<ts>` response has `Content-Disposition: attachment; filename=ciso_YYYY-MM-DD_HHMM.pdf`.
4. `GET /api/briefs/ciso/thumbnail?version=<ts>` serves PNG bytes.
5. `POST /api/briefs/ciso/regenerate` — mocks Playwright render, verifies new version appears in `list_versions()`, prior version still resolves by `?version=`.
6. `POST /api/briefs/rsm-med/regenerate` with `{narrate: true}` — new sidecar has `narrated: true`; narrate flag reaches `load_rsm_data` (mock Anthropic).
7. Stale flag: after a regenerate then a new pipeline run id advance, Latest has `stale=true`; regenerating again clears it. Prior versions always `stale=false`. Versions with `pipeline_run_id=null` always `stale=false`.
8. Error paths — unknown audience → 404; pipeline data missing for CISO → 4xx with descriptive body.

### Client testing — manual only
No automated client tests in this redesign. The app has no existing JS test harness; standing up Playwright for this alone is out of scope. Client correctness is verified via the manual acceptance checklist below. If/when Playwright is added to the project (flagged as upcoming for Risk Register UI), the scenarios below become the test suite.

### Manual acceptance checklist
- Reports tab mounts, 7 audience cards render with thumbnails + freshness.
- Preview button opens the correct PDF in a new browser tab (native viewer).
- Regenerate on CISO — thumbnail refreshes, VersionMenu grows by one.
- Narrate visible only on RSM cards; click triggers narrated regenerate (when Anthropic credits available).
- VersionMenu expand → select prior version → thumbnail swaps, Preview/Download repoint.
- Stale badge shows on Latest after pipeline run; regenerate clears it.
- Regenerate on an audience with no pipeline data shows the error strip.
- With `BRIEFS_RETENTION=5`, a 6th regenerate on the same audience prunes the oldest.

### Not tested in this redesign
- PDF content (covered by `tests/briefs/`, 63 tests, unchanged).
- Deleted in-browser render paths (no code to test).

## Migration notes

1. The old Board subviews (Global, Regional Exec) disappear. If a separate regional-exec brief is needed later, it gets its own backend generator and its own entry in `/api/briefs/`.
2. The CSS deletions are aggressive but safe — every class removed is verified unused outside the deleted JS functions.
3. `output/deliverables/archive/` is a new directory. Verify `output/` is gitignored (it should be — confirm during implementation).
4. The client-side `AUDIENCE_REGISTRY` stays as a fallback/schema definition, but its `renderer`/`generate`/`subviews`/`sales` fields go.
5. Existing `output/deliverables/{board,ciso,rsm}_mock_test.pdf` files are NOT automatically moved into the archive. They stay where they are (used by the current ad-hoc dev loop). The archive starts empty; the first regenerate per audience populates it. No backfill script needed — by design.
6. **Retention is a config knob, not a bake-in.** Default is 5 via `BRIEFS_RETENTION=5` env var. Setting `BRIEFS_RETENTION=0` switches to eternal retention with no code change.
7. **History tab naming:** the existing `#tab-history` shows regional risk heatmaps over time — unrelated to the new brief archive. Consider renaming it to `Trends` (or similar) in a follow-up so "History" doesn't become overloaded once users start asking for a dedicated archive browser.

## Success criteria

1. Reports tab loads a card grid with 7 cards (CISO, Board, 5 RSM regions), each showing a thumbnail, a relative freshness label (which is also the VersionMenu trigger), and action buttons.
2. Preview button opens the selected version's PDF in a new browser tab; native PDF viewer loads with full controls.
3. Download delivers the PDF with a human-readable filename (e.g., `ciso_2026-04-21_0412.pdf`), not the archive timestamp filename.
4. Regenerate writes PDF + thumbnail + sidecar JSON to the archive, prunes per retention, and the card refreshes without a full page reload.
5. Narrate is visible only on RSM cards, separate from Regenerate, produces a sidecar with `narrated: true`, and threads through to `load_rsm_data(..., narrate=True)`.
6. Per-audience stale detection: pipeline run ID advance on MED marks MED's Latest stale; others unaffected; prior versions never flagged stale; `pipeline_run_id=null` versions never stale.
7. Loaders return `(data, pipeline_run_id)`; run id is read from `last_run_log.json` (global) or `output/regional/{region}/meta.json` (RSM).
8. Relative date labels read as "Today / Yesterday / Mon DD" with UTC time.
9. VersionMenu lists prior versions newest-first; selecting a prior version swaps thumbnail + repoints Preview/Download.
10. With `BRIEFS_RETENTION=5` (default), a sixth regenerate prunes the oldest version (pdf + png + json). With `BRIEFS_RETENTION=0`, no pruning occurs.
11. Orphan files (pdf/png with no sidecar) are cleaned up on server startup and opportunistically on `record_version()`.
12. `tools/briefs/storage.py` + `pipeline_state.py` expose the documented interfaces; the CLI (`build_pdf.py`) calls through storage by default, with `--no-archive` as the opt-out.
13. All deleted functions (`renderCisoView`, etc.) are fully removed from `static/app.js`; no dead CSS rules remain.
14. All new tests pass (storage, pipeline-state, loaders, API). All existing `tests/briefs/` (63) still pass. Manual acceptance checklist passes.
