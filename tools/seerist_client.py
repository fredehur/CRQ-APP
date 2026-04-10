#!/usr/bin/env python3
"""Seerist API client — all endpoints under https://app.seerist.com/hyperionapi/.

Auth: x-api-key header. Responses are GeoJSON. This client normalizes
features[].properties into pipeline signal schemas.

Reference: memory/reference-seerist-api.md
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://app.seerist.com/hyperionapi/"

# CRQ region → Seerist Area of Interest code
REGION_AOI_MAP = {
    "APAC": "APAC",
    "AME": "AMER",
    "LATAM": "AMER",
    "MED": "MENA",
    "NCE": "EURC",
}

# CRQ region → ISO country codes (for Pulse, Scribe, Risk Ratings — per-country endpoints)
REGION_COUNTRIES = {
    "APAC": ["CN", "AU", "TW", "JP", "SG", "KR", "IN"],
    "AME": ["US", "CA", "MX"],
    "LATAM": ["BR", "CL", "CO", "AR", "PE"],
    "MED": ["IT", "ES", "GR", "TR", "MA", "EG"],
    "NCE": ["DE", "PL", "DK", "SE", "NO", "FI"],
}

# LATAM/MED/NCE share AoI with AME/MENA/EURC — filter by country
REGION_COUNTRY_FILTER = {
    "LATAM": {"BR", "CL", "CO", "AR", "PE"},
    "MED": {"IT", "ES", "GR", "TR", "MA", "EG"},
    "NCE": {"DE", "PL", "DK", "SE", "NO", "FI"},
}


def _normalize_event(feature: dict, region: str, seq: int, *, verified: bool = False) -> dict:
    """Normalize a GeoJSON feature into pipeline event schema."""
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates", [0, 0])  # [lon, lat]

    prefix = "seerist:verified" if verified else "seerist:events_ai"
    return {
        "signal_id": f"{prefix}:{region.lower()}-{seq:03d}",
        "title": props.get("name", ""),
        "category": props.get("eventType", "Unknown"),
        "severity": props.get("severity", 0),
        "location": {
            "lat": coords[1] if len(coords) > 1 else 0,
            "lon": coords[0] if coords else 0,
            "name": props.get("locationName", ""),
            "country_code": props.get("countryCode", ""),
        },
        "source_reliability": props.get("sourceMetadataReliability", "medium"),
        "source_count": props.get("sourcesCount", 0),
        "timestamp": props.get("publishDate", ""),
        "verified": verified,
    }


def _normalize_hotspot(feature: dict, region: str, seq: int) -> dict:
    """Normalize a hotspot GeoJSON feature."""
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates", [0, 0])
    return {
        "signal_id": f"seerist:hotspot:{region.lower()}-{seq:03d}",
        "location": {
            "name": props.get("locationName", ""),
            "lat": coords[1] if len(coords) > 1 else 0,
            "lon": coords[0] if coords else 0,
        },
        "deviation_score": props.get("deviationScore", 0.0),
        "category_hint": props.get("eventType", ""),
        "detected_at": props.get("publishDate", ""),
        "anomaly_flag": props.get("deviationScore", 0) > 0.7,
        "cluster_ids": props.get("clusterIds", []),
    }


def _date_range(days: int) -> tuple[str, str]:
    """Return (start_iso, end_iso) for the last N days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _filter_by_country(features: list, region: str) -> list:
    """For shared AoIs (LATAM/MED/NCE), filter features to region's countries."""
    country_filter = REGION_COUNTRY_FILTER.get(region)
    if not country_filter:
        return features
    return [f for f in features
            if f.get("properties", {}).get("countryCode", "").upper() in country_filter]


