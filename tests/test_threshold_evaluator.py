"""Tests for tools/threshold_evaluator.py — Phase L"""
import json
from pathlib import Path
from datetime import datetime
import pytest
import tools.threshold_evaluator as te


INLINE_AUDIENCE_CONFIG = {
    "rsm_apac": {
        "label": "APAC RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["APAC"],
        "products": {
            "weekly_intsum": {"cadence": "monday", "time_local": "07:00", "timezone": "Asia/Singapore"},
            "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}
        },
        "delivery": {"channel": "email", "recipients": ["rsm-apac@aerowind.com"]}
    },
    "rsm_ame": {
        "label": "AME RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["AME"],
        "products": {
            "weekly_intsum": {"cadence": "monday", "time_local": "07:00", "timezone": "America/New_York"},
            "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}
        },
        "delivery": {"channel": "email", "recipients": ["rsm-ame@aerowind.com"]}
    },
    "rsm_latam": {"label": "LATAM RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["LATAM"], "products": {"weekly_intsum": {"cadence": "monday"}, "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}}, "delivery": {"channel": "email", "recipients": []}},
    "rsm_med": {"label": "MED RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["MED"], "products": {"weekly_intsum": {"cadence": "monday"}, "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}}, "delivery": {"channel": "email", "recipients": []}},
    "rsm_nce": {"label": "NCE RSM", "formatter_agent": "rsm-formatter-agent", "regions": ["NCE"], "products": {"weekly_intsum": {"cadence": "monday"}, "flash": {"threshold": {"hotspot_score_min": 0.85, "site_proximity_km": 100, "event_severity_min": 4, "categories": ["Conflict", "Terrorism", "Unrest"]}}}, "delivery": {"channel": "email", "recipients": []}},
}
INLINE_SITES = {"sites": [
    {"name": "Kaohsiung Manufacturing Hub", "region": "APAC", "country": "TW", "lat": 22.62, "lon": 120.30, "type": "manufacturing"},
    {"name": "Houston Operations Center", "region": "AME", "country": "US", "lat": 29.76, "lon": -95.37, "type": "service"},
    {"name": "Sao Paulo Service Hub", "region": "LATAM", "country": "BR", "lat": -23.55, "lon": -46.63, "type": "service"},
    {"name": "Palermo Offshore Ops", "region": "MED", "country": "IT", "lat": 38.12, "lon": 13.36, "type": "manufacturing"},
    {"name": "Hamburg Manufacturing Hub", "region": "NCE", "country": "DE", "lat": 53.55, "lon": 10.00, "type": "manufacturing"},
]}


