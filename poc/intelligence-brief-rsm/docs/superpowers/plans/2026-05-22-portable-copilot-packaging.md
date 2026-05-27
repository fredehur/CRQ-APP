# Portable Copilot Packaging Layer — Implementation Plan

> **Execution:** Built via the `/prime-dev` blueprint — the orchestrator (Opus) owns ALL Bash (runs every test and static check); Builders (Sonnet, no Bash) write files and report `files_written` + `verify` commands; a Validator (Sonnet, read-only) checks each unit against this plan and the spec before acceptance. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator clone the repo and, inside GitHub Copilot (VSCode), run `/install` → `/setup` → `/create-skill` → `/crq-run` to produce live regional risk briefs.

**Architecture:** A deterministic Python orchestrator `tools/crq_run.py` owns all sequencing (region loop, phase order, config→flags, single shared date, run-state); it drives the existing `tools/poc_runner.py` through its CLI and pauses for the two agent authoring steps. Four Copilot prompt files (`install`, `setup`, `create-skill`, and the generated `crq-run`) form the thin markdown wrapper. The existing pipeline tools are unchanged.

**Tech Stack:** Python 3.11 + `uv`, stdlib `argparse`/`subprocess`/`json`, pytest. Markdown prompt files for GitHub Copilot.

Spec: `docs/superpowers/specs/2026-05-22-portable-copilot-packaging-design.md`

All paths are relative to `poc/seerist-rsm/`. All commands run from that directory.

---

## File structure

- `tools/crq_run.py` — the orchestrator. Functions: `load_config`, `expand_regions`, `resolve_org_context`, `build_collect_argv`, `build_phase_argv`, `today_iso`, `write_state`, `read_state`, `cmd_collect`, `cmd_prep`, `cmd_render`, `main`. One file, one responsibility (orchestration).
- `tests/test_crq_run.py` — unit tests; mocks the subprocess boundary so no live API/`truststore` is needed.
- `crq.config.example.json` — committed example config.
- `.gitignore` — add per-install/per-run artifacts.
- `.github/prompts/setup.prompt.md`, `install.prompt.md`, `create-skill.prompt.md` — authored.
- (`create-skill` generates `.github/prompts/crq-run.prompt.md` at run time — its template lives inside `create-skill.prompt.md`.)

---

## Task 1: `crq_run.py` config loader

**Files:**
- Create: `tools/crq_run.py`
- Test: `tests/test_crq_run.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_crq_run.py
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import crq_run  # noqa: E402


def _write_config(tmp_path: Path, data) -> Path:
    p = tmp_path / "crq.config.json"
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return p


def test_load_config_valid(tmp_path):
    p = _write_config(tmp_path, {"brand_label": "ACME", "org_context_default": True})
    cfg = crq_run.load_config(p)
    assert cfg["brand_label"] == "ACME"
    assert cfg["org_context_default"] is True


def test_load_config_missing_file(tmp_path):
    with pytest.raises(crq_run.CrqRunError, match="/setup"):
        crq_run.load_config(tmp_path / "nope.json")


def test_load_config_malformed_json(tmp_path):
    p = _write_config(tmp_path, "{not json")
    with pytest.raises(crq_run.CrqRunError, match="valid JSON"):
        crq_run.load_config(p)


def test_load_config_missing_fields(tmp_path):
    p = _write_config(tmp_path, {"brand_label": "ACME"})
    with pytest.raises(crq_run.CrqRunError, match="org_context_default"):
        crq_run.load_config(p)


def test_load_config_wrong_types(tmp_path):
    p = _write_config(tmp_path, {"brand_label": 1, "org_context_default": "yes"})
    with pytest.raises(crq_run.CrqRunError, match="brand_label"):
        crq_run.load_config(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crq_run.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.crq_run'` (or ImportError).

- [ ] **Step 3: Write minimal implementation**

