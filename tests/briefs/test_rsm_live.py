"""Integration test: load_rsm_data returns a valid RsmBriefData for MED."""
from __future__ import annotations
from tools.briefs.data.rsm import load_rsm_data
from tools.briefs.models import RsmBriefData


def test_load_rsm_data_med_returns_valid_model():
    data, _ = load_rsm_data("MED")
    assert isinstance(data, RsmBriefData)
    assert data.cover.title.startswith("AeroGrid")
    assert "MED" in data.cover.title
    assert isinstance(data.sites, list)
    assert len(data.sites) >= 1


def test_load_rsm_data_med_has_cover_meta():
    data, _ = load_rsm_data("MED")
    from datetime import date
    assert data.cover.issued_at == date.today()


def test_load_rsm_data_med_sites_have_computed():
    data, _ = load_rsm_data("MED")
    for block in data.sites:
        assert block.computed is not None
        assert block.narrative.standing_notes_synthesis is None


def test_load_rsm_data_apac_returns_valid_model():
    data, _ = load_rsm_data("APAC")
    assert isinstance(data, RsmBriefData)
    assert "APAC" in data.cover.title
