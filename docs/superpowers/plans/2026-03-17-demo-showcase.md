# Demo Showcase Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a `demo/` folder containing a professional briefing-style walkthrough and the actual pipeline intelligence outputs, targeted at a risk professional colleague with no developer background.

**Architecture:** Two tasks — (1) copy four unmodified pipeline output files into `demo/intelligence/`, (2) write `demo/README.md` as a five-section integrated narrative. No code changes. No tests. Pure content creation.

**Tech Stack:** Markdown only. No dependencies.

---

## File Map

| File | Action | Source |
|---|---|---|
| `demo/intelligence/global_summary.md` | Create (copy) | `output/global_report.md` |
| `demo/intelligence/regional_ame.md` | Create (copy) | `output/regional/ame/report.md` |
| `demo/intelligence/regional_apac.md` | Create (copy) | `output/regional/apac/report.md` |
| `demo/intelligence/regional_med.md` | Create (copy) | `output/regional/med/report.md` |
| `demo/README.md` | Create (authored) | Spec: `docs/superpowers/specs/2026-03-17-demo-showcase-design.md` |

---

## Task 1: Copy intelligence output files

**Files:**
- Create: `demo/intelligence/global_summary.md`
- Create: `demo/intelligence/regional_ame.md`
- Create: `demo/intelligence/regional_apac.md`
- Create: `demo/intelligence/regional_med.md`

These are byte-for-byte copies of the pipeline outputs. Do not edit, reformat, or add headers.

- [ ] **Step 1: Copy the four intelligence files**

```bash
mkdir -p demo/intelligence
cp output/global_report.md demo/intelligence/global_summary.md
cp output/regional/ame/report.md demo/intelligence/regional_ame.md
cp output/regional/apac/report.md demo/intelligence/regional_apac.md
cp output/regional/med/report.md demo/intelligence/regional_med.md
```

- [ ] **Step 2: Verify all four files exist and are non-empty**

```bash
wc -l demo/intelligence/*.md
```

Expected: four files, each with line counts matching their source (global_summary ~60 lines, regional files ~30–40 lines each).

- [ ] **Step 3: Commit**

```bash
git add demo/intelligence/
git commit -m "feat: add demo intelligence outputs (unmodified pipeline exports)"
```

---

## Task 2: Write demo/README.md

**Files:**
- Create: `demo/README.md`

This is the authored narrative. Write it exactly as specified below. Do not add developer content (no Python, no JSON, no CLI commands, no filenames ending in `.py` or `.json`). The full content is provided — write it verbatim, then verify quality criteria.

- [ ] **Step 1: Write demo/README.md**

Write the file at `demo/README.md` with the following content:

---

