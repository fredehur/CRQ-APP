# Board Monthly Intelligence Report — Redesign Spec

**Goal:** Produce a top-notch monthly board intelligence brief as a `.pptx` — concise (4–6 slides), threat-centric, and optimised for read-ahead distribution to board members before a monthly meeting.

**Architecture:** Derived view of the CISO brief at higher altitude. Same coherence spine (`brief_headlines.why / how / so_what`) — different cadence (monthly vs. weekly), different depth (slides vs. pages), different register (strategic awareness vs. operational decision). The CISO brief is the reference implementation; the Board deck is the summary layer.

**Cadence:** Monthly. One deck per month, typically distributed 48–72 hours before the board meeting. The CISO weekly brief feeds into the monthly board deck — the board deck represents the month's dominant posture, not individual weekly events.

**Visual register:** A1 — Cormorant Garamond for display/titles, EB Garamond for body text, system monospace for labels and metadata. Black (`#111111`), white (`#fafaf9`), and grey (`#6b7280`, `#9ca3af`) only. No red, amber, green, or brand navy in body content. Reads like a premium intelligence publication, not a corporate PowerPoint.

**Slide count:** 4–6 slides. Cover (1) + Overview (1) + one slide per escalated threat group (0–3) + Watch List (0–1). Minimum deck if zero escalated: Cover + Overview only.

---

## Slide Structure

### Slide 1 — Cover

**Content:**
- Eyebrow: `AeroGrid Wind Solutions — Restricted`
- Title: `Global Risk Intelligence Brief` (large Cormorant Garamond, 3 lines)
- Thin rule
- Metadata line: `Board Read-Ahead · [Month Year] · Cycle [N]`
- Status counts at bottom (separated by thin rule): large Cormorant numerals for each status — Active Threats / Under Watch / No Active Threat

**Status label mapping:**
| Pipeline value | Board label |
|---|---|
| `ESCALATED` | Active Threats |
| `MONITOR` | Under Watch |
| `CLEAR` | No Active Threat |

**Pipeline source:** `RegionStatus` counts across all 5 regions. `data.run_id` for cycle number. `data.timestamp[:7]` for month/year.

---

### Slide 2 — Intelligence Overview

**Layout:** Split — left 28% / right 72%, separated by a thin vertical rule.

**Left column:** Three large Cormorant numerals stacked — escalated count (dark), monitor count (grey), clear count (light grey) — each with a small-caps monospace label below (Active Threats / Under Watch / No Active Threat).

**Right column:** Global framing paragraph. Drawn from `data.exec_summary`. If absent, auto-generated: *"This month, AeroGrid faces [N] active threat scenario[s] affecting [region names]. [Primary scenario]. [Monitor summary]. [Clear summary]."*

**Footer:** `Intelligence current as of [date] · CRQ Agentic Pipeline · Not for external distribution`

**Pipeline source:** `RegionStatus` counts + `data.exec_summary` + `data.timestamp`.

---

### Slide 3–N — Active Threat (one per scenario group)

**Condition:** One slide per unique `scenario_match` across escalated regions. Omit all threat slides if zero escalated. Ordered: highest escalated region count first; ties broken by Admiralty confidence.

**Header row:** Section label (`Active Threat`) + region pill badge(s) — black filled rectangle, white monospace text, uppercase region names (e.g. `APAC · MED`).

**Assertion title:** First sentence of `brief_headlines.why` for the representative region (highest-confidence region in the group). If empty: `scenario_match` value. Rendered in large Cormorant Garamond bold (approx. 2em), max 2 lines.

**Bullets (2–3):** Remaining sentences from `brief_headlines.why` split by `_split_why()`. Each rendered with an em-dash prefix. No Admiralty codes on slide face. Plain confidence language where confidence is expressed (e.g. *"assessed with high confidence based on multiple corroborated sources"*).

**AeroGrid Exposure block:** `brief_headlines.so_what` for representative region. Rendered with 2px left border stripe (black). Label: `AeroGrid Exposure` (monospace, 8pt, grey). If empty: fallback to `so_what_text`.

