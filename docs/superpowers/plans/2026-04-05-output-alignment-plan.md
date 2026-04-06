# Output Alignment Plan — CRQ Intelligence Pipeline
**Date:** 2026-04-05
**Status:** Ready to build
**Session:** Brainstorm + architecture review complete. Build not started.

---

## Context & Why

The CRQ pipeline produces five output formats: CISO docx, Board PDF, Board PPTX, RSM brief (INTSUM + FLASH), and the live dashboard. Only the CISO docx is built correctly — intelligence-first, structured sections, proper source attribution. The other three have drifted:

- **Board PDF and PPTX** render a 2×2 grid (DRIVER/EXPOSURE/IMPACT/WATCH) populated from simplistic first-sentence extraction. They say "CISO Edition" on the cover (wrong). They produce thin, one-sentence-per-quadrant content.
- **RSM brief** has the right structure for its audience but its agent spec declares 6 inputs, 3 of which (`seerist_signals.json`, `region_delta.json`, `audience_config.json`) are often absent. Fallback is implicit — the agent guesses. No resilience.
- **`report_builder.py`** (the shared data layer) does thin extraction — 4 `board_bullets` (first sentences only). All the real extraction logic lives buried inside `export_ciso_docx.py`.

**Root cause:** Three exporters, three content pipelines. The system is format-first, not content-first.

---

## Decisions Made (locked)

| Decision | Choice |
|---|---|
| Board PDF target state | Full CISO mirror — same 7 sections, rendered as HTML→PDF |
| Board PPTX target state | One slide per escalated region, condensed. Fix framing first, design polish later. |
| RSM brief v1 | Work with existing OSINT pipeline data. No Seerist dependency. Explicit fallback. |
| PPTX prompt vault | Saved at `data/pptx_prompt_vault.md` — use as input for future PPTX design brainstorm, not this build |
| VaCR in outputs | Remove from `RegionEntry`. VaCR is not intelligence. Lives in a separate object if needed at all. |
| Exec report | Not in scope. CISO report IS the canonical output. Exec gets the same thing. |

---

## Target State — What "Done" Looks Like

### `report_builder.py` — single extraction layer (ST-1)

`RegionEntry` gains full pre-extracted intelligence sections:

```python
@dataclass
class RegionEntry:
    # existing fields kept
    name: str
    status: RegionStatus
    scenario_match: str | None
    admiralty: str | None
    velocity: str | None
    severity: str | None
    dominant_pillar: str | None
    signal_type: str | None
    confidence_label: str | None
    threat_characterisation: str | None
    top_sources: list[str] | None

    # raw pillar text (kept for reference)
    why_text: str | None
    how_text: str | None
    so_what_text: str | None

    # NEW — pre-extracted intelligence sections
    threat_actor: str | None          # extracted from why+how text
    signal_type_label: str | None     # mapped display label ("Confirmed Incident" etc.)
    intel_bullets: list[str]          # sentences from why_text, max 3
    adversary_bullets: list[str]      # sentences from how_text, max 2
    impact_bullets: list[str]         # sentences from so_what_text, non-VaCR, max 2
    watch_bullets: list[str]          # tradecraft from how/so_what overflow
    action_bullets: list[str]         # scenario-mapped recommended actions

    # REMOVED: vacr (VaCR is not intelligence)
    # board_bullets deprecated — exporters use the section fields above
```

All extraction logic moves FROM `export_ciso_docx.py` INTO `report_builder.py`:
- `_extract_threat_actor()` → move to `report_builder.py`
- `_intel_bullets()`, `_adversary_bullets()`, `_impact_bullets()`, `_watch_bullets()`, `_action_bullets()` → move to `report_builder.py`
- `_signal_type_label()` → move to `report_builder.py`
- `_SCENARIO_ACTIONS` dict → move to `report_builder.py`
- `_SIGNAL_TYPE_LABELS` dict → move to `report_builder.py`

`export_ciso_docx.py` becomes a pure renderer — reads from `RegionEntry` fields, does no extraction.

### Board PDF (`report.html.j2`) — full CISO mirror (ST-2)

Replace 2×2 grid with 7-section per-region layout:

