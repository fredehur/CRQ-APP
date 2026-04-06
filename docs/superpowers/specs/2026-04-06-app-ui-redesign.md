# App UI Redesign — Design Spec
**Date:** 2026-04-06
**Status:** Approved for implementation planning
**Scope:** Navigation, Overview tab, Reports tab (Audience Hub)
**Deferred:** Trends tab, History tab (separate brainstorm session)

---

## 1. Navigation & Information Architecture

### Problem
Eight tabs in a flat nav bar with no logical grouping. Consume-oriented tabs (intelligence output) sit next to operate-oriented tabs (pipeline management) at the same visual weight. The RSM tab creates a duplicate entry point that will compound as more audiences are added.

### Decision
**Flat tab bar with visual separator** — reorder tabs into two clusters, add a thin vertical separator between them. No mode switching, no icon rail. Minimal change, maximum clarity.

**Separator implementation:** A 1px `#21262d` `border-right` on the History tab element, plus 4px additional right-margin before the Config tab. No extra DOM elements needed.

```
Overview · Reports · Trends · History  ┆  Config · Validate · Sources
```

- Left cluster = **Intelligence** (consume/read)
- Right cluster = **Operations** (run/tune/audit)
- **RSM tab removed** — RSM content moves into the Reports Audience Hub

### Ordering rationale
- Overview first — primary landing view
- Reports second — most common follow-on action (download/send)
- Trends, History — secondary consumption
- Config, Validate, Sources — operational, accessed less frequently

---

## 2. Overview Tab

### 2a. Synthesis Bar
**Problem:** Long narrative paragraph, priority, velocity, status counts, and timestamp all crammed into a single horizontal strip at equal visual weight. Nothing signals where to look first.

**Decision:** Two-row structure.

**Row 1 (header):**
- Status badges: `4 ESCALATED` · `1 MONITOR` · `0 CLEAR` — use existing severity colours (`#ff7b72`, `#79c0ff`, `#3fb950`)
- Run metadata: timestamp + window (e.g. `Apr 6, 16:48 · 7d window`)

**Spatial relationship with split pane:** The synthesis bar is full-width (does not preserve the 280px left-column alignment from the current layout). The `gs-label` column is removed entirely. The split pane below starts at its own 280px / 1fr grid independently.

**Empty state:** When no run data exists, render a single-row message ("No run data — click Run All to start") instead of the two-row structure. Do not show zero-count badges before a run has completed.

**Row 2 (narrative):**
- Full-width narrative paragraph — room to breathe, no competing elements

Priority and velocity are **removed from the synthesis bar**. They are not in the primary information hierarchy (narrative, counts, metadata) and add visual noise. If needed, they belong in the analyst brief right panel, not the synthesis bar.

### 2b. Region List (left panel)
**Problem:** Each row shows region name + scenario text + velocity arrow + source counts. Too much noise — makes the list harder to scan, not easier.

**Decision:** Region name + status colour only.

- No scenario text
- No source counts
- No velocity arrow
- Status communicated through colour on the region name using existing severity palette: `#ff7b72` = escalated, `#79c0ff` = monitor (blue, not amber), `#3fb950` = clear
- No text badge — colour is sufficient
- **Active/selected state:** `background: #111820`, left border uses the region's own status colour (not always green). This avoids the conflict between a green active-border and a red escalated region name.

### 2c. Rate This Assessment Bar
**Problem:** Four stacked elements (label, rating pills, full-width textarea, submit button) take up significant vertical space at the bottom of the analyst brief panel.

**Decision:** Collapse to a single inline row.

- Rating pills inline (e.g. `Accurate` · `Incomplete` · `Off-target`)
- Clicking a pill saves the rating immediately — no separate submit button
- After a pill is clicked, a small inline text input appears in the same row for an optional note — it flex-grows to fill remaining row space with a max-width of 240px to prevent overflow on narrow panels
- If the user types a note and presses Enter (or clicks a tiny send icon), it patches the existing rating record with the note text — it does not create a second submission
- No "Rate this assessment" label needed — pills are self-explanatory

### 2d. Analyst Brief Panel (right panel)
No changes in this spec. Clearing noise around it will naturally give it more space. Revisit if needed post-implementation.

---

## 3. Reports Tab — Audience Hub

