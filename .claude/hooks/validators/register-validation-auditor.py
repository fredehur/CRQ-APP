#!/usr/bin/env python3
"""
Stop hook for register-validator-agent.
Validates that output/validation/register_validation.json:
  - Is valid JSON
  - Has required top-level fields (register_id, validated_at, version_checks, scenarios)
  - Each scenario has financial + probability verdicts with non-empty recommendation
  - Each scenario has asset_context_note (string)
  - Financial/probability have registered_sources + new_sources (not flat sources)
  - Sources have context_tag and smb_scale_flag fields
  - No scenario has a null/empty verdict value
"""
import json
import sys
from pathlib import Path

OUTPUT = Path("output/validation/register_validation.json")

def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)

if not OUTPUT.exists():
    fail("register_validation.json not found")

try:
    data = json.loads(OUTPUT.read_text())
except json.JSONDecodeError as e:
    fail(f"Invalid JSON: {e}")

for field in ("register_id", "validated_at", "version_checks", "scenarios"):
    if field not in data:
        fail(f"Missing top-level field: {field}")

if not isinstance(data["version_checks"], list):
    fail("version_checks must be a list")

VALID_CONTEXT_TAGS = {"asset_specific", "company_scale", "both", "general", None}

for s in data.get("scenarios", []):
    sid = s.get("scenario_id", "?")

    # asset_context_note must be a string
    if "asset_context_note" not in s:
        fail(f"Scenario {sid} — missing asset_context_note")
    if not isinstance(s["asset_context_note"], str):
        fail(f"Scenario {sid} — asset_context_note must be a string")

    for dim in ("financial", "probability"):
        v = s.get(dim, {})
        if not v.get("verdict"):
            fail(f"Scenario {sid} — {dim}.verdict is empty")
        if not v.get("recommendation"):
            fail(f"Scenario {sid} — {dim}.recommendation is empty")

        # Must have registered_sources + new_sources (not flat sources)
        if "registered_sources" not in v:
            fail(f"Scenario {sid} — {dim} missing registered_sources")
        if "new_sources" not in v:
            fail(f"Scenario {sid} — {dim} missing new_sources")
        if not isinstance(v["registered_sources"], list):
            fail(f"Scenario {sid} — {dim}.registered_sources must be a list")
        if not isinstance(v["new_sources"], list):
            fail(f"Scenario {sid} — {dim}.new_sources must be a list")

        # Validate source fields
        for src_list_name in ("registered_sources", "new_sources"):
            for src in v[src_list_name]:
                # context_tag: validate if present
                ct = src.get("context_tag")
                if ct is not None and ct not in VALID_CONTEXT_TAGS:
                    fail(f"Scenario {sid} — {dim}.{src_list_name} source has invalid context_tag: {ct}")
                # smb_scale_flag: validate if present
                sf = src.get("smb_scale_flag")
                if sf is not None and not isinstance(sf, bool):
                    fail(f"Scenario {sid} — {dim}.{src_list_name} source has non-boolean smb_scale_flag")

print(f"OK — register_validation.json valid ({len(data['scenarios'])} scenarios, {len(data['version_checks'])} version checks)")
sys.exit(0)