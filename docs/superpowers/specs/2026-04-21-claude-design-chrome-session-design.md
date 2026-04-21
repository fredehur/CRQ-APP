# Claude Design — Session 1: Web Design System

**Date:** 2026-04-21
**Status:** Draft — pending user review
**Supersedes:** nothing. This is the first entry in a multi-session Claude Design program.
**Follow-up:** a separate spec will cover per-tab page-layout sessions (Overview, Reports, Risk Register, Context, Source Library, …) once this session lands. Those sessions consume the design system produced here as locked input.

---

## Purpose

Produce a web-native design system for the AeroGrid CRQ Command Center app by running one Claude Design session. The output — a component library + shared chrome + stylesheet — extends the existing print design system (`docs/design/handoff/`) into web, and becomes the locked visual vocabulary every subsequent per-tab session consumes.

Output of the Claude Design session:

- `docs/design/handoff/Command Center Design System.html` — golden-reference HTML documenting the primitive component library and the shared chrome.
- `docs/design/handoff/styles/app.css` — web-app stylesheet that extends `tokens.css`.

Output of the implementation that follows this spec:

- `static/index.html` chrome sections restyled against the golden reference.
- In-tab primitives (buttons, pills, inputs, cards) class-swapped for consistency, without touching tab internal layouts.
- Zero changes to `app.js`.
- A Playwright screenshot fidelity test matching the print-brief pattern.

## Scope

**In scope for session 1:**

- Top app header, register bar, register drawer, progress bar, tab strip.
- Primitive components: button (primary/secondary/icon/ghost/destructive), select, input, table, card, pill/badge (severity + admiralty + category), chip, modal, tooltip, divider, tab-button.
- Loading state, empty state, toast / notification surface.
- Extension of `tokens.css` into web primitives — no new tokens, no parallel palette.

**Out of scope for session 1:**

- Per-tab layouts (Overview, Reports, Risk Register, Context, Sources, Validate, Trends, History, Run Log, Pipeline, Config).
- Any `app.js` changes.
- New features or new tabs.
- Data-visualization treatments (charts, timelines, maps) — deferred to a potential later session.
- Rebuilding, decomposing, or re-architecting the existing app.

## Design principles

1. **Extend, don't fork.** The web design system consumes `tokens.css` as-is. No new color values, no new spacing scale, no new font. Web primitives inherit the print language.
2. **Golden-reference HTML is the contract.** Same pattern that works for the three print briefs: `Command Center Design System.html` is a byte-equivalent target; `app.css` is lifted verbatim into the running app.
3. **Retrofit, not rebuild.** Claude Design sees the current chrome and primitives and proposes a restyle. It does not redesign per-tab information architecture in this session.
4. **Design-system-first sequencing.** Locking the component library and chrome before per-tab sessions prevents re-negotiating button styles, spacing, and typography nine times across later sessions.
5. **Severity and cyan semantics are invariant.** Severity colors appear only on pills/dots/chips. Cyan (`--brand-bright`) remains cyber-reserved. These rules carry over unchanged from the print system.

## Architecture

Three sequential layers.

### Layer 1 — Assemble the context bundle (I handle)

Bundle location: `docs/superpowers/specs/2026-04-21-claude-design-chrome-session-design/bundle/`.

Bundle contents:

```
bundle/
  brief.md                              # the written brief (full context for Claude Design)
  chat-prompt.md                        # the paste-able first message for the chat session
  current-chrome.html                   # standalone excerpt of static/index.html lines ~985–1044
  screenshots/
    01-overview.png                     # each top-nav tab, full viewport
    02-reports.png
    03-trends.png
    04-history.png
    05-risk-register.png
    06-source-library.png
    07-pipeline.png
    08-run-log.png
    09-config.png
    10-drawer-open.png                  # register drawer open state
  design-system/
    tokens.css                          # copied from docs/design/handoff/styles/tokens.css
    CRQ Design System.html              # copied from docs/design/handoff/
```

Screenshots are captured by the user at `http://localhost:8001` — one per top-nav tab plus one with the register drawer open. Run-state variations (mid-run progress bar, populated synthesis) are dropped from the brief; the chrome is described in prose rather than captured in motion.

### Layer 2 — Claude Design session (user handles)

