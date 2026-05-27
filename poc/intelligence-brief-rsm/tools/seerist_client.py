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
import truststore
from dotenv import load_dotenv

truststore.inject_into_ssl()
load_dotenv()

BASE_URL = "https://app.seerist.com/hyperionapi/"

# Seerist risk category UUIDs that map to cyber topics
_CYBER_RISK_CATEGORY_IDS = [
    "53bd26cf-58fb-4ce9-8d04-e239f40d6710",
    "d49316b4-45f5-4337-b69b-0b4ee12d3db7",
    "11a90149-d226-49f5-b668-1c4061a06065",
    "7b53a8c4-4ad5-41de-8c5c-73e9427a27eb",
]

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

# Country lists per CRQ region, in spec order (used for aoiId construction).
# Sets below are derived from these for defense-in-depth filtering.
_REGION_COUNTRY_ORDER = {
    "LATAM": ("BR", "CL", "CO", "AR", "PE"),
    "MED":   ("IT", "ES", "GR", "TR", "MA", "EG"),
    "NCE":   ("DE", "PL", "DK", "SE", "NO", "FI"),
}

# LATAM/MED/NCE share AoI with AME/MENA/EURC — filter by country
REGION_COUNTRY_FILTER = {r: set(cs) for r, cs in _REGION_COUNTRY_ORDER.items()}

# ISO-3 → ISO-2 for the codes /v1/wod emits for the regions we filter
_ISO3_TO_ISO2 = {
    "BRA": "BR", "CHL": "CL", "COL": "CO", "ARG": "AR", "PER": "PE",
    "ITA": "IT", "ESP": "ES", "GRC": "GR", "TUR": "TR", "MAR": "MA", "EGY": "EG",
    "DEU": "DE", "POL": "PL", "DNK": "DK", "SWE": "SE", "NOR": "NO", "FIN": "FI",
}


def _aoi_param_for_region(region: str) -> str:
    """Return the aoiId param value for a CRQ region."""
    direct = {"APAC": "APAC", "AME": "AMER"}
    if region in direct:
        return direct[region]
    ordered = _REGION_COUNTRY_ORDER.get(region)
    if not ordered:
        return REGION_AOI_MAP[region]
    return ",".join(ordered)


_DAMAGE_RATING_TO_SEVERITY = {"low": 2, "medium": 5, "high": 8, "severe": 10}


def _normalize_event(feature: dict, region: str, seq: int, *, verified: bool = False) -> dict:
    """Normalize a GeoJSON feature into pipeline event schema.

    Handles both schemas:
    - Verified events (`/v1/wod` political/maritime): camelCase props
      (`title`, `severity`, `countryCode`, `initialPublishedDate`, `damageRatingName`).
    - Cluster events (`/v2/clusters/...`): snake_case props
      (`title`, `cluster_size`, `category_types`, `timestamp`); no countryCode/severity.
    """
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates", [0, 0])  # [lon, lat]

    prefix = "seerist:verified" if verified else "seerist:events_ai"

    title = props.get("title") or props.get("name") or props.get("headline") or ""
    if isinstance(title, dict):  # hotspot-style nested headline
        title = title.get("text", "") or ""

    timestamp = (
        props.get("initialPublishedDate")
        or props.get("publishDate")
        or props.get("timestamp")
        or props.get("@timestamp")
        or ""
    )

    category = props.get("eventType")
    if not category or category == "verified":
        cats = props.get("category_types") or props.get("categories") or props.get("labeled_categories")
        if isinstance(cats, list) and cats:
            category = cats[0] if isinstance(cats[0], str) else cats[0].get("name", "Unknown")
        elif isinstance(cats, str):
            category = cats
        else:
            category = "Unknown"

    severity = props.get("severity")
    if severity is None or severity == 0:
        rating = (props.get("damageRatingName") or "").strip().lower()
        if rating in _DAMAGE_RATING_TO_SEVERITY:
            severity = _DAMAGE_RATING_TO_SEVERITY[rating]
        else:
            severity = 0

    lm = props.get("location_metadata") if isinstance(props.get("location_metadata"), dict) else {}
    location_name = (
        props.get("locationName")
        or props.get("locationPrecisionName")
        or props.get("countryName")
        or (lm.get("city") if lm else "")
        or (lm.get("state") if lm else "")
        or (lm.get("country") if lm else "")
        or ""
    )

    return {
        "signal_id": f"{prefix}:{region.lower()}-{seq:03d}",
        "title": title,
        "category": category,
        "severity": severity,
        "location": {
            "lat": coords[1] if len(coords) > 1 else 0,
            "lon": coords[0] if coords else 0,
            "name": location_name,
            "country_code": _feature_country_iso2(feature),
        },
        "source_reliability": props.get("sourceMetadataReliability", "medium"),
        "source_count": props.get("cluster_size") or props.get("sourcesCount") or 0,
        "timestamp": timestamp,
        "verified": verified,
    }


