# CRQ Geopolitical Intelligence Pipeline

A **Top-Down Cyber Risk Quantification (CRQ) agentic pipeline** built entirely with native Claude Code features. No LangChain, LangGraph, or CrewAI — just subagents, hooks, and Python tools wired together as a Unix pipeline.

---

## What This Is

This is a **risk awareness platform** — not a security report tool.

Most CRQ systems calculate dollar risk. This system does something different: it couples those pre-calculated risk figures with live geopolitical and cyber intelligence to answer the one question that matters to a board:

> **"How does this threat affect our ability to deliver business results?"**

The system is built for **AeroGrid Wind Solutions (Anonymized)** — a renewable energy company, 75% Wind Turbine Manufacturing / 25% Global Service & Maintenance. Every output is framed in terms of turbine production capacity and service delivery continuity. Technical language is forbidden by design.

### Architectural Boundary

This is the **Intelligence & Synthesis layer only**. Value-at-Cyber-Risk (VaCR) numbers come from a separate enterprise CRQ application and are treated as immutable ground truth. This system does not calculate VaCR — it consumes, contextualizes, and reports it.

---

## Who It's For

The audience is the **whole organization (~30,000 employees)** — not just the security team:

| Audience | What they get |
|----------|--------------|
| Board of Directors | Global executive brief: total VaCR exposure, cross-regional patterns, compound risk |
| CISO / C-Suite | Regional escalation status, Admiralty-rated intelligence, velocity trends |
| Regional Operations | Region-specific threat brief anchored to local crown jewels and service continuity |
| Sales & Service Teams | Clear/monitor/escalated status for their region — actionable, not alarming |

**Clear signals are as valuable as alerts.** Knowing your region is stable is actionable intelligence, not absence of information. The system routes quiet regions through a fast "clear" path so the org isn't flooded with noise.

---

## Intelligence Methodology

### The CRQ Scenario Register as Shared Risk Language

The system's analytical backbone is `data/master_scenarios.json` — a master scenario register with empirical rankings for Financial Impact, Event Frequency, and Records Affected across 9 global scenario types (Ransomware, System Intrusion, Insider Misuse, etc.).

Every threat assessment is anchored to this register. Agents cannot invent statistics. When a regional brief says "Ransomware, ranked #1 globally by financial impact," that ranking comes from the empirical baseline — not the model.

### Three-Pillar Brief Structure

Every regional intelligence brief follows the same structure:

1. **Why — Geopolitical Driver:** What macro-economic or political condition is creating the threat environment? Framed as state actor intent, economic pressure, or structural instability — never technical activity.

2. **How — Cyber Vector:** How is that condition manifesting as a specific threat to the company's assets? Connected to crown jewels and business operations — never attack mechanics or CVEs.

3. **So What — Business Impact:** What is the financial consequence? States VaCR exactly. Names the scenario and its financial rank. Closes with a forward-looking statement — what to watch for next.

### Admiralty Scale Ratings

Every gatekeeper decision includes a two-part reliability rating:

- **Source reliability** (A–D): A = always reliable, D = untested
- **Information credibility** (1–4): 1 = confirmed, 4 = cannot be judged

Example: `B2` = usually reliable source, probably true information. These ratings propagate from triage through to the board report, giving executives a calibrated view of intelligence confidence.

### Scenario Coupling Ownership

The regional analyst (Sonnet) owns the scenario determination — not the keyword scorer. The OSINT tool chain provides a hint (`scenario_map.json`), but the analyst reads `master_scenarios.json` directly, validates the hint against actual geo and cyber signals, and overrides it with reasoned judgment if warranted. This is the critical quality gate that prevents low-fidelity pattern matching from reaching the board.

### Event vs. Trend Classification

Every brief is classified before writing:

- **Event** — a specific, recent incident
- **Trend** — a sustained, worsening pattern building over time
- **Mixed** — a pre-existing trend that has now materialized into a specific incident

The classification drives the brief's prose. A trend brief describes trajectory and direction; an event brief describes what happened and what it means immediately. The `signal_type` field propagates into `data.json` for downstream dashboards.

### Velocity Analysis

After each run, `trend_analyzer.py` computes velocity per region by comparing the current run against archived runs. Each region gets a `velocity` label: `accelerating`, `stable`, or `improving`. The global executive summary synthesizes this into a global velocity narrative — is overall risk accelerating or stabilizing?

---

## Agent Hierarchy

