# AeroGrid CRQ Command Center — Design System Handoff

This package contains the design system and three golden-reference reports for the AeroGrid CRQ (Cyber Risk Quantification) reporting pipeline.

---

## What's in this package

```
handoff/
├── README.md                      — this file
├── styles/
│   ├── tokens.css                 — shared foundation — links FIRST, always
│   ├── system.css                 — design system doc only
│   ├── rsm.css                    — weekly INTSUM report
│   ├── ciso.css                   — monthly CISO brief
│   └── board.css                  — quarterly board report
├── CRQ Design System.html         — the spec page (tokens + components)
├── RSM Weekly INTSUM MED.html     — golden reference: weekly INTSUM
├── CISO Brief April 2026.html     — golden reference: monthly brief
└── Board Report Q2 2026.html      — golden reference: quarterly board report
```

---

## Architecture

Three layers, one direction of dependency:

```
         tokens.css
        (foundation)
              ↓
     ┌────────┼─────────┬──────────┐
     ↓        ↓         ↓          ↓
  system   rsm       ciso        board
   .css    .css      .css         .css
     ↓        ↓         ↓          ↓
  spec    weekly    monthly    quarterly
```

- **tokens.css** declares all CSS custom properties — color, type scale, spacing, severity semantics. No components. Zero dependencies.
- Each report stylesheet **extends** tokens. It never redefines a variable; it consumes them.
- The HTML golden references link exactly two stylesheets: `tokens.css` + one report-specific file.

---

## Integration with your Jinja2 + Playwright pipeline

### 1. Lift the CSS files verbatim

Copy `styles/*.css` into your repo's static directory, no edits. Link order in your Jinja templates must be:

```html
<link rel="stylesheet" href="{{ static }}/styles/tokens.css">
<link rel="stylesheet" href="{{ static }}/styles/board.css">  <!-- or rsm.css / ciso.css -->
```

Tokens must come first. Every downstream rule depends on the custom properties declared there.

### 2. Pin the font

All three reports load **IBM Plex Sans** at weights 400 / 500 / 600 / 700 from Google Fonts:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

In Playwright, **wait for the font to load** before calling `page.pdf()`:

```python
await page.wait_for_function("document.fonts.ready")
await page.pdf(...)
```

If you're air-gapped, self-host the same four weights and replace the `<link>` with a local `@font-face` block.

### 3. Playwright PDF settings

```python
await page.pdf(
    format="A4",
    print_background=True,       # REQUIRED — pills, bands, severity fills disappear without it
    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
    prefer_css_page_size=True,   # honors @page size if declared
)
```

Each `.page` section in the HTML already owns its own A4 padding — don't add Playwright margins on top or you'll get double-padding.

### 4. Mirror the DOM structure in your Jinja templates

The CSS is tightly coupled to the class hierarchy. If you rename a wrapper or collapse a nesting level, styles break silently. Use the three golden-reference HTML files as **byte-equivalent targets**: when your Jinja templates are fed the same data, the rendered HTML should differ only in whitespace.

**The skeleton every page shares:**

```html
<section class="page" data-screen-label="01 Cover">
  <header class="ph-top">
    <span class="brand">AeroGrid · [Report] · [Period]</span>
    <span>[Section] · p. N / T</span>
  </header>

  <div class="page-mark">
    <span class="kicker">§ [N] · [Section name]</span>
    <span class="meta">[Date · Admiralty · Confidence]</span>
  </div>

  <h1 class="page-title">[Single-sentence headline.]</h1>
  <p class="page-lede">[Supporting paragraph.]</p>

  <!-- report-specific blocks here -->

  <footer class="ph-bot">
    <span>AeroGrid Wind Solutions · [Org unit]</span>
    <span class="preparer">Prep. [X] · Rev. [Y]</span>
    <span>Internal — [Distribution] · p. N / T</span>
  </footer>
</section>
```

---

## Design grammar (the invariants)

These rules are enforced by the stylesheets and should be enforced by your Jinja templates too:

1. **Severity color is semantic-only.** `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor` are carried by **pills, dots, and chips** — never by headlines, body copy, or backgrounds.
2. **Every assertion carries an evidence anchor.** `E#` for physical evidence, `C#` for cyber. Admiralty-graded (A1–F6, typical range B1–C2).
3. **Cyan rule line** (`--brand-bright`, the cyan stripe) is reserved for cyber-only moments. Using it on a physical block breaks the visual contract.
4. **One-sentence page titles.** `.page-title` is the single assertion of the page. The `.page-lede` is the expansion.
5. **Region codes** are terse and capitalized: MED · NCE · APAC · LATAM · AME.

---

## Keeping fidelity over time

The fastest way to guarantee ongoing fidelity:

1. Check the three HTML golden references into your repo as fixtures.
2. On every CI run, render them through Playwright to PDF with the same settings your pipeline uses.
3. Diff against a committed reference PDF using `pixelmatch`, `odiff`, or similar.

Any drift from a dependency upgrade, font change, or accidental CSS edit will show up as a pixel diff immediately.

---

## Token surface (reference)

Defined in `tokens.css`. Consume these; don't redeclare.

**Color**
- `--brand-navy`, `--brand-bright` (cyan)
- `--ink-100` through `--ink-900` (neutral scale)
- `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-monitor`
- `--cat-M`, `--cat-W`, `--cat-C`, `--cat-G`, `--cat-S` (category circles)

**Type**
- Font family: `IBM Plex Sans` + system fallbacks
- `--tr-meta`, `--tr-label`, `--tr-display` (tracking values)

**Spacing & surface**
- `--s-1` through `--s-6` (scale)
- `--radius-sm`, `--radius-md`

---

## Contact / provenance

- Prepared during the CRQ Command Center design engagement.
- Golden references: v1.0 — RSM W17 · CISO Apr 2026 · Board Q2 2026.
- Open an issue against your repo's design-system label for drift reports.
