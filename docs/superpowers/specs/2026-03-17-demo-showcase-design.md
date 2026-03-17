# Demo Showcase — Design Spec

**Date:** 2026-03-17
**Status:** Approved

---

## Purpose

Create a `demo/` folder in the repository that serves as a self-contained showcase for a risk professional colleague. The audience is someone with a physical risk background who would be a receiver of the intelligence outputs, and who is also curious about what agentic AI frameworks add to risk work. No setup or code execution required to consume the demo.

---

## Audience Profile

- Risk professional (physical risk background), not a developer
- Would be a real recipient of the intelligence this pipeline produces
- Two interests: (1) is the intelligence quality good enough to trust and act on? (2) what does the agentic framework add that a static report or manual process cannot?
- Tone: professional briefing style — structured, concise, mirrors the intelligence products themselves

---

## Folder Structure

```
demo/
  README.md                        ← integrated narrative (the main document)
  intelligence/
    global_summary.md              ← global executive brief (from last pipeline run)
    regional_ame.md                ← AME brief (CRITICAL — Ransomware, $22M VaCR)
    regional_apac.md               ← APAC brief (HIGH — System Intrusion, $18.5M VaCR)
    regional_med.md                ← MED brief (MEDIUM — Insider Misuse, $4.2M VaCR)
```

The `intelligence/` files are the **actual unmodified pipeline outputs** from the last run. No editing, no polishing — what the agents wrote is what's shown.

The `README.md` is the authored narrative that contextualises them.

---

## `demo/README.md` — Content Specification

### Section 1 — The Problem (2–3 paragraphs)

Frame the gap that this system fills. Static risk reports describe a point in time. Geopolitical and cyber threat environments change weekly. A quarterly report produced by a manual process cannot detect when a stable region becomes escalated between cycles, cannot identify when three independently-assessed regional threats share the same target surface, and cannot calibrate intelligence confidence in a reproducible, auditable way.

The section ends with a single sentence that names what the pipeline does: it runs continuously, in parallel across all five regions, producing board-ready intelligence that is current, cross-calibrated, and auditable — without manual analyst hours per cycle.

### Section 2 — The Last Run at a Glance

A structured summary table of the most recent pipeline run:

| Region | Status | Severity | VaCR Exposure | Dominant Pillar | Admiralty |
|---|---|---|---|---|---|
| AME (North America) | Escalated | CRITICAL | $22,000,000 | Cyber | B2 |
| APAC | Escalated | HIGH | $18,500,000 | Geopolitical | B2 |
| MED (Mediterranean) | Escalated | MEDIUM | $4,200,000 | Geopolitical | B2 |
| LATAM | Clear | LOW | $0 | Geopolitical | C3 |
| NCE (N. & Central Europe) | Clear | LOW | $0 | Geopolitical | C3 |

**Total combined VaCR exposure: $44,700,000 across 3 escalated regions simultaneously.**

Followed by the key compound risk finding from the global synthesis: all three escalated regions independently target the same crown jewel asset class (turbine OT, predictive maintenance, manufacturing IP) despite different threat actors and vectors — a cross-regional pattern that only emerges at the synthesis layer.

Links to the four intelligence files in `intelligence/` for full detail.

### Section 3 — Reading the Intelligence

A brief guide to interpreting the pipeline's outputs, written for a risk professional who is not familiar with the format:

**Three-Pillar Brief Structure** — every regional report answers three questions in sequence:
- *Why* — the geopolitical or structural driver (what macro condition is creating the threat environment?)
- *How* — the exposure pathway (which business assets are in the firing line and how?)
- *So What* — the business consequence (VaCR figure, scenario financial rank, effect on delivery capacity)

**Admiralty Scale** — every signal is rated on two axes before it reaches the report:
- Source reliability: A (always reliable) → F (cannot be judged)
- Information credibility: 1 (confirmed by other sources) → 6 (cannot be judged)
- `B2` = usually reliable source, probably true. `E5` = untested source, unconfirmed signal.
- These ratings propagate from triage through to the board report so executives see calibrated confidence, not binary alerts.

**VaCR figures** — Value-at-Cyber-Risk figures come from a separate enterprise CRQ application and are treated as immutable inputs. The pipeline does not calculate them — it contextualises them. The $22M for AME is not an estimate produced by this system; it is the pre-calculated enterprise figure that the pipeline couples with live intelligence to explain *why that exposure is currently active*.

**Signal type** — every brief is classified before writing: Event (a specific confirmed incident), Trend (a sustained pattern building over time), or Mixed (a trend that has materialized into a specific event). This classification drives the prose and the forward-looking statement at the end of each brief.

