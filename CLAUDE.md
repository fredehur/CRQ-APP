# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Top-Down CRQ (Cyber Risk Quantification) Agentic Pipeline** built entirely with native Claude Code features — no LangChain, LangGraph, or CrewAI. It is a multi-agent geopolitical and cyber risk intelligence system that processes regional threat data and produces executive board reports.

**Client:** AeroGrid Wind Solutions (Anonymized) — Renewable Energy, 75% Wind Turbine Manufacturing / 25% Global Service & Maintenance.

**Architectural Boundary:** This system is strictly the **Intelligence & Synthesis layer**. VaCR numbers come from a separate enterprise CRQ application and are treated as immutable ground truth. This system does NOT calculate VaCR — it consumes, contextualizes, and reports it.

The system is scaffolded by a single Meta-Agent command (`/architect`) that builds the entire project autonomously.

## Product Framing (important — shapes every decision)

This is a **risk awareness platform**, not a security report tool. Key principles:

- The **CRQ scenario register** (`data/mock_crq_database.json`) is the shared risk language across the organization — everything couples back to it
- Pipeline couples quantified scenarios with live intelligence to produce business awareness
- **Audience is the whole org (~30k employees):** CISO, board, regional ops, sales, service teams — not just security engineers
- Agents write for business operators: *"How does this threat affect our ability to deliver turbines and maintain wind farms?"*
- **Clear signals are as valuable as alerts** — knowing your region is fine is actionable intelligence, not absence of information
- Every output must answer: *"How does this threat affect the company's ability to deliver business results?"*

## Engineering Protocol (MANDATORY — applies every session)

1. **Teams first:** Non-trivial tasks (multi-file, multi-step) → `TeamCreate` before touching code.
2. **Roles:** Opus orchestrates (never implements). Sonnet builds. Sonnet validates. Haiku triages.
3. **Builder/Validator pairing:** Every builder output verified by a separate validator agent before acceptance.
4. **Parallel by default:** Independent tasks run with `run_in_background: true`. Never serialize what can parallelize.
5. **Self-validate via stop hooks:** Agents prove completion — they do not claim it.
6. **Context discipline:** Delegate token-heavy work to sub-agents. Orchestrator stays lean.
7. **Clean up:** `TeamDelete` after task complete. Hard reset.
8. **Run `/prime-dev` before any build session.** Full principles: `docs/superpowers/specs/agent-design-principles.md`

## Commands

All commands use `uv` as the Python package manager:

```bash
uv run python tools/geopolitical_context.py <REGION>              # Company profile + regional feed context + empirical baseline
uv run python tools/geo_collector.py <REGION> [--mock]            # Collect geo signals → output/regional/{region}/geo_signals.json
uv run python tools/cyber_collector.py <REGION> [--mock]          # Collect cyber signals → output/regional/{region}/cyber_signals.json
uv run python tools/scenario_mapper.py <REGION> [--mock]          # Map signals → output/regional/{region}/scenario_map.json
uv run python tools/threat_scorer.py <REGION>                     # Maps HIGH/CRITICAL/MEDIUM/LOW → severity score + scenario composition
uv run python tools/report_differ.py                              # Cross-regional keyword delta brief
uv run python tools/audit_logger.py <EVENT> <MESSAGE>             # Append to output/system_trace.log
uv run python tools/write_gatekeeper_decision.py <REGION>         # Write gatekeeper_decision.json from stdin JSON
uv run python tools/write_region_data.py <REGION> <escalated|monitor|clear>  # Write regional data.json after gatekeeper
uv run python tools/write_manifest.py                             # Assemble run_manifest.json from all data.json
uv run python tools/archive_run.py                                # Archive current run to output/runs/{timestamp}/ + update output/latest/
uv run python tools/trend_analyzer.py                             # Compute velocity per region from archived runs
uv run python tools/build_dashboard.py                            # Build HTML dashboard + MD export from JSON
uv run python tools/export_pdf.py [out.pdf]                       # Export board PDF (Playwright + Jinja2); defaults to output/board_report.pdf
uv run python tools/export_pptx.py [out.pptx]                     # Export board PPTX (python-pptx); defaults to output/board_report.pptx

# Validate the CRQ database schema
uv run python .claude/hooks/validators/crq-schema-validator.py data/mock_crq_database.json

# Run the jargon auditor manually
uv run python .claude/hooks/validators/jargon-auditor.py <report_path> <label>

# Run the JSON schema auditor manually
uv run python .claude/hooks/validators/json-auditor.py <json_path> <label>
```

