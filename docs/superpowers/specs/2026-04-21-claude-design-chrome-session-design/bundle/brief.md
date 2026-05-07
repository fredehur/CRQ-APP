# AeroGrid CRQ Command Center — Web Design System Brief

## What this is

AeroGrid Wind Solutions runs a Python-based multi-agent intelligence pipeline that produces geopolitical + cyber risk reports for a renewable-energy company. This brief is scoped to producing a **web design system** for the internal web app — the "command center" where analysts operate the pipeline and consume its output.

The output of this session is the visual vocabulary (tokens extension + component library + shared chrome) that every subsequent per-tab redesign session will consume as locked input. We're not redesigning any tab's internal layout in this session — that's follow-up work.

The web app is a dark-theme FastAPI + Jinja + Tailwind dashboard at `static/index.html`. We are not redesigning information architecture; we are producing the design language the app speaks, so it matches the polished reports it generates.

## Audience

The app is used by:

- Analysts (daily workspace)
- CISO + security leadership (weekly review)
- Board + C-suite (quarterly)
- Regional Security Managers (weekly intelligence summaries)

Total organization: ~30,000 employees across five regions (APAC, AME, LATAM, MED, NCE).

## What you are producing

**Two files.**

### 1. `Command Center Design System.html`

A single self-contained HTML file that documents the entire web design system on one page. Structure:

**Section A — Primitive component library (the centerpiece).**
Every primitive listed in "Primitives required" below, with labelled examples and all relevant variants. This is the canonical reference every future per-tab session will consume. Treat it as thoroughly as the `CRQ Design System.html` spec treats print components.

**Section B — Shared chrome applied.**
The app's shell components, shown in their default/active states:

- Top header — brand mark, tab strip, time-window selector, primary action button, settings icon.
- Register bar — the "Active: <register> · <N> scenarios · Switch ▾" persistent indicator below the header.
- Register drawer — the overlay shown when Switch is clicked.
- Progress bar — appears during pipeline runs (describe in the mockup as a labelled horizontal fill, e.g. "Running APAC… step 3 of 5").
- Tab strip — nine top-nav tabs plus a gear icon, with dev-tools-subordinated.
- Toast / notification surface — neutral, success, warning, error variants.
- Empty state template — for tabs with no data.
- Loading state template — for tab-level loading.

**Section C — Token reference card (brief).**
One small table or callout showing the tokens you actually used from `tokens.css`, grouped (color, spacing, type). Not a full re-listing — just a bookmark.

The HTML must:

- Link exactly two stylesheets: `styles/tokens.css` + `styles/app.css`.
- Use IBM Plex Sans as the type family (same as the print design system). Do not default to IBM Plex Mono — the existing app does, and it is one of the pain points being fixed.
- Preserve the semantic DOM skeleton of the current chrome (see `current-chrome.html` in this bundle) so the resulting markup can be retrofit into the running app without JS changes. IDs matter: `#app-header`, `#register-bar`, `#register-drawer`, `#progress-bar-container`, `#progress-fill` and all the `#nav-*` IDs must all remain intact and in the same nesting relationships. See `current-chrome.html` for the full list.

### 2. `styles/app.css`

A single CSS file that extends `tokens.css`. Rules:

- **Consume tokens. Do not redeclare.** Every color reference must resolve via a custom property from `tokens.css` (`--brand-navy`, `--brand-bright`, `--ink-100` through `--ink-900`, `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor`). Every spacing value must come from `--s-1` through `--s-6`.
- **No hard-coded hex values.** Zero exceptions. If you need a color that isn't in tokens, flag it in the chat — do not invent one.
- **No parallel severity scale.** Do not create `sev-c`, `sev-h`, etc. Use `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor` exactly as the print system does.
- **IBM Plex Sans default.** Use the same font-loading approach as the print briefs (Google Fonts preconnect + weights 400/500/600/700).
- **Semantic class names.** Classes should describe the component (`.btn-primary`, `.pill-severity`, `.card`, `.table-default`), not the appearance (`.green`, `.padded-16`). Future tab sessions will compose them.

## Design system you must consume

Two files are attached:

- `design-system/tokens.css` — the locked token foundation. Color, type scale, spacing, severity semantics, category circles. This is immutable.
- `design-system/CRQ Design System.html` — the spec page that documents tokens + component patterns. Use this as the visual vocabulary. Note: this page is light-themed because it's the print-first spec — the web app is **dark**-themed; consume the tokens and component patterns, not the theme.

## Design invariants carried over from the print system

These rules are already enforced in print and must hold in the web app too:

1. **Severity color is semantic-only.** `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor` appear on pills, dots, and chips — never on headlines, body copy, or backgrounds.
2. **Cyan rule line is cyber-only.** `--brand-bright` (the cyan) is reserved for cyber-only moments. Do not apply it to physical or unrelated chrome elements.
3. **Region codes are terse + capitalized.** MED · NCE · APAC · LATAM · AME.
4. **Evidence anchors.** `E#` for physical, `C#` for cyber. Admiralty-graded (A1–F6). Where chrome shows evidence chips or source references, these conventions hold.
5. **IBM Plex Sans is the voice.** Not Mono.

