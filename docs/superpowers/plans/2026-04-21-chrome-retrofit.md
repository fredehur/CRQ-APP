# Chrome Retrofit Implementation Plan

**Goal:** Apply the Claude Design web design system (`docs/design/handoff/Command Center Design System.html` + `styles/app.css`) to `static/index.html`. Chrome sections only. Zero `app.js` changes. Zero changes to tab internal layouts.

**Architecture:** Five sequential passes:
1. Stage the CSS into `static/` so FastAPI serves it.
2. Link the new stylesheets after the existing inline `<style>` block so new rules win where they collide.
3. Strip conflicting baseline declarations from the inline `<style>` (universal Mono, body background/padding).
4. Remove the Tailwind `colors` config that declared a parallel severity scale (`sev-c`, `sev-h`, etc.).
5. Class-swap chrome markup (header, register bar, drawer, progress bar) for the semantic class names defined in `app.css`. Preserve every ID and every `onclick` handler verbatim.

Each pass is independently reversible. Commit after each pass.

**Tech Stack:** HTML, CSS, FastAPI static file serving, `uv run python server.py` for local verification. Playwright fidelity test deferred to a follow-up spec.

**Spec:** `docs/superpowers/specs/2026-04-21-claude-design-chrome-session-design.md`

**Claude Design output:** committed in `ad36a05` at `docs/design/handoff/Command Center Design System.html` + `docs/design/handoff/styles/app.css`.

---

## Files

**Modify:**
- `static/index.html` — head (stylesheet links, Tailwind config, inline `<style>` block) and chrome markup (approximately lines 984–1044).

**Create:**
- `static/design/styles/app.css` — copy of `docs/design/handoff/styles/app.css`, lifted verbatim per the handoff README ("Lift the CSS files verbatim").

**Do not touch:**
- `static/app.js` — no changes allowed.
- Any tab-content region of `static/index.html` (lines 1046 and below). The inline styles there remain; per-tab class-swaps happen in a separate follow-up spec.
- Any file outside `static/` and `docs/design/handoff/` for this plan.

---

## Task 1: Stage `app.css` into the served static directory

**Files:**
- Create: `static/design/styles/app.css` (copy of `docs/design/handoff/styles/app.css`)

- [ ] **Step 1: Copy the file**

```bash
cp "docs/design/handoff/styles/app.css" "static/design/styles/app.css"
```

- [ ] **Step 2: Verify byte-equivalence**

```bash
cmp -s "docs/design/handoff/styles/app.css" "static/design/styles/app.css" && echo "match" || echo "MISMATCH"
```

Expected: `match`

- [ ] **Step 3: Verify `tokens.css` sibling is already in place (it should be — untouched since the print handoff)**

```bash
ls static/design/styles/ | grep -E "^(tokens|app)\.css$"
```

Expected: both `tokens.css` and `app.css` listed.

- [ ] **Step 4: Commit**

```bash
git add static/design/styles/app.css
git commit -m "design(static): lift app.css into served static directory"
```

---

## Task 2: Link the new stylesheets and broaden the font request

Add `<link>` tags for `tokens.css` + `app.css` after the existing inline `<style>` block (cascades over conflicting rules). Broaden the Google Fonts request to include IBM Plex Sans weights 400/500/600/700 per the handoff README.

**Files:**
- Modify: `static/index.html` — head section around lines 7–8 (font link) and line 980 (end of inline `<style>`).

- [ ] **Step 1: Read the current head state to confirm line numbers**

```bash
sed -n '1,12p' static/index.html
```

Expected: lines 7–8 are the preconnect + Google Fonts `<link>`; line 9 is the Tailwind CDN `<script>`.

- [ ] **Step 2: Replace the Google Fonts link to request Plex Sans weights 400/500/600/700**

Current line 8:
```html
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
```

Replace with (keeps Mono for existing monospaced cells in tab content; adds Plex Sans 600 + 700):
```html
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

Exact Edit call:

```
Edit static/index.html
old_string:   <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
new_string:   <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- [ ] **Step 3: Add `<link>` tags for the design system AFTER the closing `</style>` tag on line 980**

The inline `<style>` block currently ends at line 980 with `  </style>` followed by `</head>` on line 981. Insert the new link tags between them.

