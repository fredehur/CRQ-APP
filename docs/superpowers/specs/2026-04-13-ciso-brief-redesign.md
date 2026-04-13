# CISO Weekly Brief — Redesign Spec

**Goal:** Produce a top-notch, weekly CISO intelligence brief as a `.docx` that a CISO can use both as a personal decision reference and as a source for upward briefings — polished, threat-centric, and coherent with the Board and RSM outputs.

**Architecture:** The brief is threat/event-centric (not region-centric). Escalated threats lead, with region mentioned as context. The three-pillar structure (`brief_headlines.why / how / so_what`) from `sections.json` is the shared backbone across CISO, Board, and RSM outputs. The CISO brief is the reference implementation; Board and RSM are derived views.

**Scope:** Weekly product only. A daily event-based memo is explicitly deferred to a future session.

**Visual register:** Pure type — Georgia serif, black/white, no colour decoration. Status signalled by a `ESCALATED` badge in solid black only (no red/amber/green). Feels like a formal intelligence document, not a dashboard printout.

---

## Document Structure

### Section 0 — Purpose of this Brief
**Content:** Static boilerplate — what this document is, who it's for, scope, distribution restriction. Updated dynamically with date, cycle number, and region count.

**Template:**
> "This brief provides AeroGrid Wind Solutions' CISO with a consolidated geopolitical and cyber threat assessment for the week of [DATE]. It covers [N] operational regions (APAC, AME, LATAM, MED, NCE) and is produced by the CRQ agentic intelligence pipeline. It is intended to support internal decision-making and upward briefing. Not for external distribution."

**Pipeline source:** Hardcoded in exporter. Dynamic fields: `report_date`, `region_count=5`.

---

### Section 1 — Intelligence Picture
**Content:** One paragraph. Global threat posture this cycle — how many regions escalated, monitored, clear; dominant threat type(s); one-sentence strategic framing.

**Pipeline source:** `global_report.management_summary` (primary). Region status counts from `RegionEntry.status` across all 5 regions.

**Render rule:** If `management_summary` is empty or absent, fall back to auto-generated sentence: "This cycle, [N] region(s) are escalated ([names]), [N] are monitored, and [N] are clear."

---

### Section 2 — Threat Assessment(s)
**One block per ESCALATED region, ordered by severity (Cyber-led before Geo-led if tied).**

Each block contains:

**Header line:**
`[Region full name]` `ESCALATED` badge (black, bold) `[dominant_pillar]-LED` `· Admiralty [admiralty]`

**What this is — 2–3 bullets:**
Precise, confidence-rated statements drawn from `brief_headlines.why`. Each bullet ends with the Admiralty code in brackets, e.g. `[B2]`. Bullets must be specific enough that the CISO understands what this IS without needing to read further — the NOT is implicit in the precision.

**Impact:**
One sentence from `brief_headlines.so_what`. Framed in terms of AeroGrid operational exposure, not abstract threat actor behaviour.

**Suggested Actions — 3–5 items:**
Numbered list from `action_bullets`. Operational, not technical. No SOC jargon.

