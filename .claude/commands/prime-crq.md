# /prime-crq — CRQ Architecture Context

Loads deep architecture context for the CRQ pipeline. Run this before any pipeline development, agent modification, or data-flow work.

Confirm with: "CRQ architecture loaded." Then state which specific area you are working in.

---

## Product Framing

This is a **risk awareness platform**, not a security report tool.

- The CRQ scenario register (`data/mock_crq_database.json`) is the shared risk language across the organization — everything couples back to it
- Audience is the whole org (~30k employees): CISO, board, regional ops, sales, service teams
- Agents write for business operators: *"How does this threat affect our ability to deliver turbines and maintain wind farms?"*
- Clear signals ("your region is fine") are as valuable as alerts
- Every output must answer: *"How does this threat affect the company's ability to deliver business results?"*

---

## Agent Hierarchy

```
run-crq (Orchestrator slash command, opus) — logs all events to output/system_trace.log
├── [PARALLEL via Task fan-out] 5x regional pipelines spawned simultaneously
│   ├── OSINT tool chain: geo_collector → cyber_collector → scenario_mapper
│   ├── gatekeeper-agent (haiku) — triage, Admiralty rating, ESCALATE/MONITOR/CLEAR
│   └── regional-analyst-agent (sonnet) — scenario coupling, brief, data.json update
│       └── Stop hook → regional-analyst-stop.py → jargon-auditor + source-attribution-auditor
├── [SEQUENTIAL after fan-in] global-builder-agent (sonnet) — synthesis only
│   ├── Stop hook → json-auditor.py
│   ├── Stop hook → validate_global_report.py (deterministic VaCR/Admiralty/scenario checks)
│   └── Stop hook → jargon-auditor.py
└── [SEQUENTIAL] global-validator-agent (haiku) — devil's advocate cross-check

RSM path (separate from main pipeline):
└── rsm-formatter-agent (sonnet) — INTSUM + flash briefs
    └── Stop hook → rsm-formatter-stop.py → rsm-brief-auditor.py
```

---

## File-Passing Contract

```
geo_collector.py        → output/regional/{region}/geo_signals.json
cyber_collector.py      → output/regional/{region}/cyber_signals.json
scenario_mapper.py      → output/regional/{region}/scenario_map.json
gatekeeper-agent        → output/regional/{region}/gatekeeper_decision.json
write_region_data.py    → output/regional/{region}/data.json  (propagates admiralty, dominant_pillar, rationale)
regional-analyst-agent  → output/regional/{region}/report.md
                        → output/regional/{region}/signal_clusters.json  (dashboard UI artifact)
                        → output/regional/{region}/data.json  (adds primary_scenario, financial_rank, signal_type)
global-builder-agent    → output/global_report.json
write_manifest.py       → output/run_manifest.json
build_dashboard.py      → output/dashboard.html + output/global_report.md
archive_run.py          → output/runs/{timestamp}/ + output/latest/
rsm-formatter-agent     → output/regional/{region}/rsm_brief_{region}_{date}.md
                        → output/regional/{region}/rsm_flash_{region}_{datetime}z.md
```

---

## data.json Schema

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

`financial_rank` and `signal_type` are null for CLEAR/MONITOR regions. Set by regional-analyst-agent for escalated regions only.

---

## Stop Hook Wiring

| Hook script | Agent | What it checks |
|---|---|---|
| `regional-analyst-stop.py` | regional-analyst-agent | Auto-discovers most recent report.md (5 min window) → runs jargon-auditor + source-attribution-auditor |
| `json-auditor.py` | global-builder-agent | JSON parseability + required keys + type validation |
| `validate_global_report.py` | global-builder-agent | VaCR arithmetic, Admiralty consistency, scenario cross-check (100% deterministic Python) |
| `jargon-auditor.py` | global-builder-agent | Forbidden jargon + SOC language + budget advice |
| `rsm-formatter-stop.py` | rsm-formatter-agent | Auto-discovers most recent rsm_*.md (5 min window) → runs rsm-brief-auditor |
| `rsm-brief-auditor.py` | (called by rsm-formatter-stop.py) | Brief type detection, required sections, ADM format, WATCH LIST depth ≥3, jargon |
| `source-attribution-auditor.py` | (called by regional-analyst-stop.py) | Evidenced claims must cite a named source from signal_clusters.json |

