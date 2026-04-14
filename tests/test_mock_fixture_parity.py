"""Every Seerist field used by the agent prompt must be present in every regional mock."""
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "data" / "mock_osint_fixtures"
REGIONS = ["apac", "ame", "latam", "med", "nce"]

REQUIRED_TOP = {"region", "collected_at", "collection_window", "situational", "analytical", "poi_alerts"}
REQUIRED_SITUATIONAL = {"events", "verified_events", "breaking_news", "news"}
REQUIRED_ANALYTICAL = {"pulse", "hotspots", "scribe", "wod_searches", "analysis_reports", "risk_ratings"}


@pytest.mark.parametrize("region", REGIONS)
def test_seerist_fixture_has_all_top_keys(region):
    data = json.loads((FIXTURES / f"{region}_seerist.json").read_text(encoding="utf-8"))
    assert REQUIRED_TOP.issubset(data.keys()), f"{region} missing {REQUIRED_TOP - data.keys()}"


@pytest.mark.parametrize("region", REGIONS)
def test_seerist_fixture_has_all_situational(region):
    data = json.loads((FIXTURES / f"{region}_seerist.json").read_text(encoding="utf-8"))
    assert REQUIRED_SITUATIONAL.issubset(data["situational"].keys())


@pytest.mark.parametrize("region", REGIONS)
def test_seerist_fixture_has_all_analytical(region):
    data = json.loads((FIXTURES / f"{region}_seerist.json").read_text(encoding="utf-8"))
    assert REQUIRED_ANALYTICAL.issubset(data["analytical"].keys())


@pytest.mark.parametrize("region", REGIONS)
def test_at_least_one_fixture_field_populated_per_new_field(region):
    """Don't accept all-empty arrays for the new fields — at least one region must have content."""
    pass


def test_at_least_one_region_populates_verified_events():
    counts = []
    for region in REGIONS:
        data = json.loads((FIXTURES / f"{region}_seerist.json").read_text(encoding="utf-8"))
        counts.append(len(data["situational"]["verified_events"]))
    assert sum(counts) > 0, "no region populates verified_events"


def test_at_least_one_region_populates_analysis_reports():
    counts = []
    for region in REGIONS:
        data = json.loads((FIXTURES / f"{region}_seerist.json").read_text(encoding="utf-8"))
        counts.append(len(data["analytical"]["analysis_reports"]))
    assert sum(counts) > 0, "no region populates analysis_reports"


def test_at_least_one_region_populates_risk_ratings():
    counts = []
    for region in REGIONS:
        data = json.loads((FIXTURES / f"{region}_seerist.json").read_text(encoding="utf-8"))
        counts.append(len(data["analytical"]["risk_ratings"]))
    assert sum(counts) > 0, "no region populates risk_ratings"


def test_at_least_one_region_populates_poi_alerts():
    counts = []
    for region in REGIONS:
        data = json.loads((FIXTURES / f"{region}_seerist.json").read_text(encoding="utf-8"))
        counts.append(len(data["poi_alerts"]))
    assert sum(counts) > 0, "no region populates poi_alerts"
