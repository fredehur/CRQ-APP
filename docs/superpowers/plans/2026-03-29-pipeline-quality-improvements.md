# Pipeline Quality Improvement Plan
**Date:** 2026-03-29
**Origin:** Live run retrospective — 5-layer review of first full OSINT-live pipeline run
**Scope:** Intelligence quality, data traceability, agent output framing, communication layer

---

## Strategic Roadmap

### Phase 1 — CISO Weekly Intelligence Update (next)
Produce a polished, standalone CISO-grade **weekly intelligence update** in Word (.docx) format. Format: executive summary → per-region breakdown (scenario + threat actor + intelligence findings + AeroGrid impact + watch indicators) → monitor regions. No VaCR figures, no Admiralty ratings — intelligence-first framing. Hand to CISO for review. Incorporate feedback before moving to the next phase. This is the first human review gate.

### Phase 2 — Seerist API + RSM Briefs
Integrate the Seerist API as a live geopolitical signal source. Wire RSM briefs for all 5 regions. Hand to the Regional Security Managers for review. Incorporate their feedback. This is the second human review gate.

### Phase 3 (future) — Daily Event-Driven CISO Flash Brief
A single-event, single-page brief triggered by a threshold breach — a confirmed attack on a peer operator, a major geopolitical escalation, or a new threat actor activity crossing the ESCALATE bar. Fires on demand (not scheduled). Format mirrors the RSM FLASH alert but framed for the CISO: what happened, why it matters for AeroGrid, what to do now. Max 1 page. Audience: CISO + relevant regional ops manager. Requires: live gatekeeper trigger hook, event-delta detection against previous run.

The P1/P2/P3 improvements below feed directly into Phase 1 — the CISO report quality depends on fixing the data and framing issues first.

---

## Context

First fully live pipeline run completed 2026-03-29. 329 signals collected via Tavily across 5 regions. All 5 layers reviewed: data collection, gatekeeper analysis, regional analyst output, global report communication. Regional analyst prompt was rewritten mid-session based on senior intelligence analyst critique. This plan captures everything remaining.

---

## P1 — Fix Now (breaks the product)

### P1-1: Source URLs dropped at synthesis
**What:** `research_collector.py` synthesises Tavily results into `geo_signals.json` and `cyber_signals.json` but drops the source URLs. Tavily returns real URLs per result. They are lost at the LLM synthesis step.
**Impact:** "Evidenced by [X]" citations have no link back to the actual article. Traceability chain is broken. An auditor or board member asking "show me the source" gets nothing.
**Fix:** Pass source URLs through the synthesis step. `geo_signals.json` and `cyber_signals.json` should include a `source_urls` list alongside `lead_indicators`. The analyst agent can then cite URL-backed sources in `signal_clusters.json`.
**Files:** `tools/research_collector.py` (synthesis prompt + output schema)

### P1-2: Cyber signals producing 0 structured indicators
**What:** Every region returned `lead_indicators: []` in `cyber_signals.json` even when Tavily returned relevant results (confirmed: 8 results for APAC cyber query). The LLM synthesis prompt for the cyber pass is not extracting structured indicators.
**Impact:** The How paragraph in every brief is inferred from geopolitical context, not evidenced cyber signals. Confidence is artificially low.
**Fix:** Review the cyber synthesis extraction prompt in `research_collector.py`. Compare against the geo prompt which does produce indicators. Likely needs more explicit instruction to extract named threat actors, incident descriptions, and attack vectors as discrete `lead_indicators`.
**Files:** `tools/research_collector.py` (`EXTRACTION_PROMPTS["cyber"]`)

### P1-3: Admiralty field empty in `gatekeeper_decision.json`
**What:** `gatekeeper_decision.json` writes the Admiralty rating into the `rationale` text but not as a structured `admiralty_rating` field. The field is present in the schema but returns null/empty.
**Impact:** Downstream consumers (global-builder, dashboard) are parsing Admiralty from prose rather than structured JSON. Fragile.
**Fix:** Update `gatekeeper-agent` prompt to explicitly write `admiralty_rating` as a top-level JSON field, separate from rationale.
**Files:** `.claude/agents/gatekeeper-agent.md`

