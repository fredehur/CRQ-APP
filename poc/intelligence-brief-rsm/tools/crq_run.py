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
SITES_PATH = PROJECT_ROOT / "data" / "aerowind_sites.json"
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
    # osint_default is optional (older configs predate it); defaults to off.
    osint_default = cfg.get("osint_default", False)
    if not isinstance(osint_default, bool):
        raise CrqRunError("crq.config.json: osint_default must be a boolean. Re-run /setup.")
    cfg["osint_default"] = osint_default
    return cfg


def _region_has_sites(region: str, sites_path: Path = SITES_PATH) -> bool:
    """True if aerowind_sites.json carries at least one site for this region.

    Used by cmd_collect to auto-fall-back to region-guided mode for regions with
    no facility footprint. Missing/invalid file → False (safer default: assume
    no org grounding rather than render an empty AEROWIND EXPOSURE block).
    """
    if not sites_path.exists():
        return False
    try:
        doc = json.loads(sites_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return any(
        s.get("region", "").upper() == region.upper()
        for s in doc.get("sites", [])
    )


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


def resolve_override(override: bool | None, config_default: bool) -> bool:
    """Generic per-run override: None means use the config default."""
    return config_default if override is None else override


def resolve_org_context(override: bool | None, config_default: bool) -> bool:
    """override: True (org-grounded) / False (region-guided) / None (use config default)."""
    return resolve_override(override, config_default)


def build_collect_argv(
    region: str, date: str, *, org_context: bool, brand_label: str, osint: bool = False
) -> list[str]:
    argv = [sys.executable, POC_RUNNER, region, date, "--collect", "--require-live"]
    if osint:
        argv.append("--osint")
    if not org_context:
        argv.append("--no-org-context")
    argv += ["--brand", brand_label]
    return argv


def build_phase_argv(region: str, date: str, phase: str) -> list[str]:
    """phase is '--prep-format' or '--render'."""
    return [sys.executable, POC_RUNNER, region, date, phase]


def build_analyze_argv(region: str, date: str, *, org_context: bool = True,
                       brand_label: str | None = None) -> list[str]:
    argv = [sys.executable, POC_RUNNER, region, date, "--analyze"]
    if not org_context:
        argv.append("--no-org-context")
    if brand_label is not None:
        argv += ["--brand", brand_label]
    return argv


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
    """Per-(date, region) brief folder. Mirrors poc_runner._day_dir.

    Shape: output/briefs/<YYYY-MM-DD>/<REGION>/
    """
    return PROJECT_ROOT / "output" / "briefs" / date / region.upper()


def cmd_collect(regions, org_grounded_override, date, osint_override=None,
                config_path=CONFIG_PATH, state_path=STATE_PATH,
                sites_path=SITES_PATH):
    cfg = load_config(config_path)
    region_list = expand_regions(regions)
    date = date or today_iso()
    org_context_requested = resolve_org_context(org_grounded_override, cfg["org_context_default"])
    osint = resolve_override(osint_override, cfg["osint_default"])
    brand_label = cfg["brand_label"]
    region_org_context: dict[str, bool] = {}
    for region in region_list:
        effective = org_context_requested and _region_has_sites(region, sites_path)
        region_org_context[region] = effective
        if org_context_requested and not effective:
            print(
                f"[crq_run] {region}: no sites in aerowind_sites.json — running region-guided.",
                file=sys.stderr,
            )
        _run(build_collect_argv(region, date, org_context=effective,
                                brand_label=brand_label, osint=osint))
    write_state(
        {
            "date": date,
            "regions": region_list,
            "org_context": org_context_requested,
            "region_org_context": region_org_context,
            "brand_label": brand_label,
        },
        state_path,
    )
    print(f"\n[crq_run] Collected signals for {date}: {', '.join(region_list)}.")
    if osint:
        print("OSINT enrich request(s) to work through:")
        for region in region_list:
            print(f"  {_day_dir(region, date) / 'osint_enrich_request.md'}")
        print(
            "\nAGENT STEP REQUIRED: for each osint_enrich_request.md above, read it and\n"
            "rewrite osint_physical_signals.json enriched (+ osint_dropped.json). Then run:\n"
            "  uv run python tools/crq_run.py analyze"
        )
    else:
        print("Next: uv run python tools/crq_run.py analyze")


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


def cmd_analyze(state_path=STATE_PATH):
    state = read_state(state_path)
    region_org_context = state.get("region_org_context", {})
    brand_label = state.get("brand_label")
    for region in state["regions"]:
        # Default true preserves prior behavior for older state files (pre-fallback).
        effective = region_org_context.get(region, state.get("org_context", True))
        _run(build_analyze_argv(region, state["date"],
                                org_context=effective, brand_label=brand_label))
    print(f"\n[crq_run] Built manifest + analyst request: {', '.join(state['regions'])}.")
    for region in state["regions"]:
        print(f"  {_day_dir(region, state['date']) / 'analyst_request.md'}")
    print(
        "\nAGENT STEP REQUIRED: for each analyst_request.md above, read it, then write\n"
        "claims.json and analyst_report.md into the SAME folder (follow the AUTHORING\n"
        "CONTRACT in the /intel-brief skill). When all regions are done, run:\n"
        "  uv run python tools/crq_run.py prep"
    )


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
    ogrp = pc.add_mutually_exclusive_group()
    ogrp.add_argument("--osint", dest="osint_override", action="store_const", const=True, default=None,
                      help="Include the OSINT physical pillar (web/news) this run (needs Tavily/Firecrawl keys)")
    ogrp.add_argument("--no-osint", dest="osint_override", action="store_const", const=False,
                      help="Skip the OSINT physical pillar this run (Seerist-only)")
    pc.add_argument("--date", default=None, help="YYYY-MM-DD; defaults to today (UTC)")

    sub.add_parser("analyze", help="Build manifest + analyst_request (after OSINT enrichment).")
    sub.add_parser("prep", help="Run --prep-format for each region in run-state.")
    sub.add_parser("render", help="Run --render for each region in run-state.")

    args = p.parse_args(argv)
    try:
        if args.cmd == "collect":
            cmd_collect(regions=args.regions, org_grounded_override=args.override,
                        osint_override=args.osint_override, date=args.date)
        elif args.cmd == "analyze":
            cmd_analyze()
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
