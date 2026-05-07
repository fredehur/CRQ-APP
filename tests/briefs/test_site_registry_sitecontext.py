"""Task 5.2: Smoke test — every site in aerowind_sites.json parses as SiteContext."""
from __future__ import annotations
import json
from pathlib import Path

from tools.briefs.models import SiteContext


def test_every_site_parses_as_site_context():
    data = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
    assert "sites" in data, "aerowind_sites.json must have a 'sites' key"
    for raw_site in data["sites"]:
        sc = SiteContext.model_validate(raw_site)
        assert sc.coordinates.lat == raw_site["lat"]
        assert sc.coordinates.lon == raw_site["lon"]
        assert sc.seerist_poi_radius_km == raw_site["poi_radius_km"]
        assert sc.personnel.total == raw_site["personnel_count"]
        assert sc.personnel.expat == raw_site["expat_count"]
        assert sc.resolved_tier in ("crown_jewel", "primary", "secondary", "minor"), (
            f"site {raw_site['site_id']} resolved_tier={sc.resolved_tier!r} is invalid"
        )


def test_crown_jewel_sites_have_ot_stack_or_cyber_actors():
    """Crown-jewel manufacturing sites should have OT stack populated."""
    data = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
    for raw_site in data["sites"]:
        sc = SiteContext.model_validate(raw_site)
        if sc.resolved_tier == "crown_jewel" and sc.asset_type == "manufacturing":
            assert sc.ot_stack, (
                f"crown_jewel manufacturing site {sc.site_id} should have ot_stack populated"
            )


def test_criticality_drivers_non_empty_for_non_minor():
    """Non-minor sites must have criticality_drivers filled in."""
    data = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
    for raw_site in data["sites"]:
        sc = SiteContext.model_validate(raw_site)
        if sc.resolved_tier != "minor":
            assert sc.criticality_drivers.strip(), (
                f"site {sc.site_id} (tier={sc.resolved_tier}) has empty criticality_drivers"
            )


def test_country_lead_email_present():
    """Every site should have a country_lead with an email."""
    data = json.loads(Path("data/aerowind_sites.json").read_text(encoding="utf-8"))
    for raw_site in data["sites"]:
        sc = SiteContext.model_validate(raw_site)
        lead = sc.resolved_country_lead
        assert "email" in lead, f"site {sc.site_id} country_lead missing email key"
