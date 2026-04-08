#!/usr/bin/env python3
"""
Stop hook for register-validator-agent.
Validates that output/validation/register_validation.json:
  - Is valid JSON
  - Has required top-level fields (register_id, validated_at, scenarios)
  - Each scenario has financial + probability verdicts with non-empty recommendation
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

for field in ("register_id", "validated_at", "scenarios"):
    if field not in data:
        fail(f"Missing top-level field: {field}")

for s in data.get("scenarios", []):
    sid = s.get("scenario_id", "?")
    for dim in ("financial", "probability"):
        v = s.get(dim, {})
        if not v.get("verdict"):
            fail(f"Scenario {sid} — {dim}.verdict is empty")
        if not v.get("recommendation"):
            fail(f"Scenario {sid} — {dim}.recommendation is empty")

print(f"OK — register_validation.json valid ({len(data['scenarios'])} scenarios)")
sys.exit(0)