User opens Claude Design (Anthropic Labs research preview — requires Pro/Max/Team/Enterprise subscription), starts a project, uploads every file in `bundle/`, pastes `brief.md` as the first message, iterates via chat (not inline comments — documented preview bug with comment persistence), exports HTML + CSS.

User drops exports into:

- `docs/design/handoff/Command Center Design System.html`
- `docs/design/handoff/styles/app.css`

### Layer 3 — Retrofit implementation (I handle via a follow-up plan)

Once Claude Design output lands in the repo, implementation is gated behind its own `writing-plans` invocation. Expected steps:

1. Copy `app.css` into `static/design/styles/` (sibling to existing `tokens.css`, `board.css`, `ciso.css`, `rsm.css`).
2. Replace `static/index.html`'s inline Tailwind config + `<style>` block with `<link>` references to `tokens.css` + `app.css`.
3. Walk chrome DOM (header, register bar, register drawer, progress bar, tab strip) and in-tab primitives. Swap inline `style=""` attributes for semantic class names matching the golden reference. Preserve every ID and every `onclick` binding.
4. Decide per-tab fate of the Tailwind CDN script — open question flagged for the implementation plan, not this spec. Lean: remove for chrome, keep for tab internals until per-tab specs retire it.
5. Add a Playwright fidelity test: render the chrome, diff against the golden reference.

## Success criteria

- `Command Center Design System.html` is valid, self-contained, renders correctly in a standalone browser using only `tokens.css` + `app.css`.
- `app.css` contains no hard-coded hex color values and no hard-coded spacing values. Every rule consumes a token from `tokens.css`.
- Every primitive (button primary/secondary/icon/ghost/destructive, select, input, table, card, pill, chip, modal, tooltip, tab-button) and every chrome element (top header, register bar, register drawer, progress bar, tab strip, empty state, loading state, toast) appears in the golden reference.
- After retrofit: `static/index.html` chrome sections contain zero inline `style=""` color attributes and zero inline hex color values.
- After retrofit: all existing pipeline smoke tests pass. No `app.js` changes.
- After retrofit: Playwright screenshot diff between running app and golden reference is whitespace-equivalent.

## Workflow and approval gates

1. **Gate 0 — spec approval.** User reviews this spec file. Approves or requests changes. No bundle work begins until approved.
2. **Gate 1 — bundle approval.** After I assemble the bundle, user reviews every file in `bundle/`. Approves or requests changes to `brief.md` before any upload to Claude Design.
3. **Gate 2 — Claude Design output approval.** After user exports from Claude Design, user reviews the output (visual fidelity to tokens, coverage of all required primitives and chrome elements) before invoking the implementation plan.
4. **Gate 3 — implementation plan approval.** `writing-plans` produces a plan; user reviews before execution.
5. **Gate 4 — implementation diff review.** User reviews the retrofit diff before merge.

## Non-goals (explicit)

- This spec does not decide per-tab ordering. Per-tab work is a separate spec written after this session lands.
- This spec does not decide the fate of the Tailwind CDN script. That belongs in the implementation plan.
- This spec does not commit to a specific Playwright diff tool (`pixelmatch` vs `odiff` vs other). That belongs in the implementation plan.
- This spec does not specify the ordering of primitives within the golden-reference component gallery. Claude Design can order them as it sees fit.

## Risks

- **Claude Design preview bugs.** Inline comments may disappear, large repos may cause performance problems. Mitigation: use chat-only iteration; do not link the repo unless Claude Design explicitly offers and handles the size.
- **Token drift.** Claude Design may invent new colors or spacing rather than consuming `tokens.css`. Mitigation: brief calls this out explicitly; user reviews output for drift before accepting.
- **Chrome-only scope creep.** Claude Design may produce layouts for tab internals. Mitigation: brief restricts scope explicitly; user declines any per-tab content in the output.
- **Retrofit fragility.** Class-swap in `index.html` may accidentally break an `app.js` selector. Mitigation: implementation plan enumerates every `getElementById` and `querySelector` in `app.js` before touching markup; any ID used by JS is preserved verbatim.

## Open questions

None blocking this spec. All open questions are deferred to either the bundle (brief wording) or the implementation plan (Tailwind CDN fate, diff tool choice).
