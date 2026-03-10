# CRQ Dev Team — Design Spec

**Date:** 2026-03-10
**Status:** Approved
**Feature flag:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

---

## Overview

A native Claude Code agent team (`crq-dev-team`) that helps build and maintain the CRQ application following disler's agentic principles. This team is strictly the **development layer** — it is not part of the CRQ intelligence pipeline and must never be confused with the runtime agents.

---

## Guiding Principles (disler)

1. **Specialized over generalized** — each agent does exactly one thing
2. **Filesystem as state** — agents communicate via files, never in-memory
3. **Deterministic over probabilistic** — Guardian hook enforces rules; LLM handles judgment only where needed
4. **Single responsibility** — one agent, one domain, one purpose
5. **Complete auditability** — every orchestrator plan and guardian decision is written to disk
6. **Commit fully** — native teams config, no hybrid hedging

---

## Team Identity

**Team name:** `crq-dev-team`
**Config:** `.claude/teams/crq-dev-team.json`
**Purpose field:** `"Development team for building and maintaining the CRQ app. These agents are NOT part of the intelligence pipeline."`

All dev team agents use the `dev-` prefix. CRQ pipeline agents (`gatekeeper-agent`, `regional-analyst-agent`, `global-builder-agent`) are completely separate and unmodified.

---

## Agent Roster

| Agent | File | Model | Trigger | Role |
|---|---|---|---|---|
| `dev-orchestrator` | `.claude/agents/dev-orchestrator.md` | Opus | `/dev` slash command | Decomposes feature requests, fans out to specialists via Task tool, assembles results |
| `dev-pipeline-engineer` | `.claude/agents/dev-pipeline-engineer.md` | Sonnet | Direct invocation | Pipeline orchestration, agent hierarchy, phases, run-crq logic |
| `dev-frontend-engineer` | `.claude/agents/dev-frontend-engineer.md` | Sonnet | Direct invocation | Dashboard, HTML, Tailwind, app.js, static assets |
| `dev-tools-engineer` | `.claude/agents/dev-tools-engineer.md` | Sonnet | Direct invocation | tools/*.py, validators, Python utilities, hooks |
| `dev-prompt-engineer` | `.claude/agents/dev-prompt-engineer.md` | Sonnet | Direct invocation | .claude/agents/*.md, .claude/commands/*.md, persona tuning |
| `dev-disler-guardian` | `.claude/agents/dev-disler-guardian.md` | Haiku | Stop hook (automatic) | Validates disler principles on every specialist completion |

**Model rationale:**
- Opus for orchestrator: decomposition and planning requires the highest reasoning quality
- Sonnet for specialists: domain execution is well-scoped, Sonnet is sufficient
- Haiku for guardian: validation is deterministic judgment, not creative reasoning

---

## Invocation Patterns

### Complex feature work → Orchestrator
```
/dev add a new export format for the board report
```
The orchestrator writes `output/.dev/plan.json`, then fans out to the relevant specialists via Task tool in parallel where tasks are independent. Results are assembled and the Guardian validates each specialist's output on Stop.

### Focused task → Direct specialist
```
use dev-frontend-engineer to fix the dashboard Tailwind layout
use dev-tools-engineer to add retry logic to export_pdf.py
```
No orchestrator overhead. Specialist does one thing, Guardian fires on Stop.

---

## Disler Guardian

The Guardian is the quality gate. It fires automatically — it is never directly invoked.

**Trigger:** Stop hook on all 4 specialist agents
**Script:** `.claude/hooks/validators/disler-guardian.py`
**Checks:**
1. **Single responsibility** — did the agent touch files outside its domain?
2. **No scope creep** — did the agent add unrequested features or refactors?
3. **Filesystem as state** — no hardcoded in-memory assumptions, all state via files
4. **No hallucinated dependencies** — imports and tool calls reference things that actually exist
5. **Disler protocol** — output files contain no preamble, no sycophancy, no unsolicited advice

**Exit codes:**
- `sys.exit(0)` — approved, agent completes
- `sys.exit(2)` — violation found, agent forced to rewrite

Circuit breaker: `.retries/dev-{agent}.retries` caps at 3 retries per session (mirrors CRQ pipeline pattern).

---

## Agent Persona (all specialists)

All agents enforce the Disler Protocol:
- Act as Unix CLI pipe — not a chatbot, not an assistant
- Zero preamble, zero sycophancy
- Filesystem as state — read what exists, write the output, stop
- Assume hostile auditing — every file written will be parsed and validated
- Output is always a file write or edit — never just text in the terminal

---

## File Structure

```
.claude/
  teams/
    crq-dev-team.json              # Team manifest
  agents/
    _README.md                     # Lists pipeline agents vs dev team agents
    # CRQ pipeline agents (unchanged)
    gatekeeper-agent.md
    regional-analyst-agent.md
    global-builder-agent.md
    # Dev team agents
    dev-orchestrator.md
    dev-pipeline-engineer.md
    dev-frontend-engineer.md
    dev-tools-engineer.md
    dev-prompt-engineer.md
    dev-disler-guardian.md
  commands/
    dev.md                         # /dev slash command
  hooks/
    validators/
      disler-guardian.py           # Guardian hook script
output/
  .dev/
    plan.json                      # Orchestrator writes before fan-out
    session.log                    # Guardian decisions per session
```

---

## Separation Guarantees

| Signal | Detail |
|---|---|
| Naming | All dev agents prefixed `dev-` — no overlap with pipeline agent names |
| Manifest | `crq-dev-team.json` `purpose` field explicitly excludes pipeline |
| CLAUDE.md | Dedicated `## Dev Team` section added |
| `_README.md` | Clear two-column listing of pipeline vs dev team agents |
| Output isolation | `output/.dev/` is never touched by pipeline; pipeline outputs never touched by dev team |

---

## Out of Scope

- This team does NOT restructure the CRQ intelligence pipeline
- This team does NOT modify VaCR figures or scenario baselines
- This team is NOT a runtime agent — it has no role in producing board reports
- The guardian does NOT audit pipeline agent output (that's `jargon-auditor.py` and `json-auditor.py`)