**Response note (footer):** One italic line auto-generated from first `action_bullets` entry for the group: *"Response: The CISO has initiated [first action] across affected sites."* If no action bullets: omit footer note.

**Speaker notes:** Full `brief_headlines.how` narrative + `intel_bullets` (up to 5) for all regions in the group. This is the evidentiary layer — available for read-ahead depth and live presentation.

**Render rules:**
- `brief_headlines.why` empty → fall back to `why_text`; if also empty → omit slide and log warning
- `brief_headlines.so_what` empty → fall back to `so_what_text`; if also empty → omit exposure block
- Source signal, Admiralty codes, dominant pillar labels → never rendered on slide face (speaker notes only)

---

### Slide N+1 — Under Watch

**Condition:** Rendered only if ≥1 MONITOR region exists. Omit entirely if zero.

**Section label:** `Under Watch`

**Entries:** One entry per MONITOR region, ordered alphabetically. Each entry:
- Region name in Cormorant Garamond bold (1.1em)
- First sentence of `brief_headlines.why`, or `why_text` first sentence if empty. Rendered in EB Garamond, grey.
- Thin rule below (except last entry)

**Footer:** *"These regions are under active intelligence monitoring. No board action required at this time."* (italic, EB Garamond, grey)

**Pipeline source:** `brief_headlines.why` from `sections.json` per region.

---

## Language Rules

These rules apply to all slide-face text. Speaker notes may use technical language.

| Forbidden | Use instead |
|---|---|
| Admiralty codes `[B2]`, `[C3]` | *"assessed with high confidence"* / *"medium confidence"* |
| `OT environments` | *"operational systems"* / *"turbine control systems"* |
| `TTPs`, `threat actor` | *"attack methods"* / *"criminal group"* / *"state-sponsored hacking group"* |
| `CYBER-LED`, `GEO-LED` | Omit entirely |
| `dominant_pillar` | Not rendered |
| `corroboration_tier`, `OSINT` | Not rendered |
| `scenario_match` raw value | Used only as fallback title if `brief_headlines.why` is empty |
| `ESCALATED`, `MONITOR`, `CLEAR` | Active Threat / Under Watch / No Active Threat |
| Region jargon (AME, NCE) | Keep region codes — board members know them |

**Confidence language mapping:**
| Admiralty | Plain language |
|---|---|
| A1–A2 | *"confirmed"* / *"verified"* |
| B1–B2 | *"assessed with high confidence based on multiple corroborated sources"* |
| C2–C3 | *"assessed with medium confidence"* |
| D–E | *"unconfirmed"* / *"low confidence"* |

---

## Data Mapping

| Slide element | Primary source | Fallback |
|---|---|---|
| Cover status counts | `RegionStatus` × 5 | — |
| Cover cycle | `data.run_id` | `"—"` |
| Cover month | `data.timestamp[:7]` | today |
| Overview counts | `RegionStatus` × 5 | — |
| Overview framing | `data.exec_summary` | Auto-generated from statuses |
| Threat title | `brief_headlines.why` first sentence | `scenario_match` |
| Threat bullets | `brief_headlines.why` sentences 2–3 | `why_text` split |
| Exposure block | `brief_headlines.so_what` | `so_what_text` |
| Response note | `action_bullets[0]` | Omit note |
| Speaker notes | `brief_headlines.how` + `intel_bullets` | `how_text` |
| Watch List entries | `brief_headlines.why` first sentence | `why_text` first sentence |

---

## Coherence with CISO Brief

| Field | CISO `.docx` (weekly) | Board `.pptx` (monthly) |
|---|---|---|
| `why` | Talking point bullets | Assertion title + bullet sentences |
| `how` | Situation section (inline) | Speaker notes only |
| `so_what` | Impact statement | AeroGrid Exposure block |

No field is computed differently — only presentation register differs. The CISO brief is the weekly depth layer; the Board deck is the monthly summary layer.

---