```markdown
# CRQ Intelligence Pipeline — Live Demo

**Client:** AeroGrid Wind Solutions (Anonymized) — Renewable Energy
**Pipeline run:** 2026-03-16 | **Regions analysed:** 5 | **Total VaCR exposure:** $44,700,000

---

## The Problem with Static Risk Reports

Most risk reports describe a point in time. A quarterly assessment tells you what the threat landscape looked like when an analyst sat down to write it — not what it looks like now. In a geopolitical and cyber threat environment that shifts weekly, that gap matters.

Three specific failures are endemic to manual, periodic reporting. First, a stable region can become an active threat between reporting cycles with no mechanism to trigger escalation. Second, when multiple regional assessments are conducted independently — by different analysts, at different times — the cross-regional pattern that spans all of them goes undetected. Third, intelligence confidence calibration is informal: different analysts apply different standards, and there is no reproducible, auditable record of why a signal was judged credible or dismissed.

This pipeline was built to address all three. It runs on demand across all five of AeroGrid's operational regions simultaneously, producing board-ready intelligence that is current, cross-calibrated, and auditable — without manual analyst hours per cycle.

---

## The Last Run at a Glance

Pipeline run: **2026-03-16** | Total combined VaCR exposure: **$44,700,000**

| Region | Status | Severity | VaCR Exposure | Dominant Pillar | Admiralty |
|---|---|---|---|---|---|
| AME (North America) | Escalated | CRITICAL | $22,000,000 | Cyber | B2 |
| APAC | Escalated | HIGH | $18,500,000 | Geopolitical | B2 |
| MED (Mediterranean) | Escalated | MEDIUM | $4,200,000 | Geopolitical | B2 |
| LATAM | Clear | LOW | $0 | Geopolitical | C3 |
| NCE (N. & Central Europe) | Clear | LOW | $0 | Geopolitical | C3 |

**Three regions escalated simultaneously** — and the most significant finding from this run is not the individual regional exposures but what the synthesis layer identified across them: all three escalated threats, despite originating from different actors using different methods (state-directed collection in APAC, financially motivated extortion in AME, insider access abuse in MED), independently target the same crown jewel asset class — turbine operational technology, predictive maintenance systems, and proprietary manufacturing IP. This is a compound risk posture, not three isolated incidents. No individual regional assessment would have surfaced it.

**Full intelligence outputs:**
- [Global Executive Summary](intelligence/global_summary.md) — cross-regional synthesis, compound risk finding, velocity narrative
- [AME Regional Brief](intelligence/regional_ame.md) — CRITICAL | Ransomware | $22,000,000
- [APAC Regional Brief](intelligence/regional_apac.md) — HIGH | System Intrusion | $18,500,000
- [MED Regional Brief](intelligence/regional_med.md) — MEDIUM | Insider Misuse | $4,200,000

> These are the unmodified outputs of the pipeline agents. Nothing has been edited or polished for presentation.

---

## Reading the Intelligence

Each document in the intelligence folder follows the same structure. Here is what to look for.

### The Three-Pillar Brief

Every regional report answers three questions in sequence:

**Why — Geopolitical Driver**
What macro-level condition is creating the threat environment? This section describes the structural cause: state actor intent, economic pressure, regulatory shift, or geopolitical competition. It does not describe attack techniques. It describes why the threat exists.

**How — Cyber Vector**
How is that condition manifesting as a specific exposure for AeroGrid? This section connects the geopolitical driver to the company's specific assets — which crown jewels are in the firing line and through what pathway. It distinguishes between what is evidenced (confirmed incidents in the sector) and what is assessed (AeroGrid's exposure based on asset alignment).

**So What — Business Impact**
What is the financial and operational consequence? This section states the VaCR figure, names the scenario type and its global financial rank, and closes with a forward-looking statement — what to watch for in the next cycle.

### Admiralty Ratings

Every signal is rated on two axes before it reaches a report:

- **Source reliability:** A (always reliable) → F (cannot be judged)
- **Information credibility:** 1 (confirmed by independent sources) → 6 (cannot be judged)

`B2` — the rating across all three escalated regions in this run — means: usually reliable source, information probably true. This is the standard working threshold for actionable intelligence. It does not mean certainty; it means the signal has been corroborated and the source has a track record.

`C3` — the rating for LATAM and NCE — means: fairly reliable source, possibly true. Adequate confidence for a CLEAR determination, but not for escalation.

These ratings propagate from triage through to the board report. Executives see calibrated confidence, not binary alerts.

### VaCR Figures

The dollar figures in these reports — $22M, $18.5M, $4.2M — are Value-at-Cyber-Risk figures from a separate enterprise CRQ application. This pipeline does not calculate them. They are pre-calculated, scenario-specific financial exposures that the pipeline couples with live intelligence to answer a different question: *is this scenario currently active, and why?*

The $22M for AME is not an estimate this system produced. It is the enterprise-calculated exposure for the Ransomware scenario in North America. The pipeline's job is to tell you whether that exposure is live right now — and it is.

### Signal Type

Every brief is classified before writing:

- **Event** — a specific, confirmed recent incident
- **Trend** — a sustained pattern building over time
- **Mixed** — a structural trend that has now materialized into a specific evidenced incident

AME is classified as an **Event** — a confirmed ransomware campaign, specific demand amount, specific recovery duration. APAC is a **Trend** — sustained state-directed collection activity with no single precipitating incident. MED is **Mixed** — a structural workforce-pressure trend that has produced a specific evidenced access incident.

The classification drives the brief's prose and its forward-looking statement. Event briefs describe what happened and what it means immediately. Trend briefs describe trajectory and where the risk is heading.

---

## How Agents Produce This

The pipeline is built with four specialist agents, each with a defined role and no overlap in responsibility. Here is what each one does and why the division matters for intelligence quality.

### Parallel Regional Analysis

All five regions are analysed simultaneously. Each region runs its own independent signal collection, triage, and (if escalated) analytical process in parallel. A pipeline run that would take a human analyst team working sequentially the better part of a working day completes in minutes. More importantly, parallel execution means no region is skipped or deferred because another region consumed resource.

### Gatekeeper Agent — Triage

Before any intelligence is written, a dedicated triage agent processes the raw signals for each region and returns one decision: **ESCALATE**, **MONITOR**, or **CLEAR**. Only escalated regions proceed to full analytical treatment.

This gate serves two purposes. It prevents low-signal noise from reaching the analytical layer and generating spurious reports. And it ensures clear regions produce a positive confirmation — "this region is stable" — rather than silence. LATAM and NCE being CLEAR in this run is actionable intelligence for the teams operating in those regions: they are not in the current threat window.

The gatekeeper also assigns an Admiralty rating to each decision, which propagates forward into every downstream output.

### Regional Analyst Agent — Intelligence Writing

For escalated regions, a dedicated analytical agent writes the three-pillar brief. It reads geo signals, cyber signals, open-source video intelligence, and the empirical master scenario register — then makes the authoritative determination of which scenario type best fits the evidence.

The scenario determination is owned by this agent, not by keyword matching. An automated keyword scorer provides an initial hint, but the analyst validates that hint against the empirical register and overrides it if the evidence warrants. This is the quality gate that prevents low-fidelity pattern matching from reaching the board.

Every brief passes through a mandatory jargon audit before it is accepted. The auditor rejects any report containing technical security operations language — no CVEs, no threat actor TTPs, no MITRE ATT&CK framework references, no unsolicited budget recommendations. If rejected, the agent rewrites. The board receives intelligence written for executives, not security engineers. This is enforced, not requested.

### Global Builder + Validator — Synthesis and Cross-Check

After all five regions complete, a synthesis agent reads every approved regional brief and writes the global executive summary. A separate devil's advocate agent then cross-checks the synthesis against the regional source data — verifying financial totals, Admiralty consistency, and scenario mapping accuracy before the report is finalised.

This two-agent check is not redundant. The synthesis agent's job is to identify cross-regional patterns; the validator's job is to confirm those patterns are grounded in the regional evidence. The compound risk finding in this run — three independent actors converging on the same asset class — was identified by the synthesis agent and confirmed by the validator.

Agents are bound to an empirical master scenario register for all financial impact and event frequency statistics. They cannot invent figures. Every ranking cited in these reports — "Ransomware ranked #1 globally by financial impact (37.6% of all losses)" — comes from that register.

---

## What This Enables That Static Reports Cannot

### Velocity Tracking Across Runs

The pipeline archives every completed run. After each cycle, a historical comparison layer examines the current run against all prior runs and assigns a velocity label per region: **accelerating**, **stable**, or **improving**. That label feeds into the global synthesis.

In this run, all five regions are assessed as **stable** — the threat posture is entrenched but not worsening. That is a material finding. A static report can tell you what the current severity is; it cannot tell you whether the situation is deteriorating or holding. The difference matters for prioritisation.

### Cross-Regional Compound Risk Detection

The most important finding in this run did not come from any individual regional brief. It came from the synthesis layer reading all five regional outputs simultaneously and recognising that three independent threat actors — state collection, criminal ransomware, insider access — all independently selected the same target: turbine operational technology and predictive maintenance systems.

This convergence is only visible when all five regions are assessed in the same cycle, by a synthesis agent that reads all five briefs at once, with an explicit mandate to look for cross-regional patterns. A human team producing regional assessments separately and sequentially would not see it. It emerges at the synthesis layer, or it does not emerge at all.

### Auditable, Reproducible Intelligence

Every pipeline run produces a full audit trace — a timestamped log of every agent decision, every quality gate result, and every rewrite event. Intelligence quality is not a function of who ran the pipeline that day or how carefully they applied the methodology. The same signals, run through the same pipeline, produce the same calibrated output. Every quality gate outcome is logged and reviewable.

This matters for governance. When a board asks "how confident are we in this assessment?", the answer is not "it depends on the analyst." The answer is a logged Admiralty rating, a documented quality gate pass, and a rewrite count that shows the report met the jargon-free standard on the first or second attempt.

---

*Pipeline: CRQ Geopolitical Intelligence System | Client: AeroGrid Wind Solutions (Anonymized) | Built with Claude Code*
```

