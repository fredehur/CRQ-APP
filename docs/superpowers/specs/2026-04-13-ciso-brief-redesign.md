# CISO Weekly Brief — Redesign Spec

**Goal:** Produce a top-notch weekly CISO intelligence brief as a `.docx` — threat-centric, concise (2–3 pages), and optimised for upward briefing. The CISO uses this as talking-point ammunition for board and CEO conversations, and as a personal decision reference.

**Architecture:** The brief is threat-centric, not region-centric. If APAC and MED are hit by the same actor, they appear in ONE threat block — not two separate region blocks. The three-pillar structure (`brief_headlines.why / how / so_what`) from `sections.json` is the shared narrative backbone across CISO, Board, and RSM outputs. The CISO brief is the reference implementation; Board and RSM are derived views at different altitudes.

**Scope:** Weekly product only. A daily event-based memo is explicitly deferred to a future session.

**Visual register:** A1 — Georgia serif, black/white only, no colour. Status signalled by `ESCALATED` in a solid black badge (outline-only for `MONITOR`). Reads like a formal intelligence document, not a dashboard printout.

**Length constraint:** 2–3 pages maximum. If content exceeds this, truncate Situation section to lead sentence only and collapse Watch List to region names + one-word status.

---

## Document Structure

### BLUF (Bottom Line Up Front)
**Position:** Top of page 1, before everything including Purpose.

**Content:** One sentence. The most important thing the CISO needs to know this cycle.

> "Two threats require CISO attention this week: a state-nexus ransomware campaign across APAC and MED energy infrastructure, and emerging supply chain exposure in LATAM."

**Pipeline source:** Auto-generated from escalated region count + `scenario_match` fields. If zero escalated: "No threats escalated this cycle — three regions remain on monitor."

---

### Section 0 — Purpose of this Brief
**Content:** Static boilerplate — what this document is, who it's for, scope, distribution restriction. Updated dynamically with date, cutoff timestamp, cycle number, and region count.

**Template:**
> "This brief provides AeroGrid Wind Solutions' CISO with a consolidated geopolitical and cyber threat assessment for the week of [DATE]. Intelligence current as of [CUTOFF TIMESTAMP]. It covers 5 operational regions (APAC, AME, LATAM, MED, NCE) and is produced by the CRQ agentic intelligence pipeline (Cycle [N]). Intended for internal decision-making and upward briefing. Not for external distribution."

**Pipeline source:** Hardcoded template. Dynamic fields: `report_date`, `cutoff_timestamp` (pipeline run timestamp), `cycle_number`.

---

### Section 1 — Intelligence Picture
**Content:** Two elements:

**Status summary (one line):**
`[N] escalated · [N] monitored · [N] clear` with cycle delta: `(+[N] since week of [DATE])` or `(unchanged)`.

**Global framing (one paragraph):**
Strategic overview of this cycle's threat posture. Drawn from `global_report.management_summary`. If absent, auto-generated: "This cycle, [escalated region names] are escalated. The dominant threat type is [dominant_pillar]. [N] regions remain on monitor."

**Pipeline source:** Region statuses from `RegionEntry.status` (all 5 regions) + `global_report.management_summary` + previous cycle data from archived run log.

---

### Section 2 — Threat Assessment(s)
**One block per THREAT — not per region. Group regions affected by the same threat actor or scenario into a single block.**

Ordering: highest Admiralty confidence first. If tied: Cyber-led before Geo-led.

Each block contains:

**Header:**
`[Threat name / scenario_match]` — `[Regions affected, comma-separated]`
`ESCALATED` badge (solid black) · `[dominant_pillar]-LED` · `Admiralty [admiralty]`
Source signal: `([N] sources · [corroboration_tier])` — e.g. "(4 sources · 2 corroborated)"

**Talking points — 2–3 bullets:**
Precise, confidence-rated statements from `brief_headlines.why`. Each bullet is a standalone talking point a CISO can quote verbatim in a board conversation. Format: plain statement + Admiralty code in brackets.