```
run-crq  (Orchestrator — opus)
│
├── [PARALLEL × 5 regions]
│   │
│   ├── OSINT tool chain (per region)
│   │     geo_collector.py → geo_signals.json
│   │     cyber_collector.py → cyber_signals.json
│   │     scenario_mapper.py → scenario_map.json  (keyword hint, advisory only)
│   │
│   ├── gatekeeper-agent  (Triage — haiku)
│   │     Reads signal files. Assesses credibility. Assigns Admiralty rating.
│   │     Routes: ESCALATE / MONITOR / CLEAR
│   │     Writes gatekeeper_decision.json — does NOT determine final scenario.
│   │
│   └── regional-analyst-agent  (Analysis — sonnet)  [ESCALATE only]
│         Owns scenario coupling — validates mapper hint against master_scenarios.json
│         Classifies signal as Event / Trend / Mixed
│         Writes 3-paragraph executive brief (Why → How → So What)
│         Writes signal_clusters.json (source clusters for dashboard + attribution)
│         Updates data.json with primary_scenario, financial_rank, signal_type
│         └── Stop hook → regional-analyst-stop.py
│               ├── jargon-auditor.py (forbidden language gate)
│               └── source-attribution-auditor.py (evidenced claims must cite named sources)
│
├── trend_analyzer.py  [after fan-in]
│     Computes velocity per region, patches data.json, writes trend_brief.json
│
├── report_differ.py
│     Cross-regional keyword delta brief
│
├── global-builder-agent  (Synthesis — sonnet)
│     Reads all approved regional briefs + trend_brief.json + data.json files
│     Synthesizes executive_summary: cross-regional patterns, compound risk, velocity narrative
│     Writes global_report.json
│     ├── Stop hook → json-auditor.py (schema validation)
│     ├── Stop hook → validate_global_report.py (deterministic: VaCR arithmetic,
│     │     Admiralty consistency, scenario cross-check, phantom region guard)
│     └── Stop hook → jargon-auditor.py
│
└── global-validator-agent  (Devil's Advocate — haiku)
      Read-only cross-check of global_report.json against regional source data
      Returns APPROVED or REWRITE (max 2 cycles, then circuit breaker)

RSM Dispatch (separate path, triggered by scheduler / rsm_dispatcher.py)
│
└── rsm-formatter-agent  (sonnet)
      Reads seerist_signals, region_delta, cyber_signals, audience_config
      Writes weekly INTSUM brief and/or flash alert per region
      └── Stop hook → rsm-formatter-stop.py
            └── rsm-brief-auditor.py (structure, ADM format, WATCH LIST depth, jargon)
```

**Five operational regions:** APAC · AME (North America) · LATAM · MED (Mediterranean) · NCE (Northern & Central Europe)

---

## Quickstart

### Prerequisites

