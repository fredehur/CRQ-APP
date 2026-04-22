# Reports V2 ledger — design spec

**Date:** 2026-04-22
**Status:** Draft — pending user review, then writing-plans
**Scope:** Reports tab only. No other tab is touched by this work.

## 1. Goal

Replace the v1 Reports card grid with a dense ledger table. Keep the trimmed V2 scope from the brainstorm: status taxonomy, per-row actions, version menu, thumbnail on hover. Defer severity/sources/pages/cadence/running/generate-all.

## 2. What the analyst experiences after this ships

Analyst opens `/#reports`. A single dense table: two sections — Leadership (CISO, Board), RSM — Regional (5 rows). Each row shows audience name, a status pill (`Ready` / `Stale` / `Empty`), freshness, and a compact action strip. Hovering an audience reveals the cover-page thumbnail in a popover. Regenerate is one click per row; Preview opens the latest PDF in a new tab; the version menu rolls back to a prior render. No card grid, no whitespace, no 240×320 dead boxes.

## 3. Scope

In scope:
- New ledger UI replacing `renderReports` in `static/app.js`.
- `app.css` additions for status pills, ledger table, popover, toast.
- Deletion of v1 `.rpt-*` inline CSS in `static/index.html` and the v1 DOM builders.

Out of scope:
- Every other tab's CSS (covered by the separate migration sweep spec).
- Brief PDF templates.
- `tokens.css` changes (print-locked).
- Severity column, sources count, pages count, cadence column, running state, "Generate all" button, grid view toggle, accessibility pass.

## 4. Targeted audit (Reports-V2-only)

Deliverable: a short section at the top of `docs/design/handoff/app-css-audit.md`, limited to Reports V2 needs.

- Which existing `app.css` primitives the ledger consumes unchanged (`.btn`, `.btn--ghost`, `.table`, `.pill`).
- Which primitives need new variants added: status-pill variants, dense `.table--ledger` variant.
- Whether `app.css` has a popover/tooltip primitive; if not, add one.
- Whether `app.css` has a toast primitive; if not, add one.

Sizing: ~1 hour.

## 5. `app.css` additions

All additions live in `static/design/styles/app.css`. No changes to `tokens.css`.

New status tokens in the dark-surface block:
- `--status-ready`, `--status-stale`, `--status-error` — specific values chosen during implementation against the existing dark-surface palette. `empty` reuses `--text-tertiary`, no new token.

New primitives:
- `.pill--status-ready`, `.pill--status-stale`, `.pill--status-empty`, `.pill--status-error` — leading dot + text label, neutral fill, dot color from the corresponding status token.
- `.table--ledger` — modifier on `.table` tightening row padding to `--s-3` (6px vertical), sticky `<thead>`, grouped `<tbody>` with subhead rows using `--text-tertiary`.
- `.popover` — absolutely positioned floating card anchored to a trigger element, flip-to-side when near viewport edge.
- `.toast` and `.toast-stack` — top-right stack of transient notifications, auto-dismiss default 6s, persistent close button, `--status-error` tinted for error variants.
- Row-actions cluster (`.row-actions`) — right-aligned action strip, uses existing `.btn--ghost` variants.

Rules from `app.css` header comment apply: no hex, tokens only, severity scale untouched, cyan = cyber + focus only.

## 6. JS refactor

`static/app.js` — replace the v1 `renderReports*` family (`renderReports`, the per-audience card builders, the thumbnail loader, the version-menu builder) with a new ledger renderer:

- `renderReportsLedger(container, briefsState)` — builds the single table from an in-memory state object. Safe-DOM only (no `innerHTML`, per v1 policy).
- `buildLedgerRow(audience)` — builds one `<tr>` with the 4 columns.
- `computeRowStatus(audience)` — pure function: takes `audience.latest_meta` + `audience.current_run_id`, returns `"ready" | "stale" | "empty"`.
- `renderVersionMenu(audience)` — dropdown anchored to row, flips up when near viewport bottom, closes on outside click / Escape / scroll.
- `renderThumbnailPopover(audience)` — anchored to audience cell, flips side on viewport edge.
- `showErrorToast(message)` — pushes onto `.toast-stack`, auto-dismisses.

All legacy v1 rendering code deleted.

## 7. Data contract

Input: existing `/api/briefs/` response.

Per-audience shape the front-end reads:
- `id` → audience_id (used for action URLs).
- `title` → display label ("CISO", "RSM · APAC", etc.).
- `canNarrate` → gates the Narrate button.
- `latest_meta` → presence controls the `empty` vs `ready/stale` branch; `latest_meta.pipeline_run_id` compares against `current_run_id`.
- `current_run_id` → reference for stale computation.
- `latest_meta.created_at` → freshness display.
- `latest_meta.narrator_flag` → shown in version menu per-version row.
- `versions[]` → version menu contents.

