import sys
import json
import os
from config import COMPANY_PROFILE_PATH, MASTER_SCENARIOS_PATH

def load_company_profile():
    if not os.path.exists(COMPANY_PROFILE_PATH):
        return {}
    with open(COMPANY_PROFILE_PATH) as f:
        return json.load(f)

def load_master_scenarios():
    if not os.path.exists(MASTER_SCENARIOS_PATH):
        return {}
    with open(MASTER_SCENARIOS_PATH) as f:
        data = json.load(f)
    return {s["incident_type"]: s for s in data.get("scenarios", [])}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: geopolitical_context.py <REGION>")
        sys.exit(1)
    region = sys.argv[1].upper()

    profile = load_company_profile()
    master = load_master_scenarios()

    print(f"=== Company Context ===")
    print(f"  Company: {profile.get('company_name', 'Unknown')}")
    print(f"  Industry: {profile.get('industry', 'Unknown')}")
    print(f"  Crown Jewels:")
    for jewel in profile.get("crown_jewels", []):
        print(f"    - {jewel}")

    # Load regional feed for geopolitical context
    feed_path = f"data/mock_threat_feeds/{region.lower()}_feed.json"
    if not os.path.exists(feed_path):
        print(f"\n  No feed data available for region: {region}")
        sys.exit(0)

    with open(feed_path) as f:
        feed = json.load(f)

    print(f"\n=== Geopolitical Risk Context: {region} ===")
    print(f"  Severity: {feed.get('severity', 'LOW')}")
    print(f"  Active Threats: {feed.get('active_threats', False)}")
    print(f"  Context: {feed.get('geopolitical_context', 'No context available.')}")

    scenario = feed.get("primary_scenario", "None")
    if scenario != "None":
        baseline = master.get(scenario, {})
        if baseline:
            print(f"\n=== Empirical Scenario Baseline: {scenario} ===")
            print(f"  Financial Impact Rank: #{baseline['financial_rank']} ({baseline['financial_impact_pct']}% of all losses)")
            print(f"  Event Frequency Rank: #{baseline['frequency_rank']} ({baseline['event_frequency_pct']}% of all events)")
            print(f"  Records Affected Rank: #{baseline['records_rank']} ({baseline['records_affected_pct']}% of all records)")