### P1-4: NCE severity field incorrect post-escalation
**What:** `data.json` for NCE shows `severity: LOW` despite being escalated (B2). `write_region_data.py` sets severity from the scenario mapper baseline and does not override it when the gatekeeper escalates.
**Impact:** Dashboard and global report consume severity from `data.json`. NCE showing LOW while escalated is misleading.
**Fix:** `write_region_data.py` should accept severity as a parameter when called with `escalated` status, or derive it from the gatekeeper decision. The gatekeeper already outputs a severity assessment in its rationale.
**Files:** `tools/write_region_data.py`

---

## P2 — Intelligence Quality (degrades output)

### P2-1: LATAM monitor section reads like internal pipeline output
**What:** The global report's LATAM watch section contains: "research scratchpad suggested E3 but corroborated global wind IP theft pattern..." — this is pipeline reasoning, not board communication.
**Impact:** Board-level document contains internal tool references. Undermines credibility.
**Fix:** Add a rule to `global-builder-agent` prompt: monitor region sections must be written in plain intelligence language — what signals were found, why it didn't reach escalation threshold. No references to internal pipeline artefacts (scratchpad, E3 ratings, collector output).
**Files:** `.claude/agents/global-builder-agent.md`

### P2-2: Executive summary mixes time horizons
**What:** The global exec summary jumps between current-cycle findings, 9-run historical context, and scenario correction notices in the same paragraph.
**Impact:** Hard to parse. The correction notice (MED scenario superseded) is important but easy to miss.
**Fix:** Structure the exec summary explicitly: (1) current-cycle headline, (2) cross-regional pattern, (3) velocity/historical context, (4) corrections/caveats. Add this structure to the global-builder-agent prompt.
**Files:** `.claude/agents/global-builder-agent.md`

### P2-3: Gap confidence not surfaced at board level
**What:** AME is B2 with confirmed peer incidents. APAC is B3 trend-inferred with no confirmed regional incidents. The exec summary presents both escalations with equal weight.
**Impact:** Board cannot calibrate urgency across regions. A B2 confirmed incident requires different response than a B3 trend assessment.
**Fix:** Global builder should explicitly flag confidence differential in the exec summary when escalated regions span more than one Admiralty confidence level. Surface the highest-confidence and lowest-confidence escalations explicitly.
**Files:** `.claude/agents/global-builder-agent.md`

---

## P3 — Nice to Have

### P3-1: YouTube seed channels stale
**What:** Multiple channels returned 404 in the live run (CFR_org, MandiantThreatIntel, others). Zero YouTube indicators produced across all 5 regions.
**Fix:** Audit `data/youtube_sources.json`. Update channel IDs/URLs. Test each channel with `yt-dlp` before committing.
**Files:** `data/youtube_sources.json`

### P3-2: `[research collection]` citation still possible
**What:** Jargon auditor catches it as a non-named source, but the agent writes it first and then gets corrected. Better to prevent than catch.
**Fix:** Add `[research collection]` to the explicit banned citation examples in the `regional-analyst-agent` quality checklist. Already partially addressed in the prompt rewrite — confirm it's explicit.
**Files:** `.claude/agents/regional-analyst-agent.md`

### P3-3: `analyst_override_note` should be a standard schema field
**What:** When the regional analyst overrides the scenario mapper, the override is ad hoc (validator forced it for MED this run). There's no standard field for it.
**Fix:** Add `analyst_override_note` as an optional field to the `data.json` schema. Update `regional-analyst-agent` to write it whenever `primary_scenario` differs from `scenario_map.scenario_match`. Update `global-builder-agent` to surface it in the regional entry when present.
**Files:** `tools/write_region_data.py`, `.claude/agents/regional-analyst-agent.md`

---

## Separate Backlog Items

### Analyst output deep review
Read all regional briefs produced to date (all 5 regions across multiple runs). Evaluate sentence structure, source citation quality, intelligence framing discipline against the updated prompt. Identify any remaining patterns to fix in the prompt or quality gates.
**When:** After P1s are resolved and a clean run is complete.

---

## What Was Already Fixed This Session
- Regional analyst prompt rewritten: Why/How now intelligence-first, org context restricted to So What
- Fabrication rule added: How paragraph may not contain findings not present in signal files
- `[research collection]` added to banned citation list
- MED analyst override documented via `analyst_override_note` (ad hoc — P3-3 formalises this)
