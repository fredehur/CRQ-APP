# Session E: Visual Alignment — Overview + Reports

**Goal:** Make the Overview and Reports tabs look like one product. Same card structure, same colour system, same typography, same component patterns. Two different audiences (analyst vs. stakeholder), one visual language.

**Why:** Currently they look like two different apps built by two different teams. The Overview uses one card style, one colour scheme, one layout grid. Reports uses a different card grid with different spacing. This session creates a shared design system and applies it to both tabs.

**Scope boundary:** HTML + CSS + JS only. Do NOT change any Python tools, agents, or data schemas. Do NOT change what data each tab displays — only how it's rendered.

**Depends on:** Session D (pipeline review) should complete first — the review may reveal content changes that affect what the tabs need to render. Visual alignment without content alignment is paint on a moving wall.

---

## Files in scope

```
static/index.html    — HTML structure for all tabs
static/app.js        — rendering functions for Overview + Reports
```

## Files NOT in scope

```
server.py            → API unchanged
tools/               → no Python changes
.claude/agents/      → no agent changes
output/              → no data changes
```

---

## Steps

1. Audit current Overview and Reports tab visually — screenshot both, annotate differences in card structure, typography, colour, spacing
2. Define shared component patterns:
   - Region card (used in Overview region list AND Reports regional detail)
   - Status badge (ESCALATED/MONITOR/CLEAR — used in both tabs)
   - Section panel (used for brief sections in Overview AND report preview in Reports)
   - Source/metadata label (Seerist strength badge, OSINT source count — could appear in both)
3. Extract shared CSS classes — move from inline/duplicated styles to reusable component classes
4. Apply to Overview tab
5. Apply to Reports tab
6. Add the source split boxes from the source-split plan (Task 3 of `2026-04-10-overview-source-split-brief-structure.md`)
7. Verify visually — both tabs side by side, same product feel
8. Commit

**Success criteria:** Both tabs feel like one product. Shared components render identically in both contexts. No functional regressions.
