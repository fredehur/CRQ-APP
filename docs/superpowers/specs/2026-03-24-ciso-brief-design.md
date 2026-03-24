# CISO Brief — Design Spec
**Date:** 2026-03-24
**Status:** Approved — guidance for future implementation
**Scope:** Board-level output redesign. RSM briefs are out of scope (already built).

---

## 1. Output Stack

The pipeline produces audience-specific outputs from one shared data layer. The web app is for analysts only — it is never handed to stakeholders.

| Audience | Outputs | Status |
|---|---|---|
| CISO / Exec | PDF · PPTX · AI voice summary | **To build** |
| Analyst / CISO | Web app | Existing |
| RSM | Weekly INTSUM + flash alerts | Already built — do not modify |
| Sales | TBD future phase | Parked |

All board-format outputs (PDF, PPTX, voice) render from the same structured data. Adding a new audience means adding a new renderer — the pipeline and data model do not change.

---

## 2. Purpose of the CISO Brief

This is not a board report. It is a **CISO brief** — a polished intelligence document that gives the CISO a clear, defensible picture of AeroGrid's risk posture so they can walk into any executive or board conversation and explain it in plain business terms.

**What it is not:**
- Not for the actual board (yet) — that is a future phase
- Not a security report — no technical jargon, no SOC language
- Not financial — VaCR numbers do NOT appear in the brief (they are internal scaffolding for agent prioritization only)

**What it is:**
- Business language throughout
- Operational consequence framing ("what stops working" not "what is the dollar exposure")
- Clear enough that a non-technical executive understands the risk posture in one read

---

## 3. Content Model — Board Brief Section

Each escalated region's `report.md` gets a new `## Board Brief` section written by the regional analyst agent. This section is what the board-format renderers (PDF, PPTX, voice) read. The existing `## Why / ## How / ## So What` pillars remain intact for the analyst/web app audience.

### Format

```markdown
## Board Brief

- **Driver:** One sentence — what structural or geopolitical force created this risk
- **Exposure:** One sentence — which AeroGrid operations or assets are in the threat's path
- **Impact:** One sentence — what stops working if this materializes (operational terms, no dollar figures)
- **Watch:** One sentence — forward indicator: what signal tells you this is getting worse
```

### Rules for the agent writing this section

- No VaCR figures, no dollar amounts
- No technical jargon (no CVEs, no malware names, no attack mechanics)
- No SOC language (no TTPs, no IoCs, no MITRE references)
- Impact must describe an operational consequence a non-technical executive can picture
- Watch must be concrete and observable — not a vague "monitor the situation"
- Each bullet: one sentence, no more

### Fallback

`report_builder.py` owns the fallback — not the renderer. If `## Board Brief` is absent in a `report.md` (old runs, pre-spec regions), `_parse_board_brief()` extracts the first sentence of each of the three existing pillars (`## Why`, `## How`, `## So What`) and maps them to Driver, Exposure, and Impact respectively. Watch is omitted when falling back. CLEAR regions get no dedicated page and `board_bullets` is `None`.

---

## 4. Document Structure

Five logical sections, rendered as pages in the PDF:

### 4.1 Cover
- Company name
- "Cyber Risk Intelligence Brief — CISO Edition"
- Date · Classification · Run ID

### 4.2 Global Posture (exec summary)
- Status strip: `3 ESCALATED · 0 MONITOR · 2 CLEAR`
- 3–4 bullets from `global_report.json → executive_summary` (compound risk story)
- Region table: Region | Scenario | Severity | Velocity — **no VaCR column**

### 4.3 Escalated Region Pages (one page per escalated region)
See Section 5 for layout detail.

### 4.4 Appendix
- Monitor regions (one line each, if any)
- Clear regions (one line each): "No active threat this cycle"
- Run metadata: pipeline ID, generated timestamp, data classification

---

## 5. Region Page Layout

**Style:** Clean Executive — white page, 3px navy top stripe, colored severity chip top-right.

**Layout:** Two-column 2×2 grid. Each of the four Board Brief bullets occupies one cell with a colored left border.

```
┌─────────────────────────────────────────────────────┐
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 3px navy stripe ▓▓▓▓▓▓▓▓▓▓▓ │
│                                                     │
│  AME — North America                  [CRITICAL]    │
│  Ransomware · Event · B2 Corroborated               │
│                                                     │
│  ┌── Driver ────────┐  ┌── Exposure ─────────────┐  │
│  │ navy left border │  │ navy left border        │  │
│  │ one sentence     │  │ one sentence            │  │
│  └──────────────────┘  └─────────────────────────┘  │
│                                                     │
│  ┌── Impact ────────┐  ┌── Watch ────────────────┐  │
│  │ red left border  │  │ amber left border       │  │
│  │ one sentence     │  │ one sentence            │  │
│  └──────────────────┘  └─────────────────────────┘  │
│                                                     │
│  Velocity: → Stable    Pillar: Cyber                │
└─────────────────────────────────────────────────────┘
```

