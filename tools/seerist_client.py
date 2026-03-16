#!/usr/bin/env python3
"""Seerist geopolitical risk intelligence client.

Seerist (formerly Geospark Analytics) is an API-first, AI-powered geopolitical
risk intelligence platform backed by Control Risks. It delivers structured
intelligence objects — not search results — covering every country globally.

Activation: set SEERIST_API_KEY in .env
Optional:   set SEERIST_CYBER_ADDON=true to enable +Cyber endpoints (separate license)

All methods return None if SEERIST_API_KEY is not set. The pipeline degrades
gracefully — osint_search.py (Tavily/DDG) handles the load when Seerist is absent.

API contract (REST, JSON responses):
  Base URL: TODO — confirm with Seerist (no public developer portal)
  Auth:     Authorization: Bearer {SEERIST_API_KEY}  (confirm header name with Seerist)

Seerist intelligence engines covered here:
  PulseAI         — 0–100 country stability score, 29 sub-category risk ratings, daily cadence
  EventsAI        — AI-classified event feed (8 categories), updated every 6 hours, 6.8M+ sources
  Verified Events — human-curated historical event DB (2008–present), war/terrorism/unrest/crime
  HotspotsAI      — anomaly detection, flags deviations before media coverage
  ScribeAI        — auto-generated written risk/threat assessment reports (on-demand)
  +Cyber          — country-level cyber risk ratings + threat actor profiles (add-on license)
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

# TODO: confirm base URL with Seerist (provided under commercial contract)
SEERIST_BASE_URL = os.environ.get("SEERIST_BASE_URL", "https://api.seerist.com/v1")

# Region → ISO country codes mapping for Seerist queries
REGION_COUNTRIES = {
    "APAC":  ["CN", "AU", "TW", "JP", "SG", "KR", "IN"],
    "AME":   ["US", "CA", "MX"],
    "LATAM": ["BR", "CL", "CO", "AR", "PE"],
    "MED":   ["IT", "ES", "GR", "TR", "MA", "EG"],
    "NCE":   ["DE", "PL", "DK", "SE", "NO", "FI"],
}

# EventsAI 8 top-level categories
EVENTS_AI_CATEGORIES = ["Conflict", "Terrorism", "Unrest", "Disasters", "Crime", "Health", "Travel Safety", "Transportation"]

# PulseAI 29 sub-category domains (full list not publicly enumerated — confirm with Seerist)
PULSE_DOMAINS = ["political", "operational", "security", "cyber", "maritime"]


def _get_client() -> httpx.Client | None:
    """Return authenticated httpx client, or None if no API key is set."""
    api_key = os.environ.get("SEERIST_API_KEY")
    if not api_key:
        return None
    return httpx.Client(
        base_url=SEERIST_BASE_URL,
        headers={
            # TODO: confirm auth header name with Seerist
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        timeout=20,
    )


def get_pulse_stability(region: str) -> dict | None:
    """PulseAI — 0–100 country stability score + 29 sub-category risk ratings.

    Updated daily. Covers every country, ~8,000 sub-national regions, 1,200+ cities.
    Bloomberg ingests this data for company-level geopolitical risk scores.

    Expected response shape (TODO: confirm field names with Seerist):
    {
        "stability_score": 42,          # 0–100, higher = more stable
        "security_risk": "High",        # Control Risks expert rating
        "political_risk": "Medium",
        "operational_risk": "Medium",
        "sub_categories": {             # 29 sub-category ratings
            "political_violence": "Low",
            "border_tension": "High",
            # ... (full list to be confirmed with Seerist)
        },
        "forecast_horizon_years": 5,
        "last_updated": "2026-03-14T00:00:00Z"
    }

    TODO: confirm endpoint path — likely GET /pulse/regions/{region} or GET /pulse/countries?codes=US,CA
    """
    client = _get_client()
    if client is None:
        return None
    countries = REGION_COUNTRIES.get(region.upper(), [])
    if not countries:
        return None
    try:
        with client:
            # TODO: replace with confirmed endpoint
            resp = client.get(f"/pulse/regions/{region.upper()}", params={"countries": ",".join(countries)})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[seerist] PulseAI error for {region}: {e}", file=sys.stderr)
        return None


def get_events_ai(region: str, days: int = 30) -> list[dict] | None:
    """EventsAI — AI-classified event feed updated every 6 hours.

    Ingests 6.8M+ OSINT sources in 100+ languages. Events are accurately
    geolocated with metadata. 8 categories: Conflict, Terrorism, Unrest,
    Disasters, Crime, Health, Travel Safety, Transportation.

    Each event shape (TODO: confirm field names with Seerist):
    {
        "event_id": "...",
        "category": "Unrest",           # one of EVENTS_AI_CATEGORIES
        "severity": 3,                  # TODO: confirm severity scale (1–5? 1–10?)
        "title": "...",
        "description": "...",
        "location": {"name": "...", "lat": 0.0, "lon": 0.0, "country_code": "TW"},
        "timestamp": "2026-03-13T18:00:00Z",
        "source_count": 12,
        "verified": false               # true = from Verified Events DB (human-curated)
    }

    Available as Esri hosted Feature Service AND via REST API — confirm preferred endpoint.
    TODO: confirm endpoint path — likely GET /events?region=APAC&days=30&categories=Conflict,Terrorism,Unrest
    """
    client = _get_client()
    if client is None:
        return None
    countries = REGION_COUNTRIES.get(region.upper(), [])
    try:
        with client:
            # TODO: replace with confirmed endpoint
            resp = client.get(
                "/events",
                params={
                    "countries": ",".join(countries),
                    "days": days,
                    "categories": ",".join(["Conflict", "Terrorism", "Unrest", "Crime"]),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("events", data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"[seerist] EventsAI error for {region}: {e}", file=sys.stderr)
        return None


def get_verified_events(region: str, days: int = 90) -> list[dict] | None:
    """Verified Events — human-curated historical event database (2008–present).

    Covers: war, terrorism, unrest, violent/organized crime.
    Each event accurately geolocated with extensive metadata.
    Use for: event-vs-trend classification (signal_type field in data.json).
    A cluster of verified events = trend; a single recent event = event.

    TODO: confirm endpoint path — likely GET /verified-events?region=APAC&from=2026-01-01
    """
    client = _get_client()
    if client is None:
        return None
    countries = REGION_COUNTRIES.get(region.upper(), [])
    try:
        with client:
            # TODO: replace with confirmed endpoint
            resp = client.get(
                "/verified-events",
                params={"countries": ",".join(countries), "days": days},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("events", data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"[seerist] VerifiedEvents error for {region}: {e}", file=sys.stderr)
        return None


def get_hotspots(region: str) -> list[dict] | None:
    """HotspotsAI — anomaly detection, surfaces deviations before media coverage.

    Detects abnormal activity against location-specific baseline norms.
    Use as an early-warning signal: a hotspot with no media coverage is a
    pre-event indicator — raise admiralty credibility hint if present.

    Each hotspot shape (TODO: confirm with Seerist):
    {
        "hotspot_id": "...",
        "location": {"name": "...", "country_code": "CN"},
        "deviation_score": 0.87,        # TODO: confirm scale
        "baseline_comparison": "...",
        "detected_at": "2026-03-14T06:00:00Z",
        "category_hint": "Unrest"
    }

    TODO: confirm endpoint path — likely GET /hotspots?region=APAC
    """
    client = _get_client()
    if client is None:
        return None
    countries = REGION_COUNTRIES.get(region.upper(), [])
    try:
        with client:
            # TODO: replace with confirmed endpoint
            resp = client.get("/hotspots", params={"countries": ",".join(countries)})
            resp.raise_for_status()
            data = resp.json()
            return data.get("hotspots", data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"[seerist] HotspotsAI error for {region}: {e}", file=sys.stderr)
        return None


def get_scribe_assessment(region: str) -> str | None:
    """ScribeAI — auto-generated written risk/threat assessment report (on-demand).

    Synthesizes PulseAI scores + EventsAI events into a narrative assessment.
    Returns plain text or markdown. Regional analyst can cite this directly.

    TODO: confirm endpoint path — likely POST /scribe/assess with region/country payload
    TODO: confirm whether ScribeAI is a separate licensed add-on or included in base
    """
    client = _get_client()
    if client is None:
        return None
    countries = REGION_COUNTRIES.get(region.upper(), [])
    try:
        with client:
            # TODO: replace with confirmed endpoint
            resp = client.post(
                "/scribe/assess",
                json={"countries": countries, "region": region.upper()},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("assessment") or data.get("report") or str(data)
    except Exception as e:
        print(f"[seerist] ScribeAI error for {region}: {e}", file=sys.stderr)
        return None


def get_cyber_risk(region: str) -> dict | None:
    """+Cyber add-on — country-level cyber risk ratings + threat actor profiles.

    Requires SEERIST_CYBER_ADDON=true in .env (separate license tier).
    Use in cyber_collector.py to provide a quantified country cyber posture
    rather than a keyword-inferred dominant_pillar.

    Expected shape (TODO: confirm with Seerist):
    {
        "cyber_risk_rating": "High",    # country-level
        "threat_actor_profiles": [
            {"name": "...", "type": "state-sponsored|criminal", "active": true}
        ],
        "historical_incidents": 47,     # count over 12 months
        "last_updated": "2026-03-14"
    }

    TODO: confirm endpoint path — likely GET /cyber/risk?countries=CN,TW
    TODO: confirm whether +Cyber is queried per-country or per-region
    """
    cyber_addon = os.environ.get("SEERIST_CYBER_ADDON", "").lower() == "true"
    if not cyber_addon:
        return None
    client = _get_client()
    if client is None:
        return None
    countries = REGION_COUNTRIES.get(region.upper(), [])
    try:
        with client:
            # TODO: replace with confirmed endpoint
            resp = client.get("/cyber/risk", params={"countries": ",".join(countries)})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[seerist] +Cyber error for {region}: {e}", file=sys.stderr)
        return None


def get_full_intelligence(region: str) -> dict:
    """Convenience aggregator — calls all available engines for a region.

    Returns dict with keys: pulse, events, verified_events, hotspots, scribe, cyber.
    Any engine that fails or is unlicensed returns None for that key.
    The caller (geo_collector.py) merges non-None values into geo_signals.json.
    """
    return {
        "pulse": get_pulse_stability(region),
        "events": get_events_ai(region),
        "verified_events": get_verified_events(region),
        "hotspots": get_hotspots(region),
        "scribe": get_scribe_assessment(region),
        "cyber": get_cyber_risk(region),
    }