## Visual Specification

**Fonts:**
- Display / slide titles / region names: Cormorant Garamond 700 (python-pptx fallback: Book Antiqua Bold or Georgia Bold)
- Body text / bullets / exposure block: EB Garamond 400 (python-pptx fallback: Georgia)
- Labels / metadata / badges / footer: system monospace (python-pptx: Courier New 8pt or Calibri 8pt)

**Colours (body content):**
- Primary text: `#111111` (near-black)
- Secondary / grey text: `#374151`
- Metadata / labels: `#9ca3af`
- Background: `#fafaf9` (off-white — approximated as white in pptx)
- No red, amber, green, or brand navy in body content

**Layout constants (10×7.5in widescreen):**
- Slide margins: 0.8in left/right, 0.6in top/bottom
- Thin rules: 0.5pt, `#e5e7eb`
- Left border stripe (exposure block): 2pt, `#111111`
- Region pill: black filled rectangle, white monospace text, 7pt

**Slide 2 split:**
- Left column: 28% width (status counts)
- Divider: 0.5pt vertical rule at 28% + gap
- Right column: remaining width (framing paragraph)

---

## Implementation Scope

Changes to `tools/export_pptx.py`:

1. **Rewrite `build_cover()`** — A1 style: large Cormorant title, thin rule, meta line, status counts (plain language labels, large numerals) at bottom.
2. **Rewrite `build_exec_summary()`** → **`build_overview()`** — split layout: counts left, framing paragraph right, vertical rule divider. Wire `data.exec_summary` with auto-generated fallback.
3. **Rewrite `build_region()`** → **`build_threat_slide()`** — one slide per `scenario_match` group. Assertion title from `brief_headlines.why`. Bullets from `_split_why()`. Exposure block from `brief_headlines.so_what`. Response note from `action_bullets[0]`. Full `brief_headlines.how` in speaker notes.
4. **Rewrite `build_appendix()`** → **`build_watch_list()`** — MONITOR regions only. Omit slide if none. One entry per region: name + first sentence of `brief_headlines.why`.
5. **Add `_group_by_scenario(entries)`** — same logic as CISO: groups `RegionEntry` list by `scenario_match`, returns `list[tuple[str, list[RegionEntry]]]`.
6. **Add `_load_sections_pptx(region_name, output_dir)`** — reads `sections.json` for a region (same pattern as `_load_sections` in `export_ciso_docx.py`).
7. **Add `_load_brief_headlines_pptx(region_name, output_dir)`** — reads `brief_headlines` from `sections.json`.
8. **Add `_plain_confidence(admiralty)`** — maps Admiralty code to plain confidence phrase.
9. **Remove RED, AMBER, GREEN from body content rendering.** Status colours removed from all slide body elements. Cover status counts use greyscale weight only (dark/mid-grey/light-grey).
10. **Update `build_presentation()`** — new call order: `build_cover` → `build_overview` → `build_threat_slide` (per scenario group, escalated only) → `build_watch_list` (if MONITOR regions exist).
11. **Update `export()`** — ensure `output_dir` param threads through to all `_load_*` helpers.

**Out of scope:**
- VaCR figures
- Action Register slide
- References slide
- Daily event-based memo
- RSM format changes
- Board `.pptx` speaker-notes formatting beyond plain text

---

## Test Criteria

- `python -m tools.export_pptx` runs without error on current mock data
- Output `.pptx` opens cleanly in PowerPoint — no broken layouts
- Cover shows plain-language status labels (Active Threats / Under Watch / No Active Threat)
- Overview slide uses split layout — counts left, framing right
- Threat slides group regions sharing `scenario_match` into one slide
- Threat slides absent when zero escalated regions
- Watch List slide absent when zero MONITOR regions
- No red, amber, or green colour in any slide body element
- Slide titles are assertion-form (from `brief_headlines.why` first sentence)
- Speaker notes contain `brief_headlines.how` for each threat slide
- Deck contains 2 slides (Cover + Overview) when zero escalated and zero monitor