Current lines 980–981:
```html
  </style>
</head>
```

New lines 980–983:
```html
  </style>

  <!-- Web design system — extends print tokens -->
  <link rel="stylesheet" href="/static/design/styles/tokens.css">
  <link rel="stylesheet" href="/static/design/styles/app.css">
</head>
```

Exact Edit call:

```
Edit static/index.html
old_string:   </style>
</head>
new_string:   </style>

  <!-- Web design system — extends print tokens -->
  <link rel="stylesheet" href="/static/design/styles/tokens.css">
  <link rel="stylesheet" href="/static/design/styles/app.css">
</head>
```

- [ ] **Step 4: Verify the URLs resolve at runtime**

Start the server:

```bash
uv run python server.py &  # run in background
```

Test:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/static/design/styles/tokens.css
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/static/design/styles/app.css
```

Expected: both return `200`.

Stop the server:
```bash
# use TaskStop on the shell ID
```

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "design(chrome): link web design system stylesheets"
```

---

## Task 3: Remove conflicting baseline declarations from inline `<style>`

The inline `<style>` sets three baseline rules that fight the new design system. Remove only those three rules. Leave every other rule in the inline `<style>` block alone — tab content depends on them.

**Files:**
- Modify: `static/index.html` — lines 34–35 inside the inline `<style>` block.

- [ ] **Step 1: Remove the universal Mono rule**

Current line 34:
```css
    * { font-family: 'IBM Plex Mono', monospace; }
```

Delete the entire line. After removal, body inherits `font-family: var(--font-sans)` from `app.css` (`html, body` rule), and individual elements that need Mono can opt in via their own rules (there are some in tab content that set mono explicitly — those stay).

Exact Edit call:

```
Edit static/index.html
old_string:     * { font-family: 'IBM Plex Mono', monospace; }
    body { background: #070a0e; color: #c9d1d9; padding-top: 60px; }
new_string:     body { padding-top: 0; }
```

Explanation:
- The universal `*` rule is gone — Sans becomes the default via app.css.
- The body `background`, `color` declarations are gone — `app.css` `html, body` handles them.
- `padding-top: 60px` is replaced with `0`. The old fixed-position header required 60px of body padding to avoid overlap; the new header uses `position: sticky` which flows with content naturally. Keeping `padding-top: 0` explicit overrides any browser default.

- [ ] **Step 2: Start the server and sanity-check the page still loads**

```bash
uv run python server.py &
```

Then:
```bash
curl -s http://localhost:8001/ | head -5
```

Expected: `<!DOCTYPE html>` followed by the opening `<html lang="en">`.

Stop the server.

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "design(chrome): remove universal Mono + body baseline overrides"
```

---

## Task 4: Remove the Tailwind severity/accent color config

The `tailwind.config` declares `sev-c`, `sev-h`, `sev-m`, `sev-ok`, `sev-mon` — a parallel severity scale that violates the design system's "single severity vocabulary" invariant. Remove the whole `tailwind.config` script block. `fontFamily.mono` inside it is also obsolete (Mono is no longer the default).

**Files:**
- Modify: `static/index.html` — lines 12–32 (the `<script>` containing `tailwind.config = {...}`).

- [ ] **Step 1: Delete the entire `tailwind.config` script**

Current lines 12–32:
```html
  <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: { mono: ['"IBM Plex Mono"', 'monospace'] },
          colors: {
            bg:      '#070a0e',
            surface: '#0d1117',
            border:  '#21262d',
            accent:  '#3fb950',
            dim:     '#6e7681',
            'sev-c': '#ff7b72',
            'sev-h': '#ffa657',
            'sev-m': '#e3b341',
            'sev-ok':'#3fb950',
            'sev-mon':'#79c0ff',
          }
        }
      }
    }
  </script>