def _patch(monkeypatch, tmp_path):
    audience_path = tmp_path / "data" / "audience_config.json"
    sites_path = tmp_path / "data" / "aerowind_sites.json"
    audience_path.parent.mkdir(parents=True, exist_ok=True)
    audience_path.write_text(json.dumps(INLINE_AUDIENCE_CONFIG), encoding="utf-8")
    sites_path.write_text(json.dumps(INLINE_SITES), encoding="utf-8")
    routing_path = tmp_path / "output" / "routing_decisions.json"
    routing_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(te, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(te, "AUDIENCE_CONFIG_PATH", audience_path)
    monkeypatch.setattr(te, "SITES_PATH", sites_path)
    monkeypatch.setattr(te, "_ROUTING_PATH", routing_path)


def _write_seerist(tmp_path, region, events=None, hotspots=None, pulse_score=70):
    p = tmp_path / "output" / "regional" / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    data = {
        "region": region,
        "pulse": {"score": pulse_score, "score_prev": pulse_score, "delta": 0, "security_risk": "Low", "political_risk": "Low"},
        "events": events or [],
        "hotspots": hotspots or [],
        "collected_at": "2026-03-20T05:00:00Z"
    }
    (p / "seerist_signals.json").write_text(json.dumps(data), encoding="utf-8")


def _write_delta(tmp_path, region, events_new=None, hotspots_new=None):
    p = tmp_path / "output" / "regional" / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    data = {
        "region": region, "period_from": "2026-03-13T05:00:00Z", "period_to": "2026-03-20T05:00:00Z",
        "pulse_delta": 0, "events_new": events_new or [], "events_resolved": [],
        "hotspots_new": hotspots_new or [], "hotspots_resolved": []
    }
    (p / "region_delta.json").write_text(json.dumps(data), encoding="utf-8")


def test_weekly_intsum_always_triggered(monkeypatch, tmp_path):
    """weekly_intsum product is always triggered (cadence-based)."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=True)
    out = tmp_path / "output" / "routing_decisions.json"
    decisions = json.loads(out.read_text())["decisions"]
    weekly = [d for d in decisions if d["product"] == "weekly_intsum" and d["triggered"]]
    assert len(weekly) == 5  # one per RSM audience


def test_flash_triggered_by_hotspot_score(monkeypatch, tmp_path):
    """Hotspot score >= 0.85 near AeroGrid site triggers flash for APAC RSM."""
    _patch(monkeypatch, tmp_path)
    # Kaohsiung hotspot — 0km from AeroGrid Kaohsiung Manufacturing Hub
    hotspot = {
        "hotspot_id": "h1", "location": {"name": "Kaohsiung, TW", "country_code": "TW"},
        "deviation_score": 0.90, "category_hint": "Unrest", "detected_at": "2026-03-19T14:00:00Z",
        "lat": 22.62, "lon": 120.30
    }
    _write_seerist(tmp_path, "APAC", hotspots=[hotspot])
    _write_delta(tmp_path, "APAC", hotspots_new=[hotspot])
    for r in ["AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 1
    assert "hotspot" in flash_decisions[0]["trigger_reason"].lower()


def test_flash_not_triggered_below_threshold(monkeypatch, tmp_path):
    """Hotspot score < 0.85 does NOT trigger flash."""
    _patch(monkeypatch, tmp_path)
    hotspot = {
        "hotspot_id": "h2", "location": {"name": "Kaohsiung, TW", "country_code": "TW"},
        "deviation_score": 0.70, "category_hint": "Unrest", "detected_at": "2026-03-19T14:00:00Z",
        "lat": 22.62, "lon": 120.30
    }
    _write_seerist(tmp_path, "APAC", hotspots=[hotspot])
    _write_delta(tmp_path, "APAC", hotspots_new=[hotspot])
    for r in ["AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 0


def test_flash_triggered_by_high_severity_event(monkeypatch, tmp_path):
    """EventsAI severity >= 4 in trigger categories fires flash."""
    _patch(monkeypatch, tmp_path)
    event = {
        "event_id": "e1", "category": "Unrest", "severity": 4,
        "title": "Major unrest near Kaohsiung",
        "location": {"name": "Kaohsiung, TW", "lat": 22.62, "lon": 120.30, "country_code": "TW"},
        "timestamp": "2026-03-19T08:00:00Z", "verified": True, "source_count": 8
    }
    _write_seerist(tmp_path, "APAC", events=[event])
    _write_delta(tmp_path, "APAC", events_new=[event])
    for r in ["AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 1


def test_flash_triggered_by_direct_cyber_targeting(monkeypatch, tmp_path):
    """osint_signals.json with aerowind_targeted=true triggers flash for that region's RSM."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    # Write osint_signals.json for APAC with direct AeroGrid targeting flag
    osint_dir = tmp_path / "output" / "regional" / "apac"
    osint_dir.mkdir(parents=True, exist_ok=True)
    (osint_dir / "osint_signals.json").write_text(json.dumps({
        "region": "APAC", "aerowind_targeted": True, "threats": [
            {"type": "phishing", "target": "AeroGrid supply chain", "severity": "HIGH"}
        ]
    }), encoding="utf-8")
    te.evaluate(force_weekly=False)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    flash_decisions = [d for d in decisions if d["product"] == "flash" and d["triggered"] and d["audience"] == "rsm_apac"]
    assert len(flash_decisions) == 1
    assert "cyber" in flash_decisions[0]["trigger_reason"].lower()


def test_routing_decisions_has_brief_path(monkeypatch, tmp_path):
    """Every triggered decision includes a brief_path field."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=True)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    for d in [x for x in decisions if x["triggered"]]:
        assert "brief_path" in d, f"Missing brief_path in: {d}"
        assert d["brief_path"].endswith(".md")


def test_delivered_flag_is_false(monkeypatch, tmp_path):
    """All new decisions have delivered=false."""
    _patch(monkeypatch, tmp_path)
    for r in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        _write_seerist(tmp_path, r)
        _write_delta(tmp_path, r)
    te.evaluate(force_weekly=True)
    decisions = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())["decisions"]
    for d in [x for x in decisions if x["triggered"]]:
        assert d["delivered"] is False
