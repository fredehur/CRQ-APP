#!/usr/bin/env python3
"""Collection quality gate — canonical check for signal grounding depth.

Usage:
    uv run python tools/collection_gate.py <REGION>

Reads osint_signals.json for the given region,
counts grounded indicators (those with a non-empty source_url),
writes collection_quality.json, and logs result to system_trace.log.

Exit code 0 = collection meets threshold, 1 = thin collection.
"""
import datetime
import json
import os
import sys
from pathlib import Path

from tools.seerist_strength import score_seerist_strength

REPO_ROOT = Path(__file__).resolve().parent.parent
COLLECTION_QUALITY_THRESHOLD = int(os.environ.get("COLLECTION_QUALITY_THRESHOLD", "3"))


def _load_signal_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _count_grounded(signals: dict) -> int:
    indicators = signals.get("lead_indicators", [])
    return sum(1 for ind in indicators if isinstance(ind, dict) and ind.get("source_url"))


def _log_collection_quality(result: dict) -> None:
    """Append collection quality result to system_trace.log."""
    region = result["region"]
    thin = result["thin_collection"]
    geo = result["geo_grounded_count"]
    cyber = result["cyber_grounded_count"]
    threshold = result["threshold"]
    msg = (
        f"[{datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}] "
        f"[COLLECTION_QUALITY] {region}: geo={geo} cyber={cyber} "
        f"thin={thin} threshold={threshold}"
    )
    try:
        log_path = REPO_ROOT / "output" / "system_trace.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass  # non-fatal


def check_collection_quality(region: str, run_id: str | None = None) -> dict:
    """Check collection quality for a region and write collection_quality.json.

    Returns dict with: region, thin_collection, geo_grounded_count,
    cyber_grounded_count, threshold.
    """
    region_lower = region.lower()
    osint = _load_signal_file(REPO_ROOT / f"output/regional/{region_lower}/osint_signals.json")

    # Count grounded indicators by pillar
    all_indicators = osint.get("lead_indicators", [])
    geo_grounded = sum(1 for ind in all_indicators if isinstance(ind, dict) and ind.get("source_url") and ind.get("pillar") == "geo")
    cyber_grounded = sum(1 for ind in all_indicators if isinstance(ind, dict) and ind.get("source_url") and ind.get("pillar") == "cyber")

    thin = geo_grounded < COLLECTION_QUALITY_THRESHOLD or cyber_grounded < COLLECTION_QUALITY_THRESHOLD

    # Score Seerist signal strength
    seerist = _load_signal_file(REPO_ROOT / f"output/regional/{region_lower}/seerist_signals.json")
    seerist_strength = score_seerist_strength(seerist)

    # collection_lag: Seerist silent but OSINT has signals
    osint_has_signals = bool(all_indicators)
    lag_detected = seerist_strength == "none" and osint_has_signals
    lag_note = (
        "OSINT signals present but Seerist has no corroborating data"
        " — assess as early indicator pending confirmation"
        if lag_detected else ""
    )

    result = {
        "region": region.upper(),
        "thin_collection": thin,
        "geo_grounded_count": geo_grounded,
        "cyber_grounded_count": cyber_grounded,
        "threshold": COLLECTION_QUALITY_THRESHOLD,
        "seerist_strength": seerist_strength,
        "collection_lag": {
            "detected": lag_detected,
            "note": lag_note,
        },
    }

    out_path = REPO_ROOT / f"output/regional/{region_lower}/collection_quality.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    _log_collection_quality(result)
    print(f"[collection_quality] {region}: geo={geo_grounded}, cyber={cyber_grounded}, thin={thin}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python tools/collection_gate.py <REGION>")
        sys.exit(1)
    region = sys.argv[1].upper()
    result = check_collection_quality(region)
    print(json.dumps(result, indent=2))
    sys.exit(1 if result["thin_collection"] else 0)