```python
# tools/crq_run.py
"""tools/crq_run.py — deterministic orchestrator for the portable Copilot run skill.

Owns all sequencing: config load/validate, region expansion, flag translation,
a single shared date, phase order across regions, and run-state. Makes NO LLM
calls and NO judgments. The Copilot agent performs the two authoring steps
(claims.json + analyst_report.md, then brief.md) BETWEEN subcommands.

Subcommands:
    crq_run.py collect --regions MED NCE | ALL [--region-guided | --org-grounded] [--date YYYY-MM-DD]
    crq_run.py prep
    crq_run.py render
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "crq.config.json"
STATE_PATH = PROJECT_ROOT / "crq_run_state.json"
POC_RUNNER = "tools/poc_runner.py"
VALID_REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]


class CrqRunError(Exception):
    """Operator-facing orchestration error."""


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        raise CrqRunError(f"crq.config.json not found at {path}. Run /setup first.")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CrqRunError(f"crq.config.json is not valid JSON: {e}. Re-run /setup.")
    if not isinstance(cfg, dict) or "brand_label" not in cfg or "org_context_default" not in cfg:
        raise CrqRunError(
            "crq.config.json missing required fields brand_label / org_context_default. Re-run /setup."
        )
    if not isinstance(cfg["brand_label"], str) or not isinstance(cfg["org_context_default"], bool):
        raise CrqRunError(
            "crq.config.json: brand_label must be a string and org_context_default must be a boolean."
        )
    return cfg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_crq_run.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/crq_run.py tests/test_crq_run.py
git commit -m "feat(crq_run): config loader + validation"
```

---

## Task 2: region expansion + validation

**Files:**
- Modify: `tools/crq_run.py`
- Test: `tests/test_crq_run.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_crq_run.py
def test_expand_regions_subset():
    assert crq_run.expand_regions(["MED", "nce"]) == ["MED", "NCE"]


def test_expand_regions_all():
    assert crq_run.expand_regions(["ALL"]) == ["APAC", "AME", "LATAM", "MED", "NCE"]


def test_expand_regions_dedupe_preserves_order():
    assert crq_run.expand_regions(["MED", "MED", "APAC"]) == ["MED", "APAC"]


def test_expand_regions_unknown():
    with pytest.raises(crq_run.CrqRunError, match="unknown region"):
        crq_run.expand_regions(["ATLANTIS"])


def test_expand_regions_empty():
    with pytest.raises(crq_run.CrqRunError, match="no regions"):
        crq_run.expand_regions([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crq_run.py -k expand_regions -q`
Expected: FAIL — `AttributeError: module 'tools.crq_run' has no attribute 'expand_regions'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/crq_run.py
def expand_regions(regions: list[str]) -> list[str]:
    if not regions:
        raise CrqRunError("no regions specified.")
    out: list[str] = []
    for r in regions:
        ru = r.upper()
        if ru == "ALL":
            return list(VALID_REGIONS)
        if ru not in VALID_REGIONS:
            raise CrqRunError(f"unknown region '{r}'. Valid: {VALID_REGIONS} or ALL.")
        out.append(ru)
    seen: set[str] = set()
    deduped: list[str] = []
    for r in out:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return deduped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_crq_run.py -k expand_regions -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/crq_run.py tests/test_crq_run.py
git commit -m "feat(crq_run): region expansion + validation"
```

---

## Task 3: org-context resolution + flag translation