---

- [ ] **Step 2: Verify quality criteria**

Check each criterion manually:

1. No developer jargon — scan for: `.py`, `.json`, `CLI`, `Python`, `bash`, `curl`, `import`, `function`, `API`. None should appear.
2. Verify figures in Section 2 table:
   - For escalated regions (AME, APAC, MED): check VaCR, severity, Admiralty, dominant pillar against `output/run_manifest.json`
   - For clear regions (LATAM, NCE): check Admiralty and dominant pillar against `output/regional/latam/data.json` and `output/regional/nce/data.json` — these fields are **not** in `run_manifest.json` for clear regions; do not use `run_manifest.json` for these two rows

   ```bash
   uv run python -c "import json; m=json.load(open('output/run_manifest.json')); [print(r, m['regions'][r]) for r in m['regions']]"
   uv run python -c "import json; print(json.load(open('output/regional/latam/data.json'))['admiralty'], json.load(open('output/regional/nce/data.json'))['admiralty'])"
   ```

   Expected clear-region Admiralty: `C3` for both LATAM and NCE.

3. The four links in the README resolve correctly — verify filenames match what was copied in Task 1.

```bash
ls demo/intelligence/
```

- [ ] **Step 3: Commit**

```bash
git add demo/README.md
git commit -m "feat: add demo/README.md — risk professional walkthrough"
```

---

## Final Verification

- [ ] **Confirm folder structure**

```bash
find demo/ -type f
```

Expected output:
```
demo/README.md
demo/intelligence/global_summary.md
demo/intelligence/regional_ame.md
demo/intelligence/regional_apac.md
demo/intelligence/regional_med.md
```

- [ ] **Confirm links in README resolve**

The four markdown links in the README use relative paths (`intelligence/global_summary.md` etc.). Verify the filenames match exactly (case-sensitive).

```bash
ls demo/intelligence/
```

Expected: `global_summary.md  regional_ame.md  regional_apac.md  regional_med.md`
