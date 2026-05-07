# Claude Design — Chat Prompt

Paste this as your first message in the Claude Design session, after uploading every file in this `bundle/` folder.

---

Hi — I'm producing a **web design system** for an internal app called the **AeroGrid CRQ Command Center**. It's a dark-theme dashboard where analysts run a geopolitical + cyber risk intelligence pipeline for a renewable-energy company (~30k employees). The app's visual language has drifted from the polished print design system we use for the reports it generates. You're going to fix that by producing the design system the web app will speak — tokens extension + primitive component library + shared chrome. Per-tab page layouts are a separate future session that will consume this system as input.

## What I've uploaded

- **`brief.md`** — full written brief with every requirement, constraint, and pain point. Read this first.
- **`current-chrome.html`** — the existing chrome markup I need to restyle. Every `id` attribute and every `onclick` handler must be preserved (JS binds to them).
- **`design-system/tokens.css`** — the locked design tokens you must consume. Do not invent colors, spacing, or fonts.
- **`design-system/CRQ Design System.html`** — the spec page showing the token vocabulary and component patterns we use for our report deliverables. The web app should feel like a live extension of this language, translated to dark-theme web. The spec page itself is light-themed; the web app is dark — consume the vocabulary, not the theme.
- **`screenshots/`** — one capture per top-nav tab plus one with the register drawer open, so you can see what the current app looks like.

## What I want you to produce

1. **`Command Center Design System.html`** — a self-contained golden-reference page organized as:
   - **Section A — Primitive component library** (the centerpiece): every primitive listed in `brief.md`, with variants. Be thorough — future per-tab sessions compose from this list.
   - **Section B — Shared chrome applied**: header, register bar, register drawer (open), progress bar, tab strip, toast surface, empty state, loading state.
   - **Section C — Token reference card**: short bookmark of which tokens you used.
   - Links exactly two stylesheets: `styles/tokens.css` and `styles/app.css`.

2. **`app.css`** — the web-app stylesheet. Extends `tokens.css`. No hard-coded hex values. No hard-coded spacing. No parallel severity palette. IBM Plex Sans. Dark theme. Semantic class names (`.btn-primary`, `.pill-severity`, `.card`) — not appearance names.

## Hard constraints — the non-negotiables

- **Dark theme.** The app stays dark. Use the `--ink-*` scale from `tokens.css` for surface hierarchy.
- **Tokens only.** Every color and every spacing value must resolve via a custom property from `tokens.css`. If you need something that isn't there, raise it in chat — do not invent.
- **Design system only.** Do not redesign any tab's internal layout. Primitive library + shared chrome only.
- **Don't touch `app.js`.** The DOM skeleton and IDs in `current-chrome.html` must be preserved verbatim.
- **Severity is semantic-only.** `--sev-critical / --sev-high / --sev-medium / --sev-monitor` appear only on pills, dots, chips. Never on headlines, body copy, or backgrounds.
- **Cyan is cyber-only.** `--brand-bright` is reserved for cyber moments. Don't apply it to generic chrome.
- **Semantic class names.** Future sessions compose from these — `.btn-primary`, not `.green-button`.

## What's weak about the current app (summary — full list in `brief.md`)

- Color drift — hex values duplicated inline instead of consuming tokens.
- Font mismatch — app defaults to IBM Plex Mono; our reports use IBM Plex Sans. Unify on Sans.
- Inline styles everywhere — 1477 lines, 47 class attrs. Retheming is impossible.
- Duplicated severity scale — app has `sev-c/sev-h/…`; tokens have `--sev-critical/…`.
- No primary/secondary button concept — every button is bespoke.
- No spacing rhythm — inline padding values scattered randomly.
- Tab nav is flat — Pipeline, Run Log, Config (dev tools) look identical to Overview, Reports, Risk Register, Source Library (stakeholder-leading). Demote the dev tabs.

## How I want to work

- **Start** by reading `brief.md` and `current-chrome.html`, then tell me you've got the scope before producing anything.
- **First draft** should be the primitive component library (Section A). That's the centerpiece and the thing future sessions consume — get it right first. I'll review before we add Section B (chrome applied) and Section C (token reference).
- **Iterate via chat**, not inline comments (known preview bug with comment persistence).
- **When in doubt, show three variants** and let me pick.
- **Push back** if anything in `brief.md` contradicts itself — I'd rather fix the brief than ship a compromise.

Ready when you are.
