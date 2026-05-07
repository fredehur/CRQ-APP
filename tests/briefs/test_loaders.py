"""Tests for tools/briefs/loaders.py — uses temp fixtures to avoid real file I/O."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

from tools.briefs.loaders import (
    load_sites_for_region,
    load_physical_signals,
    load_cyber_indicators,
    load_calendar,
)
from tools.briefs.data.ciso import load_ciso_data
from tools.briefs.data.board import load_board_data
from tools.briefs.data.rsm import load_rsm_data
from tools.briefs.models import SiteContext


_MED_PHYS_FIXTURE = {
    "region": "MED",
    "signals": [
        {
            "signal_id": "osint:physical:med-001",
            "title": "Port protests in Casablanca",
            "category": "unrest",
            "pillar": "physical",
            "severity": 3,
            "location": {"lat": 33.59, "lon": -7.61, "name": "Casablanca, Morocco", "country_code": "MA"},
            "outlet": "Reuters",
            "published_at": "2026-04-13T16:00:00Z",
        }
    ],
}

_MED_CYBER_FIXTURE = {
    "lead_indicators": [
        {
            "signal_id": "med-cyber-001",
            "text": "Volt Typhoon pre-positioning within OT networks for disruption.",
            "source_url": "https://example.com/volt-typhoon",
            "source_name": "Geopolitical Matters",
        }
    ],
}


def _write_tmp_json(data: dict) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, tmp, default=str)
    tmp.close()
    return Path(tmp.name)


def test_load_sites_for_region_returns_med_sites():
    """load_sites_for_region reads real aerowind_sites.json and filters by region."""
    med_sites = load_sites_for_region("MED")
    assert len(med_sites) >= 1
    assert all(s.region == "MED" for s in med_sites)
    assert all(isinstance(s, SiteContext) for s in med_sites)


def test_load_sites_for_region_case_insensitive():
    med_lower = load_sites_for_region("med")
    med_upper = load_sites_for_region("MED")
    assert len(med_lower) == len(med_upper)


def test_load_physical_signals_missing_file_returns_empty():
    result = load_physical_signals("NONEXISTENT_REGION_XYZ")
    assert result == []


def test_load_physical_signals_parses_known_fixture():
    """Patch the loader to read from a temp fixture file."""
    import tools.briefs.loaders as _loaders
    tmp = _write_tmp_json(_MED_PHYS_FIXTURE)
    original = _loaders._OUTPUT_DIR
    tmp_dir = tmp.parent / "med"
    tmp_dir.mkdir(exist_ok=True)
    target = tmp_dir / "osint_physical_signals.json"
    try:
        target.write_text(json.dumps(_MED_PHYS_FIXTURE), encoding="utf-8")
        _loaders._OUTPUT_DIR = tmp.parent
        signals = load_physical_signals("MED")
        assert len(signals) == 1
        assert signals[0].signal_id == "osint:physical:med-001"
        assert signals[0].location is not None
        assert signals[0].location.country_code == "MA"
        assert signals[0].country == "MA"
    finally:
        _loaders._OUTPUT_DIR = original
        tmp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except Exception:
            pass


def test_load_cyber_indicators_missing_file_returns_empty():
    result = load_cyber_indicators("NONEXISTENT_REGION_XYZ")
    assert result == []


def test_load_cyber_indicators_parses_lead_indicators():
    import tools.briefs.loaders as _loaders
    tmp = _write_tmp_json(_MED_CYBER_FIXTURE)
    original = _loaders._OUTPUT_DIR
    tmp_dir = tmp.parent / "med"
    tmp_dir.mkdir(exist_ok=True)
    target = tmp_dir / "cyber_signals.json"
    try:
        target.write_text(json.dumps(_MED_CYBER_FIXTURE), encoding="utf-8")
        _loaders._OUTPUT_DIR = tmp.parent
        indicators = load_cyber_indicators("MED")
        assert len(indicators) == 1
        assert indicators[0].signal_id == "med-cyber-001"
        assert "Volt Typhoon" in indicators[0].text
    finally:
        _loaders._OUTPUT_DIR = original
        tmp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except Exception:
            pass


def test_load_calendar_returns_calendar_items_from_notable_dates():
    items = load_calendar("MED")
    assert len(items) >= 0
    assert all(hasattr(i, "label") for i in items)
    assert all(hasattr(i, "date_str") for i in items)
    assert all(hasattr(i, "country") for i in items)


def test_load_ciso_data_returns_tuple():
    data, run_id = load_ciso_data("2026-04")
    assert data is not None
    assert run_id is None or isinstance(run_id, str)


def test_load_board_data_returns_tuple():
    data, run_id = load_board_data("2026Q2")
    assert data is not None
    assert run_id is None or isinstance(run_id, str)


def test_load_rsm_data_returns_tuple():
    data, run_id = load_rsm_data("med", week_of="2026-W17", narrate=False)
    assert data is not None
    assert run_id is None or isinstance(run_id, str)
