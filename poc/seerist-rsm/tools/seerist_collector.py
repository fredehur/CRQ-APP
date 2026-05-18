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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
FIXTURES_DIR = REPO_ROOT / "data" / "mock_osint_fixtures"

_CYBER_KEYWORDS = [
    "ransomware", "ransom", "breach", "data breach",
    "hack", "hacked", "hacker", "hacking",
    "malware", "trojan", "wiper", "rootkit",
    "phishing", "spear phish",
    "CVE-", "zero-day", "0-day", "zero day",
    "exploit", "vulnerability",
    "APT", "advanced persistent",
    "DDoS", "denial of service",
    "encrypted by", "encrypted system", "files encrypted",
    "leak", "leaked", "leaks",
    "infosec", "cyber", "cyberattack", "cybersecurity",
    "supply chain", "supply-chain",
    "ICS", "SCADA", "OT", "operational technology",
    "Sandworm", "APT28", "APT29", "APT35", "MuddyWater", "OilRig",
    "Lazarus", "MEDUSA", "LockBit", "Volt Typhoon", "Pioneer Kitten",
]

import math


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in kilometres between two (lon, lat) points."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _build_actor_lookup() -> dict[str, str]:
    """Load cyber_watchlist.json and return {lowercased token → canonical name}."""
    lookup: dict[str, str] = {}
    watchlist_path = REPO_ROOT / "data" / "cyber_watchlist.json"
    if not watchlist_path.exists():
        return lookup
    try:
        wl = json.loads(watchlist_path.read_text(encoding="utf-8"))
        for actor in wl.get("threat_actor_groups", []):
            canonical = actor.get("name", "")
            if canonical:
                lookup[canonical.lower()] = canonical
                for alias in actor.get("aliases", []):
                    if alias:
                        lookup[alias.lower()] = canonical
    except Exception:
        pass
    return lookup


def _find_relevant_actors(text: str, actor_lookup: dict[str, str]) -> list[str]:
    """Return canonical actor names whose name or alias appears in text (case-insensitive)."""
    tl = text.lower()
    seen: set[str] = set()
    result: list[str] = []
    for token, canonical in actor_lookup.items():
        if token in tl and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def _matched_keywords(text: str) -> list[str]:
    tl = text.lower()
    return [kw for kw in _CYBER_KEYWORDS if kw.lower() in tl]


def _load_threat_actor_context() -> list[str]:
    """Load all actor names + aliases from the watchlist as a flat list."""
    context: list[str] = []
    watchlist_path = REPO_ROOT / "data" / "cyber_watchlist.json"
    if not watchlist_path.exists():
        return context
    try:
        wl = json.loads(watchlist_path.read_text(encoding="utf-8"))
        for actor in wl.get("threat_actor_groups", []):
            name = actor.get("name", "")
            if name:
                context.append(name)
            context.extend(a for a in actor.get("aliases", []) if a)
    except Exception:
        pass
    return context


