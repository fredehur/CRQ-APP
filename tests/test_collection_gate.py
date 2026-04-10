"""Tests for collection_gate.py — seerist_strength and collection_lag fields."""
import json
import pytest
from pathlib import Path


def _write_osint(tmp_path, region="APAC", indicators=None):
    out = tmp_path / "output" / "regional" / region.lower()
    out.mkdir(parents=True, exist_ok=True)
    data = {"lead_indicators": indicators or []}
    (out / "osint_signals.json").write_text(json.dumps(data))


def _write_seerist(tmp_path, region="APAC", seerist_data=None):
    out = tmp_path / "output" / "regional" / region.lower()
    out.mkdir(parents=True, exist_ok=True)
    data = seerist_data or {
        "situational": {"events": [], "verified_events": [], "breaking_news": [], "news": []},
        "analytical": {"hotspots": [], "pulse": {"region_summary": {"avg_delta": 0.0}}},
    }
    (out / "seerist_signals.json").write_text(json.dumps(data))


def test_seerist_strength_high_written_when_hotspot_anomaly(tmp_path, monkeypatch):
    import tools.collection_gate as cg
    monkeypatch.setattr(cg, "REPO_ROOT", tmp_path)

    _write_osint(tmp_path, indicators=[
        {"pillar": "geo", "source_url": "http://x.com"},
        {"pillar": "geo", "source_url": "http://y.com"},
        {"pillar": "geo", "source_url": "http://z.com"},
        {"pillar": "cyber", "source_url": "http://a.com"},
        {"pillar": "cyber", "source_url": "http://b.com"},
        {"pillar": "cyber", "source_url": "http://c.com"},
    ])
    _write_seerist(tmp_path, seerist_data={
        "situational": {"events": [], "verified_events": [], "breaking_news": [], "news": []},
        "analytical": {
            "hotspots": [{"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True}],
            "pulse": {"region_summary": {"avg_delta": 0.0}},
        },
    })

    result = cg.check_collection_quality("APAC")
    assert result["seerist_strength"] == "high"
    assert result["collection_lag"]["detected"] is False


def test_seerist_strength_none_triggers_collection_lag(tmp_path, monkeypatch):
    import tools.collection_gate as cg
    monkeypatch.setattr(cg, "REPO_ROOT", tmp_path)

    _write_osint(tmp_path, indicators=[
        {"pillar": "geo", "source_url": "http://x.com"},
        {"pillar": "geo", "source_url": "http://y.com"},
        {"pillar": "geo", "source_url": "http://z.com"},
        {"pillar": "cyber", "source_url": "http://a.com"},
        {"pillar": "cyber", "source_url": "http://b.com"},
        {"pillar": "cyber", "source_url": "http://c.com"},
    ])
    _write_seerist(tmp_path)  # empty Seerist → strength=none

    result = cg.check_collection_quality("APAC")
    assert result["seerist_strength"] == "none"
    assert result["collection_lag"]["detected"] is True
    assert len(result["collection_lag"]["note"]) > 0


def test_collection_lag_false_when_seerist_none_but_no_osint(tmp_path, monkeypatch):
    import tools.collection_gate as cg
    monkeypatch.setattr(cg, "REPO_ROOT", tmp_path)

    _write_osint(tmp_path, indicators=[])  # no OSINT
    _write_seerist(tmp_path)               # no Seerist

    result = cg.check_collection_quality("APAC")
    assert result["seerist_strength"] == "none"
    assert result["collection_lag"]["detected"] is False


def test_collection_quality_json_contains_new_fields(tmp_path, monkeypatch):
    import tools.collection_gate as cg
    monkeypatch.setattr(cg, "REPO_ROOT", tmp_path)

    _write_osint(tmp_path)
    _write_seerist(tmp_path)

    cg.check_collection_quality("APAC")

    out = json.loads(
        (tmp_path / "output" / "regional" / "apac" / "collection_quality.json").read_text()
    )
    assert "seerist_strength" in out
    assert "collection_lag" in out
    assert "detected" in out["collection_lag"]
    assert "note" in out["collection_lag"]
