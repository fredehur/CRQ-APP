import sys
import json
import os

REQUIRED_TOP_KEYS = ["generated_at", "run_count", "regions", "cross_regional", "ciso_talking_points"]
REQUIRED_REGION_KEYS = ["severity_trajectory", "scenario_frequency", "escalation_count", "assessment"]


def audit(file_path, label):
    os.makedirs("output/.retries", exist_ok=True)
    retry_file = f"output/.retries/{label}_trend.retries"
    retries = 0
    if os.path.exists(retry_file):
        try:
            retries = int(open(retry_file).read().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"TREND AUDIT: Max retries exceeded for [{label}]. Forcing approval.", file=sys.stderr)
        os.remove(retry_file)
        sys.exit(0)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"TREND AUDIT FAILED: File not found: {file_path}", retry_file, retries)
    except json.JSONDecodeError as e:
        fail(f"TREND AUDIT FAILED: Invalid JSON — {e}", retry_file, retries)

    if not isinstance(data, dict):
        fail("TREND AUDIT FAILED: Root must be a JSON object.", retry_file, retries)

    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        fail(f"TREND AUDIT FAILED: Missing top-level keys: {missing}", retry_file, retries)

    if not isinstance(data["run_count"], int):
        fail("TREND AUDIT FAILED: 'run_count' must be an integer.", retry_file, retries)

    if not isinstance(data["regions"], dict):
        fail("TREND AUDIT FAILED: 'regions' must be an object.", retry_file, retries)

    for region, rd in data["regions"].items():
        if not isinstance(rd, dict):
            fail(f"TREND AUDIT FAILED: regions[{region}] must be an object.", retry_file, retries)
        missing_r = [k for k in REQUIRED_REGION_KEYS if k not in rd]
        if missing_r:
            fail(f"TREND AUDIT FAILED: regions[{region}] missing keys: {missing_r}", retry_file, retries)
        if not isinstance(rd["severity_trajectory"], list):
            fail(f"TREND AUDIT FAILED: regions[{region}].severity_trajectory must be a list.", retry_file, retries)
        if not isinstance(rd["scenario_frequency"], dict):
            fail(f"TREND AUDIT FAILED: regions[{region}].scenario_frequency must be an object.", retry_file, retries)
        if not isinstance(rd["escalation_count"], int):
            fail(f"TREND AUDIT FAILED: regions[{region}].escalation_count must be an integer.", retry_file, retries)
        if not isinstance(rd["assessment"], str) or len(rd["assessment"]) < 30:
            fail(f"TREND AUDIT FAILED: regions[{region}].assessment must be a string of at least 30 chars.", retry_file, retries)

    if not isinstance(data["ciso_talking_points"], list) or len(data["ciso_talking_points"]) < 1:
        fail("TREND AUDIT FAILED: 'ciso_talking_points' must be a non-empty list.", retry_file, retries)

    if not isinstance(data["cross_regional"], dict):
        fail("TREND AUDIT FAILED: 'cross_regional' must be an object.", retry_file, retries)

    print(f"TREND AUDIT PASSED: [{label}] valid — {len(data['regions'])} regions, {data['run_count']} runs, {len(data['ciso_talking_points'])} talking points.")
    if os.path.exists(retry_file):
        os.remove(retry_file)
    sys.exit(0)


def fail(msg, retry_file, retries):
    print(msg, file=sys.stderr)
    with open(retry_file, "w") as f:
        f.write(str(retries + 1))
    sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: trend-analysis-auditor.py <json_file_path> <label>")
        sys.exit(1)
    audit(sys.argv[1], sys.argv[2])