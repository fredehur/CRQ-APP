"""Tests for seerist_client.py — auth, region mapping, response normalization."""
import pytest
from unittest.mock import patch, MagicMock
import json


def test_region_aoi_mapping():
    """CRQ regions map to correct Seerist AoI codes."""
    from tools.seerist_client import REGION_AOI_MAP
    assert REGION_AOI_MAP["APAC"] == "APAC"
    assert REGION_AOI_MAP["AME"] == "AMER"
    assert REGION_AOI_MAP["LATAM"] == "AMER"
    assert REGION_AOI_MAP["MED"] == "MENA"
    assert REGION_AOI_MAP["NCE"] == "EURC"


def test_region_countries():
    """Each CRQ region has country codes for Pulse/Scribe."""
    from tools.seerist_client import REGION_COUNTRIES
    assert "CN" in REGION_COUNTRIES["APAC"]
    assert "TW" in REGION_COUNTRIES["APAC"]
    assert "US" in REGION_COUNTRIES["AME"]
    assert "BR" in REGION_COUNTRIES["LATAM"]
    assert "EG" in REGION_COUNTRIES["MED"]
    assert "DE" in REGION_COUNTRIES["NCE"]


def test_client_uses_x_api_key():
    """Auth must use x-api-key header, NOT Bearer."""
    with patch.dict("os.environ", {"SEERIST_API_KEY": "test-key-123"}):
        from tools.seerist_client import SeeristClient
        client = SeeristClient()
        assert client._client.headers["x-api-key"] == "test-key-123"
        assert "Authorization" not in client._client.headers


def test_client_none_without_key():
    """Client creation returns None when no API key set, ignoring parent .env files."""
    with patch.dict("os.environ", {}, clear=True), patch("dotenv.load_dotenv", lambda *args, **kwargs: False):
        import importlib
        import tools.seerist_client as mod
        importlib.reload(mod)
        assert mod.SeeristClient.create() is None


def test_base_url():
    """Base URL matches Seerist API reference."""
    from tools.seerist_client import BASE_URL
    assert BASE_URL == "https://app.seerist.com/hyperionapi/"


def test_normalize_event():
    """GeoJSON feature normalizes to pipeline signal schema."""
    from tools.seerist_client import _normalize_event
    feature = {
        "properties": {
            "name": "Labor unrest at port",
            "eventType": "Unrest",
            "severity": 6,
            "sourcesCount": 12,
            "publishDate": "2026-04-09T14:00:00.000Z",
            "sourceMetadataReliability": "high",
        },
        "geometry": {
            "type": "Point",
            "coordinates": [121.47, 31.23]
        }
    }
    result = _normalize_event(feature, "APAC", 1)
    assert result["signal_id"] == "seerist:events_ai:apac-001"
    assert result["title"] == "Labor unrest at port"
    assert result["severity"] == 6
    assert result["location"]["lon"] == 121.47
    assert result["location"]["lat"] == 31.23
    assert result["source_reliability"] == "high"
    assert result["verified"] is False


def test_filter_keeps_clusters_lowercase_iso2():
    """/v2/clusters returns location_metadata.countryCode lowercase (e.g. 'tr')."""
    from tools.seerist_client import _filter_by_country
    feats = [
        {"properties": {"location_metadata": {"countryCode": "tr"}, "title": "Istanbul protest"}},
        {"properties": {"location_metadata": {"countryCode": "il"}, "title": "Israel event"}},
        {"properties": {"location_metadata": {"countryCode": "ma"}, "title": "Morocco event"}},
    ]
    out = _filter_by_country(feats, "MED")
    titles = [f["properties"]["title"] for f in out]
    assert "Istanbul protest" in titles
    assert "Morocco event" in titles
    assert "Israel event" not in titles


def test_filter_keeps_wod_iso3_uppercase():
    """/v1/wod returns properties.countryCode uppercase ISO-3 (e.g. 'ITA')."""
    from tools.seerist_client import _filter_by_country
    feats = [
        {"properties": {"countryCode": "ITA", "title": "Italy verified event"}},
        {"properties": {"countryCode": "PSE", "title": "Palestine verified"}},
        {"properties": {"countryCode": "ESP", "title": "Spain verified"}},
    ]
    out = _filter_by_country(feats, "MED")
    titles = [f["properties"]["title"] for f in out]
    assert "Italy verified event" in titles
    assert "Spain verified" in titles
    assert "Palestine verified" not in titles


def test_filter_passes_through_when_no_filter_set():
    """APAC/AME use full AoI — no country filter applied."""
    from tools.seerist_client import _filter_by_country
    feats = [{"properties": {"countryCode": "ZZZ"}}]
    assert _filter_by_country(feats, "APAC") == feats
    assert _filter_by_country(feats, "AME") == feats


def test_filter_handles_missing_country_data():
    """Features with no country info anywhere get dropped (not crash)."""
    from tools.seerist_client import _filter_by_country
    feats = [
        {"properties": {"title": "no country"}},
        {"properties": {"location_metadata": {}, "title": "empty meta"}},
        {"properties": {"location_metadata": "not-a-dict", "title": "bad meta type"}},
    ]
    out = _filter_by_country(feats, "MED")
    assert out == []
