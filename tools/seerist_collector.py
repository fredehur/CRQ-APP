#!/usr/bin/env python3
"""Seerist signal collector — fetches all Tier 1 data types per region.

Usage:
    uv run python tools/seerist_collector.py REGION [--mock] [--window 7d]

Writes: output/regional/{region}/seerist_signals.json

Schema: See spec Appendix D for full seerist_signals.json structure.
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
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
FIXTURES_DIR = REPO_ROOT / "data" / "mock_osint_fixtures"


def _mock_collect(region: str, window_days: int) -> dict:
    """Read mock fixture, stamp metadata."""
    fixture = FIXTURES_DIR / f"{region.lower()}_seerist.json"
    if not fixture.exists():
        raise FileNotFoundError(f"Mock fixture not found: {fixture}")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["collection_window"] = {"days": window_days}
    return data


def _live_collect(region: str, window_days: int) -> dict:
    """Call Seerist API for all Tier 1 data types."""
    from tools.seerist_client import SeeristClient, REGION_COUNTRIES

    client = SeeristClient.create()
    if client is None:
        print("[seerist_collector] No SEERIST_API_KEY — falling back to mock", file=sys.stderr)
        return _mock_collect(region, window_days)

    countries = REGION_COUNTRIES.get(region, [])[:3]
    now = datetime.now(timezone.utc)

    # Load facility coords for POI search
    poi_alerts = []
    try:
        sites_doc = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
        facilities = [s for s in sites_doc.get("sites", []) if s["region"] == region]
        if facilities:
            pois = [[f["lon"], f["lat"], f["poi_radius_km"]] for f in facilities]
            poi_features = client.search_poi(pois, days=window_days)
            for i, f in enumerate(poi_features):
                props = f.get("properties", {})
                fac = facilities[0]  # nearest facility
                poi_alerts.append({
                    "signal_id": f"seerist:poi:{region.lower()}-{i + 1:03d}",
                    "facility": fac["name"],
                    "coordinates": [fac["lon"], fac["lat"]],
                    "radius_km": fac["poi_radius_km"],
                    "matching_events": [],
                    "nearest_event_km": 0,
                })
    except Exception as e:
        print(f"[seerist_collector] POI search error: {e}", file=sys.stderr)

    # Fetch last_run_timestamp for delta collection
    since = None
    try:
        rc = json.loads(Path("output/pipeline/run_config.json").read_text(encoding="utf-8"))
        since = rc.get("last_run_timestamp")
    except Exception:
        pass

    with client:
        pulse_data = client.get_pulse(countries)
        # Compute region summary from pulse
        scores = [v.get("score", 0) for v in pulse_data.values() if v.get("score")]
        deltas = [v.get("delta", 0) for v in pulse_data.values()]
        worst = min(pulse_data.items(), key=lambda x: x[1].get("score", 999)) if pulse_data else ("", {"score": 0})

        result = {
            "region": region,
            "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "collection_window": {
                "since": since or (now - __import__("datetime").timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "days": window_days,
            },
            "situational": {
                "events": client.get_events(region, window_days),
                "verified_events": client.get_verified_events(region, min(window_days * 3, 90)),
                "breaking_news": client.get_breaking_events(region),
                "news": client.get_news(region, window_days),
            },
            "analytical": {
                "pulse": {
                    "countries": pulse_data,
                    "region_summary": {
                        "worst_country": worst[0],
                        "worst_score": worst[1].get("score", 0),
                        "avg_delta": round(sum(deltas) / len(deltas), 2) if deltas else 0,
                        "trend_direction": "declining" if sum(deltas) < 0 else "stable",
                    },
                },
                "hotspots": client.get_hotspots(region, window_days),
                "scribe": [],  # Populated by scribe_enrichment.py in Phase 1b
                "wod_searches": [],  # Populated by scribe_enrichment.py in Phase 1b
                "analysis_reports": client.get_analysis_reports(region, min(window_days * 4, 30)),
                "risk_ratings": client.get_risk_ratings(countries),
            },
            "poi_alerts": poi_alerts,
            "source_provenance": "seerist",
        }

    return result


def collect(region: str, mock: bool = True, window_days: int = 7) -> dict:
    """Collect Seerist intelligence for a region."""
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
