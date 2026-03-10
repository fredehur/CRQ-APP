# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Top-Down CRQ (Cyber Risk Quantification) Agentic Pipeline** built entirely with native Claude Code features — no LangChain, LangGraph, or CrewAI. It is a multi-agent geopolitical and cyber risk intelligence system that processes regional threat data and produces executive board reports.

**Client:** AeroGrid Wind Solutions (Anonymized) — Renewable Energy, 75% Wind Turbine Manufacturing / 25% Global Service & Maintenance.

**Architectural Boundary:** This system is strictly the **Intelligence & Synthesis layer**. VaCR numbers come from a separate enterprise CRQ application and are treated as immutable ground truth. This system does NOT calculate VaCR — it consumes, contextualizes, and reports it.

The system is scaffolded by a single Meta-Agent command (`/architect`) that builds the entire project autonomously.

## Commands

All commands use `uv` as the Python package manager:

```bash
uv run python tools/regional_search.py <REGION> --mock   # Fetch {region}_feed.json (active_threats, scenario, VaCR, baselines)
uv run python tools/geopolitical_context.py <REGION>     # Company profile + regional feed context + empirical baseline
uv run python tools/threat_scorer.py <REGION>            # Maps HIGH/CRITICAL/MEDIUM/LOW → 3/3/2/1 + scenario composition
uv run python tools/report_differ.py                     # Cross-regional keyword delta brief
uv run python tools/audit_logger.py <EVENT> <MESSAGE>    # Append to output/system_trace.log
uv run python tools/write_region_data.py <REGION> <escalated|clear>  # Write regional data.json after gatekeeper
uv run python tools/write_manifest.py                    # Assemble run_manifest.json from all data.json
uv run python tools/archive_run.py                       # Archive current run to output/runs/{timestamp}/ + update output/latest/
uv run python tools/build_dashboard.py                   # Build HTML dashboard + MD export from JSON
uv run python tools/export_pdf.py [out.pdf]              # Export board PDF (Playwright + Jinja2); defaults to output/board_report.pdf
uv run python tools/export_pptx.py [out.pptx]           # Export board PPTX (python-pptx); defaults to output/board_report.pptx

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

## Sub-Agents (`.claude/agents/`)

Sub-agents are spawned by `run-crq` via the Task tool. They are not invoked directly.

| Agent | Model | Role |
|---|---|---|
| `gatekeeper-agent` | haiku | Triage — returns YES/NO per region |
| `regional-analyst-agent` | sonnet | Produces one regional executive brief |
| `global-analyst-agent` | opus | Synthesizes all regional briefs into global board JSON report |

## Architecture

### Agent Hierarchy

```
run-crq (Orchestrator slash command, opus) — logs all events to output/system_trace.log
├── [PARALLEL via Task fan-out] 5x regional pipelines spawned simultaneously
│   ├── gatekeeper-agent (Sub-agent, haiku) — fast YES/NO per region
│   └── regional-analyst-agent (Sub-agent, sonnet) — writes output/regional/{region}/report.md
│       └── Stop hook → jargon-auditor.py
└── [SEQUENTIAL after fan-in] global-analyst-agent (Sub-agent, opus) — synthesis only
    ├── Stop hook → json-auditor.py (validates output/global_report.json schema)
    └── Stop hook → jargon-auditor.py (validates output/global_report.json content)
