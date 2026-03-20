#!/usr/bin/env python3
"""Delta computer — diffs current vs previous Seerist signals.

Usage:
    delta_computer.py REGION

Reads:  output/regional/{region}/seerist_signals.json  (current)
        output/latest/regional/{region}/seerist_signals.json  (previous)
Writes: output/regional/{region}/region_delta.json

Cold-start: if no previous file exists, writes empty delta with pulse_delta=null.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
OUTPUT_ROOT = Path("output")
LATEST_ROOT = Path("output/latest")


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def compute(region: str) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}'")

    region_lower = region.lower()
    current_path = OUTPUT_ROOT / "regional" / region_lower / "seerist_signals.json"
    previous_path = LATEST_ROOT / "regional" / region_lower / "seerist_signals.json"

    current = _load_json(current_path)
    if current is None:
        raise FileNotFoundError(f"Current seerist_signals.json not found: {current_path}")

    previous = _load_json(previous_path)  # None = cold start

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    period_from = (previous or {}).get("collected_at", now)
    period_to = current.get("collected_at", now)

    # Compute pulse delta
    if previous is None:
        pulse_delta = None
    else:
        curr_score = (current.get("pulse") or {}).get("score")
        prev_score = (previous.get("pulse") or {}).get("score")
        pulse_delta = (curr_score - prev_score) if (curr_score is not None and prev_score is not None) else None

    # Diff events by event_id
    if previous is None:
        events_new = []
        events_resolved = []
    else:
        curr_event_ids = {e["event_id"] for e in current.get("events", [])}
        prev_event_ids = {e["event_id"] for e in previous.get("events", [])}
        events_new = [e for e in current.get("events", []) if e["event_id"] not in prev_event_ids]
        prev_events_by_id = {e["event_id"]: e for e in previous.get("events", [])}
        events_resolved = [e for eid, e in prev_events_by_id.items() if eid not in curr_event_ids]

    # Diff hotspots by hotspot_id
    if previous is None:
        hotspots_new = []
        hotspots_resolved = []
    else:
        curr_hotspot_ids = {h["hotspot_id"] for h in current.get("hotspots", [])}
        prev_hotspot_ids = {h["hotspot_id"] for h in previous.get("hotspots", [])}
        hotspots_new = [h for h in current.get("hotspots", []) if h["hotspot_id"] not in prev_hotspot_ids]
        prev_hotspots_by_id = {h["hotspot_id"]: h for h in previous.get("hotspots", [])}
        hotspots_resolved = [h for hid, h in prev_hotspots_by_id.items() if hid not in curr_hotspot_ids]

    delta = {
        "region": region,
        "period_from": period_from,
        "period_to": period_to,
        "pulse_delta": pulse_delta,
        "events_new": events_new,
        "events_resolved": events_resolved,
        "hotspots_new": hotspots_new,
        "hotspots_resolved": hotspots_resolved,
    }

    out_path = OUTPUT_ROOT / "regional" / region_lower / "region_delta.json"
    out_path.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[delta_computer] wrote {out_path}", file=sys.stderr)
    return delta


def main():
    if len(sys.argv) < 2:
        print("Usage: delta_computer.py REGION", file=sys.stderr)
        sys.exit(1)
    try:
        compute(sys.argv[1])
    except (ValueError, FileNotFoundError) as e:
        print(f"[delta_computer] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
