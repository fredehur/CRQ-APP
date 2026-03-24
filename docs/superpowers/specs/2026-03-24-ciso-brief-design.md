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
- Not financial — VaCR numbers do NOT appear in the brief

**What it is:**
- Business language throughout
- Operational consequence framing ("what stops working" not "what is the dollar exposure")
- Clear enough that a non-technical executive understands the risk posture in one read

---

## 3. Content Model — No New Agent Output

The existing three-pillar content (`## Why / ## How / ## So What`) already written by `regional-analyst-agent` is the source for all CISO brief content. **No new agent step, no new section in `report.md`.**

`report_builder.py` already parses these pillars into `why_text`, `how_text`, `so_what_text` on `RegionEntry`. A new `_extract_brief_sentences()` helper will derive four display fields from these:

| Display field | Source |
|---|---|
| **Driver** | First sentence of `why_text` |
| **Exposure** | First sentence of `how_text` |
| **Impact** | First non-VaCR sentence of `so_what_text` (skip sentences containing `$`) |
| **Watch** | Last sentence of `so_what_text` |

### One small agent change required

The current `## So What` paragraph leads with the VaCR figure. For the extraction above to work cleanly, the agent should open So What with the **operational consequence**, not the dollar exposure. VaCR may appear later in the paragraph if needed for analyst context — but it must not be the opening sentence.

This is a one-line addition to the regional-analyst-agent quality checklist:
> `- [ ] So What opens with operational consequence, not the VaCR figure`

### Fallback

If any pillar text is absent (CLEAR regions, parse failure), `board_bullets` is `None` and that region gets no dedicated page.

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

**Style:** Clean Executive — white page, 3px navy top stripe, severity chip top-right.

**Layout:** Two-column 2×2 grid. Each of the four extracted sentences occupies one cell with a colored left border.

```
┌─────────────────────────────────────────────────────┐
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 3px navy stripe ▓▓▓▓▓▓▓▓▓▓▓ │
│                                                     │
│  AME — North America                  [CRITICAL]    │
│  Ransomware · Event · Confidence: High              │
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
│  Trend: → Stable    Financially motivated threat    │
└─────────────────────────────────────────────────────┘
```

**Severity chip colors:**
- CRITICAL → red background (`#fee2e2` / `#991b1b` text)
- HIGH → orange background (`#ffedd5` / `#9a3412` text)
- MEDIUM → yellow background (`#fef9c3` / `#854d0e` text)

**Left border colors per cell:**
- Driver → navy (`#1e3a5f`)
- Exposure → navy (`#1e3a5f`)
- Impact → red (`#dc2626`)
- Watch → amber (`#d97706`)

**Sub-header line** (`Scenario · Signal type · Confidence: {label}`):
Admiralty code is not shown. Map code to plain-language confidence label:

| Admiralty code | Confidence label |
|---|---|
| A, B | High |
| C | Medium |
| D, E, F | Low |

**Footer** (two fields, small grey text):
- `Trend: {velocity symbol} {velocity}` — e.g. "Trend: → Stable"
- Threat characterisation — human-readable label derived from `dominant_pillar` + `primary_scenario`:

| dominant_pillar | Characterisation |
|---|---|
| Cyber | Financially motivated threat |
| Geopolitical | State-directed threat |
| Mixed | Mixed-motive threat |

The footer communicates *what kind of threat this is*, not internal data model labels.

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
| Status strip counts | Derived by `report_builder.py` from all five `data.json` files (existing pattern) |
| Compound risk bullets | `global_report.json → executive_summary` (split into 3–4 sentences) |
| Region table | `global_report.json → regional_threats[]` |
| Driver sentence | First sentence of `RegionEntry.why_text` |
| Exposure sentence | First sentence of `RegionEntry.how_text` |
| Impact sentence | First non-VaCR sentence of `RegionEntry.so_what_text` |
| Watch sentence | Last sentence of `RegionEntry.so_what_text` |
| Severity chip | `data.json → severity` |
| Velocity | `data.json → velocity` |
| Confidence label | `data.json → admiralty` mapped via confidence table (Section 5) |
| Threat characterisation | `data.json → dominant_pillar` mapped via characterisation table (Section 5) |
| Signal type | `data.json → signal_type` |

**VaCR is explicitly excluded from all rendered outputs** — cover page, exec summary status strip, region table, region pages, and appendix. The `vacr` and `total_vacr` fields remain on `ReportData` and `RegionEntry` for the analyst web app but must not be referenced in the CISO renderer paths.

---

## 8. Implementation Touchpoints (for future build)

1. **`.claude/agents/regional-analyst-agent.md`** — add one quality check line: So What must open with operational consequence, not the VaCR figure.
2. **`tools/report_builder.py`** — add `_extract_brief_sentences()` helper that derives Driver / Exposure / Impact / Watch from existing `why_text`, `how_text`, `so_what_text`; add `board_bullets: list[str] | None` to `RegionEntry`.
3. **`tools/templates/report.html.j2`** — full redesign: Clean Executive style, 2×2 region layout. Remove VaCR from cover (`cover-vacr`), exec summary status strip, region table (drop VaCR column), and region sidebar.
4. **`tools/export_pptx.py`** — full redesign: cover slide (remove VaCR figure), exec summary slide (remove VaCR badge and VaCR column), region slides (severity chip, 4-cell 2×2 grid, no VaCR). All three slide types need updating.
5. **Voice summary** — future phase; reads `executive_summary` + the four extracted sentences per region.

---

*This spec is approved design guidance. No implementation action until a separate build session is started.*
