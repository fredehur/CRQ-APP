# App CSS migration sweep — implementation plan

**Goal:** Move tab-specific CSS from the `<style>` block in `static/index.html` into `static/design/styles/app.css` for the 8 non-Reports tabs. Normalize all hex/space/type/border/radius values onto existing `tokens.css` variables. No behavior or visual-output change.

**Architecture:** Per-tab commits inside a single refactor PR. Each tab's migration is a mechanical move + normalization with a manual browser check. Resistant tabs are skipped and logged for later. No code runs the sweep — it's a deliberate per-tab operation by the engineer.

**Tech Stack:** Plain CSS · `tokens.css` custom properties (unchanged) · manual browser QA · optional Playwright screenshot diffs (non-blocking).

**Spec reference:** `docs/superpowers/specs/2026-04-22-app-css-migration-sweep.md`.

---

## File Structure

**Files modified:**

- `static/design/styles/app.css` — receives promoted tab CSS, grouped by tab in commented sections.
- `static/index.html` — inline `<style>` block shrinks as rules move out.

**Files created:**

- `docs/design/handoff/app-css-audit.md` — extended from Reports V2 plan with Table A (inline inventory) and Table B (per-tab ranking).
- `docs/design/handoff/migration-followups.md` — list of tabs/components that resisted clean migration, for a later dedicated effort.

**Files untouched:** `tokens.css`, brief PDF CSS, `static/app.js`, all Python, Reports tab (handled by Reports V2 plan).

**Normalization rules** (applied to every promoted rule):

- Hex values → replace with matching `--ink-*`, `--brand-*`, `--sev-*`, or `--status-*` tokens. If a hex has no token match, keep the hex but flag in the commit body (implementer decides if a new token is warranted — if so, punt to follow-ups).
- `px` sizing for space/gap/padding/margin → replace with `--s-*` tokens where values match.
- `font-family` literals → replace with `var(--font-sans)`.
- `font-size` literals → replace with `--fs-*` tokens where values match.
- `border-color` hex / rgba → replace with `--border-hairline`, `--border-subtle`, `--border-strong`.
- `border-radius` literals → replace with `--r-sm`, `--r-md`, `--r-lg`.
- Anything that doesn't have a clean token match stays with its literal value and gets a `// normalized: no token match` comment in app.css.

---

## Task 1: Build Table A — inline CSS inventory

**Files:**
- Modify: `docs/design/handoff/app-css-audit.md`

- [ ] **Step 1: Locate the inline `<style>` block in `static/index.html`**

Open `static/index.html`, find the `<style>` block. Note its start and end line numbers.

- [ ] **Step 2: Walk the `<style>` block rule-by-rule**

