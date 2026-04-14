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