Circuit breaker: `output/.retries/{label}.retries` — cap 3, then force-approve.

---

## Scenario Coupling

`scenario_mapper.py` keyword scorer provides a hint only. `regional-analyst-agent` owns the authoritative determination:
1. Reads `master_scenarios.json` + `company_profile.json` + signal files
2. Validates or overrides `scenario_map.json` hint
3. Writes `primary_scenario`, `financial_rank`, `signal_type` back to `data.json`

---

## Mock Mode

All agents run mock by default. OSINT chain reads `data/mock_osint_fixtures/{region}_{geo|cyber}.json`.

**Active threats (ESCALATE):** APAC (HIGH, System intrusion, $18.5M), AME (CRITICAL, Ransomware, $22M), MED (MEDIUM, Insider misuse, $4.2M)
**Quiet regions (CLEAR):** LATAM (LOW), NCE (LOW)

To go live: remove `--mock` from collector calls in `run-crq.md`. Set `TAVILY_API_KEY` in `.env`.

---

## All Tool Commands

```bash
# OSINT collection
uv run python tools/geopolitical_context.py <REGION>
uv run python tools/geo_collector.py <REGION> [--mock]
uv run python tools/cyber_collector.py <REGION> [--mock]
uv run python tools/scenario_mapper.py <REGION> [--mock]
uv run python tools/threat_scorer.py <REGION>

# Pipeline support
uv run python tools/audit_logger.py <EVENT> <MESSAGE>
uv run python tools/write_gatekeeper_decision.py <REGION>
uv run python tools/write_region_data.py <REGION> <escalated|monitor|clear>
uv run python tools/write_manifest.py
uv run python tools/archive_run.py
uv run python tools/trend_analyzer.py
uv run python tools/report_differ.py

# Output
uv run python tools/build_dashboard.py
uv run python tools/export_pdf.py [out.pdf]
uv run python tools/export_pptx.py [out.pptx]

# RSM dispatch
uv run python tools/seerist_collector.py <REGION> [--mock] [--window 7d]
uv run python tools/delta_computer.py <REGION>
uv run python tools/threshold_evaluator.py [--force-weekly] [--check-flash]
uv run python tools/rsm_dispatcher.py --weekly --mock
uv run python tools/rsm_dispatcher.py --check-flash --mock
uv run python tools/notifier.py output/routing_decisions.json [--mock]
uv run python tools/scheduler.py --once

# Validators (manual)
uv run python .claude/hooks/validators/crq-schema-validator.py data/mock_crq_database.json
uv run python .claude/hooks/validators/jargon-auditor.py <report_path> <label>
uv run python .claude/hooks/validators/json-auditor.py <json_path> <label>
uv run python .claude/hooks/validators/rsm-brief-auditor.py <brief_path> <label>
uv run python .claude/hooks/validators/validate_global_report.py
```

---

## UI Data Contract

Every run produces a deterministic structure a frontend can ingest:
- `run_manifest.json` — master state: pipeline ID, per-region status/severity/VaCR/admiralty
- `regional/{region}/data.json` — always exists for all 5 regions
- `regional/{region}/report.md` — only when `status: "escalated"`
- `global_report.json` — executive_summary, regional_threats array, monitor_regions array
- `dashboard.html` — self-contained Tailwind dashboard
- `signal_clusters.json` — source clusters consumed by dashboard UI only (not pipeline)

---

## Observability

`tools/audit_logger.py` → `output/system_trace.log`. Events: PIPELINE_START, GATEKEEPER_YES/NO, HOOK_PASS/FAIL, PHASE_COMPLETE, PIPELINE_COMPLETE.

`output/tool_trace.log` — Pre/PostToolUse hook telemetry: Write/Edit completions + Bash failures.