```
Cover page
  - "Cyber Risk Intelligence Brief" (remove "CISO Edition")
  - Status strip (ESCALATED/MONITOR/CLEAR counts)
  - Date, pipeline ID, CONFIDENTIAL

Global Posture page
  - Executive summary (4-part: HEADLINE → CROSS-REGIONAL PATTERN → VELOCITY → CAVEATS)
  - Escalated regions table (Region / Scenario / Confidence / Velocity / Severity)

Per-region page (one page per escalated region)
  - Header: region name + full name + status label [ESCALATED — GEO-LED / CYBER-LED]
  - Scenario · Threat Actor · Signal Type (label row)
  - Intel Findings (bullets from intel_bullets)
  - Observed Adversary Activity (bullets from adversary_bullets)
  - Impact for AeroGrid (bullets from impact_bullets)
  - Watch For — Adversary Tradecraft (bullets from watch_bullets)
  - Recommended Actions (bullets from action_bullets)
  - Footer: velocity · threat characterisation · sources

Appendix page
  - Monitor regions (with rationale)
  - Clear regions
  - Run metadata
```

CSS additions needed: section subheading style, bullet list style. The 2×2 `.bullets-grid` CSS can be removed.

### Board PPTX (`export_pptx.py`) — condensed one-slide-per-region (ST-3)

**Cover slide:**
- Remove "CISO Edition" subtitle
- Title: "Global Cyber Risk Intelligence Brief"
- Status strip unchanged

**Exec summary slide:** unchanged structure, content from new `RegionEntry` fields

**Region slide (one per escalated region):**
- Header band: region name + scenario + status label + severity chip
- Meta row: Threat Actor · Signal Type · Confidence
- Body: condensed bullets (1 per section max) in a vertical list, not 2×2:
  - INTEL FINDINGS: first `intel_bullets` sentence
  - ADVERSARY ACTIVITY: first `adversary_bullets` sentence
  - IMPACT FOR AEROGRID: first `impact_bullets` sentence
  - WATCH FOR: first `watch_bullets` sentence
  - RECOMMENDED ACTION: first `action_bullets` item
- Speaker notes: full content from all section arrays + velocity + sources
- Footer: velocity · threat characterisation · top sources

**Appendix slide:** unchanged

### RSM brief — resilient fallback contract (ST-4)

**Agent spec changes (`rsm-formatter-agent.md`):**

Declare explicit fallback hierarchy per input:

```
seerist_signals.json    → if absent: use geo_signals.json for PHYSICAL & GEO section
region_delta.json       → if absent: write "No comparative data for this period." in SITUATION; write "No pre-media anomalies detected this period." in EARLY WARNING
audience_config.json    → if absent: address brief to "Regional Security Manager" generically
aerowind_sites.json     → if absent: refer to "AeroGrid regional operations" generically
```

All inputs explicitly typed with fallback declared. Quality gate: brief must be written even if 3 of 6 inputs are absent.

**Python fallback handler (`tools/rsm_input_builder.py`) — NEW FILE:**

```python
# Assembles RSM agent inputs with explicit fallbacks.
# Returns a dict of paths + fallback flags consumed by rsm-formatter-agent.
# Code owns the fallback logic. Agent owns the writing.
```

This enforces the boundary principle: fallback routing is code territory, not agent territory. The agent receives clean inputs (real or fallback-derived) and writes — it never decides what to do when a file is missing.

---

## Architecture Principles Applied

### Boundary rule (from agent-boundary-principles.md)

| Task | Owner | Applied Here |
|---|---|---|
| Extract sentences from pillar text | **Code** | Moved into `report_builder.py` |
| Map Admiralty to confidence label | **Code** | Already in `report_builder.py` |
| Detect threat actor from text | **Code** | Moved into `report_builder.py` |
| Write intelligence prose | **Agent** | Stays in regional-analyst-agent |
| Fallback routing when file missing | **Code** | `rsm_input_builder.py` |
| Write RSM brief | **Agent** | rsm-formatter-agent |
| Render HTML/PPTX/DOCX sections | **Code** | Exporters are pure renderers |

### Skill contract rule (from skill-contract-principles.md)

RSM formatter agent contract after this build:

| Field | Value |
|---|---|
| Purpose | Format weekly INTSUM and flash alerts for ex-military RSMs from pipeline intelligence data |
| Inputs | geo_signals.json (required), cyber_signals.json (required), data.json (required), seerist_signals.json (optional), region_delta.json (optional), aerowind_sites.json (optional) |
| Outputs | rsm_brief_{region}_{date}.md, rsm_flash_{region}_{datetime}.md |
| Quality gate | Brief must be structurally complete (all sections present) even with optional inputs absent. Stop hook: rsm-formatter-stop.py |

---

## Build Plan

### Team structure