def _collect_cyber_signals(
    region: str,
    news: list[dict],
    hotspots: list[dict],
    cyber_features: list[dict],
    actor_lookup: dict[str, str],
) -> tuple[list[dict], dict]:
    """Merge keyword-filtered news/hotspot signals with Seerist analysis documents.

    Analysis docs win on title collision (higher-confidence source). Returns
    (cyber_signals, cyber_summary).
    """
    def _en(value) -> str:
        if isinstance(value, dict):
            return value.get("en") or value.get("EN") or next(iter(value.values()), "") or ""
        return value or ""

    # --- Pass 1: normalize analysis docs (higher priority for dedup) ---
    analysis_signals: list[dict] = []
    seen_titles: set[str] = set()

    for idx, feature in enumerate(cyber_features):
        props = feature.get("properties", {})
        title = _en(props.get("title") or props.get("name") or "")
        if not title:
            continue

        summary_raw = (
            props.get("sanitizedSummary")
            or props.get("summary")
            or props.get("description")
            or props.get("body")
            or ""
        )
        summary = _en(summary_raw)
        if len(summary) > 500:
            summary = summary[:500]

        published_date = (
            props.get("publishedDate")
            or props.get("publishDate")
            or props.get("initialPublishedDate")
            or props.get("@timestamp")
            or ""
        )
        risk_categories = props.get("riskCategories") or []
        if not isinstance(risk_categories, list):
            risk_categories = []

        original_id = str(props.get("id") or feature.get("id") or "")

        severity = props.get("severity")
        if not isinstance(severity, (int, float)) or severity == 0:
            severity = 3

        search_text = f"{title} {summary}"
        analysis_signals.append({
            "signal_id": f"seerist:cyber:{region.lower()}-{idx}",
            "source_type": "analysis",
            "title": title,
            "summary": summary,
            "matched_keywords": [],
            "published_date": published_date,
            "risk_categories": risk_categories,
            "original_id": original_id,
            "severity": severity,
            "relevant_actors": _find_relevant_actors(search_text, actor_lookup),
        })
        seen_titles.add(title)

    # --- Pass 2: keyword-filter news and hotspots, skip titles already from analysis ---
    kw_signals: list[dict] = []

    for item in news:
        title = item.get("title", "")
        if not title or title in seen_titles:
            continue
        matched = _matched_keywords(title)
        if not matched:
            continue
        seen_titles.add(title)
        kw_signals.append({
            "signal_id": "",  # assigned below
            "source_type": "news",
            "title": title,
            "summary": "",
            "matched_keywords": matched,
            "published_date": item.get("timestamp", item.get("publishDate", "")),
            "risk_categories": [],
            "original_id": item.get("signal_id", ""),
            "severity": item.get("severity", 0),
            "relevant_actors": _find_relevant_actors(title, actor_lookup),
        })

    for item in hotspots:
        headline = item.get("headline", item.get("title", ""))
        if not headline or headline in seen_titles:
            continue
        matched = _matched_keywords(headline)
        if not matched:
            continue
        seen_titles.add(headline)
        kw_signals.append({
            "signal_id": "",
            "source_type": "hotspot",
            "title": headline,
            "summary": "",
            "matched_keywords": matched,
            "published_date": item.get("timestamp", item.get("publishDate", "")),
            "risk_categories": [],
            "original_id": item.get("signal_id", ""),
            "severity": item.get("severity", 0),
            "relevant_actors": _find_relevant_actors(headline, actor_lookup),
        })

    # Merge: analysis first, then keyword signals; re-sequence signal_ids
    all_signals = analysis_signals + kw_signals
    for i, sig in enumerate(all_signals):
        sig["signal_id"] = f"seerist:cyber:{region.lower()}-{i}"

    sources_used: list[str] = []
    if analysis_signals:
        sources_used.append("seerist:analysis")
    if any(s["source_type"] == "news" for s in kw_signals):
        sources_used.append("keyword:news")
    if any(s["source_type"] == "hotspot" for s in kw_signals):
        sources_used.append("keyword:hotspots")

    summary = {
        "matched_count": len(all_signals),
        "scanned_news": len(news),
        "scanned_hotspots": len(hotspots),
        "scanned_analysis": len(cyber_features),
        "sources_used": sources_used,
        "region": region,
    }
    return all_signals, summary