**Render rule:** If `brief_headlines.why` is empty (pipeline hasn't run with real data), fall back to `why_text` (raw pillar text). If both empty, omit the block and log a warning.

---

### Section 3 — Situation
**One block per escalated region (same order as Section 2).**

**Content:** Factual ground truth — what happened, how it developed, source attribution. Drawn from `brief_headlines.how` (primary) and `intel_bullets` (supporting detail). Citations inline using `SourceRegistry` numbered references `[1]`, `[2]`, etc.

**Render rule:** If `brief_headlines.how` is empty, fall back to `how_text`. Keep to 3–5 sentences per region. No speculative language — cite Admiralty rating if confidence is below B.

---

### Section 4 — Considerations
**Two sub-sections:**

**Watch List:**
One line per MONITOR region: `[Region] — [one-sentence status summary]`. Source: `brief_headlines.why` truncated to first sentence, or `why_text` first sentence.

**Cross-cutting Implications:**
2–4 bullets drawn from `watch_bullets` (regional) and `global_report.management_summary` (global). Focus on AeroGrid-wide operational, financial, or reputational exposure. No region-by-region repetition here — this is the strategic layer.

---

### Section 5 — References
Numbered citation list built by `SourceRegistry`. Format:
`[N] Source Name — headline or URL.`

Credibility tier (A/B/C) shown inline: `[N][A] CISA Advisory — ...`

Only sources cited in Sections 2–4 appear here. No orphan references.

---

## Data Mapping

| Brief Section | Primary Source | Fallback |
|---|---|---|
| Purpose | Hardcoded template | — |
| Intelligence Picture | `global_report.management_summary` | Auto-generated status count |
| Threat bullets (§2) | `brief_headlines.why` | `why_text` (raw pillar) |
| Impact (§2) | `brief_headlines.so_what` | `so_what_text` |
| Actions (§2) | `action_bullets` | Generic action list from `ACTION_BULLETS` |
| Situation (§3) | `brief_headlines.how` | `how_text` |
| Situation detail (§3) | `intel_bullets` | — |
| Watch list (§4) | `brief_headlines.why` (first sentence) | `why_text` first sentence |
| Implications (§4) | `watch_bullets` + `global_report.management_summary` | `watch_bullets` only |
| References (§5) | `SourceRegistry` | — |

---

## Coherence Spine (shared with Board and RSM)

`brief_headlines` is the single source of narrative truth across all three deliverables:

| Field | CISO | Board (.pptx) | RSM (.md) |
|---|---|---|---|
| `why` | Threat assessment bullets | Exec summary lead | Situation opener |
| `how` | Situation section | Regional context slide | Operational ground truth |
| `so_what` | Impact + implications | Management response | Watch items for field |

The CISO brief is the reference implementation. Board and RSM are derived views of the same pipeline data at different altitudes. No field is computed differently for different audiences — only presentation differs.

---

## Visual Specification

**Font:** Georgia (body), system sans-serif (labels, badges)
**Colours:** Black (`#111`) and white only. No red/amber/green.
**Status badge:** `ESCALATED` — solid black rectangle, white text, bold, uppercase, inline with region header. `MONITOR` — black outline only, black text.
**Section headers:** 8pt, letter-spacing 1.5px, uppercase, grey (`#6b7280`), underline divider.
**Region headers:** 12pt, bold, Georgia.
**Body text:** 10pt, Georgia, `#374151`, line-height 1.65.
**Margins:** Standard A4, 2.5cm all sides.
**Header block (cover/first page):** Title + date + cycle number only. No logo, no decoration.

---

## Implementation Scope (for this session)

The following changes are in scope for the implementation plan:

1. **Restructure `export_ciso_docx.py`** — replace current region-loop structure with the 5-section template above. Reuse existing helpers (`_build_cover`, `_build_references`, `SourceRegistry`).
2. **Wire `brief_headlines`** into Sections 2 and 3 — `_load_brief_headlines` already exists; extend `_build_region_escalated` to use it for threat bullets and situation text.
3. **Add Section 0 (Purpose)** — new `_build_purpose()` function. Static template with date injection.
4. **Add Section 1 (Intelligence Picture)** — extend `_build_global_opener()` to use `global_report.management_summary` with status count fallback.
5. **Restructure Section 4 (Considerations)** — split into Watch List + Cross-cutting Implications. Wire `watch_bullets` and `global_report.management_summary`.
6. **Apply A1 visual style** — Georgia body, black/white, no colour. Update `_font()` calls throughout. Replace coloured status badges with black solid/outline pattern.

**Out of scope:**
- Daily event-based memo format
- Board `.pptx` wiring (next spec)
- RSM format changes (third spec)
- New pipeline fields (no `disambiguation` field added)

---

## Test Criteria

- `python -m tools.export_ciso_docx` runs without error on current mock data
- Output `.docx` contains all 6 sections (0–5) in order
- Section 2 is absent when no regions are escalated (monitor-only run)
- Section 2 falls back to `why_text` when `brief_headlines.why` is empty string
- References section contains only cited sources (no orphans)
- Visual: no colour other than black/white in the output document