def _normalize_hotspot(feature: dict, region: str, seq: int) -> dict:
    """Normalize a hotspot GeoJSON feature.

    Live hotspot schema: `headline` (dict), `topics` (list), `clusterIds`,
    `location_metadata` (dict), `geohash`, `age_in_hours`, `startTime`,
    `trigger_start`, `hotspotTypes`, `keywords`. No deviationScore field;
    we approximate anomaly_flag from age (recent = anomalous).
    """
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates", [0, 0])

    headline = props.get("headline") or {}
    if isinstance(headline, dict):
        headline_text = headline.get("text") or headline.get("title") or ""
    else:
        headline_text = str(headline)

    location_meta = props.get("location_metadata") or {}
    location_name = ""
    if isinstance(location_meta, dict):
        location_name = (
            location_meta.get("label")
            or location_meta.get("name")
            or location_meta.get("display")
            or ""
        )

    topics = props.get("topics") or []
    category_hint = topics[0] if isinstance(topics, list) and topics else ""

    age_hours = props.get("age_in_hours") or 999
    anomaly_flag = bool(age_hours <= 24)

    return {
        "signal_id": f"seerist:hotspot:{region.lower()}-{seq:03d}",
        "headline": headline_text,
        "location": {
            "name": location_name,
            "lat": coords[1] if len(coords) > 1 else 0,
            "lon": coords[0] if coords else 0,
        },
        "age_hours": age_hours,
        "category_hint": category_hint,
        "keywords": props.get("keywords", []),
        "detected_at": props.get("trigger_start") or props.get("startTime", ""),
        "anomaly_flag": anomaly_flag,
        "cluster_ids": props.get("clusterIds", []),
    }


def _date_range(days: int) -> tuple[str, str]:
    """Return (start_iso, end_iso) for the last N days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%dT%H:%M:%S.000Z"), end.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _feature_country_iso2(feature: dict) -> str:
    """Extract a feature's country code, normalized to ISO-2 uppercase.

    Handles three Seerist response shapes:
    - /v2/clusters and /v1/hotspots: properties.location_metadata.countryCode
      (ISO-2 lowercase, e.g. "ps")
    - /v1/wod (verified, news, breaking): properties.countryCode
      (ISO-3 uppercase, e.g. "PSE"); occasionally ISO-2 uppercase
    Returns "" when no country info is present.
    """
    props = feature.get("properties") or {}
    lm = props.get("location_metadata")
    code = ""
    if isinstance(lm, dict):
        code = lm.get("countryCode") or ""
    if not code:
        code = props.get("countryCode") or ""
    code = code.upper()
    if len(code) == 3:
        code = _ISO3_TO_ISO2.get(code, code)
    return code


def _filter_by_country(features: list, region: str) -> list:
    """For shared AoIs (LATAM/MED/NCE), filter features to region's countries."""
    country_filter = REGION_COUNTRY_FILTER.get(region)
    if not country_filter:
        return features
    return [f for f in features if _feature_country_iso2(f) in country_filter]


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
        aoi = _aoi_param_for_region(region)
        start, end = _date_range(days)
        categories = "conflict,terrorism,unrest,crime,health,transportation"
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
        aoi = _aoi_param_for_region(region)
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
        aoi = _aoi_param_for_region(region)
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
        aoi = _aoi_param_for_region(region)
        start, end = _date_range(days)
        resp = self._client.get(
            "/v1/wod",
            params={"aoiId": aoi, "sources": "analysis",
                    "start": start, "end": end, "pageSize": "10"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        def _en(value):
            if isinstance(value, dict):
                return value.get("en") or value.get("EN") or next(iter(value.values()), "")
            return value or ""

        result = []
        for i, f in enumerate(features):
            props = f.get("properties", {})
            result.append({
                "signal_id": f"seerist:analysis:{region.lower()}-{i + 1:03d}",
                "title": _en(props.get("title") or props.get("name", "")),
                "summary": _en(
                    props.get("sanitizedSummary")
                    or props.get("summary")
                    or props.get("description", "")
                ),
                "source": props.get("source", ""),
                "published_at": (
                    props.get("publishedDate")
                    or props.get("publishDate", "")
                ),
            })
        return result

    def get_cyber_analysis(self, since: datetime, page_size: int = 100) -> list[dict]:
        """Cyber Analysis — global cyber risk documents. GET /v1/wod with riskCategories filter.

        No AoI filter — cyber documents are global; region-relevance is determined downstream.
        Returns raw feature properties dicts (not GeoJSON-normalized) so the collector can
        map them into the cyber_signals schema with full field visibility.
        """
        try:
            resp = self._client.get(
                "/v1/wod",
                params={
                    "sources": "analysis",
                    "start": since.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "pageSize": str(page_size),
                    "riskCategories": ",".join(_CYBER_RISK_CATEGORY_IDS),
                },
            )
            resp.raise_for_status()
            return resp.json().get("features", [])
        except Exception as e:
            print(f"[seerist] Cyber analysis error: {e}", file=sys.stderr)
            return []

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
        aoi = _aoi_param_for_region(region)
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
        aoi = _aoi_param_for_region(region)
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
                "title": props.get("title") or props.get("name", ""),
                "source": props.get("source", ""),
                "source_type": props.get("sourceType")
                    or props.get("sourceMetadataType", "journalistic"),
                "source_reliability": props.get("sourceMetadataReliability", "medium"),
                "timestamp": (
                    props.get("initialPublishedDate")
                    or props.get("publishDate")
                    or props.get("@timestamp", "")
                ),
            })
        return result

    def search_wod(self, region: str, query: str, days: int = 7) -> dict:
        """WoD Search — Lucene syntax. GET /v1/wod with search param."""
        aoi = _aoi_param_for_region(region)
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
        aoi = _aoi_param_for_region(region)
        resp = self._client.get(
            "/v1/wod",
            params={"aoiId": aoi, "since": timestamp, "pageSize": "50"},
        )
        resp.raise_for_status()
        features = _filter_by_country(resp.json().get("features", []), region)
        return [_normalize_event(f, region, i + 1) for i, f in enumerate(features)]