Example:
> • Ransomware campaign targeting APAC and MED energy-sector OT environments — consistent with state-nexus actor TTPs [B2]
> • Supply chain vector identified via three regional vendors — medium confidence, not yet confirmed in AeroGrid environment [C3]

**Impact (one sentence):**
From `brief_headlines.so_what`. Framed as AeroGrid operational exposure, not abstract threat actor behaviour.

**Render rules:**
- `brief_headlines.why` empty → fall back to `why_text` (raw pillar text)
- Both empty → omit block, log warning to `system_trace.log`
- Source signal: pull from `source_metadata.osint.source_count` and `corroboration_tier`; if absent, omit signal line silently

---

### Section 3 — Situation
**One block per threat (same order as Section 2).**

**Content:** Factual ground truth — what happened, how it developed. Drawn from `brief_headlines.how` (primary narrative) and `intel_bullets` (supporting detail, max 3 bullets). Inline citations using `SourceRegistry` numbered references `[1]`, `[2]`.

**Length:** 3–5 sentences per threat. No speculative language. State Admiralty rating explicitly if confidence is below B.

**Render rule:** `brief_headlines.how` empty → fall back to `how_text`. Keep to 3 sentences maximum when operating under the 2–3 page length constraint.

---

### Section 4 — Watch List
**One line per MONITOR region (not escalated, not clear).**

Format: `[Region] — [one-sentence status].` Drawn from `brief_headlines.why` first sentence, or `why_text` first sentence if empty.

If zero MONITOR regions: omit section entirely.

---

### Section 5 — Action Register
**All actions consolidated in one place — not scattered across threat blocks.**

Actions drawn from `action_bullets` across all escalated regions, deduplicated. Grouped by theme if multiple regions produce the same action type. Numbered list, ordered by specificity (most specific first).

Example:
> 1. Validate offline backup integrity for turbine control systems — APAC, MED
> 2. Review vendor access controls with regional ops teams — LATAM
> 3. Brief senior leadership on emerging risk indicators — all regions

**Render rule:** Deduplicate by exact string match first, then by semantic similarity (same verb + same object = merge, append regions). If no actions available: "No specific actions required this cycle."

---

### Section 6 — Considerations
**Decision-relevant framing. Each point structured as: "Given [X], the CISO should consider [Y]."**

2–4 bullets. Drawn from `watch_bullets` (regional observations) and `global_report.management_summary` (global strategic layer). Focus on AeroGrid-wide exposure — operational, reputational, or organisational. No region-by-region repetition from earlier sections.

Example:
> • Given the APAC/MED threat pattern involves OT environments, consider accelerating the pending turbine firmware audit before the Q2 maintenance window.
> • Given three MONITOR regions share the same scenario type, consider whether this represents a coordinated campaign rather than independent incidents.

---

### Section 7 — References
Numbered citation list built by `SourceRegistry`. Each entry:
`[N][TIER] Source Name — headline or URL.`

Tier key: `[A]` = government/authoritative · `[B]` = established media/research · `[C]` = open source / lower confidence.

Only sources cited in Sections 2–4 appear here. No orphan references.

---

## Data Mapping

| Section | Primary Source | Fallback |
|---|---|---|
| BLUF | Auto-generated from escalated regions + `scenario_match` | Hardcoded zero-escalation template |
| Purpose | Hardcoded template | — |
| Status summary | `RegionEntry.status` × 5 + archive delta | No delta if no archive |
| Global framing | `global_report.management_summary` | Auto-generated from statuses |
| Threat header | `scenario_match`, `dominant_pillar`, `admiralty` | Region name only |
| Source signal | `source_metadata.osint.source_count` + `corroboration_tier` | Omit silently |
| Talking points | `brief_headlines.why` | `why_text` |
| Impact | `brief_headlines.so_what` | `so_what_text` |
| Situation narrative | `brief_headlines.how` | `how_text` |
| Situation detail | `intel_bullets` (max 3) | — |
| Watch List | `brief_headlines.why` first sentence | `why_text` first sentence |
| Action Register | `action_bullets` (all escalated regions, deduplicated) | Generic fallback message |
| Considerations | `watch_bullets` + `global_report.management_summary` | `watch_bullets` only |
| References | `SourceRegistry` | — |

