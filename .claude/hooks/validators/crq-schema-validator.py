import sys
import json

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
REQUIRED_KEYS = {"scenario_id", "department", "scenario_name", "critical_assets", "value_at_cyber_risk_usd"}

def validate(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"SCHEMA ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"SCHEMA ERROR: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print("SCHEMA ERROR: Root element must be a JSON object with region keys.", file=sys.stderr)
        sys.exit(1)

    for region, scenarios in data.items():
        if region not in VALID_REGIONS:
            print(f"SCHEMA ERROR: Unknown region '{region}'. Valid: {VALID_REGIONS}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(scenarios, list):
            print(f"SCHEMA ERROR: '{region}' must map to a list of scenarios.", file=sys.stderr)
            sys.exit(1)
        for i, scenario in enumerate(scenarios):
            missing = REQUIRED_KEYS - set(scenario.keys())
            if missing:
                print(f"SCHEMA ERROR: Scenario {i} in {region} missing fields: {missing}", file=sys.stderr)
                sys.exit(1)

    total = sum(len(v) for v in data.values())
    print(f"SCHEMA VALID: {total} scenarios across {len(data)} regions ({', '.join(data.keys())}).")
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: crq-schema-validator.py <path_to_json>")
        sys.exit(1)
    validate(sys.argv[1])
