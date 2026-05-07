from __future__ import annotations

import types
from datetime import date, datetime, timedelta, timezone

import pytest

from tools.briefs.joins import (
    actor_hits,
    calendar_ahead,
    haversine_km,
    pattern_hits,
    proximity_hits,
)
from tools.briefs.models import Coordinates, SiteContext


# ---- fixtures ----

def _minimal_site(
    lat: float = 33.57,
    lon: float = -7.59,
    radius: int = 50,
    country: str = "MA",
    relevant_attack_types: list[int] | None = None,
    relevant_seerist_categories: list[str] | None = None,
    threat_actors_of_interest: list[int] | None = None,
) -> SiteContext:
    return SiteContext.model_validate({
        "site_id": "test-site",
        "name": "Test Site",
        "region": "MED",
        "country": country,
        "lat": lat,
        "lon": lon,
        "type": "wind_farm",
        "subtype": None,
        "poi_radius_km": radius,
        "criticality": "major",
        "personnel_count": 50,
        "expat_count": 5,
        "site_lead": {"name": "Test Lead", "phone": "+1-555-0000"},
        "relevant_attack_types": relevant_attack_types or [],
        "relevant_seerist_categories": relevant_seerist_categories or [],
        "threat_actors_of_interest": threat_actors_of_interest or [],
    })


def _sig(
    signal_id: str,
    title: str,
    lat: float | None = None,
    lon: float | None = None,
    location_name: str | None = "somewhere",
    severity_int: int = 5,
    attack_type: int | None = None,
    category: str | None = None,
    perpetrator: int | None = None,
    country: str = "MA",
    published_days_ago: int = 5,
    include_location: bool = True,
):
    published = datetime.now(timezone.utc) - timedelta(days=published_days_ago)
    base = {
        "signal_id": signal_id,
        "title": title,
        "published_at": published,
        "severity": severity_int,
        "attack_type": attack_type,
        "category": category,
        "perpetrator": perpetrator,
        "country": country,
    }
    if include_location:
        base["location"] = types.SimpleNamespace(
            lat=lat if lat is not None else 0.0,
            lon=lon if lon is not None else 0.0,
            name=location_name,
        )
    return types.SimpleNamespace(**base)


def _cal_item(country: str, date_str: str, label: str):
    return types.SimpleNamespace(country=country, date_str=date_str, label=label)


# ---- haversine ----

def test_haversine_same_point_is_zero():
    p = Coordinates(lat=33.57, lon=-7.59)
    assert haversine_km(p, p) < 0.01


def test_haversine_casablanca_to_agadir():
    casablanca = Coordinates(lat=33.57, lon=-7.59)
    agadir = Coordinates(lat=30.42, lon=-9.60)
    km = haversine_km(casablanca, agadir)
    # Real-world distance is ~395-415 km
    assert 380 < km < 450


# ---- proximity_hits ----

def test_proximity_hits_includes_near_excludes_far():
    site = _minimal_site()  # Casablanca-ish, radius 50 km
    # ~10 km away (small lat bump)
    near = _sig("s-near", "Near event", lat=33.66, lon=-7.59, severity_int=7)
    # ~200 km south
    far = _sig("s-far", "Far event", lat=31.8, lon=-7.59, severity_int=7)

    result = proximity_hits(site, [near, far])
    ids = [e.signal_id for e in result]
    assert "s-near" in ids
    assert "s-far" not in ids


def test_proximity_hits_skips_no_location():
    site = _minimal_site()
    near_ok = _sig("s-ok", "Near OK", lat=33.66, lon=-7.59, severity_int=7)
    no_loc = _sig("s-noloc", "No loc", include_location=False, severity_int=9)

    result = proximity_hits(site, [no_loc, near_ok])
    ids = [e.signal_id for e in result]
    assert ids == ["s-ok"]


def test_proximity_hits_ranking():
    site = _minimal_site()
    # Both within 50km. Higher severity should come first.
    lower_sev = _sig("s-low", "Lower", lat=33.60, lon=-7.59, severity_int=5)  # medium
    higher_sev = _sig("s-high", "Higher", lat=33.70, lon=-7.59, severity_int=9)  # critical

    result = proximity_hits(site, [lower_sev, higher_sev])
    assert [e.signal_id for e in result] == ["s-high", "s-low"]
    assert result[0].severity == "critical"
    assert result[1].severity == "medium"