### Section 4 — How Agents Produce This

Explains the pipeline for a risk professional — framed around *what it means for intelligence quality*, not code.

**Parallel regional analysis** — five regional intelligence teams run simultaneously, not sequentially. Each region gets its own dedicated triage agent (Gatekeeper) and, for escalated regions, a dedicated analytical agent (Regional Analyst). A pipeline run that would take a human analyst team hours completes in minutes.

**Triage by dedicated agents (Gatekeeper)** — before any intelligence is written, a dedicated triage agent reads the raw signals for each region and makes one decision: ESCALATE, MONITOR, or CLEAR. Only escalated regions get full analytical treatment. This prevents noise from reaching the board and keeps clear regions on a fast path — confirming stability rather than ignoring it.

**Intelligence writing by dedicated agents (Regional Analyst)** — for escalated regions, a dedicated analytical agent reads the geo signals, cyber signals, YouTube OSINT, and the empirical master scenario register, then writes the three-pillar brief. The agent owns scenario determination — it validates the keyword mapper's hint against the empirical register and overrides it if the evidence warrants. This is the quality gate that prevents low-fidelity pattern matching from reaching the board.

**Mandatory quality gates** — every brief passes through a jargon auditor before it is accepted. The auditor rejects any report containing technical SOC language (CVEs, TTPs, MITRE ATT&CK references) or unsolicited budget advice. If rejected, the agent rewrites. The board receives intelligence written for executives, not security engineers — by design and by enforcement.

**Global synthesis (Global Builder + Validator)** — after all five regions complete, a synthesis agent reads every approved regional brief and produces the global executive summary. A separate devil's advocate agent then cross-checks the synthesis against the regional source data — verifying VaCR arithmetic, Admiralty consistency, and scenario mapping before the report is finalised. This two-agent check is what caught the compound risk finding (three independent actors, same target surface) in the last run.

**Empirical anchoring** — agents are bound to an empirical master scenario register for financial impact and event frequency rankings. They cannot invent statistics. When a brief says "Ransomware is ranked #1 globally by financial impact (37.6% of all losses)", that figure comes from the empirical register, not the model.

### Section 5 — What This Enables That Static Reports Cannot

Three specific capabilities that only exist because the pipeline is agentic and continuous:

1. **Velocity tracking** — the pipeline archives every run. After each cycle, a historical comparison layer examines the current run against all prior runs and assigns a velocity label per region: accelerating, stable, or improving. The global synthesis incorporates velocity into the board narrative. A static report cannot know whether a region is worsening or stabilising — it can only describe the current state.

2. **Cross-regional compound risk detection** — the global synthesis agent reads all five regional briefs simultaneously and looks for cross-regional patterns. The last run found that three independently-assessed threats (state collection in APAC, ransomware in AME, insider access in MED) all target the same crown jewel asset class. No individual regional analyst would have surfaced this — it only emerges at the synthesis layer, and only when all five regions are assessed in the same cycle.

3. **Auditable, reproducible intelligence** — every pipeline run writes a full audit trace capturing every agent decision, quality gate pass/fail, and rewrite event. Intelligence quality is not dependent on which analyst ran the process that day. The same signals, run through the same pipeline, produce the same calibrated output — with every decision logged and reviewable.

---

## Files to Create

| File | Source | Action |
|---|---|---|
| `demo/README.md` | Authored | Write from scratch per spec above |
| `demo/intelligence/global_summary.md` | `output/global_report.md` | Copy as-is |
| `demo/intelligence/regional_ame.md` | `output/regional/ame/report.md` | Copy as-is |
| `demo/intelligence/regional_apac.md` | `output/regional/apac/report.md` | Copy as-is |
| `demo/intelligence/regional_med.md` | `output/regional/med/report.md` | Copy as-is |

---

## Quality Criteria

- `demo/README.md` contains no developer jargon (no Python, no JSON, no CLI commands)
- Every claim in Section 2 is drawn from actual `output/` data files (no invented figures)
- Admiralty ratings and VaCR figures for escalated regions match `run_manifest.json`; for clear regions, Admiralty and dominant pillar are sourced from `output/regional/{region}/data.json` (these fields are not present in `run_manifest.json` for clear regions)
- The intelligence files in `intelligence/` are byte-for-byte copies of the pipeline output — no editorial changes
- A risk professional with no AI background can read the full document and understand both what the intelligence says and what the agent framework adds

---

## Out of Scope

- HTML dashboard (requires a live server to render correctly — not suitable for static GitHub browsing)
- Live GitHub Pages deployment
- Code walkthroughs or developer onboarding
- Explanation of how to run the pipeline