```

Delete all 21 lines (lines 12–32 inclusive). The Tailwind CDN `<script>` on line 9 stays — standard utilities (`hidden`, flex utilities) still used in tab content.

Exact Edit call:

```
Edit static/index.html
old_string:   <script>
    tailwind.config = {
      theme: {
        extend: {
          fontFamily: { mono: ['"IBM Plex Mono"', 'monospace'] },
          colors: {
            bg:      '#070a0e',
            surface: '#0d1117',
            border:  '#21262d',
            accent:  '#3fb950',
            dim:     '#6e7681',
            'sev-c': '#ff7b72',
            'sev-h': '#ffa657',
            'sev-m': '#e3b341',
            'sev-ok':'#3fb950',
            'sev-mon':'#79c0ff',
          }
        }
      }
    }
  </script>
new_string:
```

Result: the 21-line block is gone; Tailwind CDN loads with its default theme.

- [ ] **Step 2: Search for any remaining references to the removed classes**

```bash
grep -n "bg-sev-\|text-sev-\|border-sev-\|bg-accent\|text-accent\|border-accent" static/index.html
```

If results appear: those are Tailwind utility usages that relied on the deleted custom colors and would now render as Tailwind defaults (gray) or not render at all. **If any hits appear, halt the task and report the line numbers** — a follow-up edit is needed to convert those to design-system classes or keep them via CSS overrides. If zero hits, proceed.

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "design(chrome): remove Tailwind parallel severity scale"
```

---

## Task 5: Class-swap chrome markup

Walk the five chrome elements — top header, register bar, register drawer, progress bar, plus the hidden `#tab-overview`-adjacent container — and replace inline `style=""` attributes with semantic class names. Preserve every `id` and every `onclick`.

**Files:**
- Modify: `static/index.html` — lines 984–1044 (chrome markup).

### 5a. Top header — `#app-header`

- [ ] **Step 1: Replace the header markup**

Current (lines 985–1012):
```html
<header id="app-header">
  <div style="display:flex;align-items:center;gap:0">
    <span style="color:#3fb950;font-size:11px;letter-spacing:0.05em;margin-right:20px">// CRQ ANALYST</span>
    <nav style="display:flex;height:36px">
      <div class="nav-tab active" id="nav-overview" onclick="switchTab('overview')">Overview</div>
      <div class="nav-tab" id="nav-reports"  onclick="switchTab('reports')">Reports</div>
      <div class="nav-tab" id="nav-trends"   onclick="switchTab('trends')">Trends</div>
      <div class="nav-tab" id="nav-history"  onclick="switchTab('history')">History</div>
      <div class="nav-tab" id="nav-validate" onclick="switchTab('validate')">Risk Register</div>
      <div class="nav-tab" id="nav-sources"  onclick="switchTab('sources')">Source Library</div>
      <div class="nav-tab" id="nav-pipeline" onclick="switchTab('pipeline')">Pipeline</div>
      <div class="nav-tab" id="nav-runlog" onclick="switchTab('runlog')">Run Log</div>
    </nav>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <button id="nav-config" onclick="switchTab('config')" title="Config"
      style="background:none;border:none;cursor:pointer;padding:4px 6px;border-radius:3px;
             font-size:15px;color:#6e7681;transition:color 0.15s;line-height:1"
      onmouseover="this.style.color='#e6edf3'" onmouseout="this.style.color='#6e7681'">⚙</button>
    <select id="window-select">
      <option value="1d">Last 24h</option>
      <option value="7d" selected>Last 7 days</option>
      <option value="30d">Last 30 days</option>
      <option value="90d">Last quarter</option>
    </select>
    <button id="btn-run-all" onclick="runAll()">&#9654; RUN ALL</button>
  </div>
</header>
```

