# Reports Tab Redesign — Design Spec

**Date:** 2026-04-21
**Status:** Approved, ready for implementation plan
**Context:** Brief PDF pipeline shipped v1.0 (Board, CISO, RSM) on 2026-04-21. The Reports tab is now misaligned with the deliverable — it renders its own in-browser versions of each brief in parallel with the PDFs, creating drift and ~800 lines of maintenance surface that will rot.

## Goal

Rebuild the Reports tab as a **PDF-first preview-and-download surface** aligned with the v1.0 deliverable: the PDF is the brief, so the preview shows the PDF and the action is downloading it.

## User & job-to-be-done

**Primary user:** the analyst (internal) QA'ing briefs before they go to stakeholders.

**Job-to-be-done:** skim-level QA — open each audience's brief, eyeball it ("looks right, numbers feel sane"), download the PDF, send it by external means (email, Slack, etc.).

**Not solving:**
- Deep claim-level QA with inline source traceability (user QAs at skim depth).
- In-browser distribution (send happens outside the tool).
- Diff-against-prior-cycle views (not part of the skim workflow).
- Exec-consumes-briefs-in-browser (the earlier in-browser renders were a wrong bet).

## Architecture

Three-zone layout in the existing `rpt-shell` grid (200px rail + flex content):

```
┌─────────────┬──────────────────────────────────────────┐
│ RAIL        │ HEADER BAR                               │
│             │  Title · run meta · [stale?]             │
│ CISO  [●]   │                 [Regenerate][Download][▾]│
│ Board       ├──────────────────────────────────────────┤
│ RSM         │                                          │
│  APAC  [●]  │                                          │
│  AME        │         <iframe> PDF preview             │
│  LATAM      │                                          │
│  MED        │                                          │
│  NCE        │                                          │
└─────────────┴──────────────────────────────────────────┘
```

**Rail** — grouped list with expand-on-active. Three top-level audiences: CISO (no subviews), Board (no subviews — single PDF), RSM (subviews: APAC, AME, LATAM, MED, NCE — one PDF per region). One audience active at a time; sub-items show inline only when parent is active.

**Note on Board subviews:** the previous UI split Board into "Global" and "Regional Exec" as two in-browser render variants, but the backend produces a single board PDF. In a PDF-first world there's nothing to split. If a separate regional-exec brief is needed later, it gets its own backend generator and its own registry entry.

**Header bar** — audience title, run meta (`Last generated HH:MM UTC`, with optional `⚠ Stale` badge if the pipeline has run since the PDF was rendered), and the action cluster on the right.

**Body** — single `<iframe>` filling the remaining space. Native browser PDF rendering. No cards, no custom HTML render, no tabs.

## Components

### 1. `ReportRail`
Audience navigation. Driven by `AUDIENCE_REGISTRY`. On click fires `selectAudience(id)`. Expands sub-items inline when the parent is active.

### 2. `ReportHeader`
Title + run meta + action buttons. Fetches meta on audience change. No PUSH/HOLD buttons (deleted — they were cosmetic).

### 3. `RegenerateControl`
Button that POSTs to the regenerate endpoint. For RSM, shows a "Use AI narration" checkbox inline (narration costs Anthropic credits — must be an explicit opt-in, not a default). Disables and shows a spinner in-flight. On success reloads the iframe and refreshes meta; on failure shows an inline error strip above the iframe, iframe keeps prior render.

### 4. `PdfPreview`
`<iframe src="/api/briefs/{audience}/pdf?v={mtime}">`. Cache-busting token changes on regenerate so the browser reloads. No PDF.js — native Chromium rendering.

### 5. `OtherFormatsMenu`
A `▾` icon-button at the end of the action row. On click shows a small menu with secondary format downloads for the current audience (currently: CISO DOCX). If an audience has no secondary formats, the button isn't rendered. Board PPTX is intentionally hidden (legacy pre-v1.0 export; backend endpoint preserved but not exposed from this tab).

## Data flow

Three paths, all through existing or thin-new endpoints.

### Open an audience
1. User clicks rail row → `selectAudience(id)` sets `state.selectedAudienceId`.
2. Client GETs `/api/briefs/{audience}/meta`, renders header with `generated_at` + pipeline run ID.
3. Client sets iframe `src` to `/api/briefs/{audience}/pdf?v={mtime}`.

### Regenerate
1. User clicks Regenerate. For RSM, the "Use AI narration" checkbox state is captured.
2. Button disables, spinner shows. Client POSTs to `/api/briefs/{audience}/regenerate` with `{narrate?: bool}` body.
3. Server runs the same code path `build_pdf.py` CLI uses (via a shared internal function, not a shell-out).
4. On 200: response includes new meta. Client updates iframe src with new cache-buster, clears any stale badge, updates "last generated" timestamp.
5. On non-2xx: inline error strip above iframe shows the response body ("Anthropic API: credit balance too low", "template render error: …"). Iframe stays on the prior render. Strip is dismissible.

### Download
Plain `<a href="/api/briefs/{audience}/pdf" download>` — no JS needed.

### Stale detection
`state.lastPipelineRun` (already tracked in the app) is compared to `meta.generated_at`. If pipeline ran after PDF was rendered, `⚠ Stale` badge appears in the header meta. Regenerate clears it.

## States

Four states the UI must handle.

