# The CRQ Intelligence Pipeline — How It Works

## What the Pipeline Does

The CRQ Intelligence Pipeline is an automated multi-agent system that monitors geopolitical and cyber threats across AeroGrid's five global regions and produces a quantified, board-ready risk report — fully autonomously, in a single run.

**Input:** Live or simulated OSINT signals from 5 regions
**Output:** A $-denominated board report with regional threat briefs, a global executive summary, and an HTML dashboard

---

## The Four Phases

### Phase 1 — Signal Collection (runs in parallel across all 5 regions simultaneously)

For each region, three tools run in sequence:
- **Geo Collector** → collects geopolitical signals (government actions, trade policy, instability indicators)
- **Cyber Collector** → collects cyber threat signals (threat actor activity, sector targeting, incidents)
- **Scenario Mapper** → maps collected signals to the 9 known cyber risk scenario types

Each region produces three output files: `geo_signals.json`, `cyber_signals.json`, `scenario_map.json`

### Phase 2 — Triage (Gatekeeper Agent, per region)

A dedicated triage agent reads the signal files and makes one decision per region:

- **ESCALATE** — active, credible threat. Triggers full analysis.
- **MONITOR** — signals present but below threshold. Logged and tracked.
- **CLEAR** — no meaningful signal. Region is confirmed safe.

Escalation threshold: scenario must rank in the **top 4 globally by financial impact**.

Each decision includes an Admiralty rating (source reliability + information credibility, e.g. B2 = reliable source, probably true).

### Phase 3 — Regional Analysis (Regional Analyst Agent, escalated regions only)

For each escalated region, a dedicated analyst agent:
- Reads all signal files + company profile + master scenario data
- Writes an executive brief (Why → How → So What structure)
- Couples the threat to a specific crown jewel
- Records the primary scenario, financial rank, signal type (Event / Trend / Mixed), and VaCR exposure figure

Output: `report.md` + updated `data.json` per region

### Phase 4 — Global Synthesis

- **Global Builder Agent** reads all 5 regional outputs and synthesizes one global board report
- **Global Validator Agent** cross-checks the report against regional data (devil's advocate)
- Final output: `global_report.json`, `global_report.md`, `dashboard.html`, `board_report.pdf`, `board_report.pptx`

---

## Agent Hierarchy

```
Orchestrator (Claude Opus)
├── 5x Regional Pipelines — run simultaneously
│   ├── Gatekeeper Agent (Claude Haiku) — triage
│   └── Regional Analyst Agent (Claude Sonnet) — brief + data
├── Global Builder Agent (Claude Sonnet) — synthesis
└── Global Validator Agent (Claude Haiku) — cross-check
```

**Model selection logic:**
- Haiku for triage and validation (fast, cheap, binary decisions)
- Sonnet for analysis and synthesis (reasoning depth required)
- Opus for orchestration (manages the entire pipeline)

---

## Quality Gates

Two deterministic hooks enforce quality — the pipeline cannot complete without passing both:

| Gate | Trigger | What it checks |
|---|---|---|
| Jargon Auditor | Regional + global analyst completion | Blocks SOC language, CVEs, technical jargon — reports must be board-readable |
| JSON Auditor | Global builder completion | Validates schema: required keys, correct types, all 5 regions present |

Each gate has a circuit breaker: 3 failures → force-approve + escalate to human.

---

## Output Files Every Run Produces

| File | Purpose |
|---|---|
| `run_manifest.json` | Master state: all 5 regions, status, severity, VaCR, paths |
| `regional/{region}/data.json` | Full schema for every region (escalated or clear) |
| `regional/{region}/report.md` | Executive brief (escalated regions only) |
| `global_report.json` | Structured global board report |
| `dashboard.html` | Self-contained Tailwind executive dashboard |
| `board_report.pdf` | Export-ready PDF |
| `board_report.pptx` | Export-ready PowerPoint |
