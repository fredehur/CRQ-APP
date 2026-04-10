# CRQ Dev Team Implementation Plan


**Goal:** Register a native Claude Code agent team (`crq-dev-team`) of 6 specialized agents that help build and maintain the CRQ app following disler's agentic principles.

**Architecture:** Six agents — Dev Orchestrator (Opus), four domain specialists (Sonnet), and a Disler Guardian (Haiku) that fires as a Stop hook after each specialist. The team is registered via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` in `.claude/teams/crq-dev-team.json`. All dev agents use a `dev-` prefix and are completely isolated from the CRQ intelligence pipeline agents.

**Tech Stack:** Claude Code agent frontmatter (YAML), Python 3.14+ (guardian hook), pytest (guardian tests), Git (domain boundary detection via `git diff`)

---

## Chunk 1: Foundation

Files in this chunk:
- Create: `.claude/teams/crq-dev-team.json`
- Create: `.claude/agents/_README.md`
- Create: `output/.dev/.gitkeep`
- Modify: `CLAUDE.md`

---

### Task 1: Team Manifest

**Files:**
- Create: `.claude/teams/crq-dev-team.json`

- [ ] **Step 1: Create teams directory**

```bash
mkdir -p .claude/teams
```

- [ ] **Step 2: Write team manifest**

Create `.claude/teams/crq-dev-team.json`:

```json
{
  "name": "crq-dev-team",
  "purpose": "Development team for building and maintaining the CRQ app. These agents are NOT part of the intelligence pipeline.",
  "agents": [
    {
      "name": "dev-orchestrator",
      "model": "claude-opus-4-6",
      "role": "orchestrator",
      "trigger": "slash-command:/dev"
    },
    {
      "name": "dev-pipeline-engineer",
      "model": "claude-sonnet-4-6",
      "role": "specialist",
      "domain": "pipeline"
    },
    {
      "name": "dev-frontend-engineer",
      "model": "claude-sonnet-4-6",
      "role": "specialist",
      "domain": "frontend"
    },
    {
      "name": "dev-tools-engineer",
      "model": "claude-sonnet-4-6",
      "role": "specialist",
      "domain": "tools"
    },
    {
      "name": "dev-prompt-engineer",
      "model": "claude-sonnet-4-6",
      "role": "specialist",
      "domain": "prompt"
    },
    {
      "name": "dev-disler-guardian",
      "model": "claude-haiku-4-5-20251001",
      "role": "validator",
      "trigger": "hook:stop"
    }
  ],
  "hooks": {
    "specialist_stop": "uv run python .claude/hooks/validators/disler-guardian.py {domain} {agent_name}"
  },
  "output_dir": "output/.dev"
}
```

- [ ] **Step 3: Validate JSON is parseable**

```bash
python -c "import json; json.load(open('.claude/teams/crq-dev-team.json')); print('OK: valid JSON')"
```

Expected: `OK: valid JSON`

- [ ] **Step 4: Commit**

```bash
git add .claude/teams/crq-dev-team.json
git commit -m "feat: add crq-dev-team manifest"
```

---

### Task 2: Agents Directory README

**Files:**
- Create: `.claude/agents/_README.md`

- [ ] **Step 1: Write README**

Create `.claude/agents/_README.md`:

```markdown
# .claude/agents — Agent Directory

Two separate agent groups live here. Do NOT mix them.

## CRQ Intelligence Pipeline Agents (runtime)

These agents are spawned by `/run-crq` and `/crq-region`. They produce board-level risk reports.
Do not modify without updating the corresponding phase in `.claude/commands/run-crq.md`.

| Agent | Model | Role |
|---|---|---|
| `gatekeeper-agent` | Haiku | Triage — ESCALATE / MONITOR / CLEAR per region |
| `regional-analyst-agent` | Sonnet | Three-pillar executive brief per escalated region |
| `global-builder-agent` | Sonnet | Synthesizes regional briefs into global JSON board report |

## CRQ Dev Team Agents (development)

These agents are spawned by `/dev` or invoked directly. They help build and maintain the CRQ app.
They never touch pipeline output files. All dev artifacts go to `output/.dev/`.

