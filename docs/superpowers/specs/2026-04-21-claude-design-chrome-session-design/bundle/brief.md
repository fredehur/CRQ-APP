# AeroGrid CRQ Command Center — Chrome Redesign Brief

## What this is

AeroGrid Wind Solutions runs a Python-based multi-agent intelligence pipeline that produces geopolitical + cyber risk reports for a renewable-energy company. This brief is scoped to redesigning the **chrome** (shell + primitive components) of the internal web app — the "command center" where analysts operate the pipeline and consume its output.

The web app is a dark-theme FastAPI + Jinja + Tailwind dashboard at `static/index.html`. We are not redesigning information architecture; we are restyling what exists so the app speaks the same visual language as the reports it produces.

## Audience

The app is used by:

- Analysts (daily workspace)
- CISO + security leadership (weekly review)
- Board + C-suite (quarterly)
- Regional Security Managers (weekly intelligence summaries)

Total organization: ~30,000 employees across five regions (APAC, AME, LATAM, MED, NCE).

## What you are producing

**Two files.**

### 1. `Command Center App.html`

A single self-contained HTML file that functions as a golden-reference mockup of the chrome. It must include, all on one page:

- **State A — empty.** The app chrome before any pipeline run has happened. Register bar shows a default register; progress bar is not visible; synthesis area shows the "No run data" message.
- **State B — mid-run.** Progress bar is active showing a run in progress; synthesis area is still empty; register bar unchanged.
- **State C — populated.** After a run completes. Register bar shows active register + scenario count; progress bar hidden; synthesis area shows status counts + narrative.
- **Register drawer open** — the overlay dropdown activated from the register bar, showing a list of registers and a "+ New" action.

Plus a **component gallery** section below the state mockups covering every primitive listed in "Primitives required" below.

The HTML must:

- Link exactly two stylesheets: `styles/tokens.css` + `styles/app.css`.
- Use IBM Plex Sans as the type family (same as the print design system). Do not default to IBM Plex Mono — the existing app does, and it is one of the pain points being fixed.
- Preserve the semantic DOM skeleton of the current chrome (see `current-chrome.html` in this bundle) so the resulting markup can be retrofit into the running app without JS changes. IDs matter: `#app-header`, `#register-bar`, `#register-drawer`, `#progress-bar-container`, `#progress-fill`, `#global-synthesis`, `#synthesis-empty`, `#synthesis-populated`, `#synthesis-brief`, `#status-counts`, `#run-meta` must all remain intact and in the same nesting relationships.

### 2. `styles/app.css`

A single CSS file that extends `tokens.css`. Rules:

- **Consume tokens. Do not redeclare.** Every color reference must resolve via a custom property from `tokens.css` (`--brand-navy`, `--brand-bright`, `--ink-100` through `--ink-900`, `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor`). Every spacing value must come from `--s-1` through `--s-6`.
- **No hard-coded hex values.** Zero exceptions. If you need a color that isn't in tokens, flag it in the chat — do not invent one.
- **No parallel severity scale.** Do not create `sev-c`, `sev-h`, etc. Use `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor` exactly as the print system does.
- **IBM Plex Sans default.** Use the same font-loading approach as the print briefs (Google Fonts preconnect + weights 400/500/600/700).

## Design system you must consume

Three files are attached:

- `design-system/tokens.css` — the locked token foundation. Color, type scale, spacing, severity semantics, category circles. This is immutable.
- `design-system/CRQ Design System.html` — the spec page that documents tokens + component patterns. Use this as the visual vocabulary.
- `design-system/Board Report Q2 2026.html` — a full working example of the print design language. The web app should feel like a live, interactive extension of this.

## Design invariants carried over from the print system

These rules are already enforced in print and must hold in the web app too:

1. **Severity color is semantic-only.** `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor` appear on pills, dots, and chips — never on headlines, body copy, or backgrounds.
2. **Cyan rule line is cyber-only.** `--brand-bright` (the cyan) is reserved for cyber-only moments. Do not apply it to physical or unrelated chrome elements.
3. **Region codes are terse + capitalized.** MED · NCE · APAC · LATAM · AME.
4. **Evidence anchors.** `E#` for physical, `C#` for cyber. Admiralty-graded (A1–F6). Where chrome shows evidence chips or source references, these conventions hold.
5. **IBM Plex Sans is the voice.** Not Mono.

## The web app is dark-theme

Unlike the print briefs (which are light), the web app chrome is dark. Keep it dark. Use the ink scale from `tokens.css` to establish the dark surface hierarchy — do not invent a new dark palette.

## Primitives required in the component gallery

Each primitive needs a labelled example (or a small grid of variants).