---

## Coherence Spine (shared with Board and RSM)

`brief_headlines` is the single source of narrative truth across all three deliverables:

| Field | CISO (.docx) | Board (.pptx) | RSM (.md) |
|---|---|---|---|
| `why` | Talking point bullets | Exec summary lead | Situation opener |
| `how` | Situation section | Regional context slide | Operational ground truth |
| `so_what` | Impact statement + Considerations | Management response | Watch items for field |

No field is computed differently per audience — only presentation differs. The CISO brief is the reference implementation.

---

## Visual Specification

**Font:** Georgia (all body text), system sans-serif (labels, badges, metadata lines only)
**Colours:** Black (`#111111`) and white only — no red, amber, or green
**ESCALATED badge:** Solid black rectangle, white text, bold, uppercase, 8pt sans-serif, inline with threat header
**MONITOR badge:** Black outline only, black text (not filled)
**Section headers:** 8pt sans-serif, letter-spacing 1.5px, uppercase, grey (`#6b7280`), thin rule below
**Threat headers:** 12pt Georgia, bold
**Body text:** 10pt Georgia, `#374151`, line-height 1.65
**BLUF line:** 11pt Georgia, bold, top of page 1 — no label, no badge, just the sentence
**Margins:** A4, 2.5cm all sides
**Cover / header block:** Document title + date + cycle number only. No logo.

---

## Implementation Scope

Changes to `tools/export_ciso_docx.py`:

1. **Add `_build_bluf()`** — auto-generates BLUF sentence from escalated region list + `scenario_match`. One paragraph, no label.
2. **Add `_build_purpose()`** — static template with `report_date`, `cutoff_timestamp`, `cycle_number` injection.
3. **Extend `_build_global_opener()`** → becomes `_build_intelligence_picture()` — adds status count line + cycle delta from archive.
4. **Rewrite `_build_region_escalated()`** → becomes `_build_threat_assessment()` — groups regions by shared `scenario_match` before rendering. Adds source signal line. Wires `brief_headlines.why` for talking points, `brief_headlines.so_what` for impact.
5. **Rewrite `_build_exec_summary()`** → becomes `_build_situation()` — wires `brief_headlines.how` as primary, `how_text` as fallback.
6. **Add `_build_watch_list()`** — MONITOR regions only, one line each.
7. **Add `_build_action_register()`** — collect `action_bullets` across all escalated regions, deduplicate, render as numbered list.
8. **Rewrite `_build_monitor_section()`** → becomes `_build_considerations()` — reframes bullets as "Given X, consider Y" structure using `watch_bullets` + `global_report.management_summary`.
9. **Apply A1 visual style throughout** — remove all `RED`, `AMBER`, `GREEN` colour usage from body content. Status badges: black filled (ESCALATED) / black outline (MONITOR).
10. **Add length guard** — after assembling all sections, check estimated page count. If > 3 pages, truncate Situation to lead sentence and collapse Watch List.

**Out of scope:**
- VaCR figures in the CISO brief
- Time horizons on actions
- Daily event-based memo
- Board `.pptx` wiring (next spec)
- RSM format changes (third spec)
- New pipeline fields

---

## Test Criteria

- `python -m tools.export_ciso_docx` runs without error on current mock data
- Output `.docx` opens cleanly in Word — no broken styles, no empty sections
- BLUF appears above Section 0 on page 1
- Section 2 groups regions sharing the same `scenario_match` into one threat block
- Section 2 is absent when zero regions escalated
- Section 4 (Watch List) is absent when zero MONITOR regions
- Section 5 (Action Register) deduplicates identical action strings across regions
- Talking points fall back to `why_text` when `brief_headlines.why` is empty
- All cited sources appear in Section 7; no sources appear in Section 7 without citation
- No colour other than black/white in output document
- Document fits within 3 pages on A4 for a typical 2-region escalated run
