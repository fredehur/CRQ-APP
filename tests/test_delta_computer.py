"""Tests for tools/delta_computer.py — Phase L"""
import json
from pathlib import Path
from datetime import datetime, timezone
import pytest
import tools.delta_computer as dc


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(dc, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(dc, "LATEST_ROOT", tmp_path / "latest")


def _write_seerist(base: Path, region: str, data: dict) -> Path:
    p = base / "regional" / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    f = p / "seerist_signals.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return f


SAMPLE_EVENT = {
    "event_id": "e1", "category": "Unrest", "severity": 4,
    "title": "Strike at Kaohsiung", "location": {"name": "Kaohsiung, TW", "country_code": "TW"},
    "timestamp": "2026-03-19T08:00:00Z", "verified": True, "source_count": 5
}
SAMPLE_HOTSPOT = {
    "hotspot_id": "h1", "location": {"name": "Taipei", "country_code": "TW"},
    "deviation_score": 0.87, "category_hint": "Unrest", "detected_at": "2026-03-19T14:00:00Z"
}


def test_cold_start_no_previous(monkeypatch, tmp_path):
    """No previous seerist_signals.json → empty delta, pulse_delta null, exits 0."""
    _patch(monkeypatch, tmp_path)
    current = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [SAMPLE_EVENT], "hotspots": [SAMPLE_HOTSPOT]}
    _write_seerist(tmp_path / "output", "APAC", current)
    # No latest dir → cold start
    dc.compute("APAC")
    out = tmp_path / "output" / "regional" / "apac" / "region_delta.json"
    assert out.exists()
    delta = json.loads(out.read_text(encoding="utf-8"))
    assert delta["pulse_delta"] is None
    assert delta["events_new"] == []
    assert delta["events_resolved"] == []
    assert delta["hotspots_new"] == []
    assert delta["hotspots_resolved"] == []


def test_new_event_detected(monkeypatch, tmp_path):
    """Event in current but not previous → appears in events_new."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [SAMPLE_EVENT], "hotspots": []}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert len(delta["events_new"]) == 1
    assert delta["events_new"][0]["event_id"] == "e1"
    assert delta["events_resolved"] == []


def test_resolved_event_detected(monkeypatch, tmp_path):
    """Event in previous but not current → appears in events_resolved."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [SAMPLE_EVENT], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert delta["events_new"] == []
    assert len(delta["events_resolved"]) == 1


def test_pulse_delta_computed(monkeypatch, tmp_path):
    """Pulse delta is current_score minus previous_score."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [], "hotspots": []}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert delta["pulse_delta"] == -7


def test_new_hotspot_detected(monkeypatch, tmp_path):
    """New hotspot in current → in hotspots_new."""
    _patch(monkeypatch, tmp_path)
    prev = {"region": "APAC", "pulse": {"score": 58, "delta": 0}, "events": [], "hotspots": []}
    curr = {"region": "APAC", "pulse": {"score": 51, "delta": -7}, "events": [], "hotspots": [SAMPLE_HOTSPOT]}
    _write_seerist(tmp_path / "latest", "APAC", prev)
    _write_seerist(tmp_path / "output", "APAC", curr)
    dc.compute("APAC")
    delta = json.loads((tmp_path / "output" / "regional" / "apac" / "region_delta.json").read_text())
    assert len(delta["hotspots_new"]) == 1
    assert delta["hotspots_new"][0]["hotspot_id"] == "h1"


def test_invalid_region_raises(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="invalid region"):
        dc.compute("INVALID")


def test_output_has_period_fields(monkeypatch, tmp_path):
    """Delta output includes period_from and period_to timestamps."""
    _patch(monkeypatch, tmp_path)
    curr = {"region": "NCE", "pulse": {"score": 81, "delta": 0}, "events": [], "hotspots": [], "collected_at": "2026-03-20T05:00:00Z"}
    _write_seerist(tmp_path / "output", "NCE", curr)
    dc.compute("NCE")
    delta = json.loads((tmp_path / "output" / "regional" / "nce" / "region_delta.json").read_text())
    assert "period_from" in delta
    assert "period_to" in delta
    assert delta["region"] == "NCE"