**Severity chip colors:**
- CRITICAL → red background (`#fee2e2` / `#991b1b` text)
- HIGH → orange background (`#ffedd5` / `#9a3412` text)
- MEDIUM → yellow background (`#fef9c3` / `#854d0e` text)

**Left border colors per bullet:**
- Driver → navy (`#1e3a5f`)
- Exposure → navy (`#1e3a5f`)
- Impact → red (`#dc2626`)
- Watch → amber (`#d97706`)

**Footer:** Velocity + Dominant Pillar, small grey text, separated by thin top border.

---

## 6. Visual Style — Clean Executive

- **Background:** White (`#ffffff`)
- **Accent stripe:** 3px solid navy (`#1e3a5f`) at the top of each page
- **Body font:** `system-ui, -apple-system, Segoe UI, sans-serif`
- **Headings:** 16px bold, `#111`
- **Body text:** 10px, `#333`, line-height 1.6
- **Labels:** 8px, uppercase, letter-spacing 1.5px, navy (`#1e3a5f`)
- **Dividers:** `#f0f0f0`, 1px
- **Prints well:** no heavy backgrounds on body pages — ink-friendly

---

## 7. Data Sources (renderer reads from)

| Field | Source |
|---|---|
| Status strip counts | Derived by `report_builder.py` from all five `data.json` files (existing pattern — do not read from `global_report.json`) |
| Compound risk bullets | `global_report.json → executive_summary` (split on ` — ` or sentence boundary into 3–4 bullets) |
| Region table | `global_report.json → regional_threats[]` |
| Board Brief bullets | `report.md → ## Board Brief` section (parsed by `report_builder.py → _parse_board_brief()`) |
| Severity chip | `data.json → severity` |
| Velocity | `data.json → velocity` |
| Dominant pillar | `data.json → dominant_pillar` |
| Admiralty (display string) | `data.json → admiralty` — expanded using the Admiralty Scale map below |
| Signal type | `data.json → signal_type` |

**Admiralty Scale expansion map** (for the region page sub-header display string):

| Code | Display |
|---|---|
| A1 | Reliable — Confirmed |
| A2 | Reliable — Probably true |
| B1 | Corroborated — Confirmed |
| B2 | Corroborated — Probably true |
| B3 | Corroborated — Possibly true |
| C2 | Fairly reliable — Probably true |
| C3 | Fairly reliable — Possibly true |
| D3 | Not always reliable — Possibly true |
| E3 | Unreliable — Possibly true |
| F6 | Cannot be judged — Truth unknown |

Display as `{code} {label}` in the region page sub-header (e.g. B2 → "B2 Corroborated"), consistent with the layout diagram in Section 5.

**VaCR is explicitly excluded from all rendered outputs** — cover page, exec summary status strip, region table, region pages, and appendix. The `vacr` and `total_vacr` fields remain in `ReportData` and `RegionEntry` for the analyst web app but must not be referenced in the CISO renderer paths (template and PPTX).

---

## 8. Implementation Touchpoints (for future build)

1. **`.claude/agents/regional-analyst-agent.md`** — add a Step for writing `## Board Brief` section with the 4-bullet format and rules (Section 3)
2. **`tools/report_builder.py`** — add `_parse_board_brief()` with fallback logic (Section 3 Fallback); add `board_bullets: list[str] | None` to `RegionEntry`. Do not remove `vacr` / `total_vacr` — they serve the analyst web app.
3. **`tools/templates/report.html.j2`** — full redesign: Clean Executive style, 2×2 region layout. Remove VaCR from: cover page (`cover-vacr`), exec summary status strip, region table (drop VaCR column), and region sidebar.
4. **`tools/export_pptx.py`** — full redesign: cover slide (remove "TOTAL VALUE AT CYBER RISK" and VaCR figure), exec summary slide (remove VaCR badge and VaCR column from table), region slides (severity chip, 4-bullet 2×2 grid, no VaCR sidebar). All three slide types need updating.
5. **Voice summary** — future phase; reads `executive_summary` + Board Brief bullets

---

*This spec is approved design guidance. No implementation action until a separate build session is started.*
