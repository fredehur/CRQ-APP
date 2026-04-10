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
| CISO / C-Suite | Weekly intelligence brief (Word .docx) — scenario, threat actor, intel findings, adversary activity, impact, tradecraft, actions |
| Regional Security Managers | Weekly INTSUM + flash alerts per region (Markdown + PDF) |
| Regional Operations | Region-specific threat brief anchored to local crown jewels and service continuity |
| Sales & Service Teams | Clear/monitor/escalated status for their region — actionable, not alarming |

**Clear signals are as valuable as alerts.** Knowing your region is stable is actionable intelligence, not absence of information. The system routes quiet regions through a fast "clear" path so the org isn't flooded with noise.

---

## Web Application

The pipeline includes a FastAPI web application (port **8001**) with 7 tabs.

### Start the app

```bash
uv run python server.py
# → http://localhost:8001
```

### Tab Definitions

There are two fundamentally different kinds of tabs — **analyst workspace** and **stakeholder delivery**. Understanding the distinction matters for what data each tab reads and how it should be designed.

---

**Overview — Analyst workspace**

The analyst's operational dashboard. Shows the live intelligence picture produced by the agents and data collectors: regional status, source signal quality (Seerist strength, OSINT sources), signal clusters, convergence/divergence assessment, collection quality per region. Everything here is internal — raw material for the analyst to review, QA, and interrogate before anything goes to stakeholders.

*Data sources:* `sections.json`, `seerist_signals.json`, `osint_signals.json`, `collection_quality.json`, `signal_clusters.json`, `gatekeeper_decision.json`

*Audience:* Intelligence analyst, pipeline operator

---

**Reports — Stakeholder delivery**

Where finished outputs for external audiences live. The analyst comes here to trigger generation and preview what stakeholders will receive. Each report card is audience-specific — CISO, Board, RSM, Regional Ops. Content is polished, jargon-free, and framed for non-technical readers.

*Data sources:* `global_report.json`, `sections.json` (via `report_builder.py`), `export_ciso_docx.py`, `rsm_input_builder.py`

*Audience:* Intelligence analyst (to generate and QA), CISO, Board, RSMs (to receive)

---

**Remaining tabs:**

| Tab | Type | Purpose |
|-----|------|---------|
| **Trends** | Analyst workspace | Longitudinal trend analysis across archived pipeline runs |
| **History** | Analyst workspace | Historical run log with per-region severity charts |
| **Config** | Analyst workspace | Intelligence sources, regional footprint, agent prompts |
| **Validate** | Analyst workspace | Benchmark validation — OSINT signal + velocity columns, scenario cross-check |
| **Source Audit** | Analyst workspace | Source registry browser — tier badges, filters, flag/block workflow |

### App Structure

The app is built on two layers: the **pipeline** writes files; the **server** reads and serves them. The app never writes to `output/` — it is a read-only consumer of pipeline artifacts.

```
Pipeline (agents + Python tools)
    │
    ├── writes per region:
    │     data.json · sections.json · signal_clusters.json
    │     seerist_signals.json · osint_signals.json
    │     gatekeeper_decision.json · collection_quality.json · claims.json
    │
    └── writes globally:
          global_report.json · run_manifest.json · history.json

FastAPI server (server.py — port 8001)
    │
    ├── GET /api/overview              → run_manifest.json (region cards)
    ├── GET /api/region/{r}/sections   → sections.json (brief + bullets)
    ├── GET /api/region/{r}/data       → data.json (status, VaCR, velocity)
    ├── GET /api/global                → global_report.json
    ├── GET /api/sources               → data/sources.db (source registry)
    ├── GET /api/validation/flags      → validation/flags.json
    └── GET /api/outputs/...           → deliverables/ (generate + serve)

Browser (static/index.html + static/app.js)
    │
    ├── Overview tab     → /api/overview + /api/region/{r}/sections
    ├── Reports tab      → /api/outputs/... (generate CISO docx, board PDF)
    ├── Trends tab       → /api/trends
    ├── History tab      → /api/history
    ├── Config tab       → /api/config (read), POST /api/config (write)
    ├── Validate tab     → /api/validation/flags
    └── Source Audit tab → /api/sources
```

**Key data flows:**

- `claims.json` → `extract_sections.py` → `sections.json` → Overview + Reports
- `seerist_signals.json` + `osint_signals.json` → `sections.json`.`source_metadata` → Overview source boxes
- `claims.json`.`why_summary/how_summary/so_what_summary` → `sections.json`.`brief_headlines` → CISO + Board + RSM
- `global_report.json` → board PDF, PPTX, and the Reports tab global summary card
- `data/sources.db` → Source Audit tab (persistent across runs, never in `output/`)

