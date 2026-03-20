#!/usr/bin/env python3
"""Seerist signal collector — fetches EventsAI, HotspotsAI, PulseAI per region.

Usage:
    seerist_collector.py REGION [--mock] [--window 7d]

Writes: output/regional/{region}/seerist_signals.json

Mock mode (default when SEERIST_API_KEY absent): reads
data/mock_osint_fixtures/{region}_seerist.json
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
OUTPUT_ROOT = Path("output")
FIXTURES_DIR = Path("data/mock_osint_fixtures")
REGION_MAP_PATH = Path("data/region_country_map.json")


def _load_region_map() -> dict:
    return json.loads(REGION_MAP_PATH.read_text(encoding="utf-8"))


def _mock_collect(region: str, window_days: int) -> dict:
    fixture = FIXTURES_DIR / f"{region.lower()}_seerist.json"
    if not fixture.exists():
        raise FileNotFoundError(f"Mock fixture not found: {fixture}")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["window_days"] = window_days
    data["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return data


def _live_collect(region: str, window_days: int) -> dict:
    """Live Seerist API call. Falls back to mock if key absent."""
    api_key = os.environ.get("SEERIST_API_KEY", "")
    if not api_key:
        print(f"[seerist_collector] No SEERIST_API_KEY — falling back to mock", file=sys.stderr)
        return _mock_collect(region, window_days)

    # TODO: replace with real Seerist endpoints when API docs confirmed
    # Stub: import and call seerist_client when key is present
    try:
        from tools.seerist_client import get_full_intelligence
        raw = get_full_intelligence(region)
        return {
            "region": region,
            "window_days": window_days,
            "pulse": raw.get("pulse", {}),
            "events": raw.get("events", []),
            "hotspots": raw.get("hotspots", []),
            "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except Exception as e:
        print(f"[seerist_collector] Live collection failed: {e} — falling back to mock", file=sys.stderr)
        return _mock_collect(region, window_days)


def collect(region: str, mock: bool = True, window_days: int = 7) -> dict:
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}' — must be one of {VALID_REGIONS}")

    data = _mock_collect(region, window_days) if mock else _live_collect(region, window_days)

    out_dir = OUTPUT_ROOT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "seerist_signals.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[seerist_collector] wrote {out_path}", file=sys.stderr)
    return data


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: seerist_collector.py REGION [--mock] [--window 7d]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args or not os.environ.get("SEERIST_API_KEY")

    window_days = 7
    if "--window" in args:
        idx = args.index("--window")
        if idx + 1 < len(args):
            val = args[idx + 1].rstrip("d")
            try:
                window_days = int(val)
            except ValueError:
                pass

    try:
        collect(region, mock=mock, window_days=window_days)
    except (ValueError, FileNotFoundError) as e:
        print(f"[seerist_collector] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
