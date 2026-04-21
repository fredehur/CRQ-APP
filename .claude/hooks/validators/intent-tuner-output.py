"""Stop hook for intent-tuner-agent and intent-tuner-validator-agent.

Set INTENT_TUNER_ROLE=tuner   to validate tuner output (6 list keys + reasoning).
Set INTENT_TUNER_ROLE=validator to validate validator output (verdict + reason).
"""
import json
import os
import sys

TUNER_REQUIRED_KEYS = {
    "add_threat_terms", "remove_threat_terms",
    "add_asset_terms", "remove_asset_terms",
    "add_industry_terms", "remove_industry_terms",
    "reasoning",
}

role = os.environ.get("INTENT_TUNER_ROLE", "tuner").lower()

try:
    raw = sys.stdin.read()
    data = json.loads(raw)
except (json.JSONDecodeError, ValueError) as exc:
    print(f"[intent-tuner-output] JSON parse error: {exc}", file=sys.stderr)
    sys.exit(1)

if role == "tuner":
    missing = TUNER_REQUIRED_KEYS - set(data.keys())
    extra = set(data.keys()) - TUNER_REQUIRED_KEYS
    errors = []
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected keys: {sorted(extra)}")
    for list_key in TUNER_REQUIRED_KEYS - {"reasoning"}:
        if not isinstance(data.get(list_key), list):
            errors.append(f"'{list_key}' must be a list")
    if not isinstance(data.get("reasoning"), str):
        errors.append("'reasoning' must be a string")
    if errors:
        print(f"[intent-tuner-output] tuner validation failed: {'; '.join(errors)}", file=sys.stderr)
        sys.exit(1)

elif role == "validator":
    errors = []
    verdict = data.get("verdict")
    if verdict not in ("approved", "rejected"):
        errors.append(f"'verdict' must be 'approved' or 'rejected', got: {verdict!r}")
    if not isinstance(data.get("reason"), str) or not data["reason"].strip():
        errors.append("'reason' must be a non-empty string")
    if errors:
        print(f"[intent-tuner-output] validator validation failed: {'; '.join(errors)}", file=sys.stderr)
        sys.exit(1)

else:
    print(f"[intent-tuner-output] unknown INTENT_TUNER_ROLE: {role!r}", file=sys.stderr)
    sys.exit(1)

sys.exit(0)