No backend change. No new fields. If audit finds the mapping ambiguous, that gets resolved in the audit artifact before any code moves.

## 8. UI spec

### Row layout (text diagram)

```
┌───────────────────┬───────────┬──────────────────┬──────────────────────────────────┐
│ CISO              │ ● Ready   │ Today 17:15      │ [Preview] [Regen] [Download] ▾   │
│                   │           │ Apr 22 17:15 UTC │                                  │
├───────────────────┼───────────┼──────────────────┼──────────────────────────────────┤
│ RSM · APAC        │           │ —                │ [Regenerate] [Narrate]           │
│                   │  Empty    │                  │                                  │
└───────────────────┴───────────┴──────────────────┴──────────────────────────────────┘
  (hover = popover)   (status)    (freshness)        (actions, right-aligned)
```

Column widths: `minmax(220px, 1.6fr) 120px 180px auto`.

### Row states

- **Ready** — `● Ready` pill (status-ready dot). All 4 actions + version menu. Hover audience = thumbnail popover.
- **Stale** — `● Stale` pill (status-stale dot). All 4 actions + version menu. Hover audience = thumbnail popover.
- **Empty** — `Empty` pill (no dot, text-tertiary). Regenerate + Narrate (RSM only). No popover on hover.

### Thumbnail popover

Anchors to the right side of the audience cell, 240×320, 8px gap from cell edge. Flips to the left side if within 280px of viewport right edge. Dismisses on mouse-leave with 150ms grace. Loads `/api/briefs/{id}/thumbnail` lazily (on first hover).

### Version menu

Dropdown anchored below the `▾` trigger. Flips above the trigger when the row is within the bottom 40% of the viewport. Closes on outside click, Escape, or scroll of the ledger's scroll container. Each version row: timestamp, narrator flag if present, `Use this` action that sets the row's active version (affects the Preview / Download URLs).

### Regenerate behavior

Synchronous, same as v1. Button label flips to `Regenerating…` and is disabled during the POST. On success, the row re-renders (status recomputes, freshness updates, version menu gains an entry). On failure, `showErrorToast` pushes a message to the stack and the row's status pill flashes `error` for 3s before returning to its prior state.

### Error toast

Top-right of the tab, stack of up to 3 visible. Auto-dismiss after 6s unless the user hovers (pauses the timer) or clicks close. Tinted with `--status-error` for error variants.

## 9. Testing

- **Playwright smoke test** — open `/#reports`, assert row count = 7, assert at least one row has status pill class `.pill--status-empty`, click Regenerate on an empty row, assert the POST is sent, assert the button label flips to `Regenerating…`.
- **Playwright interaction test** — open version menu, confirm flip-up behavior near viewport bottom, close on outside click.
- **Manual smoke** — walk the ledger in the browser: all 7 rows render, hover popover works on ready rows, Regenerate end-to-end, Preview opens new tab, Narrate only on RSM rows.
- **No backend tests added** — no backend change.

## 10. Rollback

Single revertable PR. No server state changes, no API changes. `git revert <sha>`, redeploy.

## 11. Definition of done

- [ ] `docs/design/handoff/app-css-audit.md` has a Reports-V2 section covering primitive inventory + additions.
- [ ] New primitives added to `app.css`, parses without error, loads in browser.
- [ ] New status tokens added to `app.css` dark-surface block.
- [ ] `renderReportsLedger` implemented in `static/app.js`. Legacy `renderReports*` family deleted.
- [ ] v1 `.rpt-*` CSS removed from `static/index.html` `<style>` block.
- [ ] Playwright smoke + interaction tests pass.
- [ ] Manual browser walk: all 4 row states render, all 5 actions work, popover + version menu + toast all behave per spec.
- [ ] No console errors, no 404s.

## 12. Sizing

- Audit: ~1 hour
- `app.css` additions: ~half day
- JS refactor + UI implementation: ~2 Builder/Validator sessions
- Testing + QA: ~half day

Total: ~3 focused sessions.

## 13. Success criteria

No instrumentation. Success is verbal feedback from the one analyst using this tool: the ledger is faster to scan than the card grid, and no v1 workflow regressed.

## 14. Risks

- Status token color choices may need a visual iteration to feel right against the existing palette. Cheap to fix.
- Thumbnail popover may feel fiddly in practice; fallback is to drop the popover entirely and keep the thumbnail only in the version menu. Decision can be made in QA.
- Synchronous regenerate gives minimal visual feedback for long renders. Acceptable per trim decision; if analyst complains, upgrade to async in a follow-up.
