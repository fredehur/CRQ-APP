# CRQ Geopolitical Intelligence Pipeline

A **Top-Down Cyber Risk Quantification (CRQ) agentic pipeline** built entirely with native Claude Code. No LangChain, LangGraph, or CrewAI — just subagents, hooks, and Python tools wired together as a Unix pipeline.

---

## What This Is

A **risk awareness platform** — not a security report tool.

Most CRQ systems calculate dollar risk. This system couples pre-calculated risk figures with live geopolitical and cyber intelligence to answer the one question that matters to a board:

> **"How does this threat affect our ability to deliver business results?"**

Built for a fictional renewable energy company (**AeroGrid Wind Solutions** — 75% Wind Turbine Manufacturing, 25% Global Service & Maintenance). Every output is framed in terms of turbine production capacity and service delivery continuity. Technical language is forbidden by design.

### Architectural Boundary

This is the **Intelligence & Synthesis layer only**. Value-at-Cyber-Risk (VaCR) numbers come from a separate enterprise CRQ application and are treated as immutable ground truth. This system does not calculate VaCR — it consumes, contextualizes, and reports it.

---

## Who It's For

The audience is the **whole organization (~30,000 employees)** — not just the security team:

| Audience | What they get |
|----------|--------------|
| Board of Directors | Global executive brief: total VaCR exposure, cross-regional patterns, compound risk |
| CISO / C-Suite | Weekly intelligence brief (Word .docx) — scenario, threat actor, intel findings, adversary activity, impact, tradecraft, actions |
| Regional Security Managers | Weekly INTSUM + flash alerts per region (Markdown + PDF) |
| Regional Operations | Region-specific threat brief anchored to local crown jewels and service continuity |
| Sales & Service Teams | Clear/monitor/escalated status for their region — actionable, not alarming |

**Clear signals are as valuable as alerts.** Knowing your region is stable is actionable intelligence, not absence of information.

---

## Quickstart

### Prerequisites

