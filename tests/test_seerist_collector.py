"""Tests for tools/seerist_collector.py — Phase L"""
import json
from pathlib import Path
import pytest
import tools.seerist_collector as sc


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(sc, "FIXTURES_DIR", Path("data/mock_osint_fixtures"))


def test_mock_mode_writes_seerist_signals(monkeypatch, tmp_path):
    """--mock reads fixture and writes seerist_signals.json."""
    _patch(monkeypatch, tmp_path)
    sc.collect("APAC", mock=True)
    out = tmp_path / "output" / "regional" / "apac" / "seerist_signals.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["region"] == "APAC"
    assert "pulse" in data
    assert "events" in data
    assert "hotspots" in data
    assert "collected_at" in data


def test_mock_all_regions(monkeypatch, tmp_path):
    """All 5 regions have fixtures and collect without error."""
    _patch(monkeypatch, tmp_path)
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        sc.collect(region, mock=True)
        out = tmp_path / "output" / "regional" / region.lower() / "seerist_signals.json"
        assert out.exists(), f"Missing seerist_signals.json for {region}"


def test_invalid_region_exits(monkeypatch, tmp_path):
    """Invalid region raises ValueError."""
    _patch(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="invalid region"):
        sc.collect("INVALID", mock=True)


def test_live_mode_without_key_falls_back_to_mock(monkeypatch, tmp_path):
    """No SEERIST_API_KEY → falls back to mock fixture, exits 0."""
    _patch(monkeypatch, tmp_path)
    monkeypatch.delenv("SEERIST_API_KEY", raising=False)
    sc.collect("LATAM", mock=False)
    out = tmp_path / "output" / "regional" / "latam" / "seerist_signals.json"
    assert out.exists()


def test_output_schema_keys(monkeypatch, tmp_path):
    """Output file contains all required schema keys."""
    _patch(monkeypatch, tmp_path)
    sc.collect("MED", mock=True)
    out = tmp_path / "output" / "regional" / "med" / "seerist_signals.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    for key in ["region", "window_days", "pulse", "events", "hotspots", "collected_at"]:
        assert key in data, f"Missing key: {key}"
    for key in ["score", "score_prev", "delta", "security_risk", "political_risk"]:
        assert key in data["pulse"], f"Missing pulse key: {key}"
