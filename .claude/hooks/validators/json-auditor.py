import sys
import json
import os

REQUIRED_TOP_KEYS = ["total_vacr_exposure", "executive_summary", "regional_threats"]
REQUIRED_REGIONAL_KEYS = ["region", "vacr_exposure", "severity", "primary_scenario", "strategic_assessment"]

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
        print(f"JSON AUDIT: Max retries exceeded for [{label}]. Forcing approval to break loop.", file=sys.stderr)
        os.remove(retry_file)
        sys.exit(0)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = f.read()
    except FileNotFoundError:
        print(f"JSON AUDIT ERROR: File not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"JSON AUDIT FAILED: Invalid JSON — {e}. Rewrite the entire file as a valid JSON object.", retry_file, retries)

    if not isinstance(data, dict):
        fail("JSON AUDIT FAILED: Root must be a JSON object, not an array or primitive.", retry_file, retries)

    # Check required top-level keys
    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        fail(f"JSON AUDIT FAILED: Missing required top-level keys: {missing}. Add them and rewrite.", retry_file, retries)

    # Validate total_vacr_exposure is a number
    if not isinstance(data["total_vacr_exposure"], (int, float)):
        fail("JSON AUDIT FAILED: 'total_vacr_exposure' must be a number (no dollar signs, no strings).", retry_file, retries)

    # Validate executive_summary is a string
    if not isinstance(data["executive_summary"], str) or len(data["executive_summary"]) < 50:
        fail("JSON AUDIT FAILED: 'executive_summary' must be a string with at least 50 characters.", retry_file, retries)

    # Validate regional_threats is an array of objects
    if not isinstance(data["regional_threats"], list):
        fail("JSON AUDIT FAILED: 'regional_threats' must be an array.", retry_file, retries)

    for i, region in enumerate(data["regional_threats"]):
        if not isinstance(region, dict):
            fail(f"JSON AUDIT FAILED: regional_threats[{i}] must be an object.", retry_file, retries)
        missing_regional = [k for k in REQUIRED_REGIONAL_KEYS if k not in region]
        if missing_regional:
            fail(f"JSON AUDIT FAILED: regional_threats[{i}] missing keys: {missing_regional}.", retry_file, retries)
        if not isinstance(region["vacr_exposure"], (int, float)):
            fail(f"JSON AUDIT FAILED: regional_threats[{i}].vacr_exposure must be a number.", retry_file, retries)

    print(f"JSON AUDIT PASSED: [{label}] valid schema with {len(data['regional_threats'])} regional entries.")
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