New (preserves every id and onclick; adds semantic classes; demotes dev tabs via `.nav-tab-dev`):
```html
<header id="app-header">
  <div>
    <span class="brand-mark">// CRQ ANALYST</span>
    <nav>
      <div class="nav-tab active" id="nav-overview" onclick="switchTab('overview')">Overview</div>
      <div class="nav-tab" id="nav-reports"  onclick="switchTab('reports')">Reports</div>
      <div class="nav-tab" id="nav-trends"   onclick="switchTab('trends')">Trends</div>
      <div class="nav-tab" id="nav-history"  onclick="switchTab('history')">History</div>
      <div class="nav-tab" id="nav-validate" onclick="switchTab('validate')">Risk Register</div>
      <div class="nav-tab" id="nav-sources"  onclick="switchTab('sources')">Source Library</div>
      <div class="nav-sep" aria-hidden="true"></div>
      <div class="nav-tab nav-tab-dev" id="nav-pipeline" onclick="switchTab('pipeline')">Pipeline</div>
      <div class="nav-tab nav-tab-dev" id="nav-runlog" onclick="switchTab('runlog')">Run Log</div>
    </nav>
  </div>
  <div class="header-actions">
    <button id="nav-config" onclick="switchTab('config')" title="Config" class="btn-icon">⚙</button>
    <select id="window-select">
      <option value="1d">Last 24h</option>
      <option value="7d" selected>Last 7 days</option>
      <option value="30d">Last 30 days</option>
      <option value="90d">Last quarter</option>
    </select>
    <button id="btn-run-all" onclick="runAll()">&#9654; RUN ALL</button>
  </div>
</header>
```

Changes:
- Outer left `<div>` loses inline flex styles (handled by `#app-header > div` rule in `app.css`).
- Brand `<span>` becomes `.brand-mark`.
- `<nav>` loses inline flex+height (handled by `#app-header nav` rule).
- Dev tabs (Pipeline, Run Log) get the additional `.nav-tab-dev` class to visually recede. A `.nav-sep` divider is inserted before them to mark the group boundary.
- Right `<div>` becomes `.header-actions`.
- `#nav-config` gear button loses inline style + `onmouseover/onmouseout` handlers (handled by `#nav-config:hover` rule). Adds `.btn-icon` class.
- `#window-select` keeps its ID; `#window-select` selector in `app.css` styles it directly.
- `#btn-run-all` keeps its ID; `#btn-run-all` selector in `app.css` styles it directly.

### 5b. Register bar — `#register-bar`

- [ ] **Step 2: Replace the register bar markup**

Current (lines 1015–1024):
```html
<div id="register-bar">
  <span style="color:#6e7681">▣</span>
  <span style="color:#6e7681">Active:</span>
  <span id="register-bar-name" style="color:#c9d1d9;font-weight:600">—</span>
  <span style="color:#21262d">·</span>
  <span id="register-bar-count" style="color:#484f58">— scenarios</span>
  <span style="color:#21262d">·</span>
  <span id="register-bar-toggle" onclick="toggleRegisterDrawer()"
    style="color:#6e7681;cursor:pointer;letter-spacing:0.04em">Switch ▾</span>
</div>
```

New:
```html
<div id="register-bar">
  <span class="reg-icon">▣</span>
  <span class="reg-label">Active:</span>
  <span id="register-bar-name">—</span>
  <span class="reg-sep">·</span>
  <span id="register-bar-count">— scenarios</span>
  <span class="reg-sep">·</span>
  <span id="register-bar-toggle" onclick="toggleRegisterDrawer()">Switch ▾</span>
</div>
```

Changes:
- `style=""` removed from every span.
- Classes: `.reg-icon`, `.reg-label`, `.reg-sep` match selectors in `app.css`.
- `#register-bar-name`, `#register-bar-count`, `#register-bar-toggle` IDs preserved — `app.css` styles them directly.
- `onclick="toggleRegisterDrawer()"` preserved verbatim.

### 5c. Register drawer — `#register-drawer`

- [ ] **Step 3: Replace the drawer markup**

Current (lines 1027–1034):
```html
<div id="register-drawer">
  <div style="padding:8px 12px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #21262d">
    <span style="font-size:10px;font-weight:600;color:#8b949e;letter-spacing:0.05em">RISK REGISTERS</span>
    <button onclick="showRegisterForm()" style="background:#238636;color:#fff;border:none;border-radius:3px;padding:3px 8px;font-size:10px;cursor:pointer">+ New</button>
  </div>
  <div id="register-list" style="max-height:240px;overflow-y:auto"></div>
  <div id="register-form-panel" style="display:none;border-top:1px solid #21262d;padding:12px"></div>
</div>
```

New:
```html
<div id="register-drawer">
  <div class="drawer-head">
    <span class="drawer-title">Risk Registers</span>
    <button onclick="showRegisterForm()" class="btn btn-secondary btn-sm">+ New</button>
  </div>
  <div id="register-list"></div>
  <div id="register-form-panel"></div>
</div>
```