## Claude Code Slash Commands

| Command | Location | Description |
|---|---|---|
| `/architect` | `.claude/commands/` | Builds the entire system from scratch (run once to scaffold) |
| `/run-crq` | `.claude/commands/` | Runs the full pipeline — fans out 5 regional Tasks in parallel, synthesizes global report |
| `/crq-region <REGION>` | `.claude/commands/` | Re-runs a single region without touching the other four |

## Sub-Agents (`.claude/agents/`)

Sub-agents are spawned by `run-crq` via the Task tool. They are not invoked directly.

| Agent | Model | Role |
|---|---|---|
| `gatekeeper-agent` | haiku | Pure triage — reads signal files, assigns Admiralty rating, returns ESCALATE/MONITOR/CLEAR |
| `regional-analyst-agent` | sonnet | Owns scenario coupling + event/trend classification + writes three-pillar executive brief + updates data.json |
| `global-builder-agent` | sonnet | Synthesizes all regional briefs into global board JSON report |
| `global-validator-agent` | haiku | Devil's advocate — cross-checks global report against regional data files |

## Architecture

### Agent Hierarchy

```
run-crq (Orchestrator slash command, opus) — logs all events to output/system_trace.log
├── [PARALLEL via Task fan-out] 5x regional pipelines spawned simultaneously
│   ├── OSINT tool chain: geo_collector → cyber_collector → scenario_mapper
│   ├── gatekeeper-agent (Sub-agent, haiku) — triage, Admiralty rating, ESCALATE/MONITOR/CLEAR
│   └── regional-analyst-agent (Sub-agent, sonnet) — scenario coupling, brief, data.json update
│       └── Stop hook → jargon-auditor.py
├── [SEQUENTIAL after fan-in] global-builder-agent (Sub-agent, sonnet) — synthesis only
│   ├── Stop hook → json-auditor.py (validates output/global_report.json schema)
│   └── Stop hook → jargon-auditor.py (validates output/global_report.json content)
└── [SEQUENTIAL] global-validator-agent (Sub-agent, haiku) — devil's advocate cross-check
```

### Disler Behavioral Protocol

All agents enforce: Act as Unix CLI pipe (not chatbot), Zero Preamble & Zero Sycophancy, Filesystem as State, Assume Hostile Auditing.

### Empirical Scenario Anchoring

All threat feeds and geopolitical context cross-reference `data/master_scenarios.json` — the Master Scenario List with empirical Financial Impact, Event Frequency, and Records Affected rankings. Agents MUST cite these baselines; they cannot invent statistics.

### Scenario Coupling — Regional Analyst Owns It

The `scenario_mapper.py` keyword scorer provides a hint only. The `regional-analyst-agent` reads `master_scenarios.json` and `company_profile.json` directly, reasons over signal files, and makes the authoritative scenario determination. It writes back `primary_scenario`, `financial_rank`, and `signal_type` to `data.json`. This is the source of truth for downstream consumers.

### Event vs Trend Classification

Every regional brief classifies the signal as:
- **Event** — a specific, recent incident
- **Trend** — a sustained, worsening pattern over time
- **Mixed** — a trend that has materialized into a specific event

`signal_type` is stored in `data.json` and reflected in the brief prose.

### Regional Scope

Five operational regions: **APAC**, **AME** (North America), **LATAM**, **MED** (Mediterranean), **NCE** (Northern & Central Europe). **Global** is a synthesis layer only — no raw threat feed. Regions are routed ESCALATE/MONITOR/CLEAR by the gatekeeper based on `scenario_map.financial_rank ≤ 4` (top-4 by financial impact).

### File Passing Between Agents