## The web app is dark-theme

Unlike the print briefs (which are light), the web app is dark. Keep it dark. Use the ink scale from `tokens.css` to establish the dark surface hierarchy — do not invent a new dark palette.

## Primitives required in the component library

Each primitive needs a labelled example (or a small grid of variants). Be thorough — future per-tab sessions will compose from this list, so anything missing here will need to be added retroactively.

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

## Chrome (shell) applied in Section B

- **Top app header (36px tall).** Brand mark on the left ("// CRQ ANALYST" today — open to refinement). Tab nav in the header. Current labels, in order: **Overview, Reports, Trends, History, Risk Register, Source Library, Pipeline, Run Log**, plus a separate gear icon (⚙) for **Config**. Pipeline, Run Log, and Config are developer tools and should visually recede. Overview, Reports, Risk Register, Source Library are stakeholder-leading. Trends and History are analyst-secondary (keep them in the main group, not demoted). A new tab, **Context**, is imminent (separate in-flight spec) — the tab strip must accommodate a 9th top-nav label without re-layout. Time-window selector (dropdown: "Last 24h", "Last 7 days", "Last 30 days", "Last quarter"). Primary action button: "▶ RUN ALL".
- **Register bar (24px tall, directly below header).** Shows "Active: <register name> · <N> scenarios" and a "Switch ▾" toggle. Minimal, persistent-indicator feeling — not a navigation destination.
- **Register drawer.** Overlay that appears when Switch is clicked. Shows a list of registers with their scenario counts, plus a "+ New" button. Width ~320px.
- **Progress bar.** Between register bar and tab content. Shown only while a run is active. Label ("Running APAC… step 3 of 5") + thin horizontal fill.
- **Tab strip.** Where the tab labels live. Active tab clearly indicated; dev tabs visually subordinate.
- **Toast / notification surface.** Bottom-right corner. Neutral, success, warning, error variants.
- **Empty state template.** Used by tabs with no data. Headline + supporting line + primary action.
- **Loading state template.** Tab-level loading. Skeleton or spinner — your call, but token-driven.

## Pain points you are fixing

1. **Color drift.** Hex values like `#0d1117`, `#21262d`, `#c9d1d9` are duplicated inline across hundreds of elements instead of consuming `tokens.css` custom properties. Result: the app cannot be retoned without a 1400-line search-and-replace.
2. **Font mismatch.** Current app defaults to IBM Plex Mono (developer aesthetic). The reports it produces use IBM Plex Sans. Analysts mentally context-switch between "the tool" and "the deliverable." We want one voice.
3. **Inline styles everywhere.** 1477 lines of `index.html` contain only 47 `class=""` attributes. Every element is styled via inline `style=""` attributes. Retheming is impossible without touching markup.
4. **Severity tokens duplicated.** The app declares its own `sev-c`, `sev-h`, `sev-m`, `sev-ok`, `sev-mon` via a custom Tailwind config. The print system uses `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor`. One brand, two vocabularies.
5. **Ad-hoc buttons.** `RUN ALL` uses one green; `+ New` uses a different green; icon buttons have their own hover treatments. No primary/secondary concept exists.
6. **No spacing rhythm.** Padding values are `8px 16px`, `10px 16px`, `12px 16px` scattered inline. The print system has `--s-1` through `--s-6`. Adopt the print rhythm.
7. **Tab nav is weak.** All tabs currently look equal. Pipeline, Run Log, and Config are developer tools that should visually recede. Overview, Reports, Risk Register, Source Library (and the imminent Context tab) are stakeholder-facing and should lead. Trends and History are analyst-secondary — keep them in the main group, not demoted. Note: there IS a "Risk Register" top-nav tab (it opens a register-level UI); the separate **register bar** below the header is a distinct app-level state switcher for choosing WHICH register is active — design that as a persistent indicator, not a navigation destination.

## What you should NOT do

- **Do not redesign any tab's internal layout.** Out of scope. Per-tab work is a separate future session that will consume this design system as input.
- **Do not touch `app.js`.** Out of scope. The markup must accept the same JS bindings.
- **Do not invent new tokens.** Extend, don't fork.
- **Do not apply cyan to physical-pillar chrome.** Cyan is cyber-only.
- **Do not apply severity color to headlines, body copy, or backgrounds.** Pills, dots, chips only.
- **Do not remove any IDs listed in `current-chrome.html`.** The retrofit depends on them.
- **Do not propose a light theme.** The app is dark; it stays dark.

## Deliverable format

Export as a ZIP or as separate files:

- `Command Center Design System.html`
- `app.css`

Both must open correctly in a standalone browser with only `tokens.css` + `app.css` present in a `styles/` subfolder.

## Iteration preference

Use chat to request changes rather than inline comments on the canvas (preview bug with comment persistence). When in doubt, ask for three variants and let me pick. Push back if the brief contradicts itself — I'd rather rewrite the brief than ship a compromise.