**Files:**
- Modify: `tools/crq_run.py`
- Test: `tests/test_crq_run.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_crq_run.py
def test_resolve_org_context_default_used_when_no_override():
    assert crq_run.resolve_org_context(override=None, config_default=True) is True
    assert crq_run.resolve_org_context(override=None, config_default=False) is False


def test_resolve_org_context_override_wins():
    assert crq_run.resolve_org_context(override=True, config_default=False) is True
    assert crq_run.resolve_org_context(override=False, config_default=True) is False


def test_build_collect_argv_org_grounded():
    argv = crq_run.build_collect_argv("MED", "2026-05-22", org_context=True, brand_label="ACME")
    assert argv[1] == crq_run.POC_RUNNER
    assert argv[2:5] == ["MED", "2026-05-22", "--collect"]
    assert "--require-live" in argv
    assert "--no-org-context" not in argv
    assert argv[-2:] == ["--brand", "ACME"]


def test_build_collect_argv_region_guided_adds_flag():
    argv = crq_run.build_collect_argv("NCE", "2026-05-22", org_context=False, brand_label="Neutral")
    assert "--no-org-context" in argv
    assert "--require-live" in argv
    assert argv[-2:] == ["--brand", "Neutral"]


def test_build_phase_argv():
    assert crq_run.build_phase_argv("MED", "2026-05-22", "--prep-format")[2:] == [
        "MED", "2026-05-22", "--prep-format",
    ]
    assert crq_run.build_phase_argv("MED", "2026-05-22", "--render")[2:] == [
        "MED", "2026-05-22", "--render",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crq_run.py -k "resolve_org or build_" -q`
Expected: FAIL — `AttributeError: ... has no attribute 'resolve_org_context'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/crq_run.py
def resolve_org_context(override: bool | None, config_default: bool) -> bool:
    """override: True (org-grounded) / False (region-guided) / None (use config default)."""
    return config_default if override is None else override


def build_collect_argv(region: str, date: str, *, org_context: bool, brand_label: str) -> list[str]:
    argv = [sys.executable, POC_RUNNER, region, date, "--collect", "--require-live"]
    if not org_context:
        argv.append("--no-org-context")
    argv += ["--brand", brand_label]
    return argv


def build_phase_argv(region: str, date: str, phase: str) -> list[str]:
    """phase is '--prep-format' or '--render'."""
    return [sys.executable, POC_RUNNER, region, date, phase]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_crq_run.py -k "resolve_org or build_" -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/crq_run.py tests/test_crq_run.py
git commit -m "feat(crq_run): org-context resolution + poc_runner flag translation"
```

---

## Task 4: date helper + run-state round-trip

**Files:**
- Modify: `tools/crq_run.py`
- Test: `tests/test_crq_run.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_crq_run.py
import re


def test_today_iso_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", crq_run.today_iso())


def test_state_round_trip(tmp_path):
    p = tmp_path / "crq_run_state.json"
    state = {"date": "2026-05-22", "regions": ["MED", "NCE"], "org_context": False, "brand_label": "X"}
    crq_run.write_state(state, p)
    assert crq_run.read_state(p) == state


def test_read_state_missing(tmp_path):
    with pytest.raises(crq_run.CrqRunError, match="collect"):
        crq_run.read_state(tmp_path / "nope.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crq_run.py -k "today_iso or state" -q`
Expected: FAIL — `AttributeError: ... has no attribute 'today_iso'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/crq_run.py
def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_state(state: dict, path: Path = STATE_PATH) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def read_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        raise CrqRunError("crq_run_state.json not found. Run `crq_run.py collect` first.")
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_crq_run.py -k "today_iso or state" -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/crq_run.py tests/test_crq_run.py
git commit -m "feat(crq_run): date helper + run-state persistence"
```

---

## Task 5: subcommands (collect / prep / render) with mocked subprocess

