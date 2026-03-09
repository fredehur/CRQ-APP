import sys
import json
import os
from config import MASTER_SCENARIOS_PATH, SEVERITY_MAP

def load_master_scenarios():
    if not os.path.exists(MASTER_SCENARIOS_PATH):
        return {}
    with open(MASTER_SCENARIOS_PATH) as f:
        data = json.load(f)
    return {s["incident_type"]: s for s in data.get("scenarios", [])}

def score(region):
    feed_path = f"data/mock_threat_feeds/{region.lower()}_feed.json"
    if not os.path.exists(feed_path):
        print("Severity Score: 1")
        return
    with open(feed_path) as f:
        feed = json.load(f)

    if not feed.get("active_threats", False):
        print("Severity Score: 0")
        print("No active threats.")
        return

    severity_str = feed.get("severity", "LOW")
    severity_num = SEVERITY_MAP.get(severity_str, 1)
    scenario = feed.get("primary_scenario", "None")

    master = load_master_scenarios()
    baseline = master.get(scenario, {})

    print(f"Severity Score: {severity_num}")
    print(f"Severity Level: {severity_str}")
    print(f"Primary Scenario: {scenario}")
    if baseline:
        print(f"  Financial Rank: #{baseline['financial_rank']}")
        print(f"  Frequency Rank: #{baseline['frequency_rank']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Severity Score: 1")
        sys.exit(0)
    score(sys.argv[1].upper())
