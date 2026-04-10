#!/usr/bin/env python3
"""
Gate 4: Seerist source hierarchy enforcement.

Extracted as a standalone module so it can be tested independently.
Imported by .claude/hooks/validators/regional-analyst-stop.py.
"""
import json
from pathlib import Path

from tools.seerist_strength import score_seerist_strength, get_substantive_signal_ids

REGIONAL = Path(__file__).resolve().parent.parent / "output" / "regional"


def validate_seerist_hierarchy(region: str) -> tuple[bool, list[str]]:
    """
    Gate 4: Enforce Seerist-first source hierarchy.

    Derives seerist_strength directly from seerist_signals.json —
    no dependency on collection_quality.json.

    Rules (only when seerist_strength is high or low):
    A. First claim with paragraph='why' must contain a seerist:event/hotspot/pulse signal_id
    B. Every substantive Seerist signal (hotspot anomaly + verified event)
       must have a corresponding claim citing its signal_id

    When seerist_strength is 'none' or seerist_signals.json is absent: skip, return pass.
    """
    seerist_path = REGIONAL / region / "seerist_signals.json"
    claims_path = REGIONAL / region / "claims.json"

    # Graceful skip if seerist file absent
    if not seerist_path.exists():
        return True, []

    try:
        seerist = json.loads(seerist_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True, []  # non-fatal

    strength = score_seerist_strength(seerist)

    # seerist_strength=none → no Seerist signals to enforce
    if strength == "none":
        return True, []

    if not claims_path.exists():
        return False, ["claims.json not found — cannot validate Seerist hierarchy"]

    try:
        claims_data = json.loads(claims_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"claims.json is not valid JSON: {e}"]

    claims = claims_data.get("claims", [])
    violations = []

    # Rule A: first why-paragraph claim must cite a raw Seerist signal_id
    SEERIST_RAW_PREFIXES = ("seerist:event:", "seerist:hotspot:", "seerist:pulse:")
    why_claims = [c for c in claims if c.get("paragraph") == "why"]
    if why_claims:
        first_why_ids = why_claims[0].get("signal_ids", [])
        has_seerist_raw = any(
            sid.startswith(SEERIST_RAW_PREFIXES) for sid in first_why_ids
        )
        if not has_seerist_raw:
            violations.append(
                f"first why-paragraph claim '{why_claims[0].get('claim_id')}' must cite "
                f"a seerist:event/hotspot/pulse signal_id — found: {first_why_ids}"
            )
    else:
        violations.append("No claims with paragraph='why' found")

    # Rule B: every substantive Seerist signal must appear in at least one claim
    all_claim_signal_ids = {
        sid
        for c in claims
        for sid in c.get("signal_ids", [])
    }
    required_ids = get_substantive_signal_ids(seerist)
    for req_id in required_ids:
        if req_id not in all_claim_signal_ids:
            violations.append(
                f"Substantive Seerist signal '{req_id}' has no corresponding claim — "
                f"add a claim citing this signal_id"
            )

    return len(violations) == 0, violations