### Problem
- Hard-coded 2×2 card grid with no extensibility — adding a new audience requires new UI code
- RSM Briefs card in Reports duplicates the RSM tab
- Report preview (text dump below cards) is not useful
- Phase labels are pipeline-internal artefacts, not meaningful to users

### Decision: Config-driven Audience Hub

#### Audience Registry
Each audience is defined as a data object. The UI renders generically from this registry. Adding a new audience = new registry entry + new renderer function. Zero nav or structural changes.

```
{
  id:        string           // "ciso" | "board" | "rsm" | ...
  name:      string           // display name
  format:    string           // "Word (.docx)" | "PDF + PPTX" | ...
  phase:     "live" | "phase-2" | "future"
  generate:  endpoint | null  // POST to generate, or null if not applicable
  downloads: [{label, endpoint}]
  renderer:  string           // which detail view to render
}
```

**Phase controls card state:**
- `live` — full opacity, buttons active, card is clickable
- `phase-2` — reduced opacity, amber badge reading `"Coming soon"` or a specific reason (e.g. `"Requires Seerist integration"`), buttons disabled, card not clickable
- `future` — further reduced opacity, grey badge reading `"Planned"`, buttons disabled, card not clickable

Non-live cards show a tooltip on hover explaining why they are unavailable (e.g. "Available after Seerist API integration"). They must not be silently unclickable with no explanation.

#### Hub view (default)
Card grid using `grid-template-columns: repeat(auto-fill, minmax(260px, 1fr))` — scales automatically as audience count grows without manual layout changes. Each card: audience name, format, phase badge, generate + download buttons. Clicking a live card opens the detail view.

#### Detail view (generic shell)
Replaces the card grid when a card is clicked. **Transition:** 150ms `opacity` fade (`0 → 1`) on entry; same fade on return to hub via "← All reports". Structure:

```
← All reports  |  [Audience Name]  [format]      [Generate] [Download]
────────────────────────────────────────────────────────────────────────
[pluggable renderer content]
────────────────────────────────────────────────────────────────────────
Rate: [Accurate] [Incomplete] [Off-target]
```

**← All reports** navigates back to the hub.

#### Renderer shapes

**Single-doc renderer** (CISO, Board):
- Scrollable brief content rendered inline, structure determined by the audience renderer (not generic)
- CISO sections: Scenario · Threat Actor · Intel Findings · Adversary Activity · Impact · Watch For · Actions
- Board sections: to be defined when Board renderer is built
- Generate + download in shell header

**Region-list renderer** (RSM, and any future per-region audience):
- Left: narrow region list (APAC / AME / LATAM / MED / NCE), colour-coded by status
- Right: brief for selected region, scrollable
- Per-region generate + download buttons in the right pane header
- Rate bar scoped to selected region ("Rate APAC:") — `position: sticky; bottom: 0` with opaque background so it remains visible regardless of brief scroll depth
- "Generate all" in the shell header generates all 5 at once

#### RSM tab removal
The RSM tab in the nav is removed. All RSM content is accessible through `Reports → RSM Briefs card → RsmDetailView`. No functionality is lost.

#### Report preview removal
The existing "Report Preview" text section below the card grid in the current Reports tab is **removed**. It is replaced by the detail view pattern described above.

---

## 4. Deferred — Trends & History Tabs

Both tabs need redesign work but are out of scope for this spec. Flagged for a separate brainstorm session.

**Trends:** Longitudinal data visualisation, heatmap annotation (time-gated, 3+ runs). Current state is a placeholder.

**History:** Run history list. Current state functional but not reviewed for UX.

---

## 5. Implementation Notes

- `static/index.html` + `static/app.js` are the only frontend files — all changes land here
- The audience registry can live as a JS constant in `app.js` (no server-side config needed for now)
- The `RsmDetailView` renderer reuses the existing RSM tab render logic — move, don't rewrite
- The rate bar compact redesign affects `renderFeedbackSection()` in `app.js` and the `.feedback-*` CSS classes in `index.html`
- Synthesis bar changes affect `#global-synthesis` HTML and the `renderGlobalSynthesis()` JS function
- Region list changes affect `renderRegionList()` in `app.js`

---

## 6. Out of Scope

- Backend / API changes — all changes are frontend only
- New audiences beyond the registry structure — this spec establishes the pattern only
- Trends and History tab redesign (deferred)
- Any changes to the Config, Validate, or Source Audit tabs
