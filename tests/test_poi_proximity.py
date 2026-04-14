"""Pure haversine + region filtering + sorting. No LLM."""
import json
from pathlib import Path
import pytest

from tools.poi_proximity import (
    haversine_km,
    compute_proximity,
    EVENTS_OUTSIDE_RELEVANCE_KM,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_haversine_known_distance_paris_london():
    # Paris (48.8566, 2.3522) → London (51.5074, -0.1278) ≈ 343.5 km
    d = haversine_km(48.8566, 2.3522, 51.5074, -0.1278)
    assert 340 < d < 350, f"got {d}"


def test_haversine_zero_for_identical_points():
    assert haversine_km(33.57, -7.59, 33.57, -7.59) == 0


def test_compute_proximity_med_returns_dict_with_expected_keys(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = compute_proximity("MED", fixtures_only=True)
    assert result["region"] == "MED"
    assert "events_by_site_proximity" in result
    assert "computed_at" in result


def test_med_casablanca_site_has_unrest_events_within_radius(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = compute_proximity("MED", fixtures_only=True)
    casa = next(
        s for s in result["events_by_site_proximity"]
        if s["site_id"] == "med-casablanca-ops"
    )
    assert len(casa["events_within_radius"]) >= 1
    assert all(e["distance_km"] <= casa["radius_km"] for e in casa["events_within_radius"])


def test_proximity_sorted_by_distance_ascending(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = compute_proximity("MED", fixtures_only=True)
    casa = next(
        s for s in result["events_by_site_proximity"]
        if s["site_id"] == "med-casablanca-ops"
    )
    distances = [e["distance_km"] for e in casa["events_within_radius"]]
    assert distances == sorted(distances)


def test_compute_proximity_only_returns_sites_in_region(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = compute_proximity("MED", fixtures_only=True)
    regions = {s["region"] for s in result["events_by_site_proximity"]}
    assert regions == {"MED"}


def test_compute_proximity_handles_empty_event_list(monkeypatch):
    """When a region has no events, every site still appears with empty event arrays."""
    monkeypatch.chdir(REPO_ROOT)
    result = compute_proximity("LATAM", fixtures_only=True)
    assert all(
        s["events_within_radius"] == [] and s["events_outside_radius_but_relevant"] == []
        for s in result["events_by_site_proximity"]
    )


def test_outside_radius_but_relevant_filters_to_const_km(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = compute_proximity("MED", fixtures_only=True)
    for site in result["events_by_site_proximity"]:
        for e in site["events_outside_radius_but_relevant"]:
            assert site["radius_km"] < e["distance_km"] <= EVENTS_OUTSIDE_RELEVANCE_KM