class SeeristClient:
    """Seerist API client with typed methods per data type."""

    def __init__(self):
        api_key = os.environ.get("SEERIST_API_KEY", "")
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"x-api-key": api_key, "Accept": "application/json"},
            timeout=30,
        )

    @classmethod
    def create(cls) -> "SeeristClient | None":
        """Factory — returns None if no API key is set."""
        if not os.environ.get("SEERIST_API_KEY"):
            return None
        return cls()

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- Tier 1 data type methods ---

    def get_events(self, region: str, days: int = 7) -> list[dict]:
        """Events AI — clustered events. GET /v2/clusters/{categories}."""
        aoi = REGION_AOI_MAP[region]
        start, end = _date_range(days)
        categories = "Conflict,Terrorism,Unrest,Crime,Health,Transportation"
        resp = self._client.get(
            f"/v2/clusters/{categories}",
            params={"aoiId": aoi, "start": start, "end": end,
                    "severityMin": "2", "pageSize": "50"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        return [_normalize_event(f, region, i + 1) for i, f in enumerate(features)]

    def get_verified_events(self, region: str, days: int = 90) -> list[dict]:
        """Verified Events — human-confirmed. GET /v1/wod with political/maritime sources."""
        aoi = REGION_AOI_MAP[region]
        start, end = _date_range(days)
        resp = self._client.get(
            "/v1/wod",
            params={"aoiId": aoi, "sources": "political,maritime",
                    "start": start, "end": end, "pageSize": "25"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        return [_normalize_event(f, region, i + 1, verified=True) for i, f in enumerate(features)]

    def get_hotspots(self, region: str, days: int = 7) -> list[dict]:
        """Hotspots AI — anomaly detection. GET /v1/hotspots."""
        aoi = REGION_AOI_MAP[region]
        start, end = _date_range(days)
        resp = self._client.get(
            "/v1/hotspots",
            params={"aoiId": aoi, "start": start, "end": end, "pageSize": "20"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        return [_normalize_hotspot(f, region, i + 1) for i, f in enumerate(features)]

    def get_pulse(self, countries: list[str]) -> dict:
        """Pulse AI — country stability. GET /v2/pulse/country/{code} per country."""
        result = {}
        for code in countries[:3]:  # cap at 3 per region
            try:
                resp = self._client.get(
                    f"/v2/pulse/country/{code.lower()}",
                    params={"includeForecast": "true"},
                )
                resp.raise_for_status()
                data = resp.json()
                props = data.get("features", [{}])[0].get("properties", {}) if data.get("features") else data
                result[code] = {
                    "score": props.get("score", 0),
                    "color": props.get("color", ""),
                    "delta": props.get("delta", 0),
                    "forecast": props.get("forecast", 0),
                }
            except Exception as e:
                print(f"[seerist] Pulse error for {code}: {e}", file=sys.stderr)
                result[code] = {"score": 0, "color": "grey", "delta": 0, "forecast": 0}
        return result

    def get_risk_ratings(self, countries: list[str]) -> dict:
        """Risk Ratings — GET /v1/wod/risk-rating/{code} per country."""
        result = {}
        for code in countries[:3]:
            try:
                resp = self._client.get(f"/v1/wod/risk-rating/{code.lower()}")
                resp.raise_for_status()
                data = resp.json()
                props = data.get("features", [{}])[0].get("properties", {}) if data.get("features") else data
                result[code] = {
                    "overall": props.get("overall", "Unknown"),
                    "political": props.get("political", "Unknown"),
                    "security": props.get("security", "Unknown"),
                    "operational": props.get("operational", "Unknown"),
                }
            except Exception as e:
                print(f"[seerist] Risk rating error for {code}: {e}", file=sys.stderr)
        return result

    def get_analysis_reports(self, region: str, days: int = 30) -> list[dict]:
        """Analysis Reports — GET /v1/wod with sources=analysis."""
        aoi = REGION_AOI_MAP[region]
        start, end = _date_range(days)
        resp = self._client.get(
            "/v1/wod",
            params={"aoiId": aoi, "sources": "analysis",
                    "start": start, "end": end, "pageSize": "10"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        result = []
        for i, f in enumerate(features):
            props = f.get("properties", {})
            result.append({
                "signal_id": f"seerist:analysis:{region.lower()}-{i + 1:03d}",
                "title": props.get("name", ""),
                "summary": props.get("description", ""),
                "source": props.get("source", ""),
                "published_at": props.get("publishDate", ""),
            })
        return result

    def get_scribe_summary(self, country_code: str, date: str) -> dict:
        """Scribe AI — country summary. GET /v2/auto-summary/{code}/country."""
        resp = self._client.get(
            f"/v2/auto-summary/{country_code.lower()}/country",
            params={"date": date},
        )
        resp.raise_for_status()
        return resp.json()

    def get_breaking_events(self, region: str) -> list[dict]:
        """Breaking News. GET /v1/wod/breaking-events."""
        aoi = REGION_AOI_MAP[region]
        resp = self._client.get(
            "/v1/wod/breaking-events",
            params={"aoiId": aoi, "pageSize": "10"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        result = []
        for i, f in enumerate(features):
            props = f.get("properties", {})
            result.append({
                "signal_id": f"seerist:breaking:{region.lower()}-{i + 1:03d}",
                "title": props.get("name", ""),
                "status": props.get("status", "developing"),
                "severity": props.get("severity", 0),
                "timestamp": props.get("publishDate", ""),
            })
        return result

    def get_news(self, region: str, days: int = 7) -> list[dict]:
        """News — curated coverage. GET /v1/wod with sources=news."""
        aoi = REGION_AOI_MAP[region]
        start, end = _date_range(days)
        resp = self._client.get(
            "/v1/wod",
            params={"aoiId": aoi, "sources": "news", "start": start, "end": end,
                    "sourceMetadataReliability": "high,medium", "pageSize": "15"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        result = []
        for i, f in enumerate(features):
            props = f.get("properties", {})
            result.append({
                "signal_id": f"seerist:news:{region.lower()}-{i + 1:03d}",
                "title": props.get("name", ""),
                "source": props.get("source", ""),
                "source_type": props.get("sourceType", "journalistic"),
                "source_reliability": props.get("sourceMetadataReliability", "medium"),
                "timestamp": props.get("publishDate", ""),
            })
        return result

    def search_wod(self, region: str, query: str, days: int = 7) -> dict:
        """WoD Search — Lucene syntax. GET /v1/wod with search param."""
        aoi = REGION_AOI_MAP[region]
        start, end = _date_range(days)
        resp = self._client.get(
            "/v1/wod",
            params={"aoiId": aoi, "search": query,
                    "sources": "news,twitter,telegram",
                    "severityMin": "3", "start": start, "end": end,
                    "sourceMetadataReliability": "high,medium", "pageSize": "10"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        top_results = []
        for f in features[:10]:
            props = f.get("properties", {})
            top_results.append({
                "title": props.get("name", ""),
                "source": props.get("source", ""),
                "severity": props.get("severity", 0),
                "timestamp": props.get("publishDate", ""),
                "source_reliability": props.get("sourceMetadataReliability", "medium"),
            })
        return {"result_count": len(features), "top_results": top_results}

    def search_poi(self, pois: list[list[float]], days: int = 7) -> list[dict]:
        """POI Search — events near facility coordinates. GET /v1/wod with pois param."""
        start, end = _date_range(days)
        pois_str = json.dumps(pois)
        resp = self._client.get(
            "/v1/wod",
            params={"pois": pois_str, "poisDistUnits": "km",
                    "start": start, "end": end, "pageSize": "20"},
        )
        resp.raise_for_status()
        return resp.json().get("features", [])

    def get_events_since(self, region: str, timestamp: str) -> list[dict]:
        """Delta collection — events since last run. GET /v1/wod with since param."""
        aoi = REGION_AOI_MAP[region]
        resp = self._client.get(
            "/v1/wod",
            params={"aoiId": aoi, "since": timestamp, "pageSize": "50"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        return [_normalize_event(f, region, i + 1) for i, f in enumerate(features)]
