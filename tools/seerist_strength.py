#!/usr/bin/env python3
"""Shared Seerist signal strength scorer.

Used by:
  - tools/collection_gate.py                          (scores before gatekeeper runs)
  - .claude/hooks/validators/regional-analyst-stop.py (Gate 4)

One implementation, two consumers — logic cannot drift between them.
"""

PULSE_DELTA_THRESHOLD = -0.5
# Calibrate as Seerist baseline behavior is observed across regions.
# Seerist pulse runs 0–5. A delta of -0.5 (10% of scale) is a directional signal.
# Tighten toward -0.3 for higher sensitivity; loosen toward -0.7 for lower noise.


def score_seerist_strength(seerist: dict) -> str:
    """
    Score Seerist signal strength for a region.

    Returns:
        'high' — hotspot anomaly, verified event, or significant pulse drop
        'low'  — unverified events only or mild pulse decline
        'none' — empty or absent Seerist data
    """
    if not seerist:
        return "none"

    sit = seerist.get("situational", {})
    ana = seerist.get("analytical", {})

    # HIGH conditions (any one sufficient)
    hotspots = ana.get("hotspots", [])
    if any(h.get("anomaly_flag") for h in hotspots):
        return "high"

    if sit.get("verified_events"):
        return "high"

    delta = ana.get("pulse", {}).get("region_summary", {}).get("avg_delta", 0)
    if delta <= PULSE_DELTA_THRESHOLD:
        return "high"

    # LOW conditions (any one sufficient)
    if sit.get("events") or delta < 0:
        return "low"

    return "none"


def get_substantive_signal_ids(seerist: dict) -> list[str]:
    """
    Return signal_ids of all substantive Seerist signals that MUST appear
    as claims in claims.json.

    Substantive = hotspot with anomaly_flag=True OR verified_event.
    Used by Gate 4 to enforce per-signal claim coverage.
    """
    if not seerist:
        return []

    ids = []
    ana = seerist.get("analytical", {})
    sit = seerist.get("situational", {})

    for h in ana.get("hotspots", []):
        if h.get("anomaly_flag") and h.get("signal_id"):
            ids.append(h["signal_id"])

    for e in sit.get("verified_events", []):
        if e.get("signal_id"):
            ids.append(e["signal_id"])

    return ids
