"""Stop hook for threat-landscape-agent — validates threat_landscape.json."""

import json
import os
import re
import sys

REQUIRED_TOP_KEYS = [
    "generated_at", "analysis_window", "threat_actors", "scenario_lifecycle",
    "adversary_patterns", "compound_risks", "intelligence_gaps",
    "quarterly_brief", "board_talking_points", "analyst_notes",
]

REQUIRED_WINDOW_KEYS = ["from", "to", "runs_included", "runs_with_full_sections", "data_sufficiency"]
VALID_SUFFICIENCY = {"limited", "adequate", "strong"}

QUARTERLY_KEYS = ["headline", "key_actors", "persistent_threats", "emerging_threats", "intelligence_gaps", "watch_for"]

JARGON_PATTERNS = [
    r"\bCVE-\d{4}-\d+\b",
    r"\bT\d{4}(\.\d{3})?\b",       # MITRE ATT&CK
    r"\b(?:TTP|IoC|C2|C&C)\b",
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",  # IP addresses
    r"\b[a-f0-9]{32,64}\b",         # hashes
]

FILE_PATH = "output/pipeline/threat_landscape.json"
LABEL = "threat-landscape"


def fail(msg, retry_file, retries):
    print(msg, file=sys.stderr)
    with open(retry_file, "w") as f:
        f.write(str(retries + 1))
    sys.exit(2)


def audit():
    os.makedirs("output/.retries", exist_ok=True)
    retry_file = f"output/.retries/{LABEL}.retries"
    retries = 0
    if os.path.exists(retry_file):
        try:
            retries = int(open(retry_file).read().strip())
        except ValueError:
            retries = 0

    if retries >= 3:
        print(f"THREAT LANDSCAPE AUDIT: Max retries exceeded. Forcing approval.", file=sys.stderr)
        if os.path.exists(retry_file):
            os.remove(retry_file)
        sys.exit(0)

    # Load JSON
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"AUDIT FAILED: File not found: {FILE_PATH}", retry_file, retries)
    except json.JSONDecodeError as e:
        fail(f"AUDIT FAILED: Invalid JSON — {e}", retry_file, retries)

    if not isinstance(data, dict):
        fail("AUDIT FAILED: Root must be a JSON object.", retry_file, retries)

    # Required top-level keys
    missing = [k for k in REQUIRED_TOP_KEYS if k not in data]
    if missing:
        fail(f"AUDIT FAILED: Missing top-level keys: {missing}", retry_file, retries)

    # analysis_window
    window = data["analysis_window"]
    if not isinstance(window, dict):
        fail("AUDIT FAILED: analysis_window must be an object.", retry_file, retries)
    missing_w = [k for k in REQUIRED_WINDOW_KEYS if k not in window]
    if missing_w:
        fail(f"AUDIT FAILED: analysis_window missing keys: {missing_w}", retry_file, retries)
    if window["data_sufficiency"] not in VALID_SUFFICIENCY:
        fail(f"AUDIT FAILED: data_sufficiency must be one of {VALID_SUFFICIENCY}, got '{window['data_sufficiency']}'", retry_file, retries)

    sufficiency = window["data_sufficiency"]

    # Data sufficiency gating
    if sufficiency == "limited":
        if data["adversary_patterns"] and len(data["adversary_patterns"]) > 0:
            fail("AUDIT FAILED: adversary_patterns must be empty when data_sufficiency='limited'.", retry_file, retries)
        if data["compound_risks"] and len(data["compound_risks"]) > 0:
            fail("AUDIT FAILED: compound_risks must be empty when data_sufficiency='limited'.", retry_file, retries)

    # Arrays must be lists
    for key in ["threat_actors", "scenario_lifecycle", "adversary_patterns", "compound_risks", "intelligence_gaps", "board_talking_points"]:
        if not isinstance(data[key], list):
            fail(f"AUDIT FAILED: {key} must be an array.", retry_file, retries)

    # quarterly_brief completeness (when not limited)
    if sufficiency != "limited":
        qb = data["quarterly_brief"]
        if not isinstance(qb, dict):
            fail("AUDIT FAILED: quarterly_brief must be an object.", retry_file, retries)
        for k in QUARTERLY_KEYS:
            if k not in qb or not isinstance(qb[k], str) or len(qb[k].strip()) < 10:
                fail(f"AUDIT FAILED: quarterly_brief.{k} must be a non-empty string (>=10 chars).", retry_file, retries)

    # analyst_notes
    if not isinstance(data["analyst_notes"], str) or len(data["analyst_notes"]) < 10:
        fail("AUDIT FAILED: analyst_notes must be a non-empty string.", retry_file, retries)

    # Jargon scan — check all string values recursively
    def scan_jargon(obj, path=""):
        violations = []
        if isinstance(obj, str):
            for pat in JARGON_PATTERNS:
                matches = re.findall(pat, obj)
                if matches:
                    violations.append(f"  {path}: matched '{matches[0]}' (pattern: {pat})")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                violations.extend(scan_jargon(v, f"{path}.{k}"))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                violations.extend(scan_jargon(v, f"{path}[{i}]"))
        return violations

    jargon_hits = scan_jargon(data, "root")
    if jargon_hits:
        fail(f"AUDIT FAILED: Technical jargon detected:\n" + "\n".join(jargon_hits), retry_file, retries)

    # Success
    actor_count = len(data["threat_actors"])
    scenario_count = len(data["scenario_lifecycle"])
    gap_count = len(data["intelligence_gaps"])
    print(f"THREAT LANDSCAPE AUDIT PASSED: {sufficiency} data — {actor_count} actors, {scenario_count} scenarios, {gap_count} gaps.")
    if os.path.exists(retry_file):
        os.remove(retry_file)
    sys.exit(0)


if __name__ == "__main__":
    audit()
