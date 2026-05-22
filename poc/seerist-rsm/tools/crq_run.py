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
    if not isinstance(cfg["brand_label"], str):
        raise CrqRunError("crq.config.json: brand_label must be a string. Re-run /setup.")
    if not isinstance(cfg["org_context_default"], bool):
        raise CrqRunError("crq.config.json: org_context_default must be a boolean. Re-run /setup.")
    return cfg


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


def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_state(state: dict, path: Path = STATE_PATH) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def read_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        raise CrqRunError(
            "crq_run_state.json not found. Run the collect step first:\n"
            "  uv run python tools/crq_run.py collect --regions <REGION(S)>"
        )
    return json.loads(path.read_text(encoding="utf-8"))


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
    print(f"\n[crq_run] Collected signals for {date}: {', '.join(region_list)}.")
    print("Analyst request(s) to work through:")
    for region in region_list:
        print(f"  {_day_dir(region, date) / 'analyst_request.md'}")
    print(
        "\nAGENT STEP REQUIRED: for each analyst_request.md above, read it, then write\n"
        "claims.json and analyst_report.md into the SAME folder (follow the AUTHORING\n"
        "CONTRACT in the /crq-run skill). When all regions are done, run:\n"
        "  uv run python tools/crq_run.py prep"
    )


def cmd_prep(state_path=STATE_PATH):
    state = read_state(state_path)
    for region in state["regions"]:
        _run(build_phase_argv(region, state["date"], "--prep-format"))
    print(f"\n[crq_run] Prepared formatter inputs: {', '.join(state['regions'])}.")
    print("Formatter request(s) to work through:")
    for region in state["regions"]:
        print(f"  {_day_dir(region, state['date']) / 'formatter_request.md'}")
    print(
        "\nAGENT STEP REQUIRED: for each formatter_request.md above, read it, then write\n"
        "brief.md into the SAME folder (follow the AUTHORING CONTRACT). When all regions\n"
        "are done, run:\n"
        "  uv run python tools/crq_run.py render"
    )


def cmd_render(state_path=STATE_PATH):
    state = read_state(state_path)
    for region in state["regions"]:
        _run(build_phase_argv(region, state["date"], "--render"))
    print(f"\n[crq_run] Done. Briefs rendered for {', '.join(state['regions'])}.")
    print("Open each email.html in a browser to read or send the brief:")
    for region in state["regions"]:
        print(f"  {_day_dir(region, state['date']) / 'email.html'}")


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
