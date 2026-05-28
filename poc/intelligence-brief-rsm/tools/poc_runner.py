#!/usr/bin/env python3
"""Per-day RSM PoC orchestrator — four deterministic phases bracketing the
two operator-in-the-loop LLM steps (analyst + formatter), with an optional
OSINT-enrichment pause between collect and analyze. Runs for any region
(APAC / AME / LATAM / MED / NCE).

Usage:
    # Phase A: collect signals (+ write osint_enrich_request.md when --osint)
    uv run python tools/poc_runner.py MED 2026-05-17 --collect

    # [Optional operator step: run osint_enrich_request in IDE -> enriched osint_physical_signals.json]

    # Phase A-prime: build manifest + analyst_request.md
    uv run python tools/poc_runner.py MED 2026-05-17 --analyze

    # [Operator step 1: run analyst_request in IDE -> claims.json + analyst_report.md]

    # Phase B: read analyst output + build formatter_request.md
    uv run python tools/poc_runner.py MED 2026-05-17 --prep-format

    # [Operator step 2: run formatter_request in IDE -> brief.md]

    # Phase C: validate + render timestamped email HTML
    uv run python tools/poc_runner.py MED 2026-05-17 --render

All phases write to output/briefs/<date>/<cadence>/<REGION>/:
    seerist_signals.json       (--collect)
    poi_proximity.json         (--collect, if available)
    osint_physical_signals.json (--collect, if --osint; raw; enriched in the agent pause)
    osint_enrich_request.md    (--collect, if --osint — operator runs in IDE)
    _rsm_manifest_daily.json   (--analyze)
    analyst_request.md         (--analyze — operator runs in IDE)
    claims.json                (between --analyze and --prep-format, by operator+model)
    analyst_report.md          (between --analyze and --prep-format, by operator+model)
    formatter_request.md       (--prep-format — operator runs in IDE)
    brief.md                   (between --prep-format and --render, by operator+model)
    email_<YYYYMMDDTHHMMSSZ>.html (--render — operator copies + sends manually)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
BRIEFS_ROOT = OUTPUT_ROOT / "briefs"


def _cadence_from_window(window_days: int) -> str:
    return "weekly" if int(window_days) == 7 else "daily"


def _manifest_filename(cadence: str) -> str:
    return f"_rsm_manifest_{cadence}.json"


def _day_dir(region: str, date_iso: str, cadence: str = "daily") -> Path:
    """Return the per-(date, region, cadence) brief folder, creating if absent.

    Shape: output/briefs/<YYYY-MM-DD>/<daily|weekly>/<REGION>/
    Date-first grouping makes a full day's run easy to inspect together.
    """
    d = BRIEFS_ROOT / date_iso / cadence / region.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_paths(day: Path, cadence: str) -> dict[str, Path]:
    signals = day / "signals"
    requests = day / "requests"
    analysis = day / "analysis"
    manifests = day / "manifests"
    render = day / "render"
    for p in (signals, requests, analysis, manifests, render):
        p.mkdir(parents=True, exist_ok=True)
    return {
        "signals": signals,
        "requests": requests,
        "analysis": analysis,
        "manifests": manifests,
        "render": render,
        "manifest": manifests / _manifest_filename(cadence),
    }


def _cleanup_regional_staging(region: str) -> None:
    """Remove per-region collector staging after run files are copied to briefs."""
    region_dir = OUTPUT_ROOT / "regional" / region.lower()
    if region_dir.exists():
        shutil.rmtree(region_dir, ignore_errors=True)
    regional_root = OUTPUT_ROOT / "regional"
    try:
        if regional_root.exists() and not any(regional_root.iterdir()):
            regional_root.rmdir()
    except OSError:
        pass


def _run(cmd: list[str]) -> None:
    print(f"[poc_runner] $ {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise SystemExit(f"[poc_runner] command failed: {' '.join(cmd)} (exit {result.returncode})")


def _write_osint_enrich_request(
    region: str,
    date_iso: str,
    request_path: Path,
    osint_signals_path: Path,
    seerist_signals_path: Path,
    osint_dropped_path: Path,
) -> None:
    prompt = (REPO_ROOT / "prompts" / "rsm_osint_enrichment.md").read_text(encoding="utf-8")
    request_path.write_text(
        f"# OSINT enrich request — {region.upper()} {date_iso}\n\n"
        f"OSINT_PATH: {osint_signals_path}\n"
        f"SEERIST_PATH: {seerist_signals_path}\n"
        f"OSINT_DROPPED_PATH: {osint_dropped_path}\n\n"
        "## Operator/model instruction\n\n"
        "Run this in your agent workbench. Read OSINT_PATH + SEERIST_PATH, rewrite "
        "OSINT_PATH enriched, and write OSINT_DROPPED_PATH per the prompt below.\n\n"
        "## Canonical enrichment prompt\n\n"
        f"{prompt}\n",
        encoding="utf-8",
    )


def phase_collect(
    region: str,
    date_iso: str,
    *,
    window_days: int,
    require_live: bool,
    no_org_context: bool = False,
    brand: str | None = None,
    osint: bool = False,
) -> None:
    """Phase A: collect, compute POI, build manifest, write analyst_request.md.

    no_org_context: region-guided mode — collect region-wide signals only (no
    facility POI), skip the site-proximity step, and build a manifest with no
    org grounding. brand: header brand label override (defaults handled by the
    input builder per mode).
    """
    cadence = _cadence_from_window(window_days)
    day = _day_dir(region, date_iso, cadence)
    rp = _run_paths(day, cadence)
    print(
        f"[poc_runner] PHASE A — collect for {region} / {date_iso} (window={window_days}d)",
        file=sys.stderr,
    )

    # Live-mode guard: seerist_collector silently falls back to mock when
    # SEERIST_API_KEY is absent. For the live PoC week, fail loudly instead.
    if require_live and not os.environ.get("SEERIST_API_KEY"):
        raise SystemExit(
            "[poc_runner] SEERIST_API_KEY is not set, but --require-live was passed. "
            "Refusing to silently fall back to mock fixtures. "
            "Set the key in .env or drop --require-live for a mock-mode rehearsal."
        )

    # 1. Seerist collect (window configurable: --window 1 daily, --window 7 for Day 0 variety)
    collect_cmd = [sys.executable, "tools/seerist_collector.py", region, "--window", str(window_days)]
    if no_org_context:
        collect_cmd.append("--no-org-context")
    _run(collect_cmd)
    canonical = OUTPUT_ROOT / "regional" / region.lower() / "seerist_signals.json"
    if not canonical.exists():
        raise SystemExit(f"[poc_runner] expected {canonical} after collect")
    seerist_out = rp["signals"] / "seerist_signals.json"
    shutil.copy2(canonical, seerist_out)

    # 2. POI proximity (downstream tool) — site-keyed, so skipped in
    #    region-guided mode where there is no org footprint to join against.
    if not no_org_context:
        _run([sys.executable, "tools/poi_proximity.py", region])
        poi_canonical = OUTPUT_ROOT / "regional" / region.lower() / "poi_proximity.json"
        if poi_canonical.exists():
            shutil.copy2(poi_canonical, rp["signals"] / "poi_proximity.json")

    # 2b. OSINT physical pillar (optional, region-keyed). RAW collect; the
    #     Copilot agent enriches it next (osint_enrich_request.md).
    osint_canonical = OUTPUT_ROOT / "regional" / region.lower() / "osint_physical_signals.json"
    osint_out = rp["signals"] / "osint_physical_signals.json"
    osint_dropped_out = rp["signals"] / "osint_dropped.json"
    if osint:
        if require_live:
            _missing = [k for k in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY") if not os.environ.get(k)]
            if _missing:
                raise SystemExit(
                    f"[poc_runner] --osint requires {', '.join(_missing)} in .env. "
                    "Set the key(s), or run without OSINT."
                )
        osint_cmd = [sys.executable, "tools/osint_physical_collector.py", region]
        if require_live:
            osint_cmd.append("--require-live")
        _run(osint_cmd)
        if osint_canonical.exists():
            shutil.copy2(osint_canonical, osint_out)
            _write_osint_enrich_request(
                region,
                date_iso,
                rp["requests"] / "osint_enrich_request.md",
                osint_out,
                seerist_out,
                osint_dropped_out,
            )
    elif osint_out.exists():
        osint_out.unlink()

    # Keep only briefs as operator-visible output; collector staging is transient.
    _cleanup_regional_staging(region)

    print(
        f"\n[poc_runner] PHASE COLLECT COMPLETE — {region} / {date_iso} ({cadence}).\n"
        f"  {'Enrich OSINT, then ' if osint else ''}run --analyze next.",
        file=sys.stderr,
    )


def phase_analyze(
    region: str,
    date_iso: str,
    *,
    cadence: str = "daily",
    no_org_context: bool = False,
    brand: str | None = None,
) -> None:
    """Phase A-prime: build manifest + analyst_request (after OSINT enrichment)."""
    day = _day_dir(region, date_iso, cadence)
    rp = _run_paths(day, cadence)

    # 3. Build the manifest (reads aerowind_sites.json + optional signals)
    sys.path.insert(0, str(REPO_ROOT))
    from tools.rsm_input_builder import build_rsm_inputs
    # Stub osint+data sources for standalone PoC; parent pipeline writes real ones when available.
    # rsm_input_builder requires osint_signals.json + data.json at a base path.
    # Keep these run-local so output/briefs is self-contained.
    local_builder_base = rp["signals"] / "builder_inputs"
    local_builder_base.mkdir(parents=True, exist_ok=True)
    for _stub_name in ("osint_signals.json", "data.json"):
        _stub_path = local_builder_base / _stub_name
        if not _stub_path.exists():
            _stub_path.write_text("{}", encoding="utf-8")

    os.environ["CRQ_REGION_BASE_DIR"] = str(local_builder_base)
    manifest = build_rsm_inputs(
        region,
        cadence=cadence,
        include_org_context=not no_org_context,
        brand_label=brand,
    )

    # Pin optional artifacts to this run folder structure.
    optional = manifest.get("optional", {}) if isinstance(manifest, dict) else {}
    if isinstance(optional, dict):
        optional["seerist_signals"] = str(rp["signals"] / "seerist_signals.json")
        optional["osint_physical_signals"] = str(rp["signals"] / "osint_physical_signals.json")
        optional["poi_proximity"] = str(rp["signals"] / "poi_proximity.json")

    manifest_path = rp["manifest"]
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[poc_runner] manifest written: {manifest_path}", file=sys.stderr)

    # 4. Build provider-agnostic ANALYST request — first operator LLM step.
    #    Output the operator must produce: claims.json + analyst_report.md.
    analyst_prompt_path = REPO_ROOT / "prompts" / f"rsm_regional_analyst_{cadence}.md"
    if not analyst_prompt_path.exists():
        analyst_prompt_path = REPO_ROOT / "prompts" / "rsm_regional_analyst_daily.md"
    analyst_prompt = analyst_prompt_path.read_text(encoding="utf-8")
    signals_path = rp["signals"] / "seerist_signals.json"
    poi_path = rp["signals"] / "poi_proximity.json"
    claims_path = rp["analysis"] / "claims.json"
    report_path = rp["analysis"] / "analyst_report.md"
    analyst_request_path = rp["requests"] / "analyst_request.md"
    analyst_request_path.write_text(
        f"# Analyst request — {region.upper()} {date_iso}\n\n"
        f"REGION: {region.upper()}\n"
        f"CADENCE: {cadence}\n"
        f"MANIFEST_PATH: {manifest_path}\n"
        f"SIGNALS_PATH: {signals_path}\n"
        f"POI_PATH: {poi_path}\n"
        f"CLAIMS_PATH: {claims_path}\n"
        f"REPORT_PATH: {report_path}\n\n"
        "## Operator/model instruction\n\n"
        "Run this request in Claude Code, Codex, GitHub Copilot IDE, or another "
        "model workbench with access to this repository. Read MANIFEST_PATH, "
        "SIGNALS_PATH, POI_PATH. Write CLAIMS_PATH and REPORT_PATH. If the "
        "environment cannot write files directly, return both outputs in clearly "
        "delimited code blocks so the operator can save them manually.\n\n"
        "## Canonical analyst prompt\n\n"
        f"{analyst_prompt}\n",
        encoding="utf-8",
    )
    print(f"[poc_runner] analyst request written: {analyst_request_path}", file=sys.stderr)

    print(
        "\n[poc_runner] PHASE A COMPLETE — READY TO RUN ANALYST REQUEST\n"
        f"  ANALYST_REQUEST: {analyst_request_path}\n"
        f"  CLAIMS_PATH:     {claims_path}\n"
        f"  REPORT_PATH:     {report_path}\n"
        "\n"
        "  Open/paste analyst_request.md in your available agentic environment\n"
        "  (Claude Code, Codex, GitHub Copilot IDE, etc.). When it writes or\n"
        "  returns claims.json + analyst_report.md, save them and run Phase B:\n"
        f"    uv run python tools/poc_runner.py {region} {date_iso} --prep-format\n",
        file=sys.stderr,
    )


def phase_prep_format(region: str, date_iso: str, *, cadence: str = "daily") -> None:
    """Phase B: read analyst output, build formatter_request.md. No model call."""
    day = _day_dir(region, date_iso, cadence)
    rp = _run_paths(day, cadence)
    claims_path = rp["analysis"] / "claims.json"
    report_path = rp["analysis"] / "analyst_report.md"
    manifest_path = rp["manifest"]

    if not claims_path.exists():
        raise SystemExit(
            f"[poc_runner] {claims_path} not found — did your analyst environment write or return it?\n"
            f"  Run --collect first, then run analyst_request.md in your IDE."
        )
    if not report_path.exists():
        raise SystemExit(
            f"[poc_runner] {report_path} not found — did your analyst environment write or return it?\n"
            f"  Run --collect first, then run analyst_request.md in your IDE."
        )
    if not manifest_path.exists():
        raise SystemExit(
            f"[poc_runner] {manifest_path} not found — run --collect first."
        )

    # Build formatter request. The formatter prompt reads CLAIMS_PATH + REPORT_PATH
    # alongside MANIFEST_PATH; it does NOT touch raw seerist_signals.json.
    formatter_prompt_path = REPO_ROOT / "prompts" / f"rsm_formatter_{cadence}.md"
    if not formatter_prompt_path.exists():
        formatter_prompt_path = REPO_ROOT / "prompts" / "rsm_formatter_daily.md"
    formatter_prompt = formatter_prompt_path.read_text(encoding="utf-8")
    brief_path = rp["render"] / "brief.md"
    formatter_request_path = rp["requests"] / "formatter_request.md"
    formatter_request_path.write_text(
        f"# Formatter request — {region.upper()} {date_iso}\n\n"
        f"REGION: {region.upper()}\n"
        f"CADENCE: {cadence}\n"
        f"BRIEF_PATH: {brief_path}\n"
        f"MANIFEST_PATH: {manifest_path}\n"
        f"CLAIMS_PATH: {claims_path}\n"
        f"REPORT_PATH: {report_path}\n\n"
        "## Operator/model instruction\n\n"
        "Run this request in Claude Code, Codex, GitHub Copilot IDE, or another "
        "model workbench with access to this repository. Read MANIFEST_PATH, "
        "CLAIMS_PATH, REPORT_PATH. Write the completed markdown brief to "
        "BRIEF_PATH. If the environment cannot write files directly, return only "
        "the completed markdown so the operator can save it to BRIEF_PATH manually.\n\n"
        "## Canonical formatter prompt\n\n"
        f"{formatter_prompt}\n",
        encoding="utf-8",
    )
    print(f"[poc_runner] formatter request written: {formatter_request_path}", file=sys.stderr)

    print(
        "\n[poc_runner] PHASE B COMPLETE — READY TO RUN FORMATTER REQUEST\n"
        f"  FORMATTER_REQUEST: {formatter_request_path}\n"
        f"  BRIEF_PATH:        {brief_path}\n"
        "\n"
        "  Open/paste formatter_request.md in your available agentic environment.\n"
        "  When it writes or returns brief.md, save it to BRIEF_PATH and run Phase C:\n"
        f"    uv run python tools/poc_runner.py {region} {date_iso} --render\n",
        file=sys.stderr,
    )


def phase_render(region: str, date_iso: str, *, cadence: str = "daily") -> None:
    """Phase C: normalize citations, validate, render HTML. No SMTP — operator handles email."""
    day = _day_dir(region, date_iso, cadence)
    rp = _run_paths(day, cadence)
    brief_path = rp["render"] / "brief.md"
    if not brief_path.exists():
        raise SystemExit(
            f"[poc_runner] {brief_path} not found — did your formatter environment write or return the brief?\n"
            f"  Run --prep-format, then run formatter_request.md in your IDE."
        )
    manifest_path = rp["manifest"]
    if not manifest_path.exists():
        raise SystemExit(
            f"[poc_runner] {manifest_path} not found — run --collect first."
        )
    claims_path = rp["analysis"] / "claims.json"
    if not claims_path.exists():
        raise SystemExit(
            f"[poc_runner] {claims_path} not found — claims.json drives appendix synthesis. "
            "Re-run --collect/--prep-format and the analyst step."
        )

    # 1. Normalize citations: rewrite `[claim_id]` body cites to `[N]` and
    #    synthesize the APPENDIX — SOURCES block from claims.json. Idempotent;
    #    archive the raw formatter output as brief.raw.md the first time only.
    brief_raw = rp["render"] / "brief.raw.md"
    if not brief_raw.exists():
        shutil.copy2(brief_path, brief_raw)
    _run([
        sys.executable, "tools/normalize_citations.py",
        str(brief_path), str(claims_path),
    ])

    # 2. Validate brief BEFORE render (non-zero exit blocks HTML generation)
    _run([
        sys.executable, "tools/validate_brief.py",
        str(brief_path), str(manifest_path),
    ])

    # 3. Render HTML with a simple human-readable timestamp in the filename.
    render_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    html_path = rp["render"] / f"email_{render_stamp}.html"
    # Brand the subject from the manifest (region-guided runs use a neutral brand).
    try:
        _brand = json.loads(manifest_path.read_text(encoding="utf-8")).get("brand_label") or "AEROWIND"
    except Exception:
        _brand = "AEROWIND"
    cadence_label = "Weekly" if cadence == "weekly" else "Daily"
    subject = f"{_brand} // {region} {cadence_label} Intelligence — {date_iso}"
    _run([
        sys.executable, "tools/render_brief_html.py",
        str(brief_path), str(manifest_path),
        "--out", str(html_path),
        "--subject", subject,
    ])

    # 4. Write the per-run transparency log alongside the rendered email HTML. Pure
    #    derivation from existing artifacts — does not gate the render.
    _run([
        sys.executable, "tools/intel_decisions.py",
        str(day),
    ])

    print(
        f"\n[poc_runner] PHASE C COMPLETE — READY TO SEND\n"
        f"  HTML email body:   {html_path}\n"
        f"  Suggested subject: {subject}\n"
        "\n"
        "  Open the HTML file in your browser, Ctrl+A -> Ctrl+C, paste into Gmail\n"
        "  compose, set recipient, hit Send. Then record the send in ../../docs/poc/\n"
        "  med-rsm-week/_qa_log.md.\n",
        file=sys.stderr,
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="RSM PoC per-day orchestrator — three deterministic phases."
    )
    p.add_argument("region", help="Region code, e.g. MED")
    p.add_argument("date_iso", help="Brief date in YYYY-MM-DD format")
    p.add_argument(
        "--collect", action="store_true",
        help="Phase A: collect signals + write analyst_request.md",
    )
    p.add_argument(
        "--prep-format", action="store_true", dest="prep_format",
        help="Phase B: read analyst output + write formatter_request.md",
    )
    p.add_argument(
        "--render", action="store_true",
        help="Phase C: validate brief + render timestamped email HTML (operator sends manually)",
    )
    p.add_argument(
        "--window", type=int, default=1,
        help="Seerist collection window in days (default 1; use 7 for Day 0 variety)",
    )
    p.add_argument(
        "--cadence", choices=["daily", "weekly"], default="daily",
        help="Output cadence folder for analyze/prep/render phases",
    )
    p.add_argument(
        "--require-live", action="store_true",
        help="Fail if SEERIST_API_KEY is absent (prevents silent mock fallback)",
    )
    p.add_argument(
        "--no-org-context", action="store_true", dest="no_org_context",
        help="Region-guided mode: region is the only scoping input. No sites, "
             "facilities, personnel, or footprint. Produces a company-agnostic brief.",
    )
    p.add_argument(
        "--brand", default=None,
        help="Header brand label override (default: AEROWIND, or a neutral label "
             "in --no-org-context mode)",
    )
    p.add_argument(
        "--osint", action="store_true",
        help="Include the OSINT physical pillar (Tavily/Firecrawl web+news enrichment). "
             "With --require-live, fails loudly if the OSINT keys are absent.",
    )
    p.add_argument(
        "--analyze", action="store_true",
        help="Build manifest + analyst_request (after OSINT enrichment)",
    )
    args = p.parse_args()

    if not (args.collect or args.analyze or args.prep_format or args.render):
        raise SystemExit("Specify at least one phase flag: --collect, --analyze, --prep-format, or --render")

    if args.collect:
        phase_collect(
            args.region, args.date_iso,
            window_days=args.window,
            require_live=args.require_live,
            no_org_context=args.no_org_context,
            brand=args.brand,
            osint=args.osint,
        )
    if args.analyze:
        phase_analyze(args.region, args.date_iso,
                      cadence=args.cadence,
                      no_org_context=args.no_org_context, brand=args.brand)
    if args.prep_format:
        phase_prep_format(args.region, args.date_iso, cadence=args.cadence)
    if args.render:
        phase_render(args.region, args.date_iso, cadence=args.cadence)

    return 0


if __name__ == "__main__":
    sys.exit(main())
