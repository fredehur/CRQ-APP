# OSINT Window Selector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the silent `7d` OSINT default with an interactive window selector in `/run-crq` and `/crq-region`, persisting the choice to `run_config.json` as canonical state.

**Architecture:** Phase 0 of each slash command uses `AskUserQuestion` to present a 5-option menu (1d / 7d / 30d / 90d / all). The selection is written to `output/pipeline/run_config.json`. Downstream tools already handle `window=None` as no-filter — the orchestrator simply omits `--window` for the `all` case. `write_manifest.py` reads the window from `run_config.json` instead of a CLI arg.

**Tech Stack:** Python 3 / `uv` / Claude Code slash commands (`.claude/commands/`) / JSON

---

## File Map

| File | Action | Change |
|------|--------|--------|
| `tools/write_manifest.py` | Modify | Read `window` from `run_config.json`; accept `all` as valid value |
| `.claude/commands/run-crq.md` | Modify | Add `AskUserQuestion` to tools; replace silent default with interactive prompt + `run_config.json` write |
| `.claude/commands/crq-region.md` | Modify | Same pattern as run-crq — add window prompt at Step 0 |

**No changes to:** `osint_search.py`, `geo_collector.py`, `cyber_collector.py`, `research_collector.py` — they already handle `window=None` correctly.

---

## Task 1: `write_manifest.py` — read window from run_config.json

**Files:**
- Modify: `tools/write_manifest.py`

Current code reads `--window` from CLI only and does not accept `all`. When the orchestrator omits `--window` (for the `all` case), `window_used` records `"unspecified"` instead of `"all"`. Fix: read `run_config.json` as a fallback; extend valid values to include `all`.

- [ ] **Step 1: Update `build_manifest` to read run_config.json as fallback**

Replace the `build_manifest` function signature and add config file read:

```python
def build_manifest(window_used=None):
    # If not supplied via CLI, try run_config.json
    if window_used is None:
        config_path = Path("output/pipeline/run_config.json")
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                window_used = config.get("window")
            except Exception:
                pass

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # ... rest of function unchanged
```

Add `from pathlib import Path` at the top if not already imported. (It is not — add it.)

Full updated top of file:

```python
"""Assembles output/pipeline/run_manifest.json from all regional data.json files."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tools.config import REGIONS, MANIFEST_PATH
```

- [ ] **Step 2: Update argparse to accept `all`**

Replace:
```python
parser.add_argument("--window", choices=["1d", "7d", "30d", "90d"], default=None,
                    help="Date window used for OSINT collection")
```

With:
```python
parser.add_argument("--window", choices=["1d", "7d", "30d", "90d", "all"], default=None,
                    help="Date window used for OSINT collection (all = no date filter)")
```

- [ ] **Step 3: Verify manually**

```bash
# Create a minimal run_config.json
echo '{"window": "1d", "osint_mode": "mock"}' > output/pipeline/run_config.json

# Run without --window flag
uv run python tools/write_manifest.py

# Check window_used in output
python -c "import json; d=json.load(open('output/pipeline/run_manifest.json')); print('window_used:', d['window_used'])"
```

Expected output: `window_used: 1d`

- [ ] **Step 4: Verify `all` via CLI flag**

```bash
uv run python tools/write_manifest.py --window all
python -c "import json; d=json.load(open('output/pipeline/run_manifest.json')); print('window_used:', d['window_used'])"
```

Expected: `window_used: all`

- [ ] **Step 5: Commit**

```bash
git add tools/write_manifest.py
git commit -m "feat(manifest): read window from run_config.json, accept 'all' as valid value"
```

---

## Task 2: `run-crq.md` — interactive window selector + run_config.json write

**Files:**
- Modify: `.claude/commands/run-crq.md`

Two changes: (1) add `AskUserQuestion` to the `tools:` frontmatter, (2) replace the current WINDOW logic in Phase 0 with the interactive prompt + `run_config.json` write.

- [ ] **Step 1: Add `AskUserQuestion` to tools frontmatter**

Current frontmatter:
```yaml
tools: Bash, Agent, Task
```

Replace with:
```yaml
tools: Bash, Agent, Task, AskUserQuestion
```

- [ ] **Step 2: Replace Phase 0 WINDOW block**

Find the current block (lines ~38–43 in run-crq.md):

```markdown
**Determine WINDOW:**
Parse `--window` from the invocation arguments (e.g., `/run-crq --window 30d`).
- If `--window` is provided with a valid value (`1d`, `7d`, `30d`, `90d`): store as `WINDOW` (e.g., `30d`).
- If `--window` is omitted or not provided: default to `WINDOW=7d`.
Store `WINDOW` for use in Phase 1 and Phase 6.
```

Replace with:

