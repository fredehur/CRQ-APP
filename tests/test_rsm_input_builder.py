"""rsm_input_builder — cadence param + new manifest blocks."""
import json
from pathlib import Path
import pytest

from tools.rsm_input_builder import build_rsm_inputs, manifest_summary

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def chdir_repo(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)


def test_build_accepts_cadence_param(chdir_repo):
    try:
        m = build_rsm_inputs("MED", cadence="daily")
        assert m["cadence"] == "daily"
    except FileNotFoundError:
        pytest.skip("MED required pipeline files absent — covered by integration test")


def test_manifest_includes_poi_proximity_block_when_present(chdir_repo):
    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    assert "poi_proximity" in m
    assert m["poi_proximity"] is None or isinstance(m["poi_proximity"], dict)


def test_manifest_includes_site_registry_filtered_to_region(chdir_repo):
    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    sites = m["site_registry"]
    assert isinstance(sites, list)
    assert all(s["region"] == "MED" for s in sites)


def test_manifest_includes_notable_dates_next_7_days(chdir_repo):
    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    assert "notable_dates" in m
    assert isinstance(m["notable_dates"], list)


def test_invalid_cadence_raises(chdir_repo):
    with pytest.raises(ValueError, match="cadence"):
        build_rsm_inputs("MED", cadence="hourly")


def test_manifest_summary_renders_cadence(chdir_repo):
    try:
        m = build_rsm_inputs("MED", cadence="weekly")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    summary = manifest_summary(m)
    assert "weekly" in summary.lower()


def test_required_inputs_missing_still_raises(chdir_repo):
    with pytest.raises(FileNotFoundError):
        build_rsm_inputs("MED", cadence="daily", output_dir="__nonexistent_dir__")


def test_manifest_includes_cyber_watchlist_when_present(chdir_repo, tmp_path, monkeypatch):
    """If data/cyber_watchlist.json exists, manifest includes it."""
    import tools.rsm_input_builder as rib

    wl_path = tmp_path / "cyber_watchlist.json"
    wl_path.write_text(json.dumps({
        "threat_actor_groups": [{"name": "APT40", "motivation": "espionage"}],
        "sector_targeting_campaigns": [],
        "cve_watch_categories": ["ICS/SCADA"],
        "global_cyber_geographies_of_concern": ["China"],
    }), encoding="utf-8")

    # monkeypatch the module-level constant that Task B1 will add
    monkeypatch.setattr(rib, "WATCHLIST_FILE", wl_path)

    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    assert "cyber_watchlist" in m
    assert m["cyber_watchlist"] is not None
    assert m["cyber_watchlist"]["threat_actor_groups"][0]["name"] == "APT40"


def test_manifest_cyber_watchlist_none_when_absent(chdir_repo, tmp_path, monkeypatch):
    """Missing watchlist file → manifest['cyber_watchlist'] is None."""
    import tools.rsm_input_builder as rib
    monkeypatch.setattr(rib, "WATCHLIST_FILE", tmp_path / "nonexistent.json")
    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    assert m["cyber_watchlist"] is None


def test_manifest_summary_mentions_watchlist_when_present(chdir_repo, tmp_path, monkeypatch):
    """manifest_summary surfaces actor/campaign counts."""
    import tools.rsm_input_builder as rib

    wl_path = tmp_path / "cyber_watchlist.json"
    wl_path.write_text(json.dumps({
        "threat_actor_groups": [{"name": "APT40"}, {"name": "Volt Typhoon"}],
        "sector_targeting_campaigns": [{"campaign_name": "VOLT ICS"}],
        "cve_watch_categories": ["ICS/SCADA"],
    }), encoding="utf-8")
    monkeypatch.setattr(rib, "WATCHLIST_FILE", wl_path)

    try:
        m = build_rsm_inputs("MED", cadence="daily")
    except FileNotFoundError:
        pytest.skip("MED pipeline not populated")
    summary = manifest_summary(m)
    assert "watchlist" in summary.lower()
    assert "APT40" in summary or "2" in summary  # actor count or name
