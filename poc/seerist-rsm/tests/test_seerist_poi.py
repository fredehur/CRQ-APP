"""POI proximity — per-site haversine grouping tests."""
import json
from unittest.mock import MagicMock, patch

from tools import seerist_collector


def _feature(lon, lat, title="evt", severity=3):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "title": title,
            "severity": severity,
            "countryCode": "ITA",
            "publishDate": "2026-05-17T00:00:00Z",
            "sourcesCount": 4,
        },
    }


def test_poi_alerts_group_events_to_nearest_site(monkeypatch):
    """Two MED sites + two events, one near each. Each alert references its
    own site and only its own matching events."""
    sites = {"sites": [
        {"site_id": "med-pal", "name": "Palermo", "region": "MED",
         "lat": 38.13, "lon": 13.34, "poi_radius_km": 50,
         "criticality": "crown_jewel", "personnel": 120, "expat_count": 8},
        {"site_id": "med-mal", "name": "Malaga", "region": "MED",
         "lat": 36.72, "lon": -4.42, "poi_radius_km": 50,
         "criticality": "tier_one", "personnel": 85, "expat_count": 4},
    ]}
    monkeypatch.setattr("pathlib.Path.read_text",
                        lambda self, **kw: json.dumps(sites))

    fake_client = MagicMock()
    fake_client.get_pulse.return_value = {}
    fake_client.get_events.return_value = []
    fake_client.get_verified_events.return_value = []
    fake_client.get_breaking_events.return_value = []
    fake_client.get_news.return_value = []
    fake_client.get_hotspots.return_value = []
    fake_client.get_analysis_reports.return_value = []
    fake_client.get_risk_ratings.return_value = {}
    fake_client.search_poi.return_value = [
        _feature(13.35, 38.14, "near_palermo"),   # ~1km from Palermo
        _feature(-4.40, 36.73, "near_malaga"),    # ~2km from Malaga
    ]
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None

    # NOTE: _live_collect imports SeeristClient INSIDE the function, so patching
    # `seerist_collector.SeeristClient` does not intercept the import — patch on
    # the source module instead.
    with patch("tools.seerist_client.SeeristClient.create", return_value=fake_client), \
         patch("tools.seerist_client.REGION_COUNTRIES",
               {"MED": ["IT", "ES", "GR", "TR", "MA", "EG"]}):
        result = seerist_collector._live_collect("MED", window_days=1)

    alerts = result["poi_alerts"]
    assert {a["facility"] for a in alerts} == {"Palermo", "Malaga"}

    palermo = next(a for a in alerts if a["facility"] == "Palermo")
    malaga = next(a for a in alerts if a["facility"] == "Malaga")

    assert any(e["title"] == "near_palermo" for e in palermo["matching_events"])
    assert not any(e["title"] == "near_malaga" for e in palermo["matching_events"])
    assert any(e["title"] == "near_malaga" for e in malaga["matching_events"])

    assert 0 < palermo["nearest_event_km"] < 5
    assert 0 < malaga["nearest_event_km"] < 5


def test_poi_events_below_severity_2_filtered_out(monkeypatch):
    """Site with two in-radius events: severity=1 (filtered) and severity=4 (kept).
    matching_events contains only the severity=4 event; nearest_event_km reflects it."""
    sites = {"sites": [
        {"site_id": "med-pal", "name": "Palermo", "region": "MED",
         "lat": 38.13, "lon": 13.34, "poi_radius_km": 50,
         "criticality": "crown_jewel", "personnel": 120, "expat_count": 8},
    ]}
    monkeypatch.setattr("pathlib.Path.read_text",
                        lambda self, **kw: json.dumps(sites))

    fake_client = MagicMock()
    fake_client.get_pulse.return_value = {}
    fake_client.get_events.return_value = []
    fake_client.get_verified_events.return_value = []
    fake_client.get_breaking_events.return_value = []
    fake_client.get_news.return_value = []
    fake_client.get_hotspots.return_value = []
    fake_client.get_analysis_reports.return_value = []
    fake_client.get_risk_ratings.return_value = {}
    # severity=1 is ~1km away (should be filtered); severity=4 is ~3km away (should appear)
    fake_client.search_poi.return_value = [
        _feature(13.35, 38.14, "low_sev", severity=1),   # ~1km — filtered
        _feature(13.37, 38.15, "high_sev", severity=4),  # ~3km — kept
    ]
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None

    with patch("tools.seerist_client.SeeristClient.create", return_value=fake_client), \
         patch("tools.seerist_client.REGION_COUNTRIES",
               {"MED": ["IT", "ES", "GR", "TR", "MA", "EG"]}):
        result = seerist_collector._live_collect("MED", window_days=1)

    alerts = result["poi_alerts"]
    assert len(alerts) == 1
    palermo = alerts[0]
    assert len(palermo["matching_events"]) == 1
    assert palermo["matching_events"][0]["title"] == "high_sev"
    assert palermo["matching_events"][0]["severity"] == 4
    # nearest_event_km must reflect the severity=4 event, not the filtered severity=1
    assert palermo["nearest_event_km"] is not None
    assert palermo["nearest_event_km"] > 1.0  # the 1km event was filtered out


def test_poi_alert_with_no_nearby_events_records_zero(monkeypatch):
    """Site with no events inside its radius still gets an alert row — with
    empty matching_events and nearest_event_km=None (sentinel)."""
    sites = {"sites": [
        {"site_id": "med-cas", "name": "Casablanca", "region": "MED",
         "lat": 33.57, "lon": -7.59, "poi_radius_km": 50,
         "criticality": "tier_two", "personnel": 40, "expat_count": 2},
    ]}
    monkeypatch.setattr("pathlib.Path.read_text",
                        lambda self, **kw: json.dumps(sites))

    fake_client = MagicMock()
    fake_client.get_pulse.return_value = {}
    fake_client.get_events.return_value = []
    fake_client.get_verified_events.return_value = []
    fake_client.get_breaking_events.return_value = []
    fake_client.get_news.return_value = []
    fake_client.get_hotspots.return_value = []
    fake_client.get_analysis_reports.return_value = []
    fake_client.get_risk_ratings.return_value = {}
    # Event 1000km from Casablanca — outside the 50km radius
    fake_client.search_poi.return_value = [_feature(13.35, 38.14, "far_away")]
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = None

    # NOTE: _live_collect imports SeeristClient INSIDE the function, so patching
    # `seerist_collector.SeeristClient` does not intercept the import — patch on
    # the source module instead.
    with patch("tools.seerist_client.SeeristClient.create", return_value=fake_client), \
         patch("tools.seerist_client.REGION_COUNTRIES",
               {"MED": ["IT", "ES", "GR", "TR", "MA", "EG"]}):
        result = seerist_collector._live_collect("MED", window_days=1)

    alerts = result["poi_alerts"]
    assert len(alerts) == 1
    assert alerts[0]["facility"] == "Casablanca"
    assert alerts[0]["matching_events"] == []
    assert alerts[0]["nearest_event_km"] is None
