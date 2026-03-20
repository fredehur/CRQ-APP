#!/usr/bin/env python3
"""RSM Dispatcher — orchestrates RSM brief generation and delivery.

Usage:
    rsm_dispatcher.py --weekly              # Force weekly INTSUM for all RSM audiences
    rsm_dispatcher.py --check-flash        # Evaluate flash thresholds only
    rsm_dispatcher.py --mock               # Use mock mode (no email, agent in dry-run)
    rsm_dispatcher.py --region APAC        # Restrict to one region

Reads:  output/routing_decisions.json
Writes: output/routing_decisions.json (updates delivered flags)
        output/regional/{region}/rsm_brief_*.md or rsm_flash_*.md (via formatter agent)
        output/delivery_log.json (via notifier)
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, ".")

OUTPUT_ROOT = Path("output")
ROUTING_PATH = Path("output/routing_decisions.json")


def _invoke_formatter(decision: dict, mock: bool) -> None:
    """Invoke rsm-formatter-agent via claude CLI for one decision."""
    region = decision["region"]
    product = decision["product"]
    brief_path = decision["brief_path"]

    prompt = (
        f"REGION: {region}\n"
        f"PRODUCT_TYPE: {product}\n"
        f"BRIEF_PATH: {brief_path}\n\n"
        f"Follow the rsm-formatter-agent instructions exactly. "
        f"Read all required input files and write the brief to BRIEF_PATH. "
        f"Write nothing to stdout except completion confirmation."
    )

    if mock:
        # In mock mode, write a placeholder brief so the pipeline can be tested end-to-end
        Path(brief_path).parent.mkdir(parents=True, exist_ok=True)
        Path(brief_path).write_text(
            f"[MOCK] RSM {product.upper()} for {region} — placeholder brief for testing\n"
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
            encoding="utf-8"
        )
        print(f"[rsm_dispatcher] mock brief written: {brief_path}", file=sys.stderr)
        return

    try:
        result = subprocess.run(
            ["claude", "-p", "--agent", "rsm-formatter-agent", prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        if result.returncode != 0:
            print(f"[rsm_dispatcher] formatter agent failed for {region}/{product}: {result.stderr[:200]}", file=sys.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[rsm_dispatcher] formatter invocation error: {e}", file=sys.stderr)


def _invoke_notifier(mock: bool) -> None:
    """Invoke notifier.py to deliver all undelivered briefs."""
    cmd = [sys.executable, "tools/notifier.py", str(ROUTING_PATH)]
    if mock:
        cmd.append("--mock")
    subprocess.run(cmd, check=False)


def dispatch(mock: bool = True, region_filter: str | None = None) -> None:
    if not ROUTING_PATH.exists():
        print(f"[rsm_dispatcher] no routing_decisions.json — nothing to dispatch", file=sys.stderr)
        return

    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    decisions = routing.get("decisions", [])

    triggered = [
        d for d in decisions
        if d.get("triggered") and not d.get("delivered")
        and (region_filter is None or d.get("region") == region_filter.upper())
    ]

    if not triggered:
        print(f"[rsm_dispatcher] no pending triggered decisions", file=sys.stderr)
        return

    for decision in triggered:
        print(f"[rsm_dispatcher] formatting {decision['audience']} / {decision['product']}", file=sys.stderr)
        _invoke_formatter(decision, mock=mock)
        decision["delivered"] = True

    # Write back updated routing decisions
    ROUTING_PATH.write_text(json.dumps(routing, indent=2, ensure_ascii=False), encoding="utf-8")

    _invoke_notifier(mock=mock)
    print(f"[rsm_dispatcher] dispatch complete — {len(triggered)} brief(s) processed", file=sys.stderr)


def main():
    args = sys.argv[1:]
    mock = "--mock" in args

    region_filter = None
    if "--region" in args:
        idx = args.index("--region")
        if idx + 1 < len(args):
            region_filter = args[idx + 1]

    force_weekly = "--weekly" in args
    check_flash = "--check-flash" in args

    # If --weekly, run threshold_evaluator with force_weekly first
    if force_weekly or check_flash:
        import tools.threshold_evaluator as te
        te.evaluate(force_weekly=force_weekly, check_flash=check_flash or not force_weekly)

    dispatch(mock=mock, region_filter=region_filter)


if __name__ == "__main__":
    main()