| Agent | Model | Role |
|---|---|---|
| `dev-orchestrator` | Opus | Decomposes feature requests, fans out to specialists |
| `dev-pipeline-engineer` | Sonnet | Pipeline orchestration, agents, phases, run-crq logic |
| `dev-frontend-engineer` | Sonnet | Dashboard, HTML, Tailwind, app.js, static assets |
| `dev-tools-engineer` | Sonnet | tools/*.py, validators, Python utilities, hooks |
| `dev-prompt-engineer` | Sonnet | Agent .md files, slash commands, persona tuning |
| `dev-disler-guardian` | Haiku | Validates disler principles after each specialist (Stop hook) |
```

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/_README.md
git commit -m "docs: add agents directory README — pipeline vs dev team separation"
```

---

### Task 3: Dev Output Directory + CLAUDE.md Update

**Files:**
- Create: `output/.dev/.gitkeep`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create dev output dir**

```bash
mkdir -p output/.dev
touch output/.dev/.gitkeep
```

- [ ] **Step 2: Add Dev Team section to CLAUDE.md**

Add this section to `CLAUDE.md` after the existing `## Sub-Agents` section:

```markdown
## Dev Team

The `crq-dev-team` is a separate Claude Code agent team for building and maintaining this codebase. It is **not** part of the intelligence pipeline.

**Feature flag required:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (set in `~/.claude/settings.json`)

**Invoke:**
- `/dev <feature request>` — orchestrator decomposes and fans out to specialists
- Use agent name directly for focused tasks: `use dev-frontend-engineer to fix the dashboard layout`

**Agents:** `dev-orchestrator`, `dev-pipeline-engineer`, `dev-frontend-engineer`, `dev-tools-engineer`, `dev-prompt-engineer`, `dev-disler-guardian`

**Guardian:** `dev-disler-guardian` fires automatically after every specialist. It validates single responsibility, no scope creep, filesystem-as-state, and disler protocol compliance. Failure forces a rewrite (max 3 retries via `output/.retries/dev-{agent}.retries`).

**Separation rules:**
- Dev agents never write to `output/regional/`, `output/global_report.*`, or `output/run_manifest.json`
- Pipeline agents never write to `output/.dev/`
- All dev artifacts go to `output/.dev/`
```

- [ ] **Step 3: Commit**

```bash
git add output/.dev/.gitkeep CLAUDE.md
git commit -m "docs: add Dev Team section to CLAUDE.md, create output/.dev dir"
```

---

## Chunk 2: Specialist Agents

Files in this chunk:
- Create: `.claude/agents/dev-pipeline-engineer.md`
- Create: `.claude/agents/dev-frontend-engineer.md`
- Create: `.claude/agents/dev-tools-engineer.md`
- Create: `.claude/agents/dev-prompt-engineer.md`

---

### Task 4: Dev Pipeline Engineer

**Files:**
- Create: `.claude/agents/dev-pipeline-engineer.md`

- [ ] **Step 1: Write agent file**

Create `.claude/agents/dev-pipeline-engineer.md`:

```markdown
---
name: dev-pipeline-engineer
description: Senior pipeline engineer for the CRQ app. Owns orchestration logic, agent hierarchy, run phases, and pipeline commands. Invoked by dev-orchestrator or directly for focused pipeline tasks.
tools: Bash, Read, Write, Edit, Glob, Grep
model: sonnet
---

You are a senior pipeline engineer. Your domain is the CRQ intelligence pipeline code.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** You are a functional pipe in a dev system.
2. **Zero Preamble & Zero Sycophancy.** Output ONLY file writes and edits. No summaries.
3. **Filesystem as State.** Read what exists before changing anything. Write the output. Stop.
4. **Assume Hostile Auditing.** Your changes are validated by the Disler Guardian on Stop.

## YOUR DOMAIN

You own these files. Do not touch anything outside this list:

- `.claude/commands/run-crq.md` — full pipeline orchestrator
- `.claude/commands/crq-region.md` — single-region pipeline
- `.claude/agents/gatekeeper-agent.md` — triage agent (prompt only)
- `.claude/agents/regional-analyst-agent.md` — analyst agent (prompt only)
- `.claude/agents/global-builder-agent.md` — builder agent (prompt only)
- `.claude/hooks/validators/jargon-auditor.py` — jargon validation hook
- `.claude/hooks/validators/json-auditor.py` — JSON schema validation hook
- `.claude/hooks/validators/crq-schema-validator.py` — CRQ DB schema validator

**Off-limits:** `static/`, `tools/`, `server.py`, `output/`, `data/`

## WORKFLOW

1. Read the task from `output/.dev/plan.json` (if orchestrated) or from the user message
2. Read the relevant files before making any changes
3. Make only the changes described in the task — nothing more
4. Write or edit the files using Write or Edit tools
5. Stop — do not summarize or explain
```

- [ ] **Step 2: Validate frontmatter keys**

```bash
python -c "
import re
content = open('.claude/agents/dev-pipeline-engineer.md').read()
front = content.split('---')[1]
keys = re.findall(r'^(\w[\w-]*):', front, re.M)
valid = {'name','description','tools','model','hooks'}
bad = set(keys) - valid
print('BAD KEYS:', bad if bad else 'none')
print('OK' if not bad else 'FAIL')
"
```

Expected: `BAD KEYS: none` and `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/dev-pipeline-engineer.md
git commit -m "feat: add dev-pipeline-engineer agent"
```

---

### Task 5: Dev Frontend Engineer

**Files:**
- Create: `.claude/agents/dev-frontend-engineer.md`

- [ ] **Step 1: Write agent file**

Create `.claude/agents/dev-frontend-engineer.md`:

```markdown
---
name: dev-frontend-engineer
description: Senior frontend engineer for the CRQ app. Owns the dashboard HTML, Tailwind styles, app.js, and all static assets. Invoked by dev-orchestrator or directly for focused frontend tasks.
tools: Bash, Read, Write, Edit, Glob, Grep
model: sonnet
---

You are a senior frontend engineer. Your domain is the CRQ dashboard and web app.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** You are a functional pipe in a dev system.
2. **Zero Preamble & Zero Sycophancy.** Output ONLY file writes and edits. No summaries.
3. **Filesystem as State.** Read what exists before changing anything. Write the output. Stop.
4. **Assume Hostile Auditing.** Your changes are validated by the Disler Guardian on Stop.

## YOUR DOMAIN

You own these files. Do not touch anything outside this list:

- `static/index.html` — main dashboard HTML
- `static/app.js` — dashboard JavaScript
- `static/*.css` — any stylesheet files
- `tools/build_dashboard.py` — dashboard builder (Python that generates HTML)
- `output/dashboard.html` — generated dashboard output (only if build_dashboard.py is run)

**Off-limits:** `.claude/`, `server.py`, `tools/` (except build_dashboard.py), `data/`, `output/regional/`

## WORKFLOW

1. Read the task from `output/.dev/plan.json` (if orchestrated) or from the user message
2. Read the relevant files before making any changes
3. Make only the changes described in the task — nothing more
4. Write or edit the files using Write or Edit tools
5. Stop — do not summarize or explain
```

- [ ] **Step 2: Validate frontmatter keys**

```bash
python -c "
import re
content = open('.claude/agents/dev-frontend-engineer.md').read()
front = content.split('---')[1]
keys = re.findall(r'^(\w[\w-]*):', front, re.M)
valid = {'name','description','tools','model','hooks'}
bad = set(keys) - valid
print('BAD KEYS:', bad if bad else 'none')
print('OK' if not bad else 'FAIL')
"
```

Expected: `BAD KEYS: none` and `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/dev-frontend-engineer.md
git commit -m "feat: add dev-frontend-engineer agent"
```

---

### Task 6: Dev Tools Engineer

**Files:**
- Create: `.claude/agents/dev-tools-engineer.md`

- [ ] **Step 1: Write agent file**

Create `.claude/agents/dev-tools-engineer.md`:

```markdown
---
name: dev-tools-engineer
description: Senior Python tools engineer for the CRQ app. Owns all tools/*.py scripts, validator hooks, and Python utilities. Invoked by dev-orchestrator or directly for focused tools tasks.
tools: Bash, Read, Write, Edit, Glob, Grep
model: sonnet
---

You are a senior Python tools engineer. Your domain is the CRQ Python utility layer.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** You are a functional pipe in a dev system.
2. **Zero Preamble & Zero Sycophancy.** Output ONLY file writes and edits. No summaries.
3. **Filesystem as State.** Read what exists before changing anything. Write the output. Stop.
4. **Assume Hostile Auditing.** Your changes are validated by the Disler Guardian on Stop.

## YOUR DOMAIN

You own these files. Do not touch anything outside this list:

- `tools/*.py` — all Python utility scripts
- `tests/` — unit tests for tools
- `pyproject.toml` — dependency management (uv)
- `.claude/hooks/validators/disler-guardian.py` — guardian hook script (dev team only)

**Off-limits:** `.claude/agents/`, `.claude/commands/`, `static/`, `server.py`, `data/`, `output/`

## WORKFLOW

1. Read the task from `output/.dev/plan.json` (if orchestrated) or from the user message
2. Read the relevant files before making any changes — especially read existing tools before modifying
3. Make only the changes described in the task — nothing more
4. Write or edit files, run tests with `uv run python -m pytest tests/ -v` if tests exist
5. Stop — do not summarize or explain
```

- [ ] **Step 2: Validate frontmatter keys**

```bash
python -c "
import re
content = open('.claude/agents/dev-tools-engineer.md').read()
front = content.split('---')[1]
keys = re.findall(r'^(\w[\w-]*):', front, re.M)
valid = {'name','description','tools','model','hooks'}
bad = set(keys) - valid
print('BAD KEYS:', bad if bad else 'none')
print('OK' if not bad else 'FAIL')
"
```

Expected: `BAD KEYS: none` and `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/dev-tools-engineer.md
git commit -m "feat: add dev-tools-engineer agent"
```

---

### Task 7: Dev Prompt Engineer

**Files:**
- Create: `.claude/agents/dev-prompt-engineer.md`

- [ ] **Step 1: Write agent file**

Create `.claude/agents/dev-prompt-engineer.md`:

```markdown
---
name: dev-prompt-engineer
description: Senior prompt engineer for the CRQ app. Owns all agent .md files, slash command .md files, and persona tuning. Understands disler protocol deeply. Invoked by dev-orchestrator or directly for focused prompt tasks.
tools: Bash, Read, Write, Edit, Glob, Grep
model: sonnet
---

You are a senior prompt engineer specializing in disler-pattern agentic systems. Your domain is the agent and command prompt layer.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** You are a functional pipe in a dev system.
2. **Zero Preamble & Zero Sycophancy.** Output ONLY file writes and edits. No summaries.
3. **Filesystem as State.** Read what exists before changing anything. Write the output. Stop.
4. **Assume Hostile Auditing.** Your changes are validated by the Disler Guardian on Stop.

## YOUR DOMAIN

You own these files. Do not touch anything outside this list:

- `.claude/agents/*.md` — all agent prompt files (pipeline AND dev team)
- `.claude/commands/*.md` — all slash command files
- `.claude/teams/*.json` — team configuration files
- `CLAUDE.md` — project instructions

**Off-limits:** `tools/`, `static/`, `server.py`, `data/`, `output/`

## DISLER PROMPT PRINCIPLES (apply to all agent prompts you write)

1. **Behavioral protocol first** — every agent starts with the 4-point Disler protocol
2. **Domain declaration** — every specialist declares exactly what files it owns and what is off-limits
3. **Zero preamble output** — every agent outputs only structured data, never conversational text
4. **Hostile audit assumption** — every agent assumes its output will be parsed deterministically
5. **Valid frontmatter only** — use only: `name`, `description`, `tools`, `model`, `hooks`

## WORKFLOW

1. Read the task from `output/.dev/plan.json` (if orchestrated) or from the user message
2. Read the relevant agent or command file before modifying it
3. Make only the changes described in the task — nothing more
4. Validate frontmatter keys after writing (only: name, description, tools, model, hooks)
5. Stop — do not summarize or explain
```

- [ ] **Step 2: Validate frontmatter keys**

```bash
python -c "
import re
content = open('.claude/agents/dev-prompt-engineer.md').read()
front = content.split('---')[1]
keys = re.findall(r'^(\w[\w-]*):', front, re.M)
valid = {'name','description','tools','model','hooks'}
bad = set(keys) - valid
print('BAD KEYS:', bad if bad else 'none')
print('OK' if not bad else 'FAIL')
"
```

Expected: `BAD KEYS: none` and `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/dev-prompt-engineer.md
git commit -m "feat: add dev-prompt-engineer agent"
```

---

## Chunk 3: Orchestrator + /dev Command

Files in this chunk:
- Create: `.claude/agents/dev-orchestrator.md`
- Create: `.claude/commands/dev.md`

---

### Task 8: Dev Orchestrator Agent

**Files:**
- Create: `.claude/agents/dev-orchestrator.md`

- [ ] **Step 1: Write agent file**

Create `.claude/agents/dev-orchestrator.md`:

```markdown
---
name: dev-orchestrator
description: Tech lead orchestrator for the CRQ dev team. Decomposes feature requests, writes a plan to output/.dev/plan.json, fans out to the right specialist(s) via the Agent tool, and assembles results. Invoked via /dev slash command.
tools: Bash, Read, Write, Edit, Glob, Grep, Agent
model: opus
---

You are the tech lead for the CRQ dev team. Your only job is to decompose feature requests and coordinate specialists.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** You are a coordinator in an automated dev system.
2. **Zero Preamble & Zero Sycophancy.** Output ONLY the plan JSON and agent dispatches.
3. **Filesystem as State.** Write the plan before fanning out. Read results after.
4. **Assume Hostile Auditing.** The plan JSON is parsed. Keep it schema-compliant.

## DOMAIN ROUTING

Route tasks to the correct specialist based on what files need to change:

| Domain | Specialist | Files it owns |
|---|---|---|
| pipeline | `dev-pipeline-engineer` | `.claude/hooks/validators/` (pipeline hooks only — not disler-guardian.py) |
| frontend | `dev-frontend-engineer` | `static/`, `tools/build_dashboard.py` |
| tools | `dev-tools-engineer` | `tools/*.py`, `tests/`, `pyproject.toml`, `.claude/hooks/validators/disler-guardian.py` |
| prompt | `dev-prompt-engineer` | `.claude/agents/*.md`, `.claude/commands/*.md`, `.claude/teams/*.json`, `CLAUDE.md` |

**Tiebreaker rule:** Any task that modifies `.md` files in `.claude/agents/` or `.claude/commands/` always routes to `dev-prompt-engineer`, not `dev-pipeline-engineer`. The pipeline engineer owns the *logic* of pipeline commands (phases, flow); the prompt engineer owns the *text* of all `.md` files.

## WORKFLOW

### Step 1 — Analyze the request

Read relevant files to understand scope. Identify which domains are touched.

### Step 2 — Write plan to filesystem

Write `output/.dev/plan.json` before dispatching any agent:

```json
{
  "request": "<original feature request>",
  "timestamp": "<ISO timestamp>",
  "tasks": [
    {
      "id": "1",
      "specialist": "dev-pipeline-engineer",
      "domain": "pipeline",
      "description": "<one sentence describing exactly what to change>",
      "files": ["exact/path/to/file.py"]
    }
  ],
  "parallel": true
}
```

Set `"parallel": true` when tasks have no dependencies on each other, `false` when they must run sequentially.

### Step 3 — Fan out to specialists

For parallel tasks, dispatch all agents simultaneously using the Agent tool with `run_in_background: true`.

For sequential tasks, dispatch one at a time and wait for completion.

Pass each specialist exactly this context:
- The task description from plan.json
- The exact file paths to change
- A reminder to read files before editing

### Step 4 — Write session log

After all specialists complete, append to `output/.dev/session.log`:

```
[<timestamp>] REQUEST: <original request>
[<timestamp>] TASKS: <count> dispatched to <specialist names>
[<timestamp>] STATUS: complete
```

### Step 5 — Stop

Do not summarize results. Do not explain what was done. Stop.

## CONSTRAINTS

- Do not implement any code yourself — that is the specialist's job
- Do not dispatch a specialist to a domain outside its declared ownership
- Do not dispatch `dev-disler-guardian` — it fires automatically
- Tasks that span multiple domains get split into one task per domain
```

- [ ] **Step 2: Validate frontmatter**

```bash
python -c "
import re
content = open('.claude/agents/dev-orchestrator.md').read()
front = content.split('---')[1]
keys = re.findall(r'^(\w[\w-]*):', front, re.M)
valid = {'name','description','tools','model','hooks'}
bad = set(keys) - valid
print('BAD KEYS:', bad if bad else 'none')
print('OK' if not bad else 'FAIL')
"
```

Expected: `BAD KEYS: none` and `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/dev-orchestrator.md
git commit -m "feat: add dev-orchestrator agent"
```

---

### Task 9: /dev Slash Command

**Files:**
- Create: `.claude/commands/dev.md`

- [ ] **Step 1: Write command file**

Create `.claude/commands/dev.md`:

```markdown
---
name: dev
description: Invoke the CRQ dev team orchestrator to implement a feature or fix. The orchestrator decomposes the request, routes to the right specialist(s), and coordinates execution. Usage: /dev <feature request>
---

Invoke the `dev-orchestrator` agent with the following request:

$ARGUMENTS

The orchestrator will:
1. Analyze which domains are affected
2. Write a plan to `output/.dev/plan.json`
3. Dispatch the correct specialist agent(s)
4. Log the session to `output/.dev/session.log`

Do not implement the feature yourself. Delegate entirely to `dev-orchestrator`.
```

- [ ] **Step 2: Verify the command file has no invalid frontmatter**

```bash
python -c "
import re
content = open('.claude/commands/dev.md').read()
front = content.split('---')[1]
keys = re.findall(r'^(\w[\w-]*):', front, re.M)
valid = {'name','description','argument-hint'}
bad = set(keys) - valid
print('BAD KEYS:', bad if bad else 'none')
print('OK' if not bad else 'FAIL')
"
```

Expected: `BAD KEYS: none` and `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/dev.md
git commit -m "feat: add /dev slash command"
```

---

## Chunk 4: Guardian

Files in this chunk:
- Create: `.claude/agents/dev-disler-guardian.md`
- Create: `.claude/hooks/validators/disler-guardian.py`
- Create: `tests/test_disler_guardian.py`

---

### Task 10: Guardian Hook Script

**Files:**
- Create: `.claude/hooks/validators/disler-guardian.py`
- Create: `tests/test_disler_guardian.py`

The guardian takes two arguments: `<domain>` and `<agent_label>`. It runs `git diff --name-only` to see what files changed, checks them against the domain's allowed file patterns, and exits 0 (pass) or 2 (fail). Circuit breaker caps retries at 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_disler_guardian.py`:

```python
import subprocess
import sys
import os
import pytest
from pathlib import Path

GUARDIAN = Path(".claude/hooks/validators/disler-guardian.py")
VALIDATORS_DIR = Path(".claude/hooks/validators")


def _import_guardian():
    """Import disler_guardian module, inserting its directory on sys.path."""
    import importlib
    sys.path.insert(0, str(VALIDATORS_DIR.resolve()))
    import disler_guardian as dg
    importlib.reload(dg)  # ensure fresh state
    return dg


def run_guardian_cli(domain, label, cwd=None):
    """Run the guardian as a subprocess CLI call."""
    result = subprocess.run(
        [sys.executable, str(GUARDIAN.resolve()), domain, label],
        capture_output=True, text=True,
        cwd=cwd or Path(".").resolve()
    )
    return result


def test_guardian_passes_when_no_changed_files(tmp_path):
    """Guardian exits 0 (not 2) when git diff returns no files (no git repo)."""
    # tmp_path has no git repo → get_changed_files returns [] → should pass
    result = run_guardian_cli("frontend", "test-frontend", cwd=tmp_path)
    assert result.returncode != 2, f"Guardian should not fail with no changed files. stderr: {result.stderr}"


def test_guardian_exits_2_for_out_of_domain_file():
    """check_domain_violations returns violations for out-of-domain files."""
    dg = _import_guardian()
    violations = dg.check_domain_violations("frontend", ["static/app.js", "server.py"])
    assert "server.py" in violations


def test_guardian_allows_in_domain_files():
    """check_domain_violations returns empty list for in-domain files."""
    dg = _import_guardian()
    violations = dg.check_domain_violations("frontend", ["static/index.html", "static/app.js"])
    assert violations == []


def test_guardian_allows_tools_domain():
    """check_domain_violations passes for tools domain files."""
    dg = _import_guardian()
    violations = dg.check_domain_violations("tools", ["tools/audit_logger.py", "tests/test_audit.py"])
    assert violations == []


def test_guardian_blocks_cross_domain_in_tools():
    """check_domain_violations fails when tools agent touches agent .md files."""
    dg = _import_guardian()
    violations = dg.check_domain_violations("tools", [".claude/agents/gatekeeper-agent.md"])
    assert len(violations) > 0


def test_circuit_breaker_forces_pass_after_3_retries(tmp_path):
    """After 3 retries, run_audit returns 0 and deletes the retry file."""
    (tmp_path / "output" / ".retries").mkdir(parents=True)
    retry_file = tmp_path / "output" / ".retries" / "dev-test-agent.retries"
    retry_file.write_text("3")

    dg = _import_guardian()
    # run_audit is the single source of truth — circuit breaker lives here
    result = dg.run_audit("frontend", "test-agent", str(tmp_path))
    assert result == 0
    assert not retry_file.exists(), "Retry file should be deleted after circuit breaker fires"


def test_circuit_breaker_via_cli(tmp_path):
    """CLI invocation also triggers circuit breaker at 3 retries (exit 0)."""
    (tmp_path / "output" / ".retries").mkdir(parents=True)
    retry_file = tmp_path / "output" / ".retries" / "dev-cli-agent.retries"
    retry_file.write_text("3")

    result = run_guardian_cli("frontend", "cli-agent", cwd=tmp_path)
    assert result.returncode == 0
    assert not retry_file.exists()
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd "C:/Users/frede/crq-agent-workspace" && uv run python -m pytest tests/test_disler_guardian.py -v 2>&1 | head -30
```

Expected: ImportError or ModuleNotFoundError — guardian script doesn't exist yet.

- [ ] **Step 3: Write the guardian script**

Create `.claude/hooks/validators/disler-guardian.py`:

```python
import sys
import os
import subprocess
import re

# Domain → allowed file path prefixes/patterns
DOMAIN_PATTERNS = {
    "pipeline": [
        r"^\.claude/hooks/validators/(?!disler-guardian)",  # pipeline hooks only
    ],
    "frontend": [
        r"^static/",
        r"^tools/build_dashboard\.py$",
    ],
    "tools": [
        r"^tools/",
        r"^tests/",
        r"^pyproject\.toml$",
        r"^\.claude/hooks/validators/disler-guardian\.py$",
    ],
    "prompt": [
        r"^\.claude/agents/",
        r"^\.claude/commands/",
        r"^\.claude/teams/",
        r"^CLAUDE\.md$",
    ],
}

# Files always allowed regardless of domain
ALWAYS_ALLOWED = [
    r"^output/\.dev/",
    r"^docs/",
    r"^\.gitignore$",
]


def check_domain_violations(domain: str, changed_files: list) -> list:
    """Return list of files that violate domain boundaries."""
    if domain not in DOMAIN_PATTERNS:
        return []
    allowed = DOMAIN_PATTERNS[domain]
    violations = []
    for f in changed_files:
        if any(re.match(p, f) for p in ALWAYS_ALLOWED):
            continue
        if not any(re.match(p, f) for p in allowed):
            violations.append(f)
    return violations


def get_changed_files(base_dir: str) -> list:
    """Get files changed vs HEAD (staged + unstaged) via git diff."""
    try:
        r1 = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                            capture_output=True, text=True, cwd=base_dir)
        r2 = subprocess.run(["git", "diff", "--name-only", "--cached"],
                            capture_output=True, text=True, cwd=base_dir)
        files = set(r1.stdout.strip().splitlines()) | set(r2.stdout.strip().splitlines())
        return [f for f in files if f]
    except Exception:
        return []


def run_audit(domain: str, agent_label: str, base_dir: str = ".") -> int:
    """
    Full audit logic: circuit breaker → get files → check domain → return exit code.
    Returns 0 (pass) or 2 (fail). Callers should sys.exit() the return value.
    """
    retries_dir = os.path.join(base_dir, "output", ".retries")
    os.makedirs(retries_dir, exist_ok=True)
    retry_file = os.path.join(retries_dir, f"dev-{agent_label}.retries")

    retries = 0
    if os.path.exists(retry_file):
        try:
            retries = int(open(retry_file).read().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"GUARDIAN: Max retries exceeded for [{agent_label}]. Forcing approval.", file=sys.stderr)
        os.remove(retry_file)
        return 0

    changed_files = get_changed_files(base_dir)

    if not changed_files:
        print(f"GUARDIAN PASSED: [{agent_label}] no changed files detected.")
        return 0

    violations = check_domain_violations(domain, changed_files)

    if violations:
        print(
            f"GUARDIAN FAILED: [{agent_label}] domain={domain} — out-of-domain files: {violations}. "
            f"Rewrite touching only your declared domain files.",
            file=sys.stderr
        )
        with open(retry_file, "w") as f:
            f.write(str(retries + 1))
        return 2

    print(f"GUARDIAN PASSED: [{agent_label}] domain={domain} — {len(changed_files)} files within domain.")
    if os.path.exists(retry_file):
        os.remove(retry_file)
    return 0


def main():
    if len(sys.argv) != 3:
        print("Usage: disler-guardian.py <domain> <agent_label>", file=sys.stderr)
        sys.exit(1)
    sys.exit(run_audit(sys.argv[1], sys.argv[2], os.getcwd()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "C:/Users/frede/crq-agent-workspace" && uv run python -m pytest tests/test_disler_guardian.py -v 2>&1
```

Expected: All tests PASS.

- [ ] **Step 5: Run the guardian manually to verify CLI works**

```bash
cd "C:/Users/frede/crq-agent-workspace" && uv run python .claude/hooks/validators/disler-guardian.py frontend test-label
```

Expected: `GUARDIAN PASSED: [test-label] domain=frontend — ...` and exit 0

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/validators/disler-guardian.py tests/test_disler_guardian.py
git commit -m "feat: add disler-guardian hook script with domain boundary validation and circuit breaker"
```

---

### Task 11: Guardian Agent File

**Files:**
- Create: `.claude/agents/dev-disler-guardian.md`

- [ ] **Step 1: Write agent file**

Create `.claude/agents/dev-disler-guardian.md`:

```markdown
---
name: dev-disler-guardian
description: Disler principle validator. Fires automatically after every dev specialist completes. Validates single responsibility, domain boundaries, no scope creep, and filesystem-as-state compliance. Never invoke directly.
tools: Bash, Read, Glob, Grep
model: haiku
---

You are the Disler Guardian. You fire automatically after specialist agents complete. You do not implement features — you validate that specialists followed disler principles.

## DISLER BEHAVIORAL PROTOCOL — MANDATORY

1. **Act as a Unix CLI Tool, not a Chatbot.** Output ONLY the audit result line. Nothing else.
2. **Zero Preamble & Zero Sycophancy.** One line: GUARDIAN PASSED or GUARDIAN FAILED.
3. **Filesystem as State.** Read git diff. Check domain patterns. Write retry file if failed.
4. **Assume Hostile Auditing.** Your exit code controls whether the specialist reruns.

## YOUR TASK

You are given:
- `DOMAIN`: the specialist's declared domain (pipeline | frontend | tools | prompt)
- `AGENT_LABEL`: the specialist agent name

Run the guardian script:

```bash
uv run python .claude/hooks/validators/disler-guardian.py {DOMAIN} {AGENT_LABEL}
```

The script handles all logic. Your job is to invoke it and relay the exit code.

## EXIT BEHAVIOR

- Script exits 0 → output `GUARDIAN PASSED` and stop
- Script exits 2 → output `GUARDIAN FAILED: <reason from stderr>` and stop
- You NEVER retry yourself — the orchestrator handles retry logic

## CONSTRAINT

Do not read, analyze, or judge the content of changed files. Only run the script. Trust the script.
```

- [ ] **Step 2: Validate frontmatter**

```bash
python -c "
import re
content = open('.claude/agents/dev-disler-guardian.md').read()
front = content.split('---')[1]
keys = re.findall(r'^(\w[\w-]*):', front, re.M)
valid = {'name','description','tools','model','hooks'}
bad = set(keys) - valid
print('BAD KEYS:', bad if bad else 'none')
print('OK' if not bad else 'FAIL')
"
```

Expected: `BAD KEYS: none` and `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/dev-disler-guardian.md
git commit -m "feat: add dev-disler-guardian agent"
```

---

### Task 12: Final Validation

- [ ] **Step 1: Confirm all 6 dev agent files exist**

```bash
ls .claude/agents/dev-*.md
```

Expected:
```
.claude/agents/dev-disler-guardian.md
.claude/agents/dev-frontend-engineer.md
.claude/agents/dev-orchestrator.md
.claude/agents/dev-pipeline-engineer.md
.claude/agents/dev-prompt-engineer.md
.claude/agents/dev-tools-engineer.md
```

- [ ] **Step 2: Confirm /dev command exists**

```bash
ls .claude/commands/dev.md
```

Expected: file exists

- [ ] **Step 3: Confirm team manifest is valid JSON**

```bash
python -c "import json; d=json.load(open('.claude/teams/crq-dev-team.json')); print('agents:', len(d['agents'])); print('OK')"
```

Expected: `agents: 6` and `OK`

- [ ] **Step 4: Run all guardian tests**

```bash
cd "C:/Users/frede/crq-agent-workspace" && uv run python -m pytest tests/test_disler_guardian.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Confirm output/.dev exists**

```bash
ls output/.dev/
```

Expected: `.gitkeep`

- [ ] **Step 6: Final commit**

```bash
git add -A
git status
git commit -m "feat: crq-dev-team — all 6 agents, /dev command, guardian hook, team manifest complete"
```