- [Claude Code](https://claude.ai/code) installed
- [uv](https://docs.astral.sh/uv/) installed

### Install dependencies

```bash
uv sync
```

### Install Playwright (required for PDF export)

```bash
uv run playwright install chromium
```

### Run the full pipeline

```
/run-crq
```

This single command runs the complete pipeline:

| Phase | Action |
|-------|--------|
| 0 | Validate CRQ database schema, initialize trace log |
| 1 | OSINT collection → Gatekeeper triage → Regional analysis × 5 (parallel) |
| 2 | Velocity analysis — trend computation across archived runs |
| 3 | Cross-regional delta brief |
| 4 | Global JSON report + devil's advocate validation (max 2 rewrite cycles) |
| 5 | HTML dashboard, PDF board report, PowerPoint board report |
| 6 | Write run manifest, archive run to `output/runs/{timestamp}/`, finalize |

### Rebuild from existing reports

```
/run-crq rebuild
```

Skips Phases 1–2 and re-synthesizes the global report and exports from existing regional data.

### Run a single region

```
/crq-region APAC
```

Re-runs the pipeline for one region without touching the other four. Useful when fresh intelligence arrives mid-cycle.

### Load architecture context

```
/prime-crq
```

Hot-loads the full architecture reference: agent hierarchy, file-passing contract, `data.json` schema, stop hook wiring, mock configuration, and all tool commands. Run this before any pipeline development work.

---

## Output Files

All outputs are written to `output/` and archived immutably per run:

```
output/
  run_manifest.json              # Master state — pipeline ID, per-region status/severity/VaCR
  global_report.json             # Structured JSON global report (primary machine-readable output)
  global_report.md               # Markdown render of global report
  dashboard.html                 # Tailwind CSS executive dashboard with audit trace
  board_report.pdf               # PDF export for board distribution
  board_report.pptx              # PowerPoint export for board presentation
  system_trace.log               # Full pipeline observability log
  trend_brief.json               # Cross-run velocity analysis
  regional/
    {region}/
      data.json                  # Always written — status, severity, VaCR, admiralty, velocity,
                                 #   primary_scenario, financial_rank, signal_type, rationale
      report.md                  # Only for escalated regions — finalized 3-paragraph executive brief
      gatekeeper_decision.json   # Admiralty-rated triage decision + rationale
      geo_signals.json           # Geopolitical lead indicators (OSINT)
      cyber_signals.json         # Cyber threat signals (OSINT)
      scenario_map.json          # Keyword mapper hint (advisory — analyst validates)
  latest/                        # Symlink to most recent completed run
  runs/
    {timestamp}/                 # Immutable archived runs
```

### data.json Contract

Every region produces a `data.json` after the gatekeeper decision. This is the canonical state object that downstream dashboards and the global report read from:

```json
{
  "region": "AME",
  "status": "escalated",
  "severity": "CRITICAL",
  "severity_score": 3,
  "primary_scenario": "Ransomware",
  "financial_rank": 1,
  "vacr_exposure_usd": 22000000,
  "admiralty": "B2",
  "rationale": "Ransomware signals corroborated across two independent sources with recent sector precedent.",
  "velocity": "accelerating",
  "dominant_pillar": "Cyber",
  "signal_type": "Trend",
  "report_path": "regional/ame/report.md"
}
```

A UI can render escalated regions as threat cards and clear/monitor regions as status badges by reading `status` from `data.json`. Clear signals (`status: "clear"`) are first-class outputs — they confirm a region is stable, which is as operationally valuable as an escalation.

---

## Hooks & Quality Gates

| Hook | Trigger | What it checks |
|------|---------|----------------|
| `jargon-auditor.py` | Stop on `regional-analyst-agent` | Forbidden language in `report.md` |
| `source-attribution-auditor.py` | Stop on `regional-analyst-agent` | Every "evidenced" claim cites a named source from `signal_clusters.json` |
| `json-auditor.py` | Stop on `global-builder-agent` | JSON schema: required keys, types, regional threat entries |
| `validate_global_report.py` | Stop on `global-builder-agent` | Deterministic: VaCR arithmetic, Admiralty consistency vs `gatekeeper_decision.json`, scenario cross-check vs `data.json`, phantom region guard |
| `jargon-auditor.py` | Stop on `global-builder-agent` | Forbidden language in `global_report.json` |
| `rsm-brief-auditor.py` | Stop on `rsm-formatter-agent` | INTSUM/FLASH structure, valid ADM field, WATCH LIST ≥3 items, correct reply line, jargon |
| `crq-schema-validator.py` | Phase 0 | `data/mock_crq_database.json` schema before pipeline runs |

**Jargon gate** enforces three categories of forbidden output:

- **Technical cyber jargon** — CVE identifiers, IP addresses, malware hashes
- **SOC operational language** — TTPs, IoCs, MITRE ATT&CK, lateral movement, C2
- **Unsolicited budget advice** — procurement, vendor recommendations, tool purchases

**Source attribution gate** closes the hallucination vector: any claim marked "evidenced" must cite a named source from `signal_clusters.json`. Generic labels (`"Cyber Signal"`, `"Geo Signal"`) do not satisfy the requirement.

**Deterministic validation** (`validate_global_report.py`) replaces the previous LLM-based arithmetic check — Python does the math, not the model.

All audit failures return `exit(2)` and force agent rewrite with the full violation output passed inline. Circuit breaker at `output/.retries/{label}.retries` caps retries at 3.

---

## Data

```
data/
  company_profile.json              # AeroGrid Wind Solutions — crown jewels, industry footprint
  master_scenarios.json             # Empirical global baseline (9 scenario types, financial/frequency/records ranks)
  mock_crq_database.json            # Region-keyed CRQ scenarios (VaCR = immutable input from enterprise CRQ)
  mock_osint_fixtures/
    {region}_geo.json               # Mock geopolitical signals per region
    {region}_cyber.json             # Mock cyber threat signals per region
  mock_threat_feeds/
    {region}_feed.json              # Legacy flat feed schema (used by write_region_data fallback)
```

All agents run in mock mode by default. No live API keys or external data sources are required.

**Mock scenario (escalated regions):**
- AME: CRITICAL, Ransomware, $22M VaCR
- APAC: HIGH, System Intrusion, $18.5M VaCR
- MED: MEDIUM, Insider Misuse, $4.2M VaCR

**Mock scenario (quiet regions):**
- LATAM: LOW — clear, no active threat
- NCE: LOW — clear, no active threat

---

## Architecture Notes

- **Model assignment is fixed in YAML frontmatter** — haiku for triage/validation, sonnet for analysis and synthesis, opus for orchestration.
- **Parallel fan-out** — all 5 regional pipelines run simultaneously via background Tasks, then fan-in for global synthesis.
- **Filesystem as state** — every agent handoff is a file. No conversation state carries between agents.
- **Scenario coupling is analytical, not mechanical** — the regional analyst reads `master_scenarios.json` directly and owns the scenario determination. The keyword mapper is a hint, not a verdict.
- **Devil's advocate validation** — `global-validator-agent` cross-checks the global report against regional source data before the pipeline advances. Checks VaCR arithmetic, Admiralty consistency, scenario mapping, and phantom regions.
- **Admiralty Scale propagation** — the gatekeeper's reliability rating flows from `gatekeeper_decision.json` → `data.json` → `global_report.json` → dashboard. Every intelligence claim carries its confidence level.
- **Velocity tracking** — `trend_analyzer.py` reads archived runs and computes directional movement per region. The global summary synthesizes into a board-level velocity narrative.
- **Dashboard uses Tailwind CSS via CDN** — dark-mode executive dashboard with Admiralty badges, velocity arrows, and a collapsible audit trace panel.
- **Disler Behavioral Protocol** — all agents operate as Unix CLI pipes: zero preamble, zero sycophancy, filesystem as state, assume hostile auditing. Output goes to files, not conversation.

---

## Tools

| Tool | Description |
|------|-------------|
| `geo_collector.py <REGION> [--mock]` | Collect geopolitical signals → `geo_signals.json` |
| `cyber_collector.py <REGION> [--mock]` | Collect cyber threat signals → `cyber_signals.json` |
| `scenario_mapper.py <REGION> [--mock]` | Keyword-match signals to scenario → `scenario_map.json` (hint only) |
| `geopolitical_context.py <REGION>` | Company profile + regional context + empirical baseline |
| `threat_scorer.py <REGION>` | Maps severity → score (1/2/3) + scenario composition |
| `report_differ.py` | Cross-regional keyword delta brief |
| `trend_analyzer.py` | Velocity analysis across archived runs → `trend_brief.json` |
| `write_region_data.py <REGION> <status>` | Write regional `data.json` after gatekeeper decision |
| `write_gatekeeper_decision.py <REGION>` | Pipe JSON to write gatekeeper decision file |
| `write_manifest.py` | Assemble `run_manifest.json` from all regional `data.json` files |
| `archive_run.py` | Archive current run to `output/runs/{timestamp}/` + update `output/latest/` |
| `build_dashboard.py` | JSON + trace → HTML dashboard + MD export |
| `export_pdf.py [out.pdf]` | Export board PDF (Playwright + Jinja2) — includes named source citations per region |
| `export_pptx.py [out.pptx]` | Export board PPTX (python-pptx) — includes named source citations per region |
| `audit_logger.py <EVENT> <MESSAGE>` | Append timestamped event to `system_trace.log` |
| `seerist_collector.py <REGION> [--mock]` | Collect Seerist geopolitical signals → `seerist_signals.json` |
| `delta_computer.py <REGION>` | Diff current vs previous Seerist signals → `region_delta.json` |
| `threshold_evaluator.py [--force-weekly] [--check-flash]` | Evaluate audience routing → `routing_decisions.json` |
| `rsm_dispatcher.py --weekly [--mock]` | Generate + deliver weekly INTSUM for all RSMs |
| `rsm_dispatcher.py --check-flash [--mock]` | Evaluate + dispatch flash alerts |
| `notifier.py <routing_decisions.json> [--mock]` | Deliver briefs per routing decisions → `delivery_log.jsonl` |
| `scheduler.py --once` | Run all due scheduler jobs once |

All tools are invoked via `uv run python tools/<tool>`.

---

## Dependencies

Managed via `uv`. Defined in `pyproject.toml`.

| Package | Purpose |
|---------|---------|
| `fastapi` | Web server for SSE dashboard |
| `fpdf2` | PDF export |
| `jinja2` | HTML templating for PDF/dashboard |
| `playwright` | Browser-based PDF rendering |
| `python-dotenv` | Environment variable management |
| `python-pptx` | PowerPoint export |
| `sse-starlette` | Server-Sent Events for live pipeline updates |
| `uvicorn` | ASGI server |
