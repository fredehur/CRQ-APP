"""
Sections validator — deterministic check of sections.json integrity.
Runs as stop hook after regional-analyst-agent exits.

Guard: reads output/regional/*/gatekeeper_decision.json to find the region.
If decision != "ESCALATE", exit 0 immediately (no sections.json expected).

Checks:
1. sections.json exists for ESCALATED region.
2. Valid JSON.
3. All required keys present: intel_bullets, adversary_bullets, impact_bullets,
   watch_bullets, action_bullets, threat_actor, signal_type_label.
4. intel_bullets, adversary_bullets, impact_bullets are non-empty lists.

Retry pattern: output/.retries/sections-validator.retries
Max 3 retries then force-approve with warning logged to system_trace.log.
Exit codes: 0 = pass/skip, 1 = fail (triggers agent retry).
"""

import sys
import json
import glob
import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Retry machinery
# ---------------------------------------------------------------------------
RETRY_FILE = Path("output/.retries/sections-validator.retries")
MAX_RETRIES = 3


def get_retry_count() -> int:
    if RETRY_FILE.exists():
        try:
            return int(RETRY_FILE.read_text().strip())
        except Exception:
            return 0
    return 0


def increment_retry() -> int:
    count = get_retry_count() + 1
    RETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    RETRY_FILE.write_text(str(count))
    return count


def reset_retries():
    if RETRY_FILE.exists():
        RETRY_FILE.unlink()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log_trace(msg: str):
    ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    line = f"[{ts}] [SECTIONS] {msg}"
    try:
        with open("output/system_trace.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


# ---------------------------------------------------------------------------
# Region discovery
# ---------------------------------------------------------------------------
def find_latest_region() -> str | None:
    """Find the region whose sections.json was most recently written."""
    pattern = "output/regional/*/sections.json"
    files = glob.glob(pattern)
    if not files:
        return None
    import os
    latest = max(files, key=os.path.getmtime)
    return Path(latest).parent.name.upper()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
REQUIRED_KEYS = [
    "intel_bullets",
    "adversary_bullets",
    "impact_bullets",
    "watch_bullets",
    "action_bullets",
    "threat_actor",
    "signal_type_label",
]
NON_EMPTY_LISTS = ["intel_bullets", "adversary_bullets", "impact_bullets"]


def validate(region: str) -> tuple[bool, list[str]]:
    """Returns (passed, list_of_failures)."""
    region_lower = region.lower()
    base = Path(f"output/regional/{region_lower}")

    sections_path = base / "sections.json"
    gatekeeper_path = base / "gatekeeper_decision.json"

    failures = []

    # Guard: only validate ESCALATED regions
    try:
        gd = json.loads(gatekeeper_path.read_text(encoding="utf-8"))
        if gd.get("decision") != "ESCALATE":
            return True, []  # Not escalated — skip
    except Exception:
        return True, []  # No gatekeeper file — skip

    # Check 1: sections.json must exist
    if not sections_path.exists():
        failures.append("CHECK 1 FAIL: sections.json does not exist for ESCALATED region")
        return False, failures

    # Check 2: valid JSON
    try:
        data = json.loads(sections_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        failures.append(f"CHECK 2 FAIL: sections.json is not valid JSON: {e}")
        return False, failures

    # Check 3: all required keys present
    for key in REQUIRED_KEYS:
        if key not in data:
            failures.append(f"CHECK 3 FAIL: required key '{key}' missing from sections.json")

    # Check 4: non-empty lists
    for key in NON_EMPTY_LISTS:
        val = data.get(key)
        if not isinstance(val, list) or len(val) == 0:
            failures.append(f"CHECK 4 FAIL: '{key}' must be a non-empty list")

    return len(failures) == 0, failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    region = find_latest_region()
    if not region:
        # No sections.json found — might be a non-escalated run
        sys.exit(0)

    region_lower = region.lower()

    # Check retry count
    retry_count = get_retry_count()
    if retry_count >= MAX_RETRIES:
        log_trace(f"{region} sections validator force-approved after {MAX_RETRIES} retries")
        reset_retries()
        sys.exit(0)

    passed, failures = validate(region)

    if passed:
        reset_retries()
        log_trace(f"{region} sections validation PASSED")
        sys.exit(0)
    else:
        count = increment_retry()
        for f in failures:
            log_trace(f"{region} {f}")
        log_trace(f"{region} sections validation FAILED (retry {count}/{MAX_RETRIES})")
        print("\n".join(failures))
        sys.exit(1)