```markdown
**Determine WINDOW:**
Parse `--window` from the invocation arguments.
- Valid explicit values: `1d`, `7d`, `30d`, `90d`, `all`.
- If `--window` is provided with a valid value: store as `WINDOW`. Skip the prompt below.
- If `--window` is omitted: use `AskUserQuestion` to present this menu and wait for the operator's response:

  ```
  How far back should we collect OSINT signals?
    1) 1 day    — today's signals (daily ops)
    2) 1 week   — 7 days
    3) 1 month  — 30 days
    4) 3 months — 90 days
    5) All      — no date filter (baseline sweep)
  ```

  Map the response to `WINDOW`:
  - `1` → `1d`
  - `2` → `7d`
  - `3` → `30d`
  - `4` → `90d`
  - `5` → `all`

**Write run_config.json** — immediately after `WINDOW` is resolved, write the run configuration file:

```bash
python -c "
import json, os
from pathlib import Path
from datetime import datetime, timezone
Path('output/pipeline').mkdir(parents=True, exist_ok=True)
config = {
    'window': '{WINDOW}',
    'osint_mode': '{OSINT_MODE_LABEL}',
    'written_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
}
Path('output/pipeline/run_config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
print('run_config.json written — window={WINDOW}')
"
```

Where `{OSINT_MODE_LABEL}` is `live` if `OSINT_LIVE=true`, else `mock`.

Store `WINDOW` for use in Phase 1 and Phase 6.
```

- [ ] **Step 3: Update Phase 1 tool invocations for `all` case**

In Phase 1, the collector tools currently always receive `--window {WINDOW}`. When `WINDOW=all`, omit the flag entirely (the tools handle `window=None` as no-filter).

Find the Phase 1 research_collector invocation:
```
uv run python tools/research_collector.py {REGION} --window {WINDOW}
```

Replace with:
```
If WINDOW is not "all":
  uv run python tools/research_collector.py {REGION} --window {WINDOW}
Else:
  uv run python tools/research_collector.py {REGION}
```

Apply the same conditional (`if WINDOW != "all"`) to all three collector invocations:
- `tools/geo_collector.py {REGION} --mock --window {WINDOW}`
- `tools/cyber_collector.py {REGION} --mock --window {WINDOW}`
- `tools/youtube_collector.py {REGION} {OSINT_MODE} --window {WINDOW}`

- [ ] **Step 4: Update Phase 6 write_manifest.py call**

Current Phase 6:
```
uv run python tools/write_manifest.py --window {WINDOW}
```

Replace with:
```
uv run python tools/write_manifest.py
```

`write_manifest.py` now reads `window` from `run_config.json` automatically (Task 1). No arg needed.

- [ ] **Step 5: Commit**

```bash
git add .claude/commands/run-crq.md
git commit -m "feat(run-crq): interactive OSINT window selector — AskUserQuestion + run_config.json"
```

---

## Task 3: `crq-region.md` — window selector parity

**Files:**
- Modify: `.claude/commands/crq-region.md`

Same pattern as Task 2. `/crq-region APAC` should also ask for a window rather than defaulting silently.

- [ ] **Step 1: Add `AskUserQuestion` to tools frontmatter**

Current:
```yaml
tools: Bash, Agent, Read
```

Replace with:
```yaml
tools: Bash, Agent, Read, AskUserQuestion
```

- [ ] **Step 2: Add window selection block to Step 0**

Current Step 0:
```markdown
**Step 0 — Load regional data**

Read `data/mock_crq_database.json` to get the critical assets and VaCR for this region.
Log start: `uv run python tools/audit_logger.py PIPELINE_START "crq-region: {REGION} pipeline initiated"`
```

Replace with:
```markdown
**Step 0 — Load regional data + determine window**

Read `data/mock_crq_database.json` to get the critical assets and VaCR for this region.

**Determine WINDOW:**
Parse `--window` from the invocation arguments. Valid values: `1d`, `7d`, `30d`, `90d`, `all`.
- If `--window` is provided: store as `WINDOW`. Skip the prompt.
- If omitted: use `AskUserQuestion` to present:

  ```
  How far back should we collect OSINT signals?
    1) 1 day    — today's signals (daily ops)
    2) 1 week   — 7 days
    3) 1 month  — 30 days
    4) 3 months — 90 days
    5) All      — no date filter (baseline sweep)
  ```

  Map: `1`→`1d`, `2`→`7d`, `3`→`30d`, `4`→`90d`, `5`→`all`.

**Write run_config.json:**

```bash
python -c "
import json
from pathlib import Path
from datetime import datetime, timezone
Path('output/pipeline').mkdir(parents=True, exist_ok=True)
config = {
    'window': '{WINDOW}',
    'osint_mode': 'mock',
    'written_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
}
Path('output/pipeline/run_config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
print('run_config.json written — window={WINDOW}')
"
```

Log start: `uv run python tools/audit_logger.py PIPELINE_START "crq-region: {REGION} pipeline initiated — window={WINDOW}"`
```

- [ ] **Step 3: Update Step 5 write_manifest.py call**

Current Step 5:
```bash
uv run python tools/write_manifest.py
```

This already has no `--window` arg — no change needed. `write_manifest.py` will read from `run_config.json`.

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/crq-region.md
git commit -m "feat(crq-region): interactive OSINT window selector — parity with run-crq"
```

---

## Self-Review

**Spec coverage:**
- ✅ Interactive prompt when no `--window` passed — Tasks 2 + 3
- ✅ 5 options: 1d / 7d / 30d / 90d / all — Tasks 2 + 3
- ✅ `all` → omit `--window` flag downstream — Task 2 Step 3
- ✅ `run_config.json` as state file — Tasks 2 + 3
- ✅ `write_manifest.py` reads from `run_config.json` — Task 1
- ✅ Empty-arg edge case fixed — Task 1 (no CLI arg passed to manifest)
- ✅ `/crq-region` parity — Task 3
- ✅ No changes to collector tools — confirmed in file map

**Placeholder scan:** No TBDs, no "implement later", all code blocks are complete.

**Type consistency:** `run_config.json` schema (`window`, `osint_mode`, `written_at`) used consistently across Tasks 1, 2, 3.
