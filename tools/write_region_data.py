"""Writes output/regional/{region}/data.json after gatekeeper decision.

Reads output/regional/{region}/gatekeeper_decision.json if it exists
to pick up Admiralty rating, dominant_pillar, and scenario_match.
"""
import sys
import json
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.config import SEVERITY_MAP, MOCK_FEEDS_DIR


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
    dominant_pillar = feed.get("dominant_pillar", None)

    # Read gatekeeper decision file for Admiralty and enriched fields
    admiralty = None
    scenario_match = primary_scenario
    rationale = None
    gk_path = f"output/regional/{region_lower}/gatekeeper_decision.json"
    if os.path.exists(gk_path):
        try:
            with open(gk_path, encoding="utf-8") as f:
                gk = json.load(f)
            admiralty = gk.get("admiralty", {}).get("rating", None)
            scenario_match = gk.get("scenario_match", primary_scenario)
            dominant_pillar = gk.get("dominant_pillar", dominant_pillar)
            rationale = gk.get("rationale", None)
        except (json.JSONDecodeError, OSError):
            pass

    # For escalated regions, derive severity from Admiralty rating if mock feed
    # returned LOW (the default fallback). This prevents live-mode escalations
    # from being miscategorised because the mock feed hasn't been updated.
    _ADMIRALTY_SEVERITY = {
        "A1": "CRITICAL", "A2": "CRITICAL", "B1": "CRITICAL",
        "B2": "HIGH", "C1": "HIGH", "C2": "HIGH",
        "B3": "MEDIUM", "C3": "MEDIUM", "D1": "MEDIUM", "D2": "MEDIUM",
        "C4": "LOW", "D3": "LOW", "D4": "LOW",
    }
    if status == "escalated" and severity == "LOW" and admiralty:
        derived = _ADMIRALTY_SEVERITY.get(admiralty)
        if derived and derived != "LOW":
            severity = derived
            severity_score = SEVERITY_MAP.get(severity, 1)

    report_path = f"regional/{region_lower}/report.md" if status == "escalated" else None

    data = {
        "region": region_upper,
        "status": status,
        "gatekeeper_decision": status.upper(),
        "severity": severity,
        "severity_score": severity_score,
        "primary_scenario": scenario_match,
        "vacr_exposure_usd": vacr,
        "admiralty": admiralty,
        "rationale": rationale,
        "velocity": "unknown",
        "dominant_pillar": dominant_pillar,
        "report_path": report_path,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    out_dir = f"output/regional/{region_lower}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {out_path} — status: {status}, VaCR: ${vacr:,.0f}, admiralty: {admiralty or 'pending'}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: write_region_data.py <REGION> <escalated|monitor|clear>")
        sys.exit(1)
    write_data(sys.argv[1], sys.argv[2])
