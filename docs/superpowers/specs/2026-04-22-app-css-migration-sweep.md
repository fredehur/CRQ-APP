# App CSS migration sweep — design spec

**Date:** 2026-04-22
**Status:** Draft — pending user review, then writing-plans
**Scope:** The 8 app tabs other than Reports (Overview, Trends, History, Risk Register, Source Library, Context, Pipeline, Run Log). Reports V2 handles its own inline CSS in its own spec.

## 1. Goal

Promote tab-specific CSS currently embedded in the `<style>` block of `static/index.html` into `static/design/styles/app.css`. Normalize hex values, spacing, typography, and borders onto the existing `tokens.css` variables. Leave all behavior and visual output unchanged.

## 2. What the analyst experiences after this ships

Nothing visibly different. The app looks the same. Under the hood, every tab's styling flows through `app.css` and `tokens.css`. Changing a color or spacing value in one place updates all tabs, and future design iterations don't have to hunt through inline rules.

## 3. Scope

In scope:
- Every tab except Reports: Overview, Trends, History, Risk Register, Source Library, Context, Pipeline, Run Log.
- The inline `<style>` block in `static/index.html`.

Out of scope:
- Reports tab (handled by Reports V2 ledger spec).
- Brief PDF CSS (`board.css`, `ciso.css`, `rsm.css`).
- `tokens.css` (print-locked).
- Any feature work, layout change, or visual redesign on any tab.
- Tabs whose inline CSS resists clean migration — these go into a follow-ups doc for a later dedicated effort.

## 4. Audit

Deliverable: `docs/design/handoff/app-css-audit.md` with two tables.

**Table A — Inline CSS inventory.** Every rule in the inline `<style>` block, grouped by tab. Each rule tagged:
- `promote` — move to `app.css`, normalize values to tokens, no other change
- `tab-specific` — stays inline, genuinely scoped to that one tab's feature, doesn't warrant a primitive
- `legacy` — dead code, delete during sweep

**Table B — Per-tab migration ranking.** Tabs ordered by expected size of inline CSS (largest first), so the sweep front-loads the heavier tabs when reviewer attention is freshest.

Audit is a living doc. It gets updated as the sweep finds misclassified rules or dead code the first pass missed.

Sizing: ~half day.

## 5. Per-tab migration ranking (expected — confirm during audit)

Ranked rough-first by likely inline-CSS volume:

1. **Risk Register** — discovery-first redesign 2026-04-20 likely added significant inline CSS.
2. **Overview** — the analyst workspace, largest surface area.
3. **Source Library** — recent source-box redesign.
4. **Context** — newer tab with editor UI coming.
5. **Pipeline** — modest, mostly table/log styles.
6. **Trends** — small, mostly chart chrome.
7. **Run Log** — mostly trace viewer, may resist migration.
8. **History** — small.

Each becomes a separate commit in the sweep PR.

## 6. Migration rules

1. **One PR.** Title: `refactor(styles): promote inline tab CSS to app.css`. No feature work.
2. **Per-tab commits.** `refactor(styles): promote Risk Register chrome to app.css`, etc. Per-tab revertability.
3. **Strict scope per tab:**
   - Move rules from `index.html` `<style>` to `app.css`.
   - Normalize hex → tokens, space → `--s-*`, type → `--fs-*` / `--font-sans`, borders → `--border-*`, radius → `--r-*`.
   - Delete rules made redundant by the promotion.
4. **Resistant tabs are skipped.** If a tab's patterns don't map cleanly onto existing primitives, leave its inline CSS and log it in `docs/design/handoff/migration-followups.md`.
5. **Scope-creep clause.** Design opportunities noticed during migration go into `migration-followups.md`. They do not land in the sweep PR.
6. **Partial sweep is OK.** Shipping 5 of 8 tabs migrated with 3 deferred to the follow-ups doc is acceptable. Threshold: at least 4 tabs should migrate in the sweep for it to have been worth the PR overhead; below that, wait and batch with a later attempt.

## 7. Per-tab QA checklist (template, applied to each tab)

Example — **Overview tab:**

- [ ] Open `/#overview` — page renders without console errors, no 404s on CSS assets.
- [ ] The regional selector row matches pre-migration visuals (dots, spacing, active state).
- [ ] Escalated / Monitor badges render the same (color, sizing, corner radius).
- [ ] Posture paragraph typography unchanged (weight, line-height, color).
- [ ] Signal cluster boxes (source metadata + claims) render at same size, same borders.
- [ ] Scenario detail panel: same layout, same typography, same spacing between subsections.
- [ ] Hover states on interactive elements unchanged.
- [ ] Expand / collapse animations on clusters behave the same.
- [ ] Feedback buttons (Accurate / Incomplete / Off-target) render same.

Each tab's checklist is included in the sweep PR description. Reviewer walks all of them before merge.

## 8. Testing strategy

- **Manual QA per tab** — primary regression catch. Checklists in PR description.
- **Playwright screenshot diff** — optional, non-blocking. Capture before/after of each tab's landing view. Diff reviewer-readable, not pixel-exact.
- **No unit/integration tests added** — CSS migration doesn't change behavior.
- **Before-PR sanity check** — load each tab once before merging per-tab commits to catch egregious regressions early in the sweep.

## 9. Rollback

- Per-tab commits give per-tab revertability. `git revert <tab-sha>` if tab N regresses post-merge; other migrated tabs stay migrated.
- No server state changes. Rollback is "revert, redeploy."
- No feature flag needed.

## 10. Definition of done

- [ ] `docs/design/handoff/app-css-audit.md` exists with Table A (inline inventory) and Table B (ranking) filled.
- [ ] At least 4 tabs promoted into `app.css` via per-tab commits.
- [ ] Any deferred tabs logged in `docs/design/handoff/migration-followups.md` with reason.
- [ ] `static/index.html` `<style>` block is either fully migrated or only contains tab-specific rules flagged during audit.
- [ ] Each migrated tab's QA checklist passes (reviewer signs off).
- [ ] No new 404s, console errors, or visual regressions observed.
- [ ] PR description enumerates per-tab outcome: migrated / deferred / skipped, with a one-line reason per deferred tab.

## 11. Sizing

- Audit: ~half day
- Per-tab migration: ~1–2 hours per tab on average (varies with volume)
- QA + PR review: ~half day

Total: ~1–2 days focused work. Upper bound if the audit surfaces more dead code to clean than expected.

## 12. Success criteria

- Inline `<style>` block in `index.html` is substantially smaller (measurable line count reduction is the easy proxy).
- No analyst-visible change to any tab.
- Any future color or spacing change can be made in one place (`tokens.css` or `app.css`) and take effect across all migrated tabs.

## 13. Risks

- **Audit misses rules.** Living-doc treatment of the audit is the mitigation — when the sweep finds a missed rule, it gets added and migrated.
- **A tab resists more than expected.** Defer it, log in follow-ups, move on. Don't stall the sweep on a single stubborn tab.
- **Normalization changes render behavior subtly.** Hex→token swaps can surface if the old hex didn't exactly match the token value. Manual QA catches these; if a mismatch is intentional (tab needed that specific color), the rule gets flagged `tab-specific` and stays inline.
- **Scope-creep during review.** The reviewer is the last line of defense. Any commit in the sweep PR that isn't strictly promotion/normalization must be pulled into a separate PR.