- OSINT chain writes `geo_signals.json`, `cyber_signals.json`, `scenario_map.json` per region
- Gatekeeper writes `output/regional/{region}/gatekeeper_decision.json` (admiralty, dominant_pillar, rationale, scenario_match hint)
- `write_region_data.py` reads `gatekeeper_decision.json` and propagates `admiralty`, `dominant_pillar`, `rationale` into `data.json`
- Regional analyst reads all signal files + `master_scenarios.json` + `company_profile.json`, writes `report.md`, then updates `data.json` with `primary_scenario`, `financial_rank`, `signal_type`
- Global builder reads `output/regional/*/report.md` + `data.json` files + `trend_brief.json` → writes `output/global_report.json`
- Orchestrator assembles `output/run_manifest.json` from all 5 `data.json` files
- `build_dashboard.py` reads `global_report.json` + `data.json` files + trace log → generates `output/dashboard.html` and `output/global_report.md`

### data.json Schema

Written for every region (escalated, monitor, and clear):

```json
{
  "region": "APAC",
  "status": "escalated|monitor|clear",
  "gatekeeper_decision": "ESCALATE|MONITOR|CLEAR",
  "severity": "Critical|High|Medium|Low",
  "severity_score": 3,
  "primary_scenario": "Ransomware",
  "financial_rank": 1,
  "signal_type": "Event|Trend|Mixed",
  "vacr_exposure_usd": 18500000,
  "admiralty": "B2",
  "rationale": "Single-sentence triage rationale from gatekeeper",
  "velocity": "accelerating|stable|improving|unknown",
  "dominant_pillar": "Geopolitical|Cyber",
  "report_path": "regional/apac/report.md",
  "timestamp": "2026-03-13T10:33:07Z"
}
```

`financial_rank` and `signal_type` are null for CLEAR/MONITOR regions (set by analyst only for escalated regions).

### Deterministic Auditing via Stop Hooks

**jargon-auditor.py** — wired to regional and global analyst Stop events:
- Checks for forbidden technical cyber jargon (CVEs, IPs, hashes)
- Checks for forbidden SOC operational language (TTPs, IoCs, MITRE ATT&CK, lateral movement, C2)
- Checks for unsolicited budget/procurement advice
- Returns `sys.exit(2)` to force rewrite, `sys.exit(0)` to approve
- On rewrite: orchestrator passes the full auditor output to the agent — no blind rewrites

**json-auditor.py** — wired to global analyst Stop event:
- Validates output is parseable JSON
- Checks required keys: `total_vacr_exposure`, `executive_summary`, `regional_threats`
- Validates types (numbers are numbers, arrays are arrays)
- Validates each regional_threats entry has required schema
- Returns `sys.exit(2)` to force rewrite, `sys.exit(0)` to approve

### Circuit Breaker

Region-scoped retry counter files at `output/.retries/{label}.retries`. Caps retries at 3 per label to prevent infinite rewrite loops. After 3 failures, the hook forces approval and deletes the counter file.

### Observability

`tools/audit_logger.py` appends timestamped events to `output/system_trace.log`. Events: PIPELINE_START, GATEKEEPER_YES, GATEKEEPER_NO, HOOK_PASS, HOOK_FAIL, PHASE_COMPLETE, PIPELINE_COMPLETE. The trace log is rendered in a collapsible "Audit Trace" panel in the HTML dashboard.

### Threat Scoring

`threat_scorer.py` returns severity (1/2/3) plus scenario composition with Financial and Frequency ranks from the Master Scenario List. The score governs analysis depth (brief / standard / comprehensive).

### Mock Mode

All agents run in mock mode by default. The OSINT tool chain reads from `data/mock_osint_fixtures/{region}_{geo|cyber}.json`. No live API keys required for testing.

**Active threats (Gatekeeper ESCALATE):** APAC (HIGH, System intrusion, $18.5M), AME (CRITICAL, Ransomware, $22M), MED (MEDIUM, Insider misuse, $4.2M)
**Quiet regions (Gatekeeper CLEAR):** LATAM (LOW), NCE (LOW)

To go live: remove `--mock` from collector calls in `run-crq.md`. Set `TAVILY_API_KEY` in `.env` for higher-quality search (optional — DDG works without a key).

### UI-Ready Data Contract

