# Dashboard UI Alignment — Design Spec
**Date:** 2026-04-05
**Status:** Approved for implementation
**Session:** Brainstorm complete.

---

## Problem

The dashboard Overview tab renders the regional analyst's brief as a raw markdown text blob. The CISO docx, board PDF, and board PPTX all render the same content as structured 5-section intelligence briefs (Intel Findings / Adversary Activity / Impact / Watch For / Recommended Actions). The dashboard is the outlier.

**Root cause (boundary violation):** `report_builder.py` applies sentence-splitting and pattern extraction to prose paragraphs after the fact. The agent wrote structured content (Why / How / So What) and code tries to recover machine-readable sections from that prose. This is compensating for a missing output artifact — the agent should emit machine-readable sections directly alongside the prose brief.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Section data source | Agent writes `sections.json` | Filesystem as state — agent emits what it knows at write time |
| Extraction functions in report_builder | Become dead code — remove after migration | Sections come from file, not from parsing prose |
| Dashboard API | Pass-through `GET /api/region/{region}/sections` | Thin endpoint, no compute |
| Global synthesis bar | Update to 4-part structured layout | Already agreed in brainstorm |
| Trends tab label | "CISO Talking Points" → "Executive Talking Points" | Audience is whole org, not just CISO |
| Scope | Overview tab (right panel + synthesis bar) + Trends label | Other tabs already aligned |

---

## Agent Output Contract — `sections.json`

The regional analyst agent adds a new **Step 8** to its output sequence, writing `sections.json` after `data.json`:

**Path:** `output/regional/{region_lower}/sections.json`

**Schema:**
```json
{
  "region": "APAC",
  "generated_at": "<ISO 8601 UTC>",
  "threat_actor": "APT40",
  "signal_type_label": "Confirmed Incident",
  "status_label": "ESCALATED — CYBER-LED",
  "intel_bullets": [
    "Regional energy sector facing elevated state-sponsored intrusion pressure following grid operator breach."
  ],
  "adversary_bullets": [
    "Initial access via exposed SCADA web interfaces.",
    "Lateral movement toward historian servers consistent with pre-positioning pattern."
  ],
  "impact_bullets": [
    "Three AeroGrid wind farms share infrastructure with compromised peer operators.",
    "Exposure window estimated 30–60 days based on adversary dwell time patterns."
  ],
  "watch_bullets": [
    "Reconnaissance activity against historian servers and DCS access points.",
    "Credential harvesting campaigns targeting OT staff."
  ],
  "action_bullets": [
    "Audit remote access to SCADA interfaces.",
    "Brief regional ops on phishing targeting OT personnel."
  ]
}
```

**Extraction rules (agent writes these directly — does not parse its own prose):**

- `intel_bullets`: 2–3 key factual findings from the Why paragraph — what is happening in the threat environment
- `adversary_bullets`: 1–2 observed activity lines from the How paragraph — what adversaries are doing
- `impact_bullets`: 1–2 AeroGrid-specific consequence sentences from the So What paragraph — no VaCR figure, no financial language
- `watch_bullets`: 2–3 concrete watch indicators from the So What closing — the same watch items already written
- `action_bullets`: 2–3 recommended actions for the matched scenario. The agent uses the same scenario-to-action mapping already in `report_builder.py`. That dict must be copied verbatim into the agent spec as a lookup table so the agent applies it directly — no code dependency at write time.
- `threat_actor`: primary state actor or group named in the brief — empty string if none named
- `signal_type_label`: mapped from `signal_type` field — "Confirmed Incident" / "Emerging Pattern" / "Confirmed Incident + Emerging Pattern"
- `status_label`: "ESCALATED — GEO-LED" or "ESCALATED — CYBER-LED" based on `dominant_pillar`

**For CLEAR and MONITOR regions:** do not write `sections.json` — these regions have no brief.

---

## Pipeline Boundary

```
[CODE]   validate geo/cyber signal inputs
[AGENT]  regional-analyst-agent
         Input:  geo_signals.json, cyber_signals.json, data.json (required)
         Output: claims.json, report.md, signal_clusters.json, data.json (updated), sections.json (NEW)
         Gate:   regional-analyst-stop.py (existing — jargon + source attribution)
                 grounding-validator.py (existing — claims integrity)
                 sections-validator.py (NEW — schema + completeness)
[CODE]   dashboard reads sections.json via GET /api/region/{region}/sections (pass-through)
[CODE]   report_builder.py reads sections.json (replaces extraction functions)
[CODE]   exporters (PDF/PPTX/DOCX) unchanged — already read from RegionEntry fields
```

---

## Quality Gate — `sections-validator.py`

New stop hook validator, runs after `grounding-validator.py`:

```
Path: .claude/hooks/validators/sections-validator.py
Trigger: after regional-analyst-agent exits (Stop hook)
Guard: only runs for ESCALATED regions (same guard pattern as grounding-validator)

Checks:
1. sections.json exists for ESCALATED region
2. Valid JSON
3. All 7 keys present: intel_bullets, adversary_bullets, impact_bullets, watch_bullets,
   action_bullets, threat_actor, signal_type_label (status_label optional)
4. intel_bullets, adversary_bullets, impact_bullets non-empty (at least 1 item each)

Exit codes: 0 = pass/skip, 1 = fail (triggers agent retry, max 3 per grounding-validator pattern)
```