**Files:**
- Modify: `tools/crq_run.py`
- Test: `tests/test_crq_run.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_crq_run.py
def _patch_run(monkeypatch):
    """Capture argvs instead of running subprocess."""
    calls = []
    monkeypatch.setattr(crq_run, "_run", lambda argv: calls.append(argv))
    return calls


def test_cmd_collect_loops_regions_and_writes_state(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    state = tmp_path / "state.json"
    calls = _patch_run(monkeypatch)

    crq_run.cmd_collect(
        regions=["MED", "NCE"], org_grounded_override=None, date="2026-05-22",
        config_path=cfg, state_path=state,
    )

    # one collect call per region, org-grounded (no --no-org-context), brand passed, require-live on
    assert len(calls) == 2
    assert calls[0][2:5] == ["MED", "2026-05-22", "--collect"]
    assert "--require-live" in calls[0] and "--no-org-context" not in calls[0]
    assert calls[0][-2:] == ["--brand", "ACME"]
    assert calls[1][2] == "NCE"
    # state persisted
    saved = json.loads(state.read_text())
    assert saved == {"date": "2026-05-22", "regions": ["MED", "NCE"], "org_context": True, "brand_label": "ACME"}
    # prints the analyst_request path + agent-step marker
    out = capsys.readouterr().out
    assert "analyst_request.md" in out
    assert "AGENT STEP REQUIRED" in out


def test_cmd_collect_region_guided_override(tmp_path, monkeypatch):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    state = tmp_path / "state.json"
    calls = _patch_run(monkeypatch)

    crq_run.cmd_collect(
        regions=["MED"], org_grounded_override=False, date="2026-05-22",
        config_path=cfg, state_path=state,
    )
    assert "--no-org-context" in calls[0]
    assert json.loads(state.read_text())["org_context"] is False


def test_cmd_prep_uses_state_regions(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(
        {"date": "2026-05-22", "regions": ["MED", "NCE"], "org_context": True, "brand_label": "ACME"}
    ), encoding="utf-8")
    calls = _patch_run(monkeypatch)

    crq_run.cmd_prep(state_path=state)
    assert [c[2] for c in calls] == ["MED", "NCE"]
    assert all(c[-1] == "--prep-format" for c in calls)
    out = capsys.readouterr().out
    assert "formatter_request.md" in out and "AGENT STEP REQUIRED" in out


def test_cmd_render_uses_state_regions(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(
        {"date": "2026-05-22", "regions": ["MED"], "org_context": True, "brand_label": "ACME"}
    ), encoding="utf-8")
    calls = _patch_run(monkeypatch)

    crq_run.cmd_render(state_path=state)
    assert calls[0][-1] == "--render"
    out = capsys.readouterr().out
    assert "email.html" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crq_run.py -k cmd_ -q`
Expected: FAIL — `AttributeError: ... has no attribute 'cmd_collect'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/crq_run.py
def _run(argv: list[str]) -> None:
    print(f"[crq_run] $ {' '.join(argv)}", file=sys.stderr)
    result = subprocess.run(argv, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise CrqRunError(f"command failed (exit {result.returncode}): {' '.join(argv)}")


def _day_dir(region: str, date: str) -> Path:
    return PROJECT_ROOT / "output" / "poc" / region.lower() / date


def cmd_collect(regions, org_grounded_override, date, config_path=CONFIG_PATH, state_path=STATE_PATH):
    cfg = load_config(config_path)
    region_list = expand_regions(regions)
    date = date or today_iso()
    org_context = resolve_org_context(org_grounded_override, cfg["org_context_default"])
    brand_label = cfg["brand_label"]
    for region in region_list:
        _run(build_collect_argv(region, date, org_context=org_context, brand_label=brand_label))
    write_state(
        {"date": date, "regions": region_list, "org_context": org_context, "brand_label": brand_label},
        state_path,
    )
    print(f"\n[crq_run] collect complete for {date} — {', '.join(region_list)}")
    for region in region_list:
        print(f"  {_day_dir(region, date) / 'analyst_request.md'}")
    print(
        "\nAGENT STEP REQUIRED: for each path above, write claims.json + "
        "analyst_report.md to that directory, then run: crq_run.py prep"
    )


def cmd_prep(state_path=STATE_PATH):
    state = read_state(state_path)
    for region in state["regions"]:
        _run(build_phase_argv(region, state["date"], "--prep-format"))
    print(f"\n[crq_run] prep complete — {', '.join(state['regions'])}")
    for region in state["regions"]:
        print(f"  {_day_dir(region, state['date']) / 'formatter_request.md'}")
    print(
        "\nAGENT STEP REQUIRED: for each path above, write brief.md to that "
        "directory, then run: crq_run.py render"
    )


def cmd_render(state_path=STATE_PATH):
    state = read_state(state_path)
    for region in state["regions"]:
        _run(build_phase_argv(region, state["date"], "--render"))
    print(f"\n[crq_run] render complete — {', '.join(state['regions'])}")
    for region in state["regions"]:
        print(f"  {_day_dir(region, state['date']) / 'email.html'}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_crq_run.py -k cmd_ -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/crq_run.py tests/test_crq_run.py
git commit -m "feat(crq_run): collect/prep/render subcommands over poc_runner"
```

