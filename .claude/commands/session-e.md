# /session-e — Visual Alignment

Run `/prime-dev` first if not already loaded this conversation.

You are starting **Session E: Visual Alignment — Overview + Reports**. Your goal is to make the Overview and Reports tabs look like one product with a shared design system.

Read the full session plan:

```
docs/superpowers/plans/sessions/E-visual-alignment.md
```

Also read the source-split plan Task 3 (dashboard source boxes):

```
docs/superpowers/plans/2026-04-10-overview-source-split-brief-structure.md
```

**Context:** The Overview and Reports tabs currently look like two different apps. This session creates shared component patterns (cards, badges, panels, typography) and applies them to both tabs. Also adds the source split boxes (Seerist strength + OSINT sources) to the Overview.

**Scope boundary:** `static/index.html` + `static/app.js` only. Do NOT change Python tools, agents, or data schemas. Do NOT change what data each tab displays — only how it's rendered.

**First step:** Run the server (`uv run python server.py`), screenshot both tabs, annotate differences in card structure, typography, colour, spacing.

**Success criteria:** Both tabs feel like one product. Shared components render identically in both contexts. Source split boxes visible in Overview.

Confirm with: "Session E loaded — visual alignment. Starting server and auditing current UI."