Every pipeline run produces a deterministic output structure a frontend can ingest:
- **`run_manifest.json`** — master state: pipeline ID, timestamp, per-region status/severity/VaCR/admiralty, output file paths
- **`regional/{region}/data.json`** — always exists for all 5 regions; full schema above
- **`regional/{region}/report.md`** — only exists when `status: "escalated"`
- **`global_report.json`** — structured JSON with executive_summary, regional_threats array, monitor_regions array
- **`dashboard.html`** — self-contained Tailwind executive dashboard
- A UI renders escalated regions as threat cards and clear regions as status badges by reading `status` from `data.json`

## Project Structure

```
.claude/
  commands/          # Orchestrator slash commands (run-crq.md, architect.md, crq-region.md)
  agents/            # Sub-agents (gatekeeper, regional-analyst, global-builder, global-validator)
  hooks/validators/  # jargon-auditor.py, json-auditor.py, crq-schema-validator.py
data/
  company_profile.json              # AeroGrid Wind Solutions — crown jewels, industry, footprint
  master_scenarios.json             # Empirical global baseline (9 scenario types with ranks)
  mock_crq_database.json            # Region-keyed CRQ scenarios (VaCR = immutable input)
  mock_osint_fixtures/              # {region}_{geo|cyber}.json — mock OSINT for --mock mode
tools/                              # Python utility scripts
  geo_collector.py                  # Geo OSINT → geo_signals.json
  cyber_collector.py                # Cyber OSINT → cyber_signals.json
  scenario_mapper.py                # Signal → scenario hint → scenario_map.json
  audit_logger.py                   # Append events to system_trace.log
  build_dashboard.py                # JSON + trace → HTML dashboard + MD export
  write_gatekeeper_decision.py      # Validated write of gatekeeper_decision.json
  write_region_data.py              # Writes data.json from gatekeeper + feed data
output/
  latest/                           # Always points to the most recent completed run
  runs/
    {timestamp}/                    # Archived completed runs (immutable once written)
      run_manifest.json             # Master state file — single source of truth for any UI
      regional/
        {region}/
          data.json                 # Always written — full schema including admiralty, rationale, signal_type
          report.md                 # Only for escalated regions — finalized executive brief
          gatekeeper_decision.json  # Triage decision with Admiralty, dominant_pillar, rationale
          geo_signals.json          # Geopolitical signals
          cyber_signals.json        # Cyber threat signals
          scenario_map.json         # Scenario mapper hint
      global_report.json            # Structured JSON global report (primary output)
      global_report.md              # Markdown render (generated by build_dashboard.py)
      dashboard.html                # Tailwind CSS executive dashboard with audit trace
      system_trace.log              # Pipeline observability log
      board_report.pdf
      board_report.pptx
  .retries/                         # Circuit breaker counter files (transient, not archived)
docs/
  superpowers/specs/
    2026-03-10-roadmap-design.md    # Approved build roadmap — phases D through F-5
    agent-design-principles.md      # Disler/agentic engineering principles — read before every build session
```

## Critical YAML Rule

All `.md` subagent files use ONLY these valid frontmatter keys: `name`, `description`, `tools`, `model`, `hooks`. Do NOT use `color`, `argument-hint`, or any non-standard key.

## Geopolitical Persona

Agents speak as **Strategic Geopolitical & Cyber Risk Analysts**, not SOC engineers. Reports are board-level executive briefs structured as:
1. **Why** — geopolitical driver (state actor intent, economic pressure, structural instability)
2. **How** — cyber vector (which business assets are exposed and how — not attack mechanics)
3. **So What** — business impact (VaCR figure, scenario financial rank, effect on manufacturing capacity and service delivery)

Zero technical jargon, zero SOC language, zero budget advice. Financial anchors to VaCR figures in dollars at every level.

## Agent Team Pipeline

For multi-agent build tasks, follow the pipeline in `C:/Users/frede/agent-team-blueprint/CLAUDE.md`. Creates a Planner (Opus), Builders (Sonnet), and Validator (Sonnet) team with deterministic quality gates.

## Dependencies

Managed via `uv`. Key packages: `fpdf2`, `python-pptx`, `python-dotenv`, `playwright`, `jinja2`.