- [Claude Code](https://claude.ai/code) installed
- [uv](https://docs.astral.sh/uv/) installed

### Install & run

```bash
uv sync
uv run playwright install chromium   # required for PDF export
uv run python server.py              # http://localhost:8001
```

### Run the full pipeline

```
/run-crq
```

Runs the complete pipeline: OSINT collection, gatekeeper triage, regional analysis (5 regions in parallel), velocity analysis, trend synthesis, global report + devil's advocate validation, dashboard + PDF/PPTX/DOCX exports, archival.

### Other commands

| Command | Description |
|---------|-------------|
| `/crq-region APAC` | Re-run a single region without touching the other four |
| `/prime-crq` | Load full architecture context (agents, schemas, hooks, data flow) |
| `/prime-dev` | Pre-build ritual — engineering principles, team structure, protocol |
| `/validate-register` | Run VaCR source validation against the active risk register |

### Pipeline flags

| Flag | Effect |
|------|--------|
| `--window 30d` | OSINT collection window (default: `7d`) |
| `--deep` | Enable deep research pass |
| `--deep-scope=all` | Deep research for all regions, not just escalated |
| `--depth=quick\|standard\|deep` | Research depth per region (default: `standard`) |
| `--rsm` | Enable RSM brief generation |

### OSINT modes

| Mode | Trigger | Behaviour |
|------|---------|-----------|
| **Mock** (default) | No env vars | `osint_collector.py --mock` — reads from `data/mock_osint_fixtures/` |
| **Live** | `OSINT_LIVE=true` in `.env` | `osint_collector.py` — 3-pass LLM research loop with Tavily/DDG |

Seerist collection (`seerist_collector.py`) runs when `SEERIST_API_KEY` is set; mock mode otherwise. YouTube collection runs in both modes.

---

## Web Application

FastAPI web app on port **8001** with 9 tabs:

| Tab | Type | Purpose |
|-----|------|---------|
| **Overview** | Analyst workspace | Live intelligence picture — regional status, source signals, signal clusters, convergence/divergence |
| **Reports** | Stakeholder delivery | Generate and preview CISO, Board, and RSM deliverables |
| **Trends** | Analyst workspace | Longitudinal trend analysis across archived pipeline runs |
| **History** | Analyst workspace | Historical run log with per-region severity charts |
| **Risk Register** | Analyst workspace | CRQ scenario register — VaCR benchmarks, scenario validation, source cross-check |
| **Source Library** | Analyst workspace | OSINT + benchmark source browser — tier badges, filters, flag/block workflow |
| **Pipeline** | Analyst workspace | Visual pipeline architecture — node graph, agent roles, Admiralty scale reference |
| **Run Log** | Analyst workspace | Live pipeline execution log — phase progress, region outcomes, duration |
| **Config** | Analyst workspace | Intelligence sources, regional footprint, agent prompts (gear icon) |

**Overview** = analyst workspace (raw intelligence, internal). **Reports** = stakeholder delivery (polished, external).

---

## Agent Hierarchy

```
run-crq  (Orchestrator — opus)
│
├── [PARALLEL x 5 regions]
│   │
│   ├── OSINT tool chain (per region)
│   │     osint_collector.py → osint_signals.json          [geo + cyber unified]
│   │     seerist_collector.py → seerist_signals.json      [Tier 1 geopolitical]
│   │     youtube_collector.py → youtube_signals.json
│   │     scenario_mapper.py → scenario_map.json  (keyword hint, advisory only)
│   │     collection_gate.py → collection_quality.json
│   │
│   ├── gatekeeper-agent  (Triage — haiku)
│   │     Reads signal files + collection quality. Assesses credibility.
│   │     Assigns Admiralty rating. Routes: ESCALATE / MONITOR / CLEAR
│   │     Writes gatekeeper_decision.json — does NOT determine final scenario.
│   │
│   └── regional-analyst-agent  (Analysis — sonnet)  [ESCALATE only]
│         Owns scenario coupling — validates mapper hint against master_scenarios.json
│         Classifies signal as Event / Trend / Mixed
│         Writes 3-paragraph executive brief (Why → How → So What)
│         Writes sections.json, signal_clusters.json, data.json
│         └── Stop hooks: jargon, source attribution, sections schema
│
├── trend_analyzer.py  [Phase 2 — after fan-in]
├── trends-synthesis-agent  [Phase 2.5 — longitudinal patterns]
├── report_differ.py  [Phase 3 — cross-regional delta]
│
├── global-builder-agent  (Synthesis — sonnet)  [Phase 4]
│     Synthesizes all regional briefs → global_report.json
│     └── Stop hooks: JSON schema, deterministic validation, jargon
│
├── global-validator-agent  (Devil's Advocate — haiku)  [Phase 4b]
│     Read-only cross-check. APPROVED or REWRITE (max 2 cycles).
│
├── [Phase 5 — Dashboard & Export]
│     dashboard.html · board_report.pdf · board_report.pptx · ciso_brief.docx
│
├── [Phase 6 — Archive & Registry]
│     run_manifest.json · archived run · source registry · history.json
│
└── [Phase 7 — RSM Briefs, optional]
      rsm-formatter-agent (sonnet) → weekly INTSUMs per region
```

**Agents:**

| Agent | Model | Role |
|-------|-------|------|
| `gatekeeper-agent` | haiku | Triage — Admiralty rating, ESCALATE/MONITOR/CLEAR |
| `regional-analyst-agent` | sonnet | Three-pillar brief, scenario coupling, data.json |
| `global-builder-agent` | sonnet | Cross-regional synthesis → global_report.json |
| `global-validator-agent` | haiku | Devil's advocate cross-check |
| `rsm-formatter-agent` | sonnet | Weekly INTSUM + flash alerts for RSMs |
| `trends-synthesis-agent` | sonnet | Longitudinal trend patterns across archived runs |
| `threat-landscape-agent` | sonnet | Adversary patterns, scenario lifecycles, compound risks |
| `register-validator-agent` | sonnet | VaCR source validation against active risk register |

**Five operational regions:** APAC · AME (North America) · LATAM · MED (Mediterranean) · NCE (Northern & Central Europe)

---

## Intelligence Methodology

### Three-Pillar Brief Structure

Every regional intelligence brief follows the same structure:

1. **Why — Geopolitical Driver:** What macro-economic or political condition is creating the threat environment?
2. **How — Cyber Vector:** How is that condition manifesting as a specific threat to the company's assets?
3. **So What — Business Impact:** What is the financial consequence? States VaCR exactly. Names the scenario and its financial rank.

### Admiralty Scale Ratings

Every gatekeeper decision includes a two-part reliability rating:

- **Source reliability** (A–D): A = completely reliable, D = not usually reliable
- **Information credibility** (1–4): 1 = confirmed, 4 = doubtful

These ratings propagate from triage through to the board report.

### Scenario Coupling

The regional analyst (Sonnet) owns the scenario determination — not the keyword scorer. The OSINT tool chain provides a hint (`scenario_map.json`), but the analyst validates against `master_scenarios.json` and overrides with reasoned judgment if warranted.

### Velocity Analysis

After each run, `trend_analyzer.py` computes velocity per region by comparing the current run against archived runs. Each region gets a `velocity` label: `accelerating`, `stable`, or `improving`.

---

## Quality Gates

The pipeline enforces quality through **15 stop hooks** — validators that run after each agent and force rewrites on failure (exit code 2, max 3 retries):

- **Jargon auditor** — forbids technical cyber jargon, SOC language, unsolicited budget advice, pipeline language, and generic source labels (5 categories)
- **Source attribution** — every "evidenced" claim must cite a named source from `signal_clusters.json`
- **Sections validator** — `sections.json` schema + completeness
- **JSON auditor** — global report schema: required keys, types, regional entries
- **Deterministic validation** — Python does VaCR arithmetic, Admiralty consistency, scenario cross-check, phantom region guard (not the model)
- **Grounding validator** — validates agent claims against source data
- **RSM brief auditor** — INTSUM/FLASH structure, Admiralty field, watch list depth
- **Regional analyst stop gate** — final quality check on regional output
- **Trend / threat-landscape / register-validation auditors** — schema + completeness for synthesis outputs

---

## Project Structure

```
.claude/
  commands/          # Slash commands (run-crq, crq-region, architect, prime-crq, etc.)
  agents/            # 8 sub-agent definitions with stop hooks
  hooks/
    validators/      # 15 quality gate scripts
    telemetry/       # Tool-level trace hooks

data/
  company_profile.json         # AeroGrid — crown jewels, industry footprint
  master_scenarios.json        # Empirical baseline (9 scenario types)
  mock_crq_database.json       # Region-keyed CRQ scenarios (VaCR = immutable input)
  regional_footprint.json      # Per-region crown jewels, sites, operational context
  sources.db                   # Persistent source registry (SQLite)
  registers/                   # Named CRQ risk registers
  mock_osint_fixtures/         # Mock signals per region

tools/                         # ~50 Python utility scripts (collectors, exporters, validators)
static/                        # index.html + app.js (Tailwind CSS dashboard)
server.py                      # FastAPI backend (~70 API routes)

output/
  pipeline/                    # run_manifest.json, global_report.json, dashboard.html, history
  regional/{region}/           # data.json, sections.json, signals, clusters per region
  deliverables/                # board PDF, PPTX, CISO DOCX
  delivery/                    # RSM briefs, flash alerts, delivery log
  validation/                  # Register validation results + cache
  runs/{timestamp}/            # Immutable archived runs
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python `uv`, requires >= 3.14 |
| Server | FastAPI + uvicorn (port 8001) |
| Frontend | Vanilla HTML/JS + Tailwind CSS |
| PDF export | Playwright + Jinja2 |
| PPTX export | python-pptx |
| DOCX export | python-docx |
| Intelligence | Anthropic API (live OSINT), DuckDuckGo Search |
| Streaming | SSE via sse-starlette |
| Source registry | SQLite (`data/sources.db`) |

---

## Architecture Notes

- **Model assignment is fixed in YAML frontmatter** — haiku for triage/validation, sonnet for analysis/synthesis, opus for orchestration.
- **Parallel fan-out** — all 5 regional pipelines run simultaneously, then fan-in for global synthesis.
- **Filesystem as state** — every agent handoff is a file. No conversation state carries between agents.
- **Scenario coupling is analytical, not mechanical** — the regional analyst reads `master_scenarios.json` directly and owns the determination.
- **Devil's advocate validation** — `global-validator-agent` cross-checks the global report against regional source data before the pipeline advances.
- **Deterministic arithmetic** — `validate_global_report.py` does the math in Python, not the model.
- **Admiralty propagation** — reliability ratings flow from gatekeeper → data.json → global_report.json → dashboard.
- **Source attribution** — signal files carry `sources: [{name, url}]`. CISO briefs, board reports, and the dashboard all render real citations, not generic labels.
