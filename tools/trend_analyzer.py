"""
Reads output/runs/*/run_manifest.json to compute velocity per region.
Writes output/trend_brief.json and patches velocity into each regional data.json.
"""
import json
import os
import sys
from config import REGIONS

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
RUNS_DIR = "output/runs"
TREND_OUTPUT = "output/trend_brief.json"


def load_historical_runs():
    """Return list of run manifests sorted oldest-first."""
    if not os.path.exists(RUNS_DIR):
        return []
    manifests = []
    for run_dir in sorted(os.listdir(RUNS_DIR)):
        manifest_path = os.path.join(RUNS_DIR, run_dir, "run_manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifests.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
    return manifests


def compute_velocity(severity_history):
    """
    Given a list of severity strings oldest-first, return direction.
    Requires at least 2 data points.
    """
    if len(severity_history) < 2:
        return "unknown"
    scores = [SEVERITY_ORDER.get(s.upper(), 0) for s in severity_history]
    last, prev = scores[-1], scores[-2]
    if last < prev:
        return "improving"
    elif last > prev:
        return "accelerating"
    else:
        return "stable"


def analyze():
    runs = load_historical_runs()
    trend = {}

    for region in REGIONS:
        history = []
        for run in runs:
            region_data = run.get("regions", {}).get(region, {})
            sev = region_data.get("severity", "UNKNOWN")
            status = region_data.get("status", "unknown")
            history.append({
                "run_id": run.get("pipeline_id", "unknown"),
                "timestamp": run.get("run_timestamp", ""),
                "severity": sev,
                "status": status,
            })

        severity_list = [h["severity"] for h in history]
        direction = compute_velocity(severity_list)

        trend[region] = {
            "direction": direction,
            "run_count": len(history),
            "last_3_runs": [h["severity"] for h in history[-3:]],
            "history": history,
        }

    os.makedirs("output", exist_ok=True)
    with open(TREND_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(trend, f, indent=2)

    patched = 0
    for region in REGIONS:
        data_path = f"output/regional/{region.lower()}/data.json"
        if os.path.exists(data_path):
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            data["velocity"] = trend[region]["direction"]
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            patched += 1

    run_count = len(runs)
    print(f"Trend analysis complete — {run_count} historical run(s) analyzed, {patched} data.json files patched.")
    for region in REGIONS:
        t = trend[region]
        print(f"  {region}: {t['direction']} | last runs: {t['last_3_runs'] or ['(no history)']}")


if __name__ == "__main__":
    analyze()
