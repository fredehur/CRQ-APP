"""
Reads current pipeline state from filesystem and prints a concise status report.
No LLM. No API calls. Deterministic.

Usage: uv run python tools/status_report.py
"""
import json
import os
from tools.config import REGIONS, MANIFEST_PATH, TREND_BRIEF_PATH

STATUS_ICON = {
    "escalated": "[!] ESCALATED",
    "monitor":   "[~] WATCH    ",
    "clear":     "[ok] CLEAR   ",
    "missing":   "[-] MISSING  ",
}

VELOCITY_ICON = {
    "accelerating": "^",
    "stable":       "=",
    "improving":    "v",
    "unknown":      "-",
}


def load(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def run():
    manifest  = load(str(MANIFEST_PATH))
    trend     = load(str(TREND_BRIEF_PATH))

    print()
    print("=" * 70)
    print("  CRQ PIPELINE STATUS")
    print("=" * 70)

    if manifest:
        print(f"  Pipeline : {manifest.get('pipeline_id', 'unknown')}")
        print(f"  Run time : {manifest.get('run_timestamp', 'unknown')}")
        print(f"  Total VaCR: ${manifest.get('total_vacr_exposure_usd', 0):,.0f}")
    else:
        print("  No run manifest found — pipeline has not completed a run yet.")

    print()
    print(f"  {'REGION':<8} {'STATUS':<16} {'SEV':<10} {'VaCR':>14}  {'ADM':<4}  {'TREND':<3}  PILLAR")
    print("  " + "-" * 66)

    escalated = monitor = clear = 0

    for region in REGIONS:
        data = load(f"output/regional/{region.lower()}/data.json")
        if not data:
            print(f"  {region:<8} ⚪ NO DATA")
            continue

        status   = data.get("status", "missing")
        severity = data.get("severity", "–")
        vacr     = data.get("vacr_exposure_usd", 0)
        admiralty = data.get("admiralty") or "-"
        pillar   = (data.get("dominant_pillar") or "-")[:12]

        # Velocity from trend_brief if available, else from data.json
        velocity = "unknown"
        if trend and region in trend:
            velocity = trend[region].get("direction", "unknown")
        else:
            velocity = data.get("velocity", "unknown")
        vel_icon = VELOCITY_ICON.get(velocity, "–")

        status_label = STATUS_ICON.get(status, f"  {status.upper():<14}")
        vacr_str = f"${vacr:>13,.0f}" if vacr else f"{'$0':>14}"

        print(f"  {region:<8} {status_label}  {severity:<10} {vacr_str}  {admiralty:<4}  {vel_icon:<3}  {pillar}")

        if status == "escalated": escalated += 1
        elif status == "monitor":  monitor   += 1
        elif status == "clear":    clear     += 1

    print()
    print(f"  Escalated: {escalated}  |  Watch: {monitor}  |  Clear: {clear}")

    if trend:
        run_counts = [v.get("run_count", 0) for v in trend.values()]
        max_runs = max(run_counts) if run_counts else 0
        print(f"  Trend data: {max_runs} historical run(s) analyzed")

    print("=" * 70)
    print()


if __name__ == "__main__":
    run()
