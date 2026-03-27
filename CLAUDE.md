# CLAUDE.md

**Project:** Top-Down CRQ Agentic Pipeline — AeroGrid Wind Solutions (renewable energy). Multi-agent geopolitical + cyber risk intelligence → executive board reports. Native Claude Code only — no LangChain/LangGraph/CrewAI.

**Boundary:** Intelligence & Synthesis layer only. VaCR = immutable input from separate CRQ app. Never calculate — consume, contextualize, report.

## Engineering Protocol (MANDATORY — every session)

1. **Teams first:** Non-trivial tasks → `TeamCreate` before touching code.
2. **Roles:** Opus orchestrates (never implements). Sonnet builds. Sonnet validates. Haiku triages.
3. **Builder/Validator pairing:** Every output verified by separate validator before acceptance.
4. **Parallel by default:** Independent tasks run with `run_in_background: true`.
5. **Stop hooks:** Agents prove completion — they do not claim it.
6. **Context discipline:** Delegate token-heavy work to sub-agents.
7. **Clean up:** `TeamDelete` after task complete. Hard reset.
8. **Run `/prime-dev` before build sessions.** Principles: `docs/superpowers/specs/agent-design-principles.md`

## Stack

Python `uv` | FastAPI `server.py` | Playwright + Jinja2 (PDF) | python-pptx | Tailwind (dashboard)

Key packages: `fpdf2`, `python-pptx`, `python-dotenv`, `playwright`, `jinja2`

## Slash Commands

| Command | Description |
|---|---|
| `/run-crq` | Full pipeline — 5 regional tasks in parallel, global synthesis |
| `/crq-region <REGION>` | Re-run single region |
| `/prime-crq` | Load deep architecture context (agents, data flow, schemas, hooks) |
| `/architect` | Scaffold entire system from scratch |
| `/prime-dev` | Pre-build ritual — read principles, declare team, confirm protocol |

## Agents (`.claude/agents/`)

| Agent | Model | Role |
|---|---|---|
| `gatekeeper-agent` | haiku | Triage — Admiralty rating, ESCALATE/MONITOR/CLEAR |
| `regional-analyst-agent` | sonnet | Scenario coupling, three-pillar brief, data.json — stop hook: jargon + source attribution |
| `global-builder-agent` | sonnet | Synthesizes all regions → global_report.json — stop hook: JSON schema + jargon + VaCR validation |
| `global-validator-agent` | haiku | Devil's advocate cross-check of global report |
| `rsm-formatter-agent` | sonnet | Weekly INTSUM + flash alerts for RSMs — stop hook: RSM brief auditor |

## Key Directories

```
.claude/commands/     # Slash commands (run-crq, crq-region, architect, prime-crq)
.claude/agents/       # Sub-agent definitions with stop hooks
.claude/hooks/        # validators/ (auditors, schema checks) + telemetry/ (tool trace)
data/                 # company_profile.json, master_scenarios.json, mock_osint_fixtures/
tools/                # Python utility scripts (collectors, exporters, dashboard, RSM dispatcher)
output/               # Pipeline artifacts — regional/, global_report.json, dashboard.html, runs/
```

## Critical Rules

- YAML frontmatter: `name`, `description`, `tools`, `model`, `hooks` ONLY. No `color`, `argument-hint`.
- Persona: Strategic Geopolitical & Cyber Risk Analyst — NOT SOC engineer. Zero technical jargon, zero SOC language, zero budget advice.
- Regions: APAC, AME, LATAM, MED, NCE. Mock mode default (`--mock` flag on collectors).
- Agents write for the whole org (~30k employees): CISO, board, regional ops, sales — not just security teams.

**Run `/prime-crq` for:** agent hierarchy, file-passing contract, data.json schema, stop hook wiring, mock config, UI data contract, and all tool commands.
