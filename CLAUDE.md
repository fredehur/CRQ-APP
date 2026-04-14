# CLAUDE.md

**Project:** Top-Down CRQ Agentic Pipeline — AeroGrid Wind Solutions (renewable energy). Multi-agent geopolitical + cyber risk intelligence → executive board reports. Native Claude Code only — no LangChain/LangGraph/CrewAI.

**Boundary:** Intelligence & Synthesis layer only. VaCR = immutable input from separate CRQ app. Never calculate — consume, contextualize, report.

## Universal Principles (single source of truth)

Agent design, boundary, and skill-contract principles live in the **agent-team-blueprint repo**:
`C:/Users/frede/agent-team-blueprint/docs/` — do not maintain copies here.
`/prime-dev` reads from that path directly.

## Engineering Protocol (MANDATORY — every session)

1. **Teams first:** Non-trivial tasks → `TeamCreate` before touching code.
2. **Roles:** Opus orchestrates (never implements). Sonnet builds. Sonnet validates. Haiku triages.
3. **Builder/Validator pairing:** Every output verified by separate validator before acceptance.
4. **Parallel by default:** Independent tasks run with `run_in_background: true`.
5. **No Bash in background agents:** Builders get Read/Edit/Write/Glob/Grep only. Validators get Read/Glob/Grep only. Orchestrator owns all Bash execution. See `agent-team-blueprint/docs/agent-boundary-principles.md` → Tool Permission Model.
6. **Stop hooks:** Agents prove completion — they do not claim it.
7. **Context discipline:** Delegate token-heavy work to sub-agents.
8. **jcodemunch first:** All code navigation via index tools — see policy below.
9. **Clean up:** `TeamDelete` after task complete. Hard reset.
10. **Run `/prime-dev` before build sessions.** Principles: `C:/Users/frede/agent-team-blueprint/docs/agent-design-principles.md`

## Code Exploration Policy

Always use jCodemunch-MCP tools for code navigation. Never fall back to Read, Grep, Glob, or Bash for code exploration.

```
Read / Grep / Glob / Bash  →  last resort only (markdown, JSON data files)
jcodemunch-mcp             →  default for ALL code navigation
```

**Start any session:**
1. `list_repos` — confirm the project is indexed. If not: `index_folder { "path": "." }`

**Finding code:**
- symbol by name → `search_symbols` (add `kind=`, `language=`, `file_pattern=` to narrow)
- string, comment, config value → `search_text` (supports regex, `context_lines`)

**Reading code:**
- before opening any file → `get_file_outline` first
- one symbol → `get_symbol`
- multiple symbols → `get_symbols` (batch)

**Repo structure:**
- `get_repo_outline` → dirs, languages, symbol counts
- `get_file_tree` → file layout, filter with `path_prefix`

**After editing/adding a file:** `index_folder { "path": ".", "incremental": true }` to keep the index fresh.
**After deleting a file:** `invalidate_cache { "repo": "local/<repo-name>" }` — incremental does NOT prune stale symbols for deleted files.

Full reference: `C:/Users/frede/agent-team-blueprint/docs/tools/jcodemunch-mcp.md`

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
| `rsm-formatter-agent` | sonnet | Daily + weekly INTSUM + flash alerts for RSMs — stop hooks: brief auditor + context checks (site discipline, personnel match, cadence sections, scribe quote, consequence length, empty-stub) |

## RSM Path

| Command | Effect |
|---|---|
| `uv run python tools/rsm_dispatcher.py --daily --mock` | All 5 regions × daily, parallel fan-out, empty stub on quiet days, delivery_log row per region |
| `uv run python tools/rsm_dispatcher.py --daily --mock --region MED` | One region × daily |
| `uv run python tools/rsm_dispatcher.py --weekly --mock` | Weekly INTSUM via existing routing |
| `uv run python tools/poi_proximity.py REGION --mock` | Recompute event-site proximity + cascade for a region |
| `uv run python tools/osint_physical_collector.py REGION --mock` | Pull OSINT physical-pillar signals |

**Per-region invariants:**
- Brief unit of work = `(region, cadence)` — never aggregate across regions
- Site name discipline: every site mentioned in a brief must be in `data/aerowind_sites.json` for that region
- Personnel counts in briefs must match registry exactly — stop hook enforces this
- Daily empty stub is generated by code (`_write_daily_empty_stub`), not the agent
- `output/delivery_log.json` is append-only — every daily run logs even quiet days

**Canonical site registry:** `data/aerowind_sites.json` is the only source of truth. `company_profile.facilities` was removed — anything that read it now reads `aerowind_sites.json` and filters by `region`.

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
