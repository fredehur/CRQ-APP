"""Site registry invariants — schema, uniqueness, regional coverage."""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITES_PATH = REPO_ROOT / "data" / "aerowind_sites.json"
REQUIRED_FIELDS = {
    "site_id", "name", "region", "country", "lat", "lon",
    "type", "poi_radius_km", "personnel_count", "expat_count",
    "shift_pattern", "criticality", "produces",
    "dependencies", "feeds_into", "customer_dependencies",
    "previous_incidents", "site_lead", "duty_officer",
    "embassy_contact", "notable_dates",
}
ALL_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
VALID_CRITICALITY = {"crown_jewel", "major", "standard"}


def _load():
    return json.loads(SITES_PATH.read_text(encoding="utf-8"))["sites"]


def test_every_site_has_required_fields():
    for site in _load():
        missing = REQUIRED_FIELDS - set(site.keys())
        assert not missing, f"{site.get('site_id', '?')} missing {missing}"


def test_site_ids_are_unique():
    ids = [s["site_id"] for s in _load()]
    assert len(ids) == len(set(ids)), "duplicate site_id"


def test_no_duplicate_region_name_pairs():
    pairs = [(s["region"], s["name"]) for s in _load()]
    assert len(pairs) == len(set(pairs)), "duplicate (region, name)"


def test_every_region_has_at_least_one_site():
    regions = {s["region"] for s in _load()}
    assert ALL_REGIONS.issubset(regions), f"missing regions: {ALL_REGIONS - regions}"


def test_lat_lon_in_valid_range():
    for s in _load():
        assert -90 <= s["lat"] <= 90, f"{s['site_id']} bad lat"
        assert -180 <= s["lon"] <= 180, f"{s['site_id']} bad lon"


def test_criticality_is_valid_label():
    for s in _load():
        assert s["criticality"] in VALID_CRITICALITY, f"{s['site_id']} bad criticality"


def test_company_profile_no_longer_has_facilities():
    profile = json.loads(
        (REPO_ROOT / "data" / "company_profile.json").read_text(encoding="utf-8")
    )
    assert "facilities" not in profile, "facilities should be moved to aerowind_sites.json"


def test_site_registry_audit_exists():
    audit = REPO_ROOT / "data" / "site_registry_audit.json"
    assert audit.exists(), "site_registry_audit.json must exist"
    data = json.loads(audit.read_text(encoding="utf-8"))
    assert "mocked_fields" in data and "sourced_fields" in data