def _mock_collect(region: str, window_days: int) -> dict:
    """Read mock fixture, stamp metadata."""
    fixture = FIXTURES_DIR / f"{region.lower()}_seerist.json"
    if not fixture.exists():
        raise FileNotFoundError(f"Mock fixture not found: {fixture}")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["collection_window"] = {"days": window_days}

    threat_actor_context = _load_threat_actor_context()
    data.setdefault("analytical", {})["threat_actor_context"] = threat_actor_context

    # Mock mode: run keyword filter on fixture news/hotspots; no live analysis endpoint
    actor_lookup = _build_actor_lookup()
    news = data.get("situational", {}).get("news", [])
    hotspots = data.get("analytical", {}).get("hotspots", [])
    cyber_signals, cyber_summary = _collect_cyber_signals(
        region, news, hotspots, [], actor_lookup
    )
    data["cyber_signals"] = cyber_signals
    data["cyber_summary"] = cyber_summary

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

    # Load facility coords for POI search — group events by nearest facility
    poi_alerts = []
    try:
        sites_doc = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
        facilities = [s for s in sites_doc.get("sites", []) if s["region"] == region]
        if facilities:
            pois = [[f["lon"], f["lat"], f["poi_radius_km"]] for f in facilities]
            poi_features = client.search_poi(pois, days=window_days)
            for fac in facilities:
                fac_events = []
                nearest_km = float("inf")
                for feature in poi_features:
                    coords = feature.get("geometry", {}).get("coordinates", [0, 0])
                    if len(coords) < 2:
                        continue
                    d = _haversine_km(fac["lon"], fac["lat"], coords[0], coords[1])
                    if d <= fac["poi_radius_km"]:
                        props = feature.get("properties", {})
                        if props.get("severity", 0) < 2:
                            continue
                        fac_events.append({
                            "title": props.get("title") or props.get("name", ""),
                            "severity": props.get("severity", 0),
                            "distance_km": round(d, 2),
                            "verified": props.get("eventType") == "verified",
                            "source_count": props.get("cluster_size") or props.get("sourcesCount", 0),
                            "timestamp": props.get("initialPublishedDate") or props.get("publishDate", ""),
                        })
                        nearest_km = min(nearest_km, d)
                poi_alerts.append({
                    "signal_id": f"seerist:poi:{region.lower()}-{fac['site_id']}",
                    "facility": fac["name"],
                    "site_id": fac["site_id"],
                    "coordinates": [fac["lon"], fac["lat"]],
                    "radius_km": fac["poi_radius_km"],
                    "matching_events": fac_events,
                    "nearest_event_km": round(nearest_km, 2) if nearest_km != float("inf") else None,
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
        scores = [v.get("score", 0) for v in pulse_data.values() if v.get("score")]
        deltas = [v.get("delta", 0) for v in pulse_data.values()]
        worst = min(pulse_data.items(), key=lambda x: x[1].get("score", 999)) if pulse_data else ("", {"score": 0})

        cyber_since = now - timedelta(days=window_days)
        cyber_features = client.get_cyber_analysis(cyber_since, page_size=100)
        news = client.get_news(region, window_days)
        hotspots = client.get_hotspots(region, window_days)

        result = {
            "region": region,
            "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "collection_window": {
                "since": since or cyber_since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "days": window_days,
            },
            "situational": {
                "events": client.get_events(region, window_days),
                "verified_events": client.get_verified_events(region, min(window_days * 3, 90)),
                "breaking_news": client.get_breaking_events(region),
                "news": news,
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
                "hotspots": hotspots,
                "scribe": [],  # Populated by scribe_enrichment.py in Phase 1b
                "wod_searches": [],  # Populated by scribe_enrichment.py in Phase 1b
                "analysis_reports": client.get_analysis_reports(region, min(window_days * 4, 30)),
                "risk_ratings": client.get_risk_ratings(countries),
            },
            "poi_alerts": poi_alerts,
            "source_provenance": "seerist",
        }

    # Stamp watchlist context for downstream agents — non-fatal if absent
    threat_actor_context = _load_threat_actor_context()
    result["analytical"]["threat_actor_context"] = threat_actor_context

    # Merge analysis docs + keyword-filtered news/hotspots into cyber_signals[]
    actor_lookup = _build_actor_lookup()
    cyber_signals, cyber_summary = _collect_cyber_signals(
        region, news, hotspots, cyber_features, actor_lookup
    )
    result["cyber_signals"] = cyber_signals
    result["cyber_summary"] = cyber_summary

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
