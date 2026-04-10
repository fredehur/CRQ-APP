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
    """Client creation returns None when no API key set."""
    with patch.dict("os.environ", {}, clear=True):
        import importlib
        import tools.seerist_client as mod
        importlib.reload(mod)
        # SeeristClient should raise or return None
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
