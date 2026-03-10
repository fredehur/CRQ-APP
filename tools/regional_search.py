import sys
import json
import os
from config import MASTER_SCENARIOS_PATH

def load_master_scenarios():
    if not os.path.exists(MASTER_SCENARIOS_PATH):
        return {}
    with open(MASTER_SCENARIOS_PATH) as f:
        data = json.load(f)
    return {s["incident_type"]: s for s in data.get("scenarios", [])}

def search(region, mock=True):
    if not mock:
        print("Live search not configured. Re-run with --mock flag.")
        sys.exit(1)
    feed_path = f"data/mock_threat_feeds/{region.lower()}_feed.json"
    if not os.path.exists(feed_path):
        print(f"No threat feed found for region: {region}")
        sys.exit(0)
    with open(feed_path) as f:
        feed = json.load(f)

    active = feed.get("active_threats", False)
    severity = feed.get("severity", "LOW")
    scenario = feed.get("primary_scenario", "None")
    vacr = feed.get("vacr_exposure_usd", 0)
    geo_ctx = feed.get("geopolitical_context", "")

    geo_signals = feed.get("geo_signals", {})
    cyber_signals = feed.get("cyber_signals", {})
    dominant_pillar = feed.get("dominant_pillar", None)

    print(f"=== Threat Intelligence: {region} ===")
    print(f"  Active Threats: {active}")
    print(f"  Severity: {severity}")
    print(f"  Primary Scenario: {scenario}")
    print(f"  VaCR Exposure: ${vacr:,.0f}")
    print(f"  Dominant Pillar: {dominant_pillar or 'N/A'}")
    print(f"  Geopolitical Context: {geo_ctx}")

    if geo_signals:
        print(f"\n=== Geopolitical Signals (The Why) ===")
        print(f"  {geo_signals.get('summary', '')}")
        for indicator in geo_signals.get("lead_indicators", []):
            print(f"  • {indicator}")

    if cyber_signals:
        print(f"\n=== Cyber Signals (The How) ===")
        print(f"  {cyber_signals.get('summary', '')}")
        if cyber_signals.get("threat_vector"):
            print(f"  Threat Vector: {cyber_signals['threat_vector']}")
        for asset in cyber_signals.get("target_assets", []):
            print(f"  • Target: {asset}")

    if active and scenario != "None":
        master = load_master_scenarios()
        baseline = master.get(scenario, {})
        if baseline:
            print(f"\n=== Empirical Baseline: {scenario} ===")
            print(f"  Financial Impact Rank: #{baseline['financial_rank']} ({baseline['financial_impact_pct']}% of all losses)")
            print(f"  Event Frequency Rank: #{baseline['frequency_rank']} ({baseline['event_frequency_pct']}% of all events)")
            print(f"  Records Affected Rank: #{baseline['records_rank']} ({baseline['records_affected_pct']}% of all records)")
    else:
        print(f"\n  No active threat campaign. Gatekeeper should route NO.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: regional_search.py <REGION> [--mock]")
        sys.exit(1)
    region = sys.argv[1].upper()
    mock = "--mock" in sys.argv
    search(region, mock)
