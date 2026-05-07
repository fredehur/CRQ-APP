# Playwright Tab Review — Chrome Retrofit Visual Audit

**Goal:** Screenshot every tab after the chrome retrofit and record visual inconsistencies to fix in a follow-up session.

**When to run:** After the chrome retrofit lands (committed `3baa199`). Server must be running on port 8001.

**Scope:** Visual audit only — no fixes in this task. Findings become a fix list.

---

## Tabs to review

| Tab ID | Label | switchTab key |
|---|---|---|
| nav-overview | Overview | overview |
| nav-reports | Reports | reports |
| nav-trends | Trends | trends |
| nav-history | History | history |
| nav-validate | Risk Register | validate |
| nav-sources | Source Library | sources |
| nav-pipeline | Pipeline | pipeline |
| nav-runlog | Run Log | runlog |
| nav-config | Config | config |

---

## What to check per tab

1. **Chrome renders correctly** — header height, register bar, drawer toggle, progress bar all use design-system classes (no leftover inline styles visible).
2. **Font** — body text is IBM Plex Sans (not Mono) except for monospace-specific cells which should still be Mono.
3. **Tab-content layout** — no collapsed sections, no overflow, no z-index fights with the new sticky header.
4. **Colour bleed** — no hardcoded `#070a0e`, `#0d1117`, `#238636`, `#3fb950` inline colours surviving in chrome area (lines 967–1027 of index.html).
5. **Active tab highlight** — clicking each tab moves the `.active` class correctly.
6. **Register drawer** — opens/closes, "+ New" button works, form panel shows/hides.
7. **Run All button** — present, styled with design-system class.
8. **Dev tab recede** — Pipeline and Run Log visually dimmer than stakeholder tabs.
9. **Console errors** — zero 404s, zero JS exceptions.

---

## Output format

For each tab, record:

```
Tab: <name>
Screenshot: output/playwright-review/<tab>.png
Issues:
  - <description of issue, element selector or line number if known>
  - …
```

Collate all issues into a single fix list at the bottom of this doc (or a new `2026-04-21-playwright-tab-fixes.md`).

---

## How to run

```bash
# start server
uv run python server.py &

# run playwright review script (to be written)
uv run python tools/playwright_tab_review.py
```

The review script should:
1. Navigate to `http://localhost:8001`
2. For each tab: click the nav element, wait for content to render, take a full-page screenshot, log console errors.
3. Write screenshots to `output/playwright-review/`.
4. Print a summary of any console errors per tab.

---

## Fix session

After the audit, open a new session and run `/brainstorming` with the issue list as input to scope the fixes.