# ---- pattern_hits ----

def test_pattern_hits_by_attack_type():
    site = _minimal_site(relevant_attack_types=[14])
    sig = _sig(
        "p-at", "Attack-type match", lat=33.6, lon=-7.6,
        attack_type=14, severity_int=6, country="MA", published_days_ago=5,
    )
    result = pattern_hits(site, [sig])
    assert len(result) == 1
    assert result[0].signal_id == "p-at"
    assert result[0].join_reason == "pattern"
    assert result[0].distance_km is None


def test_pattern_hits_by_category():
    site = _minimal_site(relevant_seerist_categories=["civil_unrest"])
    sig = _sig(
        "p-cat", "Category match", lat=33.6, lon=-7.6,
        category="civil_unrest", severity_int=7, country="MA", published_days_ago=3,
    )
    result = pattern_hits(site, [sig])
    assert len(result) == 1
    assert result[0].signal_id == "p-cat"


def test_pattern_hits_wrong_country():
    site = _minimal_site(country="MA", relevant_attack_types=[14])
    sig = _sig(
        "p-wrong", "Wrong country", lat=33.6, lon=-7.6,
        attack_type=14, severity_int=6, country="FR", published_days_ago=5,
    )
    result = pattern_hits(site, [sig])
    assert result == []


def test_pattern_hits_too_old():
    site = _minimal_site(relevant_attack_types=[14])
    sig = _sig(
        "p-old", "Too old", lat=33.6, lon=-7.6,
        attack_type=14, severity_int=6, country="MA", published_days_ago=45,
    )
    result = pattern_hits(site, [sig])
    assert result == []


# ---- actor_hits ----

def test_actor_hits_matches_perpetrator():
    site = _minimal_site(threat_actors_of_interest=[42])
    sig = _sig(
        "a-match", "Actor hit", lat=33.6, lon=-7.6,
        perpetrator=42, severity_int=8,
    )
    result = actor_hits(site, [sig])
    assert len(result) == 1
    assert result[0].signal_id == "a-match"
    assert result[0].join_reason == "actor"
    assert result[0].distance_km is None
    assert result[0].severity == "critical"


def test_actor_hits_no_match():
    site = _minimal_site(threat_actors_of_interest=[42])
    sig = _sig(
        "a-nomatch", "Other actor", lat=33.6, lon=-7.6,
        perpetrator=99, severity_int=8,
    )
    sig_none = _sig(
        "a-none", "No actor", lat=33.6, lon=-7.6,
        perpetrator=None, severity_int=8,
    )
    result = actor_hits(site, [sig, sig_none])
    assert result == []


# ---- calendar_ahead ----

def test_calendar_ahead_includes_upcoming():
    ref = date(2026, 4, 21)
    site = _minimal_site(country="MA")
    event_date = (ref + timedelta(days=7)).isoformat()
    item = _cal_item("MA", event_date, "National Day")

    result = calendar_ahead(site, [item], horizon_days=14, reference_date=ref)
    assert len(result) == 1
    assert result[0].label == "National Day"
    assert result[0].horizon_days == 7


def test_calendar_ahead_excludes_past():
    ref = date(2026, 4, 21)
    site = _minimal_site(country="MA")
    event_date = (ref - timedelta(days=1)).isoformat()
    item = _cal_item("MA", event_date, "Yesterday")

    result = calendar_ahead(site, [item], horizon_days=14, reference_date=ref)
    assert result == []


def test_calendar_ahead_excludes_beyond_horizon():
    ref = date(2026, 4, 21)
    site = _minimal_site(country="MA")
    event_date = (ref + timedelta(days=20)).isoformat()
    item = _cal_item("MA", event_date, "Too far")

    result = calendar_ahead(site, [item], horizon_days=14, reference_date=ref)
    assert result == []


def test_calendar_ahead_wrong_country():
    ref = date(2026, 4, 21)
    site = _minimal_site(country="MA")
    event_date = (ref + timedelta(days=5)).isoformat()
    item = _cal_item("FR", event_date, "French holiday")

    result = calendar_ahead(site, [item], horizon_days=14, reference_date=ref)
    assert result == []
