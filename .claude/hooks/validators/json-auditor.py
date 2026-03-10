import sys
import json
import os

REQUIRED_TOP_KEYS = ["total_vacr_exposure", "executive_summary", "regional_threats"]
REQUIRED_REGIONAL_KEYS = ["region", "vacr_exposure", "severity", "primary_scenario", "strategic_assessment"]
VALID_ADMIRALTY_RELIABILITY = {"A", "B", "C", "D", "E", "F"}
VALID_ADMIRALTY_CREDIBILITY = {"1", "2", "3", "4", "5", "6"}
VALID_VELOCITIES = {"accelerating", "stable", "improving", "unknown"}


def audit_json(file_path, label):
    os.makedirs("output/.retries", exist_ok=True)
    retry_file = f"output/.retries/{label}_json.retries"
    retries = 0
    if os.path.exists(retry_file):
        try:
            retries = int(open(retry_file).read().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"JSON AUDIT: Max retries exceeded for [{label}]. Forcing approval.", file=sys.stderr)
        os.remove(retry_file)
        sys.exit(0)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = f.read()
    except FileNotFoundError:
        print(f"JSON AUDIT ERROR: File not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"JSON AUDIT FAILED: Invalid JSON — {e}. Rewrite the entire file as a valid JSON object.", retry_file, retries)

    if not isinstance(data, dict):
        fail("JSON AUDIT FAILED: Root must be a JSON object, not an array or primitive.", retry_file, retries)

    # Required top-level keys
    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        fail(f"JSON AUDIT FAILED: Missing required top-level keys: {missing}.", retry_file, retries)

    if not isinstance(data["total_vacr_exposure"], (int, float)):
        fail("JSON AUDIT FAILED: 'total_vacr_exposure' must be a number.", retry_file, retries)

    if not isinstance(data["executive_summary"], str) or len(data["executive_summary"]) < 50:
        fail("JSON AUDIT FAILED: 'executive_summary' must be a string with at least 50 characters.", retry_file, retries)

    if not isinstance(data["regional_threats"], list):
        fail("JSON AUDIT FAILED: 'regional_threats' must be an array.", retry_file, retries)

    # Validate each regional threat entry
    for i, region in enumerate(data["regional_threats"]):
        if not isinstance(region, dict):
            fail(f"JSON AUDIT FAILED: regional_threats[{i}] must be an object.", retry_file, retries)
        missing_regional = [k for k in REQUIRED_REGIONAL_KEYS if k not in region]
        if missing_regional:
            fail(f"JSON AUDIT FAILED: regional_threats[{i}] missing keys: {missing_regional}.", retry_file, retries)
        if not isinstance(region["vacr_exposure"], (int, float)):
            fail(f"JSON AUDIT FAILED: regional_threats[{i}].vacr_exposure must be a number.", retry_file, retries)

        # Validate Admiralty rating format if present
        admiralty = region.get("admiralty_rating")
        if admiralty is not None:
            if not isinstance(admiralty, str) or len(admiralty) != 2:
                fail(f"JSON AUDIT FAILED: regional_threats[{i}].admiralty_rating must be a 2-char string like 'B2'.", retry_file, retries)
            if admiralty[0].upper() not in VALID_ADMIRALTY_RELIABILITY:
                fail(f"JSON AUDIT FAILED: regional_threats[{i}].admiralty_rating reliability '{admiralty[0]}' invalid. Must be A-F.", retry_file, retries)
            if admiralty[1] not in VALID_ADMIRALTY_CREDIBILITY:
                fail(f"JSON AUDIT FAILED: regional_threats[{i}].admiralty_rating credibility '{admiralty[1]}' invalid. Must be 1-6.", retry_file, retries)

        # Validate velocity if present
        velocity = region.get("velocity")
        if velocity is not None and velocity not in VALID_VELOCITIES:
            fail(f"JSON AUDIT FAILED: regional_threats[{i}].velocity '{velocity}' invalid. Must be one of {VALID_VELOCITIES}.", retry_file, retries)

    # Validate monitor_regions if present
    monitor_regions = data.get("monitor_regions")
    if monitor_regions is not None:
        if not isinstance(monitor_regions, list):
            fail("JSON AUDIT FAILED: 'monitor_regions' must be an array.", retry_file, retries)

    print(f"JSON AUDIT PASSED: [{label}] valid schema — {len(data['regional_threats'])} escalated, {len(data.get('monitor_regions', []))} monitored.")
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
        print("Usage: json-auditor.py <json_file_path> <label>")
        sys.exit(1)
    audit_json(sys.argv[1], sys.argv[2])