Changes:
- Header `<div>` gets `.drawer-head` class; inline flex/padding/border gone.
- Title `<span>` gets `.drawer-title`; inline uppercase/size gone. Case changes from "RISK REGISTERS" → "Risk Registers" since `.drawer-title` rule applies `text-transform: uppercase`.
- "+ New" button gets `.btn .btn-secondary .btn-sm` (design-system button classes); inline green gone.
- `#register-list` keeps ID; `max-height` + overflow handled by `app.css` `#register-list` rule.
- `#register-form-panel` keeps ID; `display:none` handled by `app.css` (`#register-form-panel` default, `.open` override). Note: if existing JS on `showRegisterForm()` does `document.getElementById('register-form-panel').style.display = 'block'`, it still works — inline style beats class. If JS instead toggles a class, update accordingly. **Check `app.js` before editing** (read-only, no changes): grep for `register-form-panel`.

Sub-step 3a: confirm JS toggle behavior before editing.

```bash
grep -n "register-form-panel" static/app.js
```

If JS uses `style.display`, the existing behavior still works. If JS toggles `.open`, the existing class rule still works. If it uses `.hidden` class (Tailwind), it still works. Record what it does and report back — do not modify `app.js` regardless.

### 5d. Progress bar — `#progress-bar-container`

- [ ] **Step 4: Replace the progress bar markup**

Current (lines 1037–1044):
```html
<div id="progress-bar-container" class="hidden" style="padding:4px 16px">
  <div style="display:flex;align-items:center;gap:10px">
    <span id="progress-label" style="font-size:10px;color:#6e7681;white-space:nowrap">Initializing...</span>
    <div style="flex:1;background:#21262d;border-radius:2px;height:2px;overflow:hidden">
      <div id="progress-fill" style="width:0%"></div>
    </div>
  </div>
</div>
```

New:
```html
<div id="progress-bar-container" class="hidden">
  <div>
    <span id="progress-label">Initializing...</span>
    <div class="progress-track">
      <div id="progress-fill" style="width:0%"></div>
    </div>
  </div>
</div>
```

Changes:
- Outer `#progress-bar-container` loses inline padding (handled by `#progress-bar-container` rule in `app.css`). Keeps `.hidden` Tailwind utility.
- Inner `<div>` loses inline flex (handled by `#progress-bar-container > div` rule).
- `#progress-label` loses inline typography (handled by `#progress-label` rule).
- Track `<div>` becomes `.progress-track` (matches `app.css`).
- `#progress-fill` keeps its ID + its inline `style="width:0%"` — that's required because `app.js` sets this width live during runs. The ID-level `app.css` rule handles color, height, radius, transition; the inline width is the live state.

### 5e. Run all chrome replacements in a single Edit call

- [ ] **Step 5: Apply all four markup replacements**

Execute the four Edit operations (5a, 5b, 5c, 5d) in order. After each, re-read the file offset to confirm no syntax error.

- [ ] **Step 6: Smoke-check the HTML**

```bash
python -c "import html.parser; p = html.parser.HTMLParser(); p.feed(open('static/index.html').read()); print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add static/index.html
git commit -m "design(chrome): class-swap header, register bar, drawer, progress bar"
```

---

## Task 6: Manual verification

Confirm the retrofit renders correctly and no functionality regresses. No automation in this plan — Playwright fidelity test is deferred.

- [ ] **Step 1: Start the dev server**

```bash
uv run python server.py &
```

Wait until `http://localhost:8001/` responds 200:

```bash
for i in {1..8}; do code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/ --max-time 2); if [ "$code" = "200" ]; then break; fi; sleep 1; done; echo "status=$code"
```

- [ ] **Step 2: Ask the user to open the app and inspect**

Present this checklist:

1. **Header chrome** — 36px dark bar with "// CRQ ANALYST" in cyan on the left, 8 tabs (Overview, Reports, Trends, History, Risk Register, Source Library, separator, Pipeline, Run Log) followed by gear + time-window + RUN ALL on the right.
2. **Dev tabs recede** — Pipeline and Run Log should look dimmer / smaller-weight than Overview–Source Library.
3. **Register bar** — single row below header with "▣  Active:  —  ·  — scenarios  ·  Switch ▾". Uppercase, small text, muted colors.
4. **Click Switch ▾** — drawer opens below with "Risk Registers" title + "+ New" button that looks like a secondary button (not bespoke green).
5. **Click each tab** — content renders without layout breakage. Tab internals may look stylistically unchanged; that's expected (per-tab redesign is separate).
6. **Open the browser console** — no new errors from missing CSS files, missing Tailwind classes, or JS exceptions.

- [ ] **Step 3: Stop the server**

Use `TaskStop` on the background shell ID.

- [ ] **Step 4: No commit here** — manual verification produces no artifacts.

---

## Task 7: Update the spec's implementation section with the actual diff and follow-ups

- [ ] **Step 1: Append a "Shipped" section to `docs/superpowers/specs/2026-04-21-claude-design-chrome-session-design.md`**

Add at the bottom of the file:

```markdown
## Shipped

Implementation landed on 2026-04-21 via plan `docs/superpowers/plans/2026-04-21-chrome-retrofit.md`. Commits:

- `<commit-sha>` — lift `app.css` into `static/design/styles/`
- `<commit-sha>` — link web design system stylesheets
- `<commit-sha>` — remove universal Mono + body baseline overrides
- `<commit-sha>` — remove Tailwind parallel severity scale
- `<commit-sha>` — class-swap header, register bar, drawer, progress bar

**Deferred to follow-up specs:**
- Per-tab content class-swaps (scope of the Session 2+ per-tab redesign program).
- Playwright screenshot fidelity regression test.
- Removal of the Tailwind CDN entirely — still needed for tab-content `.hidden` and a handful of utilities.
```

Fill in the actual commit SHAs after each task's commit lands.

- [ ] **Step 2: Commit the spec update**

```bash
git add docs/superpowers/specs/2026-04-21-claude-design-chrome-session-design.md
git commit -m "docs(specs): mark chrome retrofit shipped + note deferrals"
```

---

## Self-review checklist

**Spec coverage:**
- [x] "Copy `app.css` into `static/design/styles/`" — Task 1.
- [x] "Replace `static/index.html`'s inline Tailwind config + `<style>` block with `<link>` references" — partially: Tasks 2, 3, 4. Kept tab-internal `<style>` rules (per "do not touch tab internals" scope).
- [x] "Walk chrome DOM and swap inline `style=""` attributes for semantic class names" — Task 5.
- [x] "Preserve every ID and every `onclick` binding" — Task 5 calls this out per sub-task.
- [x] "Decide per-tab fate of the Tailwind CDN script — open question flagged for the implementation plan" — resolved: keep CDN, remove only `tailwind.config`.
- [x] "Add a Playwright fidelity test" — explicitly deferred to a follow-up, documented in Task 7.

**Placeholder scan:**
- No "TBD", "TODO", or "similar to above" placeholders. Every edit step shows exact before/after.

**Ambiguity:**
- Task 5c flags one JS-behavior check (`showRegisterForm` / `register-form-panel`) that requires confirmation before editing, not a blocking ambiguity.

**Risks:**
- Tailwind CDN still loads; Tailwind's default config may introduce unexpected styling in the chrome if any element used `bg-bg`, `text-accent`, etc. that depended on the removed custom colors. Task 4 Step 2 grep catches this.
- `#register-form-panel` behavior under `.open` class vs inline `display:block` — Task 5c Step 3a confirms before editing.
- Font-family cascade: removing `* { Mono }` means any tab-internal element that relied on inheriting Mono without explicitly setting it will now inherit Sans. Per scoped review: monospace-critical tab content already sets `font-family` explicitly.

---

## Success criteria

- `static/design/styles/app.css` is byte-equivalent to `docs/design/handoff/styles/app.css`.
- `static/index.html` links `tokens.css` + `app.css` and no longer declares the parallel severity scale.
- Chrome (header, register bar, drawer, progress bar) renders with the new design system when the app is opened at `http://localhost:8001`.
- All tabs click through without JS errors and without layout collapse.
- `app.js` is untouched: `git diff --stat static/app.js` shows zero changes.
- No inline hex color values remain in chrome markup (lines 984–1044 of `static/index.html`).