---

## Files Changed

### Agent

| File | Change |
|---|---|
| `.claude/agents/regional-analyst-agent.md` | Add Step 8 — write `sections.json`. Add to self-validation checklist: `- [ ] sections.json written with all 5 bullet arrays non-empty and threat_actor/signal_type_label populated`. Copy `_SCENARIO_ACTIONS` dict from `report_builder.py` into agent spec as lookup table for action_bullets. |

### New files

| File | Purpose |
|---|---|
| `.claude/hooks/validators/sections-validator.py` | Stop hook — validates sections.json schema + completeness |

### Server

| File | Change |
|---|---|
| `server.py` | Add `GET /api/region/{region}/sections` — reads `output/regional/{region_lower}/sections.json`, returns JSON. Returns `{}` if file absent. |

### Dashboard

| File | Change |
|---|---|
| `static/app.js` | Replace `renderBriefSection()` — fetch from `/api/region/{region}/sections`, render 5 labelled blocks with coloured left borders. Update synthesis bar render to use 4-part structure. Rename "CISO Talking Points" → "Executive Talking Points" in `renderTrends()`. |

### Extraction cleanup (after sections.json is live)

| File | Change |
|---|---|
| `tools/report_builder.py` | Replace extraction function calls with `sections.json` file read. Remove `_intel_bullets`, `_adversary_bullets`, `_impact_bullets`, `_watch_bullets`, `_action_bullets`, `_extract_threat_actor`, `_signal_type_label` in the same implementation — removal is gated on the "Mock pipeline run produces sections.json" done criterion passing. |

---

## Dashboard — Right Panel Layout

```
┌─────────────────────────────────────────────────────┐
│ [ESCALATED]  Asia Pacific           B2  ↑ 3/4 runs  │
├─────────────────────────────────────────────────────┤
│ Supply Chain Disruption  [CONFIRMED INCIDENT]        │
│ Threat Actor: APT40  ·  ESCALATED — CYBER-LED        │
├─────────────────────────────────────────────────────┤
│ ▌ INTEL FINDINGS                                     │
│   Regional energy sector facing elevated pressure…   │
│                                                      │
│ ▌ OBSERVED ADVERSARY ACTIVITY                        │
│   Initial access via exposed SCADA interfaces…       │
│                                                      │
│ ▌ IMPACT FOR AEROGRID                                │
│   Three wind farms share infrastructure with…        │
│                                                      │
│ ▌ WATCH FOR                                          │
│   Reconnaissance against historian servers…          │
│                                                      │
│ ▌ RECOMMENDED ACTIONS                                │
│   Audit remote access to SCADA interfaces…           │
├─────────────────────────────────────────────────────┤
│ SIGNAL CLUSTERS                                      │
│   [CYBER] OT Network Intrusion Cluster  3 ▶          │
│   [GEO]   Grid Infrastructure Targeting  2 ▶         │
├─────────────────────────────────────────────────────┤
│ ▶ Source Evidence                                    │
└─────────────────────────────────────────────────────┘
```

Left border colours:
- INTEL FINDINGS: `#1f6feb` (blue)
- OBSERVED ADVERSARY ACTIVITY: `#388bfd` (lighter blue)
- IMPACT FOR AEROGRID: `#3fb950` (green)
- WATCH FOR: `#e3b341` (amber)
- RECOMMENDED ACTIONS: `#ff7b72` (red)

---

## Dashboard — Global Synthesis Bar

Replace raw `synthesis-brief` paragraph with structured elements:

```
GLOBAL SYNTHESIS  |  [headline sentence from exec_summary HEADLINE part]
                  |  [3 ESCALATED] · [1 WATCH] · [1 CLEAR]  ↑ velocity
```

Data source: `output/global_report.json` → `exec_summary` field (already fetched on load).
Status counts: already computed in `state.regionData` — derive from status field per region.

**Fallback (no global_report.json):** show status counts only + text: "Run pipeline to generate global synthesis." Do not show an empty headline slot.

---

## Done Criteria

- [ ] `regional-analyst-agent.md` has Step 8 — write `sections.json`
- [ ] `sections-validator.py` exists and wired as stop hook
- [ ] Mock pipeline run produces `sections.json` for all escalated regions
- [ ] `GET /api/region/{region}/sections` returns correct JSON
- [ ] Dashboard right panel shows 5 labelled sections for escalated regions
- [ ] Dashboard right panel shows correct "no brief" state for CLEAR/MONITOR regions
- [ ] Global synthesis bar shows structured 4-part layout
- [ ] "CISO Talking Points" renamed "Executive Talking Points" in Trends tab
- [ ] `report_builder.py` reads from `sections.json` (extraction functions removed/deprecated)
- [ ] Validator confirms all criteria pass

---

## Out of Scope

- Reports tab (working)
- Validate tab (already aligned)
- Source Audit tab (already aligned)
- History tab (informational, no change needed)
- RSM tab (separate phase — Seerist dependency)
- Config tab (operational, not output-facing)
- PPTX visual design polish (separate session with pptx_prompt_vault.md)
