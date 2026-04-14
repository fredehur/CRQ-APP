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
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, ".")
from tools.config import ROUTING_PATH as ROUTING_FILE_PATH

OUTPUT_ROOT = Path("output")
ROUTING_PATH = ROUTING_FILE_PATH
DELIVERY_LOG_PATH = OUTPUT_ROOT / "delivery_log.json"


def _append_delivery_log(region: str, cadence: str, brief_path: Path, status: str) -> None:
    """Append one row to the daily delivery log (JSONL)."""
    import sys as _sys
    log_path = _sys.modules[__name__].DELIVERY_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": region.upper(),
        "cadence": cadence,
        "brief_path": str(brief_path),
        "status": status,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


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


ALL_REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]


def _has_new_signals(region: str, output_root: Path) -> bool:
    """Return True if region has at least one new event/hotspot/cyber signal in this window."""
    base = output_root / "regional" / region.lower()
    osint = base / "osint_signals.json"
    seerist = base / "seerist_signals.json"
    physical = base / "osint_physical_signals.json"

    def _count(path, key="signals"):
        if not path.exists():
            return 0
        try:
            return len(json.loads(path.read_text(encoding="utf-8")).get(key, []))
        except Exception:
            return 0

    n_cyber = _count(osint)
    n_physical = _count(physical)
    n_seerist = 0
    if seerist.exists():
        try:
            doc = json.loads(seerist.read_text(encoding="utf-8"))
            n_seerist = (
                len(doc.get("situational", {}).get("events", []))
                + len(doc.get("situational", {}).get("breaking_news", []))
                + len(doc.get("analytical", {}).get("hotspots", []))
            )
        except Exception:
            pass
    return (n_cyber + n_physical + n_seerist) > 0


def _write_daily_empty_stub(region: str, output_root: Path) -> Path:
    """Write the daily empty-stub brief directly — no agent invocation."""
    region_lower = region.lower()
    out_dir = output_root / "regional" / region_lower
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    brief_path = out_dir / f"rsm_daily_{region_lower}_{date_str}.md"

    body = (
        f"AEROWIND // {region.upper()} DAILY // {date_str}Z\n"
        f"PULSE: n/a | ADM: C3 | NEW: 0 EVT · 0 HOT · 0 CYB\n\n"
        f"▪ No new physical events past 24h\n"
        f"▪ No new cyber signals\n"
        f"▪ No pre-media anomalies\n"
        f"▪ No site-specific alerts\n\n"
        f"Automated check ran {timestamp}. Nothing to escalate. Next check 24h.\n\n"
        f"---\n"
        f"Reply: ACKNOWLEDGED | AeroGrid Intelligence // {region.upper()} RSM\n"
    )
    brief_path.write_text(body, encoding="utf-8")
    return brief_path


def _write_daily_mock_brief(region: str, output_root: Path) -> Path:
    """Write a populated mock daily brief for the test path. Real dispatch invokes the agent."""
    region_lower = region.lower()
    out_dir = output_root / "regional" / region_lower
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    brief_path = out_dir / f"rsm_daily_{region_lower}_{date_str}.md"
    body = (
        f"AEROWIND // {region.upper()} DAILY // {date_str}Z\n"
        f"PULSE: 3.0 (▼ 0.4) | ADM: B2 | NEW: 1 EVT · 0 HOT · 0 CYB\n\n"
        f"█ SITUATION\n[MOCK] One sentence on what changed in last 24h.\n\n"
        f"█ AEROWIND EXPOSURE\n[MOCK] Site block.\n\n"
        f"█ PHYSICAL & GEOPOLITICAL — LAST 24H\nNo new events.\n\n"
        f"█ CYBER — LAST 24H\nNo new signals.\n\n"
        f"█ EARLY WARNING — NEW\nNo new anomalies.\n\n"
        f"█ TODAY'S CALL\n[MOCK] Operational call for today.\n\n"
        f"---\n"
        f"Reply: ACKNOWLEDGED · INVESTIGATING · FALSE POSITIVE | "
        f"AeroGrid Intelligence // {region.upper()} RSM\n"
    )
    brief_path.write_text(body, encoding="utf-8")
    return brief_path


async def _process_region_daily(region: str, output_root: Path, mock: bool) -> Path:
    if not _has_new_signals(region, output_root):
        path = _write_daily_empty_stub(region, output_root)
        _append_delivery_log(region, "daily", path, "stub")
        return path
    if mock:
        path = _write_daily_mock_brief(region, output_root)
        _append_delivery_log(region, "daily", path, "delivered")
        return path
    region_lower = region.lower()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    brief_path = output_root / "regional" / region_lower / f"rsm_daily_{region_lower}_{date_str}.md"
    decision = {
        "region": region.upper(),
        "product": "daily",
        "brief_path": str(brief_path),
        "audience": f"rsm_{region_lower}",
    }
    await asyncio.to_thread(_invoke_formatter, decision, False)
    _append_delivery_log(region, "daily", brief_path, "delivered")
    return brief_path


def dispatch_daily(regions: list[str] | None = None, mock: bool = True) -> list[Path]:
    """Run the daily cadence for the given regions in parallel.

    Returns a list of brief paths written (one per region).
    """
    targets = regions or ALL_REGIONS
    targets = [r.upper() for r in targets]

    _mod = sys.modules[__name__]

    async def _run():
        return await asyncio.gather(
            *[_process_region_daily(r, _mod.OUTPUT_ROOT, mock) for r in targets]
        )

    return list(asyncio.run(_run()))


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
    daily = "--daily" in args

    if daily:
        regions = [region_filter] if region_filter else None
        written = dispatch_daily(regions=regions, mock=mock)
        print(f"[rsm_dispatcher] daily — {len(written)} brief(s) written", file=sys.stderr)
        return

    if force_weekly or check_flash:
        import tools.threshold_evaluator as te
        te.evaluate(force_weekly=force_weekly, check_flash=check_flash or not force_weekly)

    dispatch(mock=mock, region_filter=region_filter)


if __name__ == "__main__":
    main()