- **Orchestrator: Opus** — coordinate, define contracts, validate final output. Does not write code.
- **Builder A: Sonnet** — ST-1: enrich `report_builder.py`, move extraction from `export_ciso_docx.py`
- **Builder B: Sonnet** — ST-2 + ST-3: rewrite `report.html.j2`, update `export_pptx.py`
- **Builder C: Sonnet** — ST-4: update `rsm-formatter-agent.md`, create `tools/rsm_input_builder.py`
- **Validator: Sonnet** — cross-check all builders against this spec

### Execution order

```
Phase 1 (sequential):
  Builder A → ST-1 (report_builder.py)
  [Wait for Builder A to complete — ST-2 and ST-3 depend on new RegionEntry fields]

Phase 2 (parallel):
  Builder B → ST-2 (report.html.j2) + ST-3 (export_pptx.py)
  Builder C → ST-4 (rsm-formatter-agent.md + rsm_input_builder.py)
  [Run in parallel, run_in_background: true]

Phase 3 (sequential):
  Validator → cross-check all output against this plan
  Orchestrator → accept or loop builders for correction
  TeamDelete
```

### Sub-task contracts

**ST-1 — Builder A**
```
depends_on: tools/report_builder.py, tools/export_ciso_docx.py
feeds_into: ST-2 (report.html.j2), ST-3 (export_pptx.py), export_ciso_docx.py (now a renderer)
context: This is the foundational change. All exporters become pure renderers after this.
files_to_modify: tools/report_builder.py, tools/export_ciso_docx.py
deliverable: RegionEntry with all 7 new section fields. export_ciso_docx.py reads from fields, does no extraction.
```

**ST-2 + ST-3 — Builder B**
```
depends_on: ST-1 complete (new RegionEntry fields available)
feeds_into: board_report.pdf, board_report.pptx (downloaded from Reports tab)
context: PDF is a full CISO mirror. PPTX is condensed one-slide-per-region. Both use RegionEntry section fields.
files_to_modify: tools/templates/report.html.j2, tools/export_pptx.py
deliverable: PDF with 7 sections per region. PPTX with condensed vertical bullet list per region. "CISO Edition" removed from both.
```

**ST-4 — Builder C**
```
depends_on: nothing (independent of ST-1/2/3)
feeds_into: RSM tab in app, notifier.py delivery
context: RSM brief must work without Seerist. Fallback logic is code, not agent prose.
files_to_create: tools/rsm_input_builder.py
files_to_modify: .claude/agents/rsm-formatter-agent.md
deliverable: rsm_input_builder.py with explicit fallback per input. Agent spec with typed contract (inputs, outputs, quality gate, fallback declared).
```

---

## Files Affected

| File | Change | Sub-task |
|---|---|---|
| `tools/report_builder.py` | Add 7 new `RegionEntry` fields. Move extraction functions from ciso_docx. Remove `vacr` and `board_bullets`. | ST-1 |
| `tools/export_ciso_docx.py` | Remove extraction logic. Read from `RegionEntry` fields. Becomes pure renderer. | ST-1 |
| `tools/templates/report.html.j2` | Replace 2×2 grid with 7-section layout. Fix cover title. | ST-2 |
| `tools/export_pptx.py` | Fix cover label. Replace region slide with condensed vertical list + speaker notes. | ST-3 |
| `.claude/agents/rsm-formatter-agent.md` | Typed input contract with explicit fallback per file. | ST-4 |
| `tools/rsm_input_builder.py` | NEW. Code-owned fallback handler for RSM inputs. | ST-4 |

---

## What Is NOT in Scope

- Dashboard alignment (follows naturally once structure is clear — separate task)
- PPTX visual design polish (brainstorm with pptx_prompt_vault.md — future session)
- Seerist API integration (Phase 2 — separate plan)
- Board vs. CISO split into separate reports (future — when CISO Phase 1 handoff is complete)
- M4/M5 source quality (separate plan: `2026-04-01-sources-redesign.md`)

---

## Done Criteria

- [ ] `report_builder.py` exposes all 7 section fields on `RegionEntry`
- [ ] `export_ciso_docx.py` reads from `RegionEntry` fields, contains no extraction logic
- [ ] Board PDF per-region page shows 7 sections matching CISO structure
- [ ] Board PDF cover says "Cyber Risk Intelligence Brief" (not "CISO Edition")
- [ ] Board PPTX region slide shows condensed bullets per section + speaker notes
- [ ] Board PPTX cover has correct title
- [ ] `rsm_input_builder.py` exists with fallback logic for all 6 RSM inputs
- [ ] `rsm-formatter-agent.md` has typed contract with explicit fallback declared
- [ ] Validator confirms all changes against this spec
- [ ] Pipeline run produces all outputs without error