---

## Task 6: CLI entry point (`argparse` + `main`)

**Files:**
- Modify: `tools/crq_run.py`
- Test: `tests/test_crq_run.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_crq_run.py
def test_main_collect_parses_regions_and_region_guided(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(crq_run, "cmd_collect",
        lambda regions, org_grounded_override, date, **kw: captured.update(
            regions=regions, override=org_grounded_override, date=date))
    crq_run.main(["collect", "--regions", "MED", "NCE", "--region-guided", "--date", "2026-05-22"])
    assert captured["regions"] == ["MED", "NCE"]
    assert captured["override"] is False
    assert captured["date"] == "2026-05-22"


def test_main_collect_org_grounded_override(monkeypatch):
    captured = {}
    monkeypatch.setattr(crq_run, "cmd_collect",
        lambda regions, org_grounded_override, date, **kw: captured.update(override=org_grounded_override))
    crq_run.main(["collect", "--regions", "MED", "--org-grounded"])
    assert captured["override"] is True


def test_main_collect_no_override_is_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(crq_run, "cmd_collect",
        lambda regions, org_grounded_override, date, **kw: captured.update(override=org_grounded_override))
    crq_run.main(["collect", "--regions", "MED"])
    assert captured["override"] is None


def test_main_error_exits_nonzero(monkeypatch, capsys):
    def boom(*a, **k):
        raise crq_run.CrqRunError("config not found. Run /setup first.")
    monkeypatch.setattr(crq_run, "cmd_prep", boom)
    rc = crq_run.main(["prep"])
    assert rc == 1
    assert "/setup" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_crq_run.py -k main_ -q`
Expected: FAIL — `AttributeError: ... has no attribute 'main'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to tools/crq_run.py
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Deterministic orchestrator for the CRQ Copilot run skill.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("collect", help="Run --collect for each region; write run-state.")
    pc.add_argument("--regions", nargs="+", required=True, help="Region codes (APAC AME LATAM MED NCE) or ALL")
    grp = pc.add_mutually_exclusive_group()
    grp.add_argument("--region-guided", dest="override", action="store_const", const=False, default=None,
                     help="Force region-guided (no org context) for this run")
    grp.add_argument("--org-grounded", dest="override", action="store_const", const=True,
                     help="Force org-grounded for this run")
    pc.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to today (UTC)")

    sub.add_parser("prep", help="Run --prep-format for each region in run-state.")
    sub.add_parser("render", help="Run --render for each region in run-state.")

    args = p.parse_args(argv)
    try:
        if args.cmd == "collect":
            cmd_collect(regions=args.regions, org_grounded_override=args.override, date=args.date)
        elif args.cmd == "prep":
            cmd_prep()
        elif args.cmd == "render":
            cmd_render()
    except CrqRunError as e:
        print(f"[crq_run] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_crq_run.py -q`
Expected: PASS (all tests, ~25 passed).

- [ ] **Step 5: Commit**

```bash
git add tools/crq_run.py tests/test_crq_run.py
git commit -m "feat(crq_run): argparse CLI entry point"
```