For each CSS rule in the block, identify which tab it belongs to by its selector. Common clues: class prefixes like `.overview-*`, `.trends-*`, `.risk-*`, `.src-*`, `.ctx-*`, `.pipe-*`, `.runlog-*`, `.hist-*`. Rules with generic selectors (`body`, `nav`, etc.) belong to "global chrome" and are not part of this sweep (they're already global).

- [ ] **Step 3: Populate Table A in the audit doc**

Append to `docs/design/handoff/app-css-audit.md` after the Reports V2 section:

```markdown
---

## App CSS migration sweep — Table A: Inline CSS inventory

**Source:** `static/index.html` `<style>` block, lines {START}-{END}.

| Rule (selector) | Line | Tab | Tag |
|---|---|---|---|
| .overview-rail | 412 | Overview | promote |
| .overview-badge | 418 | Overview | promote |
| ... | ... | ... | ... |
```

Fill every rule. Tags: `promote` | `tab-specific` | `legacy`.

Rule of thumb for tagging:
- `promote` — rule is mechanically movable; contains hex/px/font literals that will normalize.
- `tab-specific` — rule is genuinely unique to one tab's feature, not a reusable primitive. Example: a specific scatter-chart axis style. Stays inline but gets moved into `app.css` under a tab-labeled comment block; the "tab-specific" tag is about whether it warrants a primitive, not whether it moves.
- `legacy` — dead code. Confirm by grepping for the class name across the codebase (`grep -rn "classname" static/ tools/ tests/`). If zero matches outside the CSS rule itself, tag `legacy` and it will be deleted, not moved.

- [ ] **Step 4: Commit**

```bash
git add docs/design/handoff/app-css-audit.md
git commit -m "docs(audit): populate Table A — inline CSS inventory for migration sweep"
```

---

## Task 2: Build Table B — per-tab migration ranking

**Files:**
- Modify: `docs/design/handoff/app-css-audit.md`

- [ ] **Step 1: Count lines per tab from Table A**

Count rules per tab grouping from Table A. Sort descending.

- [ ] **Step 2: Append Table B**

```markdown
## App CSS migration sweep — Table B: Per-tab migration order

Largest first, so reviewer attention is front-loaded.

| Rank | Tab | Rule count | Expected effort | Risk notes |
|---|---|---|---|---|
| 1 | Risk Register | {N} | ~2h | Discovery-first redesign 2026-04-20 likely added bespoke components |
| 2 | Overview | {N} | ~2h | Largest analyst surface, many interactive states |
| 3 | Source Library | {N} | ~1.5h | Recent source-box redesign |
| 4 | Context | {N} | ~1h | Newer tab, thinner CSS |
| 5 | Pipeline | {N} | ~1h | Mostly table/log |
| 6 | Trends | {N} | ~0.5h | Small, chart chrome |
| 7 | Run Log | {N} | ~?? | Trace viewer may resist migration — candidate for skip |
| 8 | History | {N} | ~0.5h | Small |
```

- [ ] **Step 3: Commit**

```bash
git add docs/design/handoff/app-css-audit.md
git commit -m "docs(audit): add Table B — per-tab migration ranking"
```

---

## Task 3: Create the follow-ups log

**Files:**
- Create: `docs/design/handoff/migration-followups.md`

- [ ] **Step 1: Write the initial file**

```markdown
# Migration sweep follow-ups

Log of tabs / components that resisted the 2026-04-22 app.css migration sweep. Items here are deferred to a later dedicated effort.

## Skipped during sweep

_(populated as tabs are skipped)_

| Tab / component | Reason | Notes |
|---|---|---|
```

- [ ] **Step 2: Commit**

```bash
git add docs/design/handoff/migration-followups.md
git commit -m "docs(migration): seed follow-ups log for skipped tabs"
```

---

## Task 4: Per-tab migration — procedure (template)

This task is the **procedure** applied to each tab in Tasks 5-12. Not a commit by itself — it defines the steps every per-tab task follows.

For tab N:

- [ ] **Step 1: Isolate tab N's rules in `static/index.html` `<style>` block**

From Table A, list every rule tagged `promote` or `tab-specific` for tab N. Identify exact line ranges.

- [ ] **Step 2: Open `static/design/styles/app.css` and find the insertion point**

Append a commented section at the end of `app.css`:

```css
/* ---------- Tab: {tab name} ---------- */
```

All of tab N's promoted rules land under this header.

- [ ] **Step 3: Move rules from `index.html` to `app.css`**

Cut each `promote` / `tab-specific` rule from the inline `<style>` block and paste under the tab header in `app.css`. Preserve selector order within the tab.

- [ ] **Step 4: Normalize values per the rules at the top of this plan**

For each moved rule: replace hex with tokens (where matched), `px` with `--s-*`, font literals with `var(--font-sans)`, `font-size` with `--fs-*`, border color with `--border-*`, radius with `--r-*`. Keep literals with `// normalized: no token match` where no token maps.

- [ ] **Step 5: Delete `legacy`-tagged rules**

From Table A, any rule tagged `legacy` is removed from the inline block and NOT copied to `app.css`.

- [ ] **Step 6: Reload `/#<tab>` in the browser and walk the tab's QA checklist**

Each per-tab task has its own checklist (inlined below).

- [ ] **Step 7: Commit**

```bash
git add static/design/styles/app.css static/index.html
git commit -m "refactor(styles): promote {tab} chrome to app.css"
```

If the tab resists — normalization changes its render, or a primitive is needed that doesn't exist — abort migration for that tab:

```bash
git restore static/design/styles/app.css static/index.html
```

Log the tab in `migration-followups.md` with the reason, commit the log update:

```bash
git add docs/design/handoff/migration-followups.md
git commit -m "docs(migration): log {tab} as skipped — {reason}"
```

---

## Task 5: Migrate Risk Register (rank 1)

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html`

Follow the Task 4 procedure. Tab-specific QA checklist:

- [ ] Open `/#risk-register`.
- [ ] Register selector dropdown renders with correct spacing, hover, active state.
- [ ] Discovery block (T1 / T2 / T3 banners) renders unchanged in size, color, border.
- [ ] Scenario cards render unchanged.
- [ ] Reading list panel renders at same size, same row styling.
- [ ] Tier badges (T1 / T2 / T3) have identical color coding.
- [ ] Empty states unchanged.
- [ ] Polling indicator animation unchanged.
- [ ] Scenario detail panel (VaCR table, SiteContext box) unchanged.
- [ ] Edit modals (if any) unchanged.

Commit message: `refactor(styles): promote Risk Register chrome to app.css`.

---

## Task 6: Migrate Overview (rank 2)

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html`

Follow the Task 4 procedure. QA checklist:

- [ ] Open `/#overview`.
- [ ] Top-left state bar: ESCALATED / MONITOR counts + timestamp unchanged.
- [ ] Posture paragraph: font, weight, line-height unchanged.
- [ ] Region selector: dot colors per severity, active-region ring, hover states unchanged.
- [ ] Regional section header: severity pill, Admiralty rating chip, DRAFT / PUBLISHED badge all unchanged.
- [ ] Scenario detail block: INTEL FINDINGS / OBSERVED / IMPACT / WATCH / RECOMMENDED subsections unchanged in spacing and typography.
- [ ] Signal cluster accordions: expand / collapse animation and arrow rotation unchanged.
- [ ] Feedback buttons: Accurate / Incomplete / Off-target unchanged.

Commit message: `refactor(styles): promote Overview chrome to app.css`.

---

## Task 7: Migrate Source Library (rank 3)

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html`

Follow the Task 4 procedure. QA checklist:

- [ ] Open `/#source-library`.
- [ ] Search / filter row unchanged.
- [ ] Source rows render at same density, same metadata layout.
- [ ] Source-type badges (T1 / T2 / T3) unchanged.
- [ ] Hover states on source rows unchanged.
- [ ] Source detail panel unchanged.

Commit message: `refactor(styles): promote Source Library chrome to app.css`.

---

## Task 8: Migrate Context (rank 4)

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html`

Follow the Task 4 procedure. QA checklist:

- [ ] Open `/#context`.
- [ ] Sub-section navigation unchanged.
- [ ] Editor surfaces (text fields, file slots) unchanged.
- [ ] Save state indicators unchanged.
- [ ] Audit matrix (if present) unchanged.

Commit message: `refactor(styles): promote Context chrome to app.css`.

---

## Task 9: Migrate Pipeline (rank 5)

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html`

Follow the Task 4 procedure. QA checklist:

- [ ] Open `/#pipeline`.
- [ ] Run history table unchanged.
- [ ] Run status chips unchanged.
- [ ] Trace expansion behavior unchanged.
- [ ] Run metadata header unchanged.

Commit message: `refactor(styles): promote Pipeline chrome to app.css`.

---

## Task 10: Migrate Trends (rank 6)

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html`

Follow the Task 4 procedure. QA checklist:

- [ ] Open `/#trends`.
- [ ] Chart chrome unchanged (axis labels, gridlines, legend typography).
- [ ] Metric cards unchanged.
- [ ] Time-range selector unchanged.

Commit message: `refactor(styles): promote Trends chrome to app.css`.

---

## Task 11: Migrate Run Log (rank 7) — candidate for skip

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html` OR
- Modify: `docs/design/handoff/migration-followups.md` (if skipped)

Follow the Task 4 procedure. If the trace viewer uses patterns that don't normalize cleanly (bespoke monospace sizing, custom scroll container, syntax-highlight colors with no token mapping), **abort and log in follow-ups** per the Task 4 skip flow.

If migrated, QA checklist:
- [ ] Open `/#runlog`.
- [ ] Trace viewer renders unchanged (mono sizing, color coding, scrolling).
- [ ] Run selector unchanged.
- [ ] Filter controls unchanged.

Commit message: `refactor(styles): promote Run Log chrome to app.css` OR `docs(migration): log Run Log as skipped — {reason}`.

---

## Task 12: Migrate History (rank 8)

**Files:**
- Modify: `static/design/styles/app.css`, `static/index.html`

Follow the Task 4 procedure. QA checklist:

- [ ] Open `/#history`.
- [ ] History rows render unchanged.
- [ ] Date group headers unchanged.
- [ ] Expansion / collapse animations unchanged.

Commit message: `refactor(styles): promote History chrome to app.css`.

---

## Task 13: Sweep completion check — verify threshold met + clean up

**Files:**
- Modify: `docs/design/handoff/migration-followups.md`

- [ ] **Step 1: Count successful migrations**

Look at `git log --oneline` for the branch. Count `refactor(styles): promote {tab}` commits.

Threshold: at least 4 tabs must be migrated for the sweep to be worth the PR overhead. If fewer than 4 succeeded, close the PR as draft, leave the successful commits in the branch, and log the situation in `migration-followups.md` as "sweep attempted but fell short of threshold." Do not merge.

- [ ] **Step 2: Verify `static/index.html` `<style>` block is reduced**

```bash
wc -l static/index.html
grep -c "^}" static/index.html  # rough rule count by closing brace on own line
```

Compare line counts pre-sweep (captured at the start of Task 1) vs now. Expected: substantial reduction.

- [ ] **Step 3: Verify no CSS parse errors**

Open `/` in the browser, visit every migrated tab, open DevTools Console, confirm no CSS-related errors or 404s.

- [ ] **Step 4: Finalize follow-ups log**

Make sure every skipped tab has a row in `migration-followups.md` with:
- Tab name
- Specific reason (normalization broke a visual; primitive needed that doesn't exist; trace viewer uses bespoke patterns; etc.)
- Suggested next-step (dedicated redesign session; add new primitive first; accept as permanent inline).

- [ ] **Step 5: Commit cleanup if any**

```bash
git add docs/design/handoff/migration-followups.md
git commit -m "docs(migration): finalize follow-ups log after sweep"
```

---

## Task 14: Full manual walk + PR preparation

**Files:** none modified directly.

- [ ] **Step 1: Manual walk across all migrated tabs**

Visit each migrated tab. Confirm no visible regression vs. pre-sweep behavior. Use the per-tab checklists from Tasks 5-12 as reference. Issues found get fixed in the relevant per-tab commit (cherry-pick or amend only the commit for that tab, never a blanket commit at the end).

- [ ] **Step 2: Optional — Playwright screenshot diff across tabs**

If available and bandwidth allows:

```bash
uv run pytest tests/ui/ -k screenshot -v  # if a screenshot diff fixture exists
```

Non-blocking. Purpose: catch subtle regressions the manual eye missed. Skip if not set up.

- [ ] **Step 3: Full pytest suite sanity check**

```bash
uv run pytest -q --ignore=tests/test_export_ciso_docx.py
```

Expected: pass count unchanged from pre-sweep. CSS migration shouldn't change Python behavior.

- [ ] **Step 4: Prepare PR**

PR title: `refactor(styles): promote inline tab CSS to app.css`.

PR description:
```markdown
## Summary

Sweep to promote tab-specific CSS from `static/index.html` inline `<style>` block
into `static/design/styles/app.css`. Values normalized onto `tokens.css`.
No behavior or visual change intended.

## Migrated tabs

- [x] Risk Register
- [x] Overview
- [x] Source Library
- [x] Context
- [x] Pipeline
- [x] Trends
- [ ] Run Log (skipped — see follow-ups log)
- [x] History

## Deferred

See `docs/design/handoff/migration-followups.md`.

## Test plan

- [ ] Manual QA walk of every migrated tab per the per-tab checklists in the plan.
- [ ] Full pytest suite passes (excluding pre-existing skips).
- [ ] DevTools console: no CSS errors, no 404s on any tab.
```

---

## Self-review

Checking this plan against the spec at `docs/superpowers/specs/2026-04-22-app-css-migration-sweep.md`:

**Spec coverage:**
- Audit (spec §4 Tables A + B) → Tasks 1 and 2.
- Per-tab migration ranking (spec §5) → Task 2.
- Migration rules (spec §6) → Task 4 procedure + top-of-plan normalization rules.
- Per-tab QA checklists (spec §7) → Tasks 5-12, each with its own inlined checklist.
- Testing strategy (spec §8) → Task 14 manual walk + optional screenshot diff.
- Rollback (spec §9) → Task 4 per-tab revert flow + per-tab commits enable post-merge revert.
- DoD (spec §10) items all present: audit tables done (Tasks 1-2), 4+ tabs migrated (threshold in Task 13), deferred tabs logged (Tasks 3, 13), checklists pass (Tasks 5-12), PR description enumerates outcomes (Task 14).
- Sizing (spec §11) — per-tab estimates in Table B align with Tasks 5-12 sizing.
- Success criteria (spec §12) — Task 13 Step 2 measures inline line-count reduction.

**Placeholder scan:** Tables A and B have `{N}`, `{tab}`, `{reason}` placeholders — these are **intentional**, to be filled by the implementer at audit time with concrete values. The procedure's variable placeholders (`{tab name}`) are template-style, used in the Task 4 procedure by design. No placeholder represents missing plan content — they mark where data-dependent values plug in.

**Type / naming consistency:** tab identifiers consistent across plan (`Risk Register`, `Overview`, `Source Library`, `Context`, `Pipeline`, `Trends`, `Run Log`, `History`). Normalization tokens (`--s-*`, `--fs-*`, `--border-*`, `--r-*`, `--ink-*`) match what exists in `tokens.css`. Tag vocabulary (`promote` / `tab-specific` / `legacy`) consistent across Tasks 1 and 4.

**Caveats for the implementer:**
- Tab class prefixes (`.overview-*`, `.risk-*`, etc.) in Task 1 Step 2 are hypothetical — the audit may surface different actual prefixes.
- Task 13's "rough rule count by closing brace" metric is heuristic; the real gate is the DoD checklist, not the line count.
- `tests/ui/` location in Task 14 Step 2 assumes Playwright tests exist there; adjust per repo convention (same caveat as Reports V2 plan).

Gaps / ambiguity: none remaining.