### 1. No brief PDF yet
Centred block in body: *"No brief generated yet."* + single Regenerate button. No 404 noise, no broken iframe.

### 2. Pipeline data is missing (nothing to regenerate from)
Centred block: *"Pipeline hasn't run for this region/period. Run `/run-crq` or `/crq-region` first."* Regenerate button is disabled. Run-meta strip shows no timestamp.

### 3. Regenerate fails mid-flight
Inline error strip above iframe (red-left border, matches existing `.rpt-section` style). Body = server response message. Iframe keeps prior render. Strip has a `×` dismiss button.

### 4. Iframe fails to render
After 3s iframe `load` timeout: fallback link "Preview failed to load. [Download PDF directly]". Defensive against Electron PDF-plugin edge cases.

## Scope of change

### Deleted from `static/app.js`
- `renderCisoView` (~50 lines)
- `renderBoardGlobalView` (~50 lines)
- `renderBoardRegionalView` (~80 lines)
- `renderRsmInReports` (~600 lines)
- `_hubGenerate` (tied to deleted PUSH button)
- Any private helpers of the above that become dead code

### Deleted from `static/index.html` CSS
- `.rpt-section*`, `.rpt-cards`, `.rpt-card*`, `.rpt-decision*`, `.rpt-tp*`, `.rpt-watch*`, `.rpt-region-selector`, `.rpt-region-btn*`

### Kept in `static/index.html` CSS
- `.rpt-shell`, `.rpt-rail*`, `.rpt-content`, `.rpt-action-bar*`, `.rpt-btn*`, `.rpt-live-badge`, `.rpt-plan-badge`

### Changes to `AUDIENCE_REGISTRY`
- Drop `renderer` field (no dispatch to custom renderers).
- Drop `sales` (future) entry entirely (YAGNI — bring back when there's content).
- Drop the `generate` field (replaced by standardized regenerate endpoint).
- `downloads` array becomes the source list for the "Other formats ▾" menu — the primary PDF is a dedicated button, not an entry in this list.
- Board `subviews` removed — single PDF, no split.
- RSM gains `subviews` for the 5 regions (APAC, AME, LATAM, MED, NCE).

### New in `server.py`
- `GET /api/briefs/{audience}/meta` → `{generated_at, pipeline_run_id}` (thin: reads PDF mtime + current pipeline state from `output/pipeline/last_run_log.json`).
  - For RSM: `GET /api/briefs/rsm/{region}/meta`.
- `POST /api/briefs/{audience}/regenerate` with body `{narrate?: bool}` → calls the same internal function that `build_pdf.py` CLI calls, returns updated meta. For RSM only, `narrate` threads through to `load_rsm_data(..., narrate=True)`.

### Explicitly out of scope
- PPTX board endpoint / backend — not touched, just hidden from the UI.
- CISO DOCX endpoint — not touched, stays reachable via "Other formats ▾".
- History tab (`#tab-history`) — not merged into Reports in this redesign.
- Pipeline agents, brief data loaders, templates, `renderer.py` — v1.0, don't touch.
- Cross-browser testing — target is Chromium/Electron.

## Testing

### New server tests (`tests/test_briefs_api.py` — create if absent, else append)
1. `GET /api/briefs/ciso/meta` returns `{generated_at, pipeline_run_id}` when PDF exists; returns 404 when not.
2. `GET /api/briefs/rsm/MED/meta` — same pattern, scoped by region.
3. `POST /api/briefs/ciso/regenerate` — invokes the shared render function (mock Playwright call); returns fresh meta; `generated_at` has advanced.
4. `POST /api/briefs/rsm/MED/regenerate` with `narrate=true` — verifies the flag reaches `load_rsm_data`. Mock Anthropic SDK.
5. Error surfaces — bad region, pipeline data missing → 4xx with JSON error body.

### Manual Playwright acceptance (one-off, not automated)
- Every rail item opens a PDF in iframe.
- Regenerate reloads iframe with fresh render.
- Forced error (stop pipeline, click Regenerate) shows error strip.
- Download button delivers the correct file with correct filename.

### Not tested in this redesign
- PDF content itself (covered by `tests/briefs/`, 63 tests, unchanged).
- Deleted in-browser render paths (no code to test).
- Non-Chromium browsers (not supported target).

## Migration note

The `AUDIENCE_REGISTRY` shape changes. Any code reading `renderer`, `generate`, or `sales` entries must be audited and updated. The only known consumer is the Reports tab itself (`renderAudienceContent` et al), which is being rewritten. If the audit finds other consumers, they get updated in the same PR.

## Success criteria

1. Clicking any rail item opens the corresponding PDF in the preview pane within 1s on cached content.
2. Clicking Regenerate on an audience with available pipeline data rebuilds the PDF and refreshes the preview without a full page reload.
3. The RSM narration checkbox is visible only for RSM audiences, unchecked by default, and threads through to the narration call.
4. All four UI states (no-brief / no-pipeline / regenerate-error / iframe-load-error) render cleanly.
5. `renderCisoView`, `renderBoardGlobalView`, `renderBoardRegionalView`, `renderRsmInReports`, and `_hubGenerate` are fully removed from `static/app.js`.
6. All 5 new server tests pass. All existing `tests/briefs/` (63) still pass.
7. The CSS block in `static/index.html` shrinks by the removed in-browser-render rules.