- **Button** — primary, secondary, icon-only, ghost, destructive. Include disabled state for primary.
- **Select / dropdown** — closed + open. Include the register-drawer pattern as a specialized case.
- **Input** — text, number. Default + focus + error states.
- **Table** — header row, body row, alternating density (default + compact). Sort indicator on one column.
- **Card** — surface with subtle border. Variant with severity accent (left border tinted).
- **Pill / badge** — severity (critical, high, medium, monitor, ok), admiralty grade (B1, C2, etc.), region code.
- **Chip** — filter/tag. Selected + unselected.
- **Modal** — overlay dialog with header, body, and two-button footer.
- **Tooltip** — over an info icon.
- **Divider / section header** — labeled horizontal rule.
- **Tab button** — inside a tab's content (not the top nav). Active + inactive.

## Chrome (shell) required

- **Top app header (36px tall).** Brand mark on the left ("AeroGrid · CRQ Command Center" or similar). Tab nav in the middle or right. Current tabs (9): Overview, Reports, Sources, Validate, Trends, History, Run Log, Pipeline, Config. The last three (Run Log, Pipeline, Config) are developer tools and should visually recede. A tenth tab, **Context**, is imminent (separate in-flight spec) — the tab strip must accommodate it without re-layout. Time-window selector (dropdown: "Last 24h", "Last 7 days", "Last 30 days", "Last quarter"). Primary action button: "▶ RUN ALL". Settings icon button (⚙).
- **Register bar (24px tall, directly below header).** Shows "Active: <register name> · <N> scenarios" and a "Switch ▾" toggle. Minimal, read-only-feeling.
- **Register drawer.** Overlay that appears when Switch is clicked. Shows a list of registers with their scenario counts, plus a "+ New" button. Width ~320px.
- **Progress bar.** Appears between register bar and tab content when a run is in progress. Shows a label ("Running APAC… step 3 of 5") + a thin progress fill.
- **Tab strip.** Below register bar (or integrated into header — your call). 9 tabs. Active tab clearly indicated.
- **Toast / notification surface.** Bottom-right corner. Neutral, success, warning, error variants.
- **Empty state template.** For tabs that have no data yet. Includes a message + a primary action.
- **Loading state template.** For in-tab loading. Skeleton or spinner — your call, but keep it token-driven.

## Pain points in the current chrome (what you are fixing)

1. **Color drift.** Hex values like `#0d1117`, `#21262d`, `#c9d1d9` are duplicated inline across hundreds of elements instead of consuming `tokens.css` custom properties. Result: the app cannot be retoned without a 1400-line search-and-replace.
2. **Font mismatch.** Current app defaults to IBM Plex Mono (developer aesthetic). The reports it produces use IBM Plex Sans. Analysts mentally context-switch between "the tool" and "the deliverable." We want one voice.
3. **Inline styles everywhere.** 1477 lines of `index.html` contain only 47 `class=""` attributes. Every element is styled via inline `style=""` attributes. Retheming is impossible without touching markup.
4. **Severity tokens duplicated.** The app declares its own `sev-c`, `sev-h`, `sev-m`, `sev-ok`, `sev-mon` via a custom Tailwind config. The print system uses `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor`. One brand, two vocabularies.
5. **Ad-hoc buttons.** `RUN ALL` uses one green; `+ New` uses a different green; icon buttons have their own hover treatments. No primary/secondary concept exists.
6. **No spacing rhythm.** Padding values are `8px 16px`, `10px 16px`, `12px 16px` scattered inline. The print system has `--s-1` through `--s-6`. Adopt the print rhythm.
7. **Tab nav is weak.** All 9 tabs currently look equal. Config, Run Log, and Pipeline are developer tools that should visually recede. Overview, Reports, Sources (and the imminent Context tab) are stakeholder-facing and should lead. Risk Register management is handled via the register bar/drawer (not a top-nav tab) — that flow is separate and should feel like an app-level state switcher, not a navigation destination.

## What you should NOT do

- **Do not redesign any tab's internal layout.** Out of scope. Per-tab work is a separate future session.
- **Do not touch `app.js`.** Out of scope. The markup must accept the same JS bindings.
- **Do not invent new tokens.** Extend, don't fork.
- **Do not apply cyan to physical-pillar chrome.** Cyan is cyber-only.
- **Do not apply severity color to headlines, body copy, or backgrounds.** Pills, dots, chips only.
- **Do not remove any IDs listed in the "semantic DOM skeleton" section above.** The retrofit depends on them.
- **Do not propose a light theme.** The app is dark; it stays dark.

## Deliverable format

Export as a ZIP or as separate files:

- `Command Center App.html`
- `app.css`

Both must open correctly in a standalone browser with only `tokens.css` + `app.css` present in a `styles/` subfolder.

## Iteration preference

Use chat to request changes rather than inline comments on the canvas (preview bug with comment persistence). When in doubt, ask for three variants and let me pick. Push back if the brief contradicts itself — I'd rather rewrite the brief than ship a compromise.