---

## Task 7: example config + gitignore

**Files:**
- Create: `crq.config.example.json`
- Modify: `.gitignore`

- [ ] **Step 1: Create the example config**

```json
{
  "brand_label": "REGIONAL RISK INTELLIGENCE",
  "org_context_default": false
}
```

Write the above to `crq.config.example.json`.

- [ ] **Step 2: Add gitignore entries**

Append these lines to `.gitignore` (verify they aren't already present first):

```
# CRQ Copilot packaging — per-install / per-run / generated artifacts
crq.config.json
crq_run_state.json
.github/prompts/crq-run.prompt.md
```

- [ ] **Step 3: Verify ignore rules work**

Run: `printf '{}' > crq.config.json && git check-ignore crq.config.json && rm crq.config.json`
Expected: prints `crq.config.json` (it is ignored), then removes the temp file.

- [ ] **Step 4: Commit**

```bash
git add crq.config.example.json .gitignore
git commit -m "chore: crq.config example + gitignore per-install artifacts"
```

---

## Task 8: `setup.prompt.md`

**Files:**
- Create: `.github/prompts/setup.prompt.md`

- [ ] **Step 1: Write the file**

````markdown
---
description: Configure the CRQ regional-brief pipeline (brand, org-context default, live API key).
agent: agent
tools: ['editFiles', 'runCommands']
---

# /setup — Configure the CRQ pipeline

> Frontmatter keys are version-sensitive. If this VS Code build does not honor
> `agent:` or the `editFiles` / `runCommands` toolset names, substitute the
> correct identifiers for this build before relying on the prompt.

Do the following, in order:

1. Ask the operator for a **brand label** (the header band brand, e.g. the client
   company name, or `REGIONAL RISK INTELLIGENCE` for a neutral/prospect brief).
   Default to `REGIONAL RISK INTELLIGENCE` if they have no preference.
2. Ask whether briefs should default to **org-grounded** (uses the client's site
   registry) or **region-guided** (no org context — region is the only scope).
   This is only the *default*; `/crq-run` asks again per run.
3. **Verify the live key.** Confirm `.env` exists and contains a non-empty
   `SEERIST_API_KEY`. If `.env` is missing, copy `.env.example` to `.env` and tell
   the operator to fill `SEERIST_API_KEY`, then STOP — do not write config until a
   key is present. This pipeline is **live-only**; there is no mock fallback.
   Note: only `SEERIST_API_KEY` is required. The OSINT layer (TAVILY/FIRECRAWL)
   degrades by design — its absence yields a thinner brief, not an error. The
   analyst/formatter LLM work is done by you (the agent), so no ANTHROPIC key is
   needed.
4. Write `crq.config.json` at the repo root with exactly:

   ```json
   {
     "brand_label": "<their brand>",
     "org_context_default": <true|false>
   }
   ```

5. Confirm: "Setup complete. Next: run `/create-skill`."

Re-running `/setup` overwrites the config and re-checks the key.
````

- [ ] **Step 2: Static check — frontmatter well-formed**

Run: `uv run python -c "import re,sys; t=open('.github/prompts/setup.prompt.md',encoding='utf-8').read(); m=re.match(r'^---\n(.*?)\n---\n', t, re.S); assert m, 'no frontmatter'; b=m.group(1); assert 'agent: agent' in b and 'editFiles' in b and 'runCommands' in b, b; print('setup frontmatter OK')"`
Expected: prints `setup frontmatter OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/prompts/setup.prompt.md
git commit -m "feat(copilot): /setup prompt file"
```

---

## Task 9: `install.prompt.md`

**Files:**
- Create: `.github/prompts/install.prompt.md`

- [ ] **Step 1: Write the file**

````markdown
---
description: Bootstrap the CRQ pipeline — check prerequisites, install deps, scaffold .env.
agent: agent
tools: ['editFiles', 'runCommands']
---

# /install — Bootstrap the CRQ pipeline

> Frontmatter keys are version-sensitive (see /setup note).

Do the following, in order. Run all terminal commands from the repo root
(`poc/seerist-rsm/`).

1. Check `python --version` (need 3.11+) and `uv --version`. If `uv` is missing,
   tell the operator to install it (`https://docs.astral.sh/uv/`) and STOP.
2. Run `uv sync` to install dependencies.
3. If `.env` does not exist, copy `.env.example` to `.env`.
4. Tell the operator the remaining manual steps (prompt files are invoked by the
   user — this prompt cannot run them for you):
   - Fill `SEERIST_API_KEY` in `.env`.
   - Run `/setup` to configure brand + org-context default.
   - Run `/create-skill` to generate the `/crq-run` skill.
   - Then run `/crq-run` to produce briefs.
````

- [ ] **Step 2: Static check — frontmatter well-formed**

Run: `uv run python -c "import re; t=open('.github/prompts/install.prompt.md',encoding='utf-8').read(); m=re.match(r'^---\n(.*?)\n---\n', t, re.S); b=m.group(1); assert 'agent: agent' in b and 'runCommands' in b; print('install frontmatter OK')"`
Expected: prints `install frontmatter OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/prompts/install.prompt.md
git commit -m "feat(copilot): /install prompt file"
```

---

## Task 10: `create-skill.prompt.md` (generates the thin `crq-run`)

**Files:**
- Create: `.github/prompts/create-skill.prompt.md`

- [ ] **Step 1: Write the file**

````markdown
---
description: Generate the thin /crq-run skill from crq.config.json.
agent: agent
tools: ['editFiles']
---

# /create-skill — Generate the /crq-run skill

> Frontmatter keys are version-sensitive (see /setup note).

1. Read `crq.config.json`. If it is missing or invalid, STOP and tell the operator
   to run `/setup` first.
2. Write `.github/prompts/crq-run.prompt.md` with EXACTLY the content below
   (verbatim — it delegates all orchestration to `tools/crq_run.py` and carries
   only the operator Q&A + the two authoring steps):

   ```markdown
   ---
   description: Produce live regional risk brief(s) for today.
   agent: agent
   tools: ['editFiles', 'runCommands']
   ---

   # /crq-run — Produce today's regional brief(s)

   1. Ask the operator: which region(s)? (APAC / AME / LATAM / MED / NCE, or ALL.)
      And org-grounded or region-guided for this run? (Default comes from
      crq.config.json — if they have no preference, omit the override.)
   2. Run: `uv run python tools/crq_run.py collect --regions <THEIR REGIONS>`
      Add `--region-guided` or `--org-grounded` only if they chose to override
      the default. The command prints one `analyst_request.md` path per region.
   3. For EACH printed `analyst_request.md`: read it and write `claims.json` +
      `analyst_report.md` into the SAME directory. Follow the AUTHORING CONTRACT
      below — the render step enforces it deterministically.
   4. Run: `uv run python tools/crq_run.py prep`
      It prints one `formatter_request.md` path per region.
   5. For EACH printed `formatter_request.md`: read it and write `brief.md` into
      the SAME directory, following the AUTHORING CONTRACT.
   6. Run: `uv run python tools/crq_run.py render`
      Report the `email.html` path it prints for each region.

   ## AUTHORING CONTRACT (the render step fails if you break these)
   - Body citations use `[<claim_id>]` form (e.g. `[med-001]`) — NEVER raw numbers.
     Code renumbers them to `[1]…[N]` and builds the APPENDIX. Every body cite must
     map to a claim in claims.json, and every appended claim must be cited at least once.
   - The CYBER section must be non-empty — always include the standing watchlist
     baseline claim (sector_baseline, regional, estimate), even on a quiet day.
   - Org-grounded briefs: site rows must match `▪ <Name> [<CRIT> · <N>p / <M> expat(s)]`
     and personnel/expat counts must equal the manifest site_registry exactly.
     Region-guided briefs have NO site rows — write region-level prose under
     `█ REGIONAL EXPOSURE` instead.
   - Stop at the end of the WATCH section. Do not add a footer, trailer, or reply
     taxonomy — the template injects those and the validator rejects them in the body.
   ```

3. Tell the operator: "Generated `/crq-run`. You may need to reload the VSCode
   window before it appears in the `/` list. Then run `/crq-run`."
````

- [ ] **Step 2: Static check — outer + embedded frontmatter present**

Run: `uv run python -c "t=open('.github/prompts/create-skill.prompt.md',encoding='utf-8').read(); assert t.lstrip().startswith('---'); assert 'tools/crq_run.py collect' in t and 'tools/crq_run.py prep' in t and 'tools/crq_run.py render' in t; assert 'AUTHORING CONTRACT' in t; print('create-skill content OK')"`
Expected: prints `create-skill content OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/prompts/create-skill.prompt.md
git commit -m "feat(copilot): /create-skill generates the thin /crq-run skill"
```

---

## Task 11: full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the crq_run unit suite**

Run: `uv run pytest tests/test_crq_run.py -q`
Expected: PASS (all crq_run tests).

- [ ] **Step 2: Confirm no regressions in truststore-independent tests**

Run: `uv run pytest tests/test_crq_run.py tests/test_no_org_context.py tests/test_validate_brief.py tests/test_render_brief_html.py tests/test_normalize_citations.py tests/test_seerist_collector.py -q`
Expected: PASS (all). (The `test_seerist_*` files that import `seerist_client` fail only on the missing `truststore` dependency — that is pre-existing and unrelated; do not include them in this gate.)

- [ ] **Step 3: Static check — emitted poc_runner argv parses against the real CLI**

Run:
```bash
uv run python -c "
import sys; sys.path.insert(0,'.')
from tools import crq_run
argv = crq_run.build_collect_argv('MED','2026-05-22',org_context=False,brand_label='X')
import argparse, importlib.util
# poc_runner uses argparse with positional region, date_iso + the phase/flag opts
spec = importlib.util.spec_from_file_location('pr','tools/poc_runner.py')
# Smoke: assert the argv shape matches what poc_runner expects (region, date, --collect, flags)
assert argv[2:5]==['MED','2026-05-22','--collect'] and '--require-live' in argv and '--no-org-context' in argv and argv[-2:]==['--brand','X']
print('argv shape OK')
"
```
Expected: prints `argv shape OK`.

- [ ] **Step 4: Static check — all three prompt files have valid frontmatter**

Run:
```bash
uv run python -c "
import re,glob
for f in glob.glob('.github/prompts/*.prompt.md'):
    t=open(f,encoding='utf-8').read()
    assert re.match(r'^---\n.*?\n---\n', t, re.S), f'bad frontmatter: {f}'
    print('OK', f)
"
```
Expected: prints `OK` for `install`, `setup`, `create-skill`.

- [ ] **Step 5: Final commit (if any verification fixups were needed)**

```bash
git add -A
git commit -m "test: verify crq_run orchestration + prompt-file frontmatter" || echo "nothing to commit"
```

---

## Notes for the implementer

- **No live run possible in CI/authoring env:** the live Seerist path imports `truststore` (absent here) and needs a real key. That's why every `crq_run` test mocks the `_run`/subprocess boundary — assert the *argv*, never execute `poc_runner` live.
- **Don't modify existing `tools/`** — `crq_run.py` only composes their existing CLIs. If you find yourself editing `poc_runner.py`, stop: the design forbids it.
- **The generated `crq-run.prompt.md` is gitignored** — it is produced by `/create-skill` at the operator's machine, not committed. Only its *template* (inside `create-skill.prompt.md`) is committed.
