# Reports Tab Redesign — Design Spec

**Date:** 2026-04-21 (v2 after self-critique)
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

**Each card** — cover-page thumbnail, audience name, freshness label (relative date + UTC time), optional stale/error badge, and three buttons: **Preview** (opens PDF in new tab), **Regenerate**, **Download**. RSM cards additionally show a **Narrate** button (separate from Regenerate, because narration is an expensive AI call that produces new content).

## Components

### 1. `AudienceCard`
Self-contained card for one audience (or one RSM region).

Input props:
- `id` — e.g. `ciso`, `board`, `rsm-med`
- `title` — display name
- `thumbnailUrl` — endpoint returning PNG of cover page
- `meta` — `{generated_at, pipeline_run_id, stale}` from `/meta` endpoint
- `canNarrate` — boolean, true only for RSM

Renders:
- Thumbnail image (lazy-loaded, falls back to a neutral placeholder when no PDF yet)
- Title + relative freshness label ("Today · 04:12 UTC" / "Yesterday · 04:12 UTC" / "Apr 18 · 04:12 UTC")
- Stale badge when `meta.stale === true`
- Buttons: Preview, Regenerate, Download, (Narrate if `canNarrate`)
- Inline error strip when regenerate/narrate fails

Local state per card: in-flight (disables buttons + shows spinner on that card), error (shows strip). Card state never leaks to other cards.

### 2. `ThumbnailGenerator` (server-side)
A small addition to the PDF render path: after Playwright creates the PDF, take a screenshot of page 1 of the same HTML and save to `output/deliverables/{audience}_thumbnail.png`. Size ≈ 480px wide. One PNG per brief. No separate render path, no caching layer — it's produced inline with the PDF.

### 3. `RelativeDate` helper
Pure function `formatRelative(iso_utc) → string`. Examples:
- Same UTC day as now → `"Today · HH:MM UTC"`
- Previous UTC day → `"Yesterday · HH:MM UTC"`
- Older → `"Mon DD · HH:MM UTC"`

### 4. `OtherFormatsMenu` (per card)
A `▾` icon-button rendered at the end of the action row when an audience has secondary formats. CISO has this (DOCX). Board and RSM currently don't.

## Data flow

Three paths.

### Render initial view
1. Reports tab mounts → GET `/api/briefs/` returns the full list of audiences the server knows about, each with `{id, title, canNarrate, meta}` where `meta` is the current `{generated_at, pipeline_run_id, stale}`.
2. Client renders one `AudienceCard` per entry.
3. Each card sets its thumbnail `<img src="/api/briefs/{id}/thumbnail?v={mtime}">`.

This replaces the hardcoded client-side `AUDIENCE_REGISTRY` for the Reports tab's internal use. (The registry stays as a thin client cache but is populated from the server response.)

### Preview
`<a href="/api/briefs/{id}/pdf" target="_blank" rel="noopener">Preview</a>` — opens in a new browser tab, full native PDF viewer. Zero client code beyond the anchor.

### Regenerate
1. Click → card's button disables, spinner shows.
2. `POST /api/briefs/{id}/regenerate` with empty body.
3. Server calls the same internal function `build_pdf.py` CLI uses; PDF and thumbnail are both regenerated.
4. On 200: response contains updated `meta`. Card refreshes thumbnail src with new cache-buster, refreshes freshness label, clears stale badge.
5. On non-2xx: inline error strip on that card with server's error body. Thumbnail stays on the prior image. Strip is dismissible; also auto-clears on next successful action.

### Narrate (RSM only)
Same as Regenerate but with `POST /api/briefs/rsm/{region}/regenerate` body `{narrate: true}`. Server threads `narrate=True` through to `load_rsm_data()`. Error handling identical.

### Download
`<a href="/api/briefs/{id}/pdf" download>Download</a>` — plain anchor with `download` attribute.

### Stale detection
- For CISO and Board, `pipeline_run_id` is the global pipeline run. `stale = current_global_run_id > rendered_run_id`.
- For RSM, `pipeline_run_id` is per-region. `GET /api/briefs/rsm/{region}/meta` returns the region-specific run; `stale = current_region_run_id > rendered_region_run_id`.
- The server computes `stale` and returns it as a bool in the meta object. The client just renders the badge, no logic.

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
- `GET /api/briefs/` — returns the full audience list with per-item meta.
- `GET /api/briefs/{id}/meta` — single audience meta (`{id}` encodes region for RSM: `rsm-med`, etc.).
- `GET /api/briefs/{id}/thumbnail` — PNG of cover page.
- `POST /api/briefs/{id}/regenerate` with optional `{narrate: bool}` body.

