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

    # Phase C: validate + render email.html
    uv run python tools/poc_runner.py MED 2026-05-17 --render

All phases write to output/poc/<region.lower()>/<date>/:
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
    email.html                 (--render — operator copies + sends manually)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
POC_ROOT = OUTPUT_ROOT / "poc"


def _day_dir(region: str, date_iso: str) -> Path:
    d = POC_ROOT / region.lower() / date_iso
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run(cmd: list[str]) -> None:
    print(f"[poc_runner] $ {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        raise SystemExit(f"[poc_runner] command failed: {' '.join(cmd)} (exit {result.returncode})")


def _write_osint_enrich_request(region: str, date_iso: str, day: Path, osint_canonical: Path) -> None:
    prompt = (REPO_ROOT / "prompts" / "rsm_osint_enrichment.md").read_text(encoding="utf-8")
    seerist_path = OUTPUT_ROOT / "regional" / region.lower() / "seerist_signals.json"
    (day / "osint_enrich_request.md").write_text(
        f"# OSINT enrich request — {region.upper()} {date_iso}\n\n"
        f"OSINT_PATH: {osint_canonical}\n"
        f"SEERIST_PATH: {seerist_path}\n"
        f"OSINT_DROPPED_PATH: {osint_canonical.parent / 'osint_dropped.json'}\n\n"
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
    day = _day_dir(region, date_iso)
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
    shutil.copy2(canonical, day / "seerist_signals.json")

    # 2. POI proximity (downstream tool) — site-keyed, so skipped in
    #    region-guided mode where there is no org footprint to join against.
    if not no_org_context:
        _run([sys.executable, "tools/poi_proximity.py", region])
        poi_canonical = OUTPUT_ROOT / "regional" / region.lower() / "poi_proximity.json"
        if poi_canonical.exists():
            shutil.copy2(poi_canonical, day / "poi_proximity.json")

    # 2b. OSINT physical pillar (optional, region-keyed). RAW collect; the
    #     Copilot agent enriches it next (osint_enrich_request.md).
    osint_canonical = OUTPUT_ROOT / "regional" / region.lower() / "osint_physical_signals.json"
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
            shutil.copy2(osint_canonical, day / "osint_physical_signals.json")
            _write_osint_enrich_request(region, date_iso, day, osint_canonical)
    elif osint_canonical.exists():
        osint_canonical.unlink()

    print(
        f"\n[poc_runner] PHASE COLLECT COMPLETE — {region} / {date_iso}.\n"
        f"  {'Enrich OSINT, then ' if osint else ''}run --analyze next.",
        file=sys.stderr,
    )


def phase_analyze(
    region: str,
    date_iso: str,
    *,
    no_org_context: bool = False,
    brand: str | None = None,
) -> None:
    """Phase A-prime: build manifest + analyst_request (after OSINT enrichment)."""
    day = _day_dir(region, date_iso)

    # 3. Build the manifest (reads aerowind_sites.json + optional signals)
    sys.path.insert(0, str(REPO_ROOT))
    from tools.rsm_input_builder import build_rsm_inputs
    # Stub osint+data sources for standalone PoC; parent pipeline writes real ones when available.
    _regional_dir = OUTPUT_ROOT / "regional" / region.lower()
    _regional_dir.mkdir(parents=True, exist_ok=True)
    for _stub_name in ("osint_signals.json", "data.json"):
        _stub_path = _regional_dir / _stub_name
        if not _stub_path.exists():
            _stub_path.write_text("{}", encoding="utf-8")
    manifest = build_rsm_inputs(
        region,
        cadence="daily",
        include_org_context=not no_org_context,
        brand_label=brand,
    )
    manifest_path = day / "_rsm_manifest_daily.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[poc_runner] manifest written: {manifest_path}", file=sys.stderr)

    # 4. Build provider-agnostic ANALYST request — first operator LLM step.
    #    Output the operator must produce: claims.json + analyst_report.md.
    analyst_prompt_path = REPO_ROOT / "prompts" / "rsm_regional_analyst_daily.md"
    analyst_prompt = analyst_prompt_path.read_text(encoding="utf-8")
    signals_path = day / "seerist_signals.json"
    poi_path = day / "poi_proximity.json"
    claims_path = day / "claims.json"
    report_path = day / "analyst_report.md"
    analyst_request_path = day / "analyst_request.md"
    analyst_request_path.write_text(
        f"# Analyst request — {region.upper()} {date_iso}\n\n"
        f"REGION: {region.upper()}\n"
        f"CADENCE: daily\n"
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


def phase_prep_format(region: str, date_iso: str) -> None:
    """Phase B: read analyst output, build formatter_request.md. No model call."""
    day = _day_dir(region, date_iso)
    claims_path = day / "claims.json"
    report_path = day / "analyst_report.md"
    manifest_path = day / "_rsm_manifest_daily.json"

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
    formatter_prompt_path = REPO_ROOT / "prompts" / "rsm_formatter_daily.md"
    formatter_prompt = formatter_prompt_path.read_text(encoding="utf-8")
    brief_path = day / "brief.md"
    formatter_request_path = day / "formatter_request.md"
    formatter_request_path.write_text(
        f"# Formatter request — {region.upper()} {date_iso}\n\n"
        f"REGION: {region.upper()}\n"
        f"CADENCE: daily\n"
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


def phase_render(region: str, date_iso: str) -> None:
    """Phase C: normalize citations, validate, render HTML. No SMTP — operator handles email."""
    day = _day_dir(region, date_iso)
    brief_path = day / "brief.md"
    if not brief_path.exists():
        raise SystemExit(
            f"[poc_runner] {brief_path} not found — did your formatter environment write or return the brief?\n"
            f"  Run --prep-format, then run formatter_request.md in your IDE."
        )
    manifest_path = day / "_rsm_manifest_daily.json"
    if not manifest_path.exists():
        raise SystemExit(
            f"[poc_runner] {manifest_path} not found — run --collect first."
        )
    claims_path = day / "claims.json"
    if not claims_path.exists():
        raise SystemExit(
            f"[poc_runner] {claims_path} not found — claims.json drives appendix synthesis. "
            "Re-run --collect/--prep-format and the analyst step."
        )

    # 1. Normalize citations: rewrite `[claim_id]` body cites to `[N]` and
    #    synthesize the APPENDIX — SOURCES block from claims.json. Idempotent;
    #    archive the raw formatter output as brief.raw.md the first time only.
    brief_raw = day / "brief.raw.md"
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

    # 3. Render HTML
    html_path = day / "email.html"
    # Brand the subject from the manifest (region-guided runs use a neutral brand).
    try:
        _brand = json.loads(manifest_path.read_text(encoding="utf-8")).get("brand_label") or "AEROWIND"
    except Exception:
        _brand = "AEROWIND"
    subject = f"{_brand} // {region} Daily Intelligence — {date_iso}"
    _run([
        sys.executable, "tools/render_brief_html.py",
        str(brief_path), str(manifest_path),
        "--out", str(html_path),
        "--subject", subject,
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
        help="Phase C: validate brief + render email.html (operator sends manually)",
    )
    p.add_argument(
        "--window", type=int, default=1,
        help="Seerist collection window in days (default 1; use 7 for Day 0 variety)",
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
                      no_org_context=args.no_org_context, brand=args.brand)
    if args.prep_format:
        phase_prep_format(args.region, args.date_iso)
    if args.render:
        phase_render(args.region, args.date_iso)

    return 0


if __name__ == "__main__":
    sys.exit(main())
