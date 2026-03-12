# CRQ Geopolitical Intelligence Pipeline

A Top-Down Cyber Risk Quantification (CRQ) agentic pipeline built entirely with native Claude Code features. No LangChain, LangGraph, or CrewAI — just subagents, hooks, and Python tools.

---

## Core Philosophy

This system answers one question for every region it analyzes:

> **"How does this threat affect the company's ability to deliver business results?"**

Every output is a board-level executive brief. Technical jargon is forbidden by design — no CVEs, no malware hashes, no SOC terminology. Every threat is anchored to a **Value-at-Cyber-Risk (VaCR)** dollar figure so executives can make financial decisions, not security ones.

The jargon auditor hook enforces this automatically. If an agent produces a report with forbidden language, it is forced to rewrite it before the output is accepted.

---

## Agent Hierarchy

```
run-crq  (Orchestrator — opus)
├── [PARALLEL × 5 regions] regional pipelines
│   ├── gatekeeper-agent  (Triage — haiku)
│   │     ESCALATE / MONITOR / CLEAR per region.
│   │     Fast and cheap. Skips regions with no active top-4 threat.
│   │     Writes gatekeeper_decision.json with Admiralty rating.
│   │
│   └── regional-analyst-agent  (Analysis — sonnet)
│         Writes a 2–3 paragraph executive brief anchored to VaCR.
│         └── Stop hook → jargon-auditor.py
│
├── global-builder-agent  (Synthesis — sonnet)
│     Reads all approved regional briefs and cross-regional delta.
│     Writes global_report.json (structured JSON).
│     ├── Stop hook → json-auditor.py (schema validation)
│     └── Stop hook → jargon-auditor.py
│
└── global-validator-agent  (Devil's Advocate — haiku)
      Read-only cross-check of global report against regional data.
      Checks: VaCR arithmetic, Admiralty consistency, scenario mapping,
      region counts, phantom regions.
      Returns APPROVED or REWRITE (max 2 cycles, then circuit breaker).
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

### Run the full pipeline

```
/run-crq
```

This single command runs the complete pipeline:

| Phase | Action |
|-------|--------|
| 0 | Validate CRQ database schema, initialize trace log |
| 1 | Fan-out: Gatekeeper triage → Regional analysis × 5 (parallel) |
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

Re-runs the pipeline for one region without touching the other four.

---

## Output Files

All outputs are written to `output/` and archived per run:

```
output/
  run_manifest.json              # Master state — pipeline ID, per-region status/severity/VaCR
  global_report.json             # Structured JSON global report (primary output)
  global_report.md               # Markdown render of global report
  dashboard.html                 # Tailwind CSS executive dashboard with audit trace
  board_report.pdf               # PDF export for board distribution
  board_report.pptx              # PowerPoint export for board presentation
  system_trace.log               # Pipeline observability log
  trend_brief.json               # Cross-run velocity analysis
  regional/
    {region}/
      data.json                  # Always written — status: "escalated" | "monitor" | "clear"
      report.md                  # Only for escalated regions — finalized executive brief
      gatekeeper_decision.json   # Admiralty-rated triage decision
  latest/                        # Symlink to most recent completed run
  runs/
    {timestamp}/                 # Archived immutable runs
```

---

## Tools

| Tool | Description |
|------|-------------|
| `regional_search.py <REGION> --mock` | Loads mock threat feed for a region |
| `geopolitical_context.py <REGION>` | Company profile + regional feed context + empirical baseline |
| `threat_scorer.py <REGION>` | Maps severity → score (1/2/3) + scenario composition |
| `report_differ.py` | Cross-regional keyword delta brief |
| `trend_analyzer.py` | Velocity analysis across archived runs → `trend_brief.json` |
| `write_region_data.py <REGION> <status>` | Write regional `data.json` after gatekeeper decision |
| `write_gatekeeper_decision.py <region>` | Pipe JSON to write gatekeeper decision file |
| `write_manifest.py` | Assemble `run_manifest.json` from all regional `data.json` files |
| `archive_run.py` | Archive current run to `output/runs/{timestamp}/` + update `output/latest/` |
| `build_dashboard.py` | JSON + trace → HTML dashboard + MD export |
| `export_pdf.py [out.pdf]` | Export board PDF (Playwright + Jinja2) |
| `export_pptx.py [out.pptx]` | Export board PPTX (python-pptx) |
| `audit_logger.py <EVENT> <MESSAGE>` | Append timestamped event to `system_trace.log` |

All tools are invoked via `uv run python tools/<tool>`.

---

## Hooks & Validators

| Hook | Trigger | Action |
|------|---------|--------|
| `jargon-auditor.py` | Stop event on `regional-analyst-agent` | Audits `report.md` for forbidden language |
| `jargon-auditor.py` | Stop event on `global-builder-agent` | Audits `global_report.json` for forbidden language |
| `json-auditor.py` | Stop event on `global-builder-agent` | Validates JSON schema: required keys, types, regional threat entries |
| `crq-schema-validator.py` | Phase 0 | Validates `data/mock_crq_database.json` before pipeline runs |

The jargon auditor checks three categories:

- **Technical cyber jargon** — CVE identifiers, IP addresses, malware hashes
- **SOC operational language** — TTPs, IoCs, MITRE ATT&CK, lateral movement, C2
- **Unsolicited budget advice** — procurement, vendor recommendations, tool purchases

An audit failure returns `exit(2)`, which forces the agent to regenerate. A circuit breaker at `output/.retries/{label}.retries` caps retries at 3 to prevent infinite loops.

---

## Data

```
data/
  company_profile.json              # AeroGrid Wind Solutions — crown jewels, industry, footprint
  master_scenarios.json             # Empirical global baseline (9 scenario types with financial ranks)
  mock_crq_database.json            # Region-keyed CRQ scenarios (VaCR = immutable input)
  mock_threat_feeds/
    apac_feed.json                  # Mock threat intelligence — APAC
    ame_feed.json                   # Mock threat intelligence — AME
    latam_feed.json                 # Mock threat intelligence — LATAM
    med_feed.json                   # Mock threat intelligence — MED
    nce_feed.json                   # Mock threat intelligence — NCE
```

All agents run in mock mode by default. No live API keys or external data sources are required.

**Active threats (Gatekeeper ESCALATE):** APAC (HIGH, System intrusion, $18.5M), AME (CRITICAL, Ransomware, $22M), MED (MEDIUM, Insider misuse, $4.2M)
**Quiet regions (Gatekeeper CLEAR):** LATAM (LOW), NCE (LOW)

---

## Architecture Notes

- **Model assignment is fixed in YAML frontmatter** — haiku for triage/validation, sonnet for regional analysis and global synthesis, opus for orchestration.
- **Parallel fan-out** — all 5 regional pipelines run simultaneously via background Tasks, then fan-in for global synthesis.
- **Filesystem as state** — every agent handoff is a file. No conversation state carries between agents.
- **Devil's advocate validation** — `global-validator-agent` cross-checks the global report against regional source data before the pipeline advances. Max 2 rewrite cycles, then circuit breaker force-approves.
- **Empirical anchoring** — all threat assessments cross-reference `master_scenarios.json` with real-world financial impact and frequency rankings. Agents cannot invent statistics.
- **Admiralty Scale** — every gatekeeper decision includes a reliability (A–D) × credibility (1–4) rating for source quality assessment.
- **Dashboard uses Tailwind CSS via CDN** — renders as a dark-mode executive dashboard with collapsible audit trace panel.

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