All endpoints read from / write to `output/deliverables/`.

### Modified in `tools/briefs/renderer.py`
- After the Playwright `page.pdf(...)` call, take an element screenshot of the first `.page` (the cover) and save as PNG: `await page.locator('section.page').first.screenshot(path=thumbnail_path)`. Resize to ~480px wide before writing (keeps file small, ~40–80 KB). Thumbnail lands alongside the PDF in `output/deliverables/`. Two files per render, one Playwright session.

### Explicitly out of scope
- PPTX board endpoint / backend (legacy, not exposed in UI).
- CISO DOCX endpoint (stays reachable via "Other formats ▾" on the CISO card).
- History tab (`#tab-history`) merge — separate concern.
- Pipeline agents, brief data loaders, templates — v1.0, don't touch.
- Non-Chromium browsers.

## Testing

### New server tests (`tests/test_briefs_api.py`)
1. `GET /api/briefs/` returns the full list with expected ids and per-item meta.
2. `GET /api/briefs/ciso/meta` returns meta when PDF exists; 404 when not.
3. `GET /api/briefs/rsm/med/meta` — per-region meta including per-region pipeline run id.
4. `GET /api/briefs/ciso/thumbnail` returns PNG bytes; 404 when no PDF has been rendered.
5. `POST /api/briefs/ciso/regenerate` — invokes the render function (mock Playwright); both PDF and thumbnail files appear (or have newer mtimes); response has updated meta.
6. `POST /api/briefs/rsm/med/regenerate` with `{narrate: true}` — threads narrate flag to `load_rsm_data` (mock Anthropic).
7. Stale computation — when pipeline run id advances after render, `meta.stale === true`.
8. Error paths — unknown region → 404; pipeline data missing for CISO → 4xx with descriptive body.

### New client tests (`tests/test_reports_tab.py` via Playwright automation)
1. Reports tab mounts, fetches `/api/briefs/`, renders one card per audience.
2. Preview button has `target="_blank"` and the correct href.
3. Regenerate button click triggers POST to the correct endpoint with empty body; card's thumbnail src updates on response.
4. Narrate button visible only on RSM cards; click triggers POST with `{narrate: true}`.
5. Stale badge renders when the server returns `stale: true`.
6. Error strip appears on regenerate failure and dismisses on `×`.

### Manual acceptance
- Eyeball the grid on a fresh pipeline run. Confirm thumbnails look right and freshness labels match. Click Preview on each card, confirm new-tab PDFs render.

### Not tested in this redesign
- PDF content (covered by `tests/briefs/`, 63 tests, unchanged).
- Deleted in-browser render paths (no code to test).

## Migration notes

1. The old Board subviews (Global, Regional Exec) disappear. If a separate regional-exec brief is needed later, it gets its own backend generator and its own entry in `/api/briefs/`.
2. The CSS deletions are aggressive but safe — every class removed is verified unused outside the deleted JS functions.
3. The thumbnail feature means each render writes an extra file; `output/deliverables/` should be excluded from git (likely already is — verify).
4. The client-side `AUDIENCE_REGISTRY` stays as a fallback/schema definition, but its `renderer`/`generate`/`subviews`/`sales` fields go.

## Success criteria

1. Reports tab loads a card grid with 7 cards (CISO, Board, 5 RSM regions), each showing a thumbnail and a relative freshness label.
2. Preview button opens the PDF in a new browser tab; the native PDF viewer loads with full controls (search, zoom, print).
3. Regenerate rebuilds both PDF and thumbnail; the card refreshes without a full page reload.
4. Narrate is visible only on RSM cards, separate from Regenerate, and threads through to `load_rsm_data(..., narrate=True)`.
5. Per-region stale detection works: running pipeline for MED marks only the MED card stale, not others.
6. Relative date labels read as "Today / Yesterday / Mon DD" with UTC time.
7. All deleted functions (`renderCisoView`, etc.) are fully removed from `static/app.js`; no dead CSS rules remain.
8. All new server tests pass. All existing `tests/briefs/` (63) still pass. Playwright client tests pass.
