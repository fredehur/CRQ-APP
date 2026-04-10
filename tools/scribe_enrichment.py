#!/usr/bin/env python3
"""Scribe enrichment — Phase 1b targeted query enrichment.

Reads osint_signals.json + scenario_map.json, constructs targeted Scribe/WoD
queries, appends results to seerist_signals.json under analytical.scribe[]
and analytical.wod_searches[].

Usage:
    uv run python tools/scribe_enrichment.py REGION [--mock]

Depends on: osint_signals.json, scenario_map.json, seerist_signals.json (all from Phase 1a)
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


def build_enrichment_plan(osint_signals: dict, scenario_map: dict, region: str) -> dict:
    """Build Scribe country calls + WoD search queries. Deterministic — no LLM."""
    from tools.seerist_client import REGION_COUNTRIES

    plan = {"scribe_countries": [], "wod_searches": []}

    # Channel A — Scribe for top 2 countries in region
    countries = REGION_COUNTRIES.get(region, [])[:2]
    plan["scribe_countries"] = countries

    # Channel B — WoD targeted searches from OSINT findings
    scenario = scenario_map.get("scenario_match")
    if scenario:
        plan["wod_searches"].append({
            "query": f"{scenario} energy infrastructure",
            "derived_from": [f"scenario_map:{scenario.lower().replace(' ', '_')}"],
        })

    pillar = osint_signals.get("dominant_pillar", "Cyber")
    plan["wod_searches"].append({
        "query": f"{pillar.lower()} threat renewable energy",
        "derived_from": [f"osint:dominant_pillar:{pillar.lower()}"],
    })

    # Bonus — actor search if clean name found in indicators
    actor = _extract_actor_if_clean(osint_signals)
    if actor:
        plan["wod_searches"].append({
            "query": f"{actor} energy",
            "derived_from": [f"osint:actor:{actor.lower()}"],
        })

    plan["wod_searches"] = plan["wod_searches"][:3]  # hard cap
    return plan


def _extract_actor_if_clean(osint_signals: dict) -> str | None:
    """Extract threat actor name if it appears cleanly in indicators."""
    known_actors = {
        "Volt Typhoon", "APT41", "Sandworm", "Lazarus Group",
        "APT28", "APT29", "Kimsuky", "Charming Kitten",
    }
    for ind in osint_signals.get("lead_indicators", []):
        text = ind.get("text", "") if isinstance(ind, dict) else str(ind)
        for actor in known_actors:
            if actor.lower() in text.lower():
                return actor
    return None


def _mock_enrich(region: str) -> dict:
    """Read mock Scribe fixture."""
    fixture = FIXTURES_DIR / f"{region.lower()}_scribe.json"
    if not fixture.exists():
        return {"scribe": [], "wod_searches": []}
    return json.loads(fixture.read_text(encoding="utf-8"))


def _live_enrich(region: str, plan: dict, window_days: int) -> dict:
    """Call Seerist Scribe + WoD search APIs."""
    from tools.seerist_client import SeeristClient

    client = SeeristClient.create()
    if client is None:
        print("[scribe_enrichment] No API key — returning empty", file=sys.stderr)
        return {"scribe": [], "wod_searches": []}

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%dT00:00:00.000Z")
    scribe_results = []
    wod_results = []

    with client:
        # Channel A — Scribe country summaries
        for i, country in enumerate(plan["scribe_countries"]):
            try:
                resp = client.get_scribe_summary(country, date_str)
                scribe_results.append({
                    "signal_id": f"seerist:scribe:{region.lower()}-{i + 1:03d}",
                    "type": "country_summary",
                    "country_code": country,
                    "assessment": resp.get("summary", str(resp)),
                    "date": now.strftime("%Y-%m-%d"),
                    "derived_from": [f"region_map:{region}→{country}"],
                })
            except Exception as e:
                print(f"[scribe_enrichment] Scribe error for {country}: {e}", file=sys.stderr)

        # Channel B — WoD searches
        for i, search in enumerate(plan["wod_searches"]):
            try:
                result = client.search_wod(region, search["query"], window_days)
                wod_results.append({
                    "signal_id": f"seerist:wod:{region.lower()}-{i + 1:03d}",
                    "query": search["query"],
                    "derived_from": search["derived_from"],
                    "result_count": result["result_count"],
                    "top_results": result["top_results"],
                    "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
            except Exception as e:
                print(f"[scribe_enrichment] WoD search error: {e}", file=sys.stderr)

    return {"scribe": scribe_results, "wod_searches": wod_results}


def enrich(region: str, mock: bool = True, window_days: int = 7) -> None:
    """Run Scribe enrichment and append to seerist_signals.json."""
    region = region.upper()
    if region not in VALID_REGIONS:
        raise ValueError(f"invalid region '{region}'")

    base = OUTPUT_ROOT / "regional" / region.lower()
    seerist_path = base / "seerist_signals.json"

    if not seerist_path.exists():
        print(f"[scribe_enrichment] No seerist_signals.json for {region} — skipping", file=sys.stderr)
        return

    seerist = json.loads(seerist_path.read_text(encoding="utf-8"))

    if mock:
        enrichment = _mock_enrich(region)
    else:
        # Read OSINT + scenario_map for query construction
        osint_path = base / "osint_signals.json"
        scenario_path = base / "scenario_map.json"
        osint = json.loads(osint_path.read_text(encoding="utf-8")) if osint_path.exists() else {}
        scenario = json.loads(scenario_path.read_text(encoding="utf-8")) if scenario_path.exists() else {}

        plan = build_enrichment_plan(osint, scenario, region)
        enrichment = _live_enrich(region, plan, window_days)

    # Append to seerist_signals.json — only overwrite if enrichment returned non-empty data
    seerist.setdefault("analytical", {})
    scribe_data = enrichment.get("scribe")
    wod_data = enrichment.get("wod_searches")
    if scribe_data:
        seerist["analytical"]["scribe"] = scribe_data
    if wod_data:
        seerist["analytical"]["wod_searches"] = wod_data

    seerist_path.write_text(json.dumps(seerist, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[scribe_enrichment] enriched {seerist_path} — {len(enrichment.get('scribe', []))} scribe + {len(enrichment.get('wod_searches', []))} wod", file=sys.stderr)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: scribe_enrichment.py REGION [--mock]", file=sys.stderr)
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

    enrich(region, mock=mock, window_days=window_days)


if __name__ == "__main__":
    main()