**What the Overview reads (analyst workspace):**
Every intermediate file — `sections.json`, `seerist_signals.json`, `collection_quality.json`, `signal_clusters.json`. The analyst sees the raw intelligence picture, source quality, and convergence/divergence — before anything is polished for stakeholders.

**What the Reports tab reads (stakeholder delivery):**
Only finished outputs — `global_report.json` for board content, `sections.json` for per-region briefs. Generation triggers (`export_ciso_docx.py`, `export_pdf.py`) run server-side on demand. The analyst previews what stakeholders receive.

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
│   │     research_collector.py → geo_signals.json + cyber_signals.json  [live mode]
│   │     geo_collector.py + cyber_collector.py → signals                [mock mode]
│   │     youtube_collector.py → youtube_signals.json                    [always]
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
│         Writes signal_clusters.json (source clusters for dashboard + attribution)
│         Writes sections.json (structured sections for dashboard rendering)
│         Updates data.json with primary_scenario, financial_rank, signal_type
│         └── Stop hooks:
│               ├── jargon-auditor.py (forbidden language gate)
│               ├── source-attribution-auditor.py (evidenced claims must cite named sources)
│               └── sections-validator.py (sections.json schema + completeness)
│
├── [Phase 1.5 — Deep Research, if --deep flag]
│     deep_research.py geo + cyber per region (overwrites shallow signals)
│
├── trend_analyzer.py  [Phase 2 — after fan-in]
│     Computes velocity per region, patches data.json, writes trend_brief.json
│
├── trends-synthesis-agent  [Phase 2.5]
│     Longitudinal patterns across all archived runs → trend_analysis.json
│
├── report_differ.py  [Phase 3]
│     Cross-regional keyword delta brief
│
├── global-builder-agent  (Synthesis — sonnet)  [Phase 4]
│     Reads all approved regional briefs + trend_brief.json + data.json files
│     Synthesizes executive_summary: cross-regional patterns, compound risk, velocity
│     Writes global_report.json
│     ├── Stop hook → json-auditor.py (schema validation)
│     ├── Stop hook → validate_global_report.py (deterministic: VaCR arithmetic,
│     │     Admiralty consistency, scenario cross-check, phantom region guard)
│     └── Stop hook → jargon-auditor.py
│
├── global-validator-agent  (Devil's Advocate — haiku)  [Phase 4b]
│     Read-only cross-check of global_report.json against regional source data
│     Returns APPROVED or REWRITE (max 2 cycles, then circuit breaker)
│
├── [Phase 5 — Dashboard & Export]
│     build_dashboard.py → dashboard.html + global_report.md
│     export_pdf.py → board_report.pdf
│     export_pptx.py → board_report.pptx
│     export_ciso_docx.py → ciso_brief.docx
│
├── [Phase 6 — Finalize]
│     write_manifest.py → run_manifest.json
│     archive_run.py → output/runs/{timestamp}/
│     update_source_registry.py → data/sources.db
│     build_history.py → history.json
│
└── [Phase 7 — RSM Briefs, if --rsm flag]
      rsm_dispatcher.py → weekly INTSUMs per region
      └── rsm-formatter-agent  (sonnet)
            Writes INTSUM + flash alerts per region
            └── Stop hook → rsm-brief-auditor.py
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
| 0 | Validate CRQ database schema, initialize trace log, load prior feedback |
| 1 | OSINT collection → Gatekeeper triage → Regional analysis × 5 (parallel) → Jargon audit → Cluster enrichment |
| 1.5 | Deep research pass (optional, `--deep` flag) |
| 2 | Velocity analysis — trend computation across archived runs |
| 2.5 | Trend synthesis — longitudinal pattern analysis |
| 3 | Cross-regional delta brief |
| 4 | Global JSON report + devil's advocate validation (max 2 rewrite cycles) |
| 5 | HTML dashboard, PDF + PPTX board reports, CISO Word brief |
| 6 | Write run manifest, archive run, update source registry, build history |
| 7 | RSM briefs (optional, `--rsm` flag) |

### Pipeline flags

| Flag | Effect |
|------|--------|
| `--window 30d` | OSINT collection window (default: `7d`) |
| `--deep` | Enable Phase 1.5 deep research pass |
| `--deep-scope=all` | Deep research for all regions, not just escalated |
| `--depth=quick\|standard\|deep` | Research depth per region (default: `standard`) |
| `--rsm` | Enable Phase 7 RSM brief generation |

### OSINT modes

| Mode | Trigger | Behaviour |
|------|---------|-----------|
| **Mock** (default) | No env vars | `geo_collector.py --mock` + `cyber_collector.py --mock` — reads from `data/mock_osint_fixtures/` |
| **Live** | `OSINT_LIVE=true` in `.env` | `research_collector.py` — 3-pass LLM research loop with Tavily/DDG, writes real signals |

YouTube collection runs in both modes.

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

### Pre-build ritual (development sessions)

```
/prime-dev
```

Required before any code-change session. Loads the agentic engineering principles from the `agent-team-blueprint` repo, declares the Opus/Sonnet team structure, and confirms the engineering protocol checklist — including `mode: "bypassPermissions"` on all background agent spawns, parallelism, stop hooks, and TeamDelete.

---

## Output Files

All outputs are written to `output/` subdirectories and archived immutably per run:

```
output/
  pipeline/
    run_manifest.json              # Master state — pipeline ID, per-region status/severity/VaCR
    global_report.json             # Structured JSON global report (primary machine-readable output)
    global_report.md               # Markdown render of global report
    dashboard.html                 # Tailwind CSS executive dashboard
    history.json                   # Historical run data for History tab charts
    trend_brief.json               # Cross-run velocity analysis
    trend_analysis.json            # Longitudinal trend synthesis
    feedback_trends.json           # Aggregated analyst feedback across runs
    routing_decisions.json         # Audience routing decisions
  deliverables/
    board_report.pdf               # PDF export for board distribution
    board_report.pptx              # PowerPoint export for board presentation
    ciso_brief.docx                # CISO Weekly Brief (Word) — canonical intelligence output
  delivery/
    ciso/                          # CISO flash alerts
    rsm/                           # RSM weekly INTSUMs + flash alerts
    delivery_log.jsonl             # Delivery audit trail
  regional/
    {region}/
      data.json                    # Always written — status, severity, VaCR, admiralty, velocity,
                                   #   primary_scenario, financial_rank, signal_type, source_quality
      report.md                    # Only for escalated regions — 3-paragraph executive brief
      sections.json                # Structured sections for dashboard rendering (escalated only)
      signal_clusters.json         # Source clusters with enriched URLs + credibility tiers
      gatekeeper_decision.json     # Admiralty-rated triage decision + rationale
      geo_signals.json             # Geopolitical lead indicators (OSINT)
      cyber_signals.json           # Cyber threat signals (OSINT)
      youtube_signals.json         # YouTube OSINT signals
      scenario_map.json            # Keyword mapper hint (advisory — analyst validates)
      collection_quality.json      # Collection quality gate assessment
      context_block.txt            # Regional footprint context for gatekeeper
      research_scratchpad.json     # Working theory + audit trail (live mode only)
  validation/
    flags.json                     # Validation flags (OSINT signal + velocity per scenario)
    candidates.json                # Benchmark source candidates
    cache/                         # Validation cache files
  logs/
    system_trace.log               # Full pipeline observability log
    tool_trace.log                 # Tool-level telemetry
  runs/
    {timestamp}/                   # Immutable archived runs
  latest/                          # Copy of most recent completed run
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
  "source_quality": { "tier_a": 2, "tier_b": 5, "tier_c": 1, "total": 8 },
  "report_path": "regional/ame/report.md"
}
```

A UI can render escalated regions as threat cards and clear/monitor regions as status badges by reading `status` from `data.json`. Clear signals (`status: "clear"`) are first-class outputs — they confirm a region is stable, which is as operationally valuable as an escalation.

---

## Source Registry

Sources are tracked in a persistent SQLite database (`data/sources.db`) with three tables:

| Table | Purpose |
|-------|---------|
| `sources_registry` | Per unique source — domain, type, credibility tier (A/B/C), collection type, blocked flag |
| `source_appearances` | Per run/region/pillar — tracks which sources appeared and whether they were cited |
| `seerist_events` | Ready for Seerist API integration — structured signals, not URL-based citations |

Source quality over time is measured by `cited_count / appearance_count` ratio. Tiers are auto-assigned by domain (A = government/intelligence, B = industry/news, C = social) with manual override preserved.

The Source Audit tab in the web app provides a browsable view: grouped by publication, collapsible rows, tier badges, and filters by region/type/tier/cited/blocked.

---

## Hooks & Quality Gates

| Hook | Trigger | What it checks |
|------|---------|----------------|
| `jargon-auditor.py` | Stop on `regional-analyst-agent` | Forbidden language in `report.md` |
| `source-attribution-auditor.py` | Stop on `regional-analyst-agent` | Every "evidenced" claim cites a named source from `signal_clusters.json` |
| `sections-validator.py` | Stop on `regional-analyst-agent` | `sections.json` schema + all 5 bullet arrays populated |
| `json-auditor.py` | Stop on `global-builder-agent` | JSON schema: required keys, types, regional threat entries |
| `validate_global_report.py` | Stop on `global-builder-agent` | Deterministic: VaCR arithmetic, Admiralty consistency vs `gatekeeper_decision.json`, scenario cross-check vs `data.json`, phantom region guard |
| `jargon-auditor.py` | Stop on `global-builder-agent` | Forbidden language in `global_report.json` |
| `rsm-brief-auditor.py` | Stop on `rsm-formatter-agent` | INTSUM/FLASH structure, valid ADM field, WATCH LIST depth, jargon |
| `grounding-validator.py` | Pre-tool hook | Validates grounding of agent claims |
| `crq-schema-validator.py` | Phase 0 | `data/mock_crq_database.json` schema before pipeline runs |

**Jargon gate** enforces three categories of forbidden output:

- **Technical cyber jargon** — CVE identifiers, IP addresses, malware hashes
- **SOC operational language** — TTPs, IoCs, MITRE ATT&CK, lateral movement, C2
- **Unsolicited budget advice** — procurement, vendor recommendations, tool purchases
- **Pipeline language** — "research collection cycle", "noisy corpus", "signal files"
- **Generic source labels** — `[Cyber Signal — ...]`, `[Geo Signal — ...]`

**Source attribution gate** closes the hallucination vector: any claim marked "evidenced" must cite a named source from `signal_clusters.json`. Generic labels do not satisfy the requirement.

**Deterministic validation** (`validate_global_report.py`) replaces LLM-based arithmetic — Python does the math, not the model.

All audit failures return `exit(2)` and force agent rewrite with the full violation output passed inline. Circuit breaker at `output/.retries/{label}.retries` caps retries at 3.

---

## Data

```
data/
  company_profile.json              # AeroGrid Wind Solutions — crown jewels, industry footprint
  master_scenarios.json             # Empirical global baseline (9 scenario types, financial/frequency/records ranks)
  mock_crq_database.json            # Region-keyed CRQ scenarios (VaCR = immutable input from enterprise CRQ)
  regional_footprint.json           # Per-region crown jewels, site locations, operational context
  sources.db                        # Persistent source registry (SQLite)
  blocked_urls.txt                  # URLs blocked from OSINT collection
  youtube_sources.json              # YouTube channel seeds per region
  validation_sources.json           # Benchmark sources for validation tab
  schedule_config.json              # Scheduler configuration
  mock_osint_fixtures/
    {region}_geo.json               # Mock geopolitical signals per region
    {region}_cyber.json             # Mock cyber threat signals per region
  mock_threat_feeds/
    {region}_feed.json              # Legacy flat feed schema (used by write_region_data fallback)
```

All agents run in mock mode by default. No live API keys or external data sources are required.

---

## Tools

| Tool | Description |
|------|-------------|
| `research_collector.py <REGION> [--window]` | Live 3-pass LLM research loop → `geo_signals.json` + `cyber_signals.json` |
| `geo_collector.py <REGION> [--mock] [--window]` | Mock geopolitical signals → `geo_signals.json` |
| `cyber_collector.py <REGION> [--mock] [--window]` | Mock cyber threat signals → `cyber_signals.json` |
| `youtube_collector.py <REGION> [--mock] [--window]` | YouTube OSINT signals → `youtube_signals.json` |
| `deep_research.py <REGION> <geo\|cyber> [--depth]` | Deep research pass — overwrites shallow signals |
| `scenario_mapper.py <REGION> [--mock]` | Keyword-match signals to scenario → `scenario_map.json` (hint only) |
| `collection_gate.py <REGION>` | Collection quality assessment → `collection_quality.json` |
| `build_context.py <REGION>` | Build regional footprint context block for gatekeeper |
| `geopolitical_context.py <REGION>` | Company profile + regional context + empirical baseline |
| `threat_scorer.py <REGION>` | Maps severity → score (1/2/3) + scenario composition |
| `write_region_data.py <REGION> <status>` | Write regional `data.json` after gatekeeper decision |
| `enrich_clusters.py <REGION>` | Add URL + credibility tier to signal cluster sources |
| `report_differ.py` | Cross-regional keyword delta brief |
| `trend_analyzer.py` | Velocity analysis across archived runs → `trend_brief.json` |
| `write_manifest.py [--window]` | Assemble `run_manifest.json` from all regional `data.json` files |
| `archive_run.py` | Archive current run to `output/runs/{timestamp}/` + update `output/latest/` |
| `build_dashboard.py` | JSON + trace → HTML dashboard + MD export |
| `build_history.py` | Build `history.json` from archived runs |
| `export_pdf.py [out.pdf]` | Export board PDF (Playwright + Jinja2) |
| `export_pptx.py [out.pptx]` | Export board PPTX (python-pptx) |
| `export_ciso_docx.py` | Export CISO Weekly Brief (python-docx) → `ciso_brief.docx` |
| `update_source_registry.py` | Upsert sources from signal files into `data/sources.db` |
| `source_harvester.py` | Upsert benchmark sources (Tier A) into registry |
| `feedback_writer.py [--summarize]` | Write/read analyst feedback per region per run |
| `feedback_summary.py` | Aggregate feedback across runs → `feedback_trends.json` |
| `seerist_collector.py <REGION> [--mock]` | Collect Seerist geopolitical signals → `seerist_signals.json` |
| `delta_computer.py <REGION>` | Diff current vs previous Seerist signals → `region_delta.json` |
| `rsm_dispatcher.py --weekly [--mock]` | Generate + deliver weekly INTSUM for all RSMs |
| `rsm_dispatcher.py --check-flash [--mock]` | Evaluate + dispatch flash alerts |
| `validate_env.py` | Validate environment variables for live mode |
| `audit_logger.py <EVENT> <MESSAGE>` | Append timestamped event to `system_trace.log` |
| `discover.py <REGION>` | Source discovery agent for new OSINT channels |
| `suggest_config.py` | Suggest configuration improvements based on run history |

All tools are invoked via `uv run python tools/<tool>`.

---

## Architecture Notes

- **Model assignment is fixed in YAML frontmatter** — haiku for triage/validation, sonnet for analysis and synthesis, opus for orchestration.
- **Parallel fan-out** — all 5 regional pipelines run simultaneously via background agents, then fan-in for global synthesis.
- **Filesystem as state** — every agent handoff is a file. No conversation state carries between agents.
- **Scenario coupling is analytical, not mechanical** — the regional analyst reads `master_scenarios.json` directly and owns the scenario determination. The keyword mapper is a hint, not a verdict.
- **Devil's advocate validation** — `global-validator-agent` cross-checks the global report against regional source data before the pipeline advances. Checks VaCR arithmetic, Admiralty consistency, scenario mapping, and phantom regions.
- **Admiralty Scale propagation** — the gatekeeper's reliability rating flows from `gatekeeper_decision.json` → `data.json` → `global_report.json` → dashboard. Every intelligence claim carries its confidence level.
- **Velocity tracking** — `trend_analyzer.py` reads archived runs and computes directional movement per region. The global summary synthesizes into a board-level velocity narrative.
- **sections.json contract** — regional analyst writes structured sections (scenario, threat actor, intel findings, adversary activity, impact, watch for, actions) that the dashboard fetches directly via `/api/region/{region}/sections`.
- **Source attribution** — `research_collector.py` returns `sources: [{name, url}]` per signal file. The CISO brief, board reports, and dashboard all render real source citations, not generic labels.
- **Audience Hub** — Reports tab uses `AUDIENCE_REGISTRY` (JS constant) to render config-driven cards. Live audiences (CISO, Board) are clickable with preview + download. Future audiences (RSM, Sales) show phase badges and tooltips.
- **Disler Behavioral Protocol** — all agents operate as Unix CLI pipes: zero preamble, zero sycophancy, filesystem as state, assume hostile auditing. Output goes to files, not conversation.

---

## Dependencies

Managed via `uv`. Defined in `pyproject.toml`.

| Package | Purpose |
|---------|---------|
| `fastapi` | Web server + API |
| `fpdf2` | PDF generation |
| `jinja2` | HTML templating for PDF/dashboard |
| `playwright` | Browser-based PDF rendering |
| `python-dotenv` | Environment variable management |
| `python-pptx` | PowerPoint export |
| `python-docx` | CISO Word brief export |
| `sse-starlette` | Server-Sent Events for live pipeline updates |
| `uvicorn` | ASGI server |