```

### Disler Behavioral Protocol

All agents enforce: Act as Unix CLI pipe (not chatbot), Zero Preamble & Zero Sycophancy, Filesystem as State, Assume Hostile Auditing.

### Empirical Scenario Anchoring

All threat feeds and geopolitical context cross-reference `data/master_scenarios.json` — the Master Scenario List with empirical Financial Impact, Event Frequency, and Records Affected rankings. Agents MUST cite these baselines; they cannot invent statistics.

### Regional Scope

Five operational regions: **APAC**, **AME** (North America), **LATAM**, **MED** (Mediterranean), **NCE** (Northern & Central Europe). **Global** is a synthesis layer only — no raw threat feed. Some regions may be skipped by the gatekeeper if no credible top-4 financial impact threat exists.

### File Passing Between Agents

- Each regional task writes `output/regional/{region}/data.json` immediately after gatekeeper decision (both escalated and clear)
- Regional analyst writes `output/regional/{region}/report.md` (escalated regions only)
- Global analyst reads from `output/regional/*/report.md` (all approved regional briefs)
- Global analyst writes JSON to `output/global_report.json`
- Orchestrator assembles `output/run_manifest.json` from all 5 `data.json` files in Phase 5
- `build_dashboard.py` reads `global_report.json` + `data.json` files + trace log → generates `output/dashboard.html` and `output/global_report.md`

### Deterministic Auditing via Stop Hooks

**jargon-auditor.py** — wired to regional and global analyst Stop events:
- Checks for forbidden technical cyber jargon (CVEs, IPs, hashes)
- Checks for forbidden SOC operational language (TTPs, IoCs, MITRE ATT&CK, lateral movement, C2)
- Checks for unsolicited budget/procurement advice
- Returns `sys.exit(2)` to force rewrite, `sys.exit(0)` to approve

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

All agents run in mock mode by default. `regional_search.py` reads from `data/mock_threat_feeds/{region}_feed.json`. No live API keys are required for testing.

**Active threats (Gatekeeper YES):** APAC (HIGH, System intrusion, $18.5M), AME (CRITICAL, Ransomware, $22M), MED (MEDIUM, Insider misuse, $4.2M)
**Quiet regions (Gatekeeper NO):** LATAM (LOW, no active threats), NCE (LOW, no active threats)

### UI-Ready Data Contract

Every pipeline run produces a deterministic output structure a frontend can ingest:
- **`run_manifest.json`** — master state: pipeline ID, timestamp, per-region status/severity/VaCR, output file paths
- **`regional/{region}/data.json`** — always exists for all 5 regions; `status: "escalated"|"clear"`, `report_path: string|null`
- **`regional/{region}/report.md`** — only exists when `status: "escalated"`
- A UI renders escalated regions as threat cards and clear regions as green "Clear" badges by reading `status` from `data.json`

## Project Structure

```
.claude/
  commands/          # Orchestrator slash commands (run-crq.md, architect.md)
  agents/            # Sub-agents spawned by orchestrator (gatekeeper, regional, global)
  hooks/validators/  # jargon-auditor.py, json-auditor.py, crq-schema-validator.py
data/
  company_profile.json              # AeroGrid Wind Solutions — crown jewels, industry, footprint
  master_scenarios.json             # Empirical global baseline (9 scenario types with ranks)
  mock_crq_database.json            # Region-keyed CRQ scenarios (VaCR = immutable input)
  mock_threat_feeds/                # {region}_feed.json — flat schema: active_threats, severity, primary_scenario, vacr_exposure_usd, geopolitical_context
tools/                              # Python utility scripts
  audit_logger.py                   # Append events to system_trace.log
  build_dashboard.py                # JSON + trace → HTML dashboard + MD export
output/
  latest/                           # Always points to the most recent completed run
  runs/
    {timestamp}/                    # Archived completed runs (immutable once written)
      run_manifest.json             # Master state file — single source of truth for any UI
      regional/
        {region}/
          data.json                 # Always written — status: "escalated" or "clear"
          report.md                 # Only for escalated regions — finalized executive brief
      global_report.json            # Structured JSON global report (primary output)
      global_report.md              # Markdown render (generated by build_dashboard.py)
      dashboard.html                # Tailwind CSS executive dashboard with audit trace
      system_trace.log              # Pipeline observability log
      board_report.pdf
      board_report.pptx
  .retries/                         # Circuit breaker counter files (transient, not archived)
```

## Critical YAML Rule

All `.md` subagent files use ONLY these valid frontmatter keys: `name`, `description`, `tools`, `model`, `hooks`. Do NOT use `color`, `argument-hint`, or any non-standard key.

## Geopolitical Persona

Agents speak as **Strategic Geopolitical & Cyber Risk Analysts**, not SOC engineers. Every output must answer: *"How does this threat affect the company's ability to deliver business results?"* Reports are board-level executive briefs — zero technical jargon, financial anchors to VaCR figures in dollars.

## Dependencies

Managed via `uv`. Key packages: `fpdf2`, `python-pptx`, `python-dotenv`.
