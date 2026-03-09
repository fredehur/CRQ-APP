"""Writes output/regional/{region}/data.json after gatekeeper decision."""
import sys
import json
import os
from datetime import datetime, timezone
from config import SEVERITY_MAP, MOCK_FEEDS_DIR

def write_data(region, status):
    region_upper = region.upper()
    region_lower = region.lower()

    feed_path = f"{MOCK_FEEDS_DIR}/{region_lower}_feed.json"
    feed = {}
    if os.path.exists(feed_path):
        with open(feed_path) as f:
            feed = json.load(f)

    severity = feed.get("severity", "LOW")
    severity_score = SEVERITY_MAP.get(severity, 1)
    primary_scenario = feed.get("primary_scenario", None)
    if primary_scenario == "None":
        primary_scenario = None
    vacr = feed.get("vacr_exposure_usd", 0)

    gatekeeper = "YES" if status == "escalated" else "NO"
    report_path = f"regional/{region_lower}/report.md" if status == "escalated" else None

    data = {
        "region": region_upper,
        "status": status,
        "gatekeeper_decision": gatekeeper,
        "severity": severity,
        "severity_score": severity_score,
        "primary_scenario": primary_scenario,
        "vacr_exposure_usd": vacr,
        "report_path": report_path,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out_dir = f"output/regional/{region_lower}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {out_path} — status: {status}, VaCR: ${vacr:,.0f}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: write_region_data.py <REGION> <escalated|clear>")
        sys.exit(1)
    write_data(sys.argv[1], sys.argv[2])
