"""Tests for tools/rsm_dispatcher.py — Phase L"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import tools.rsm_dispatcher as rd


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(rd, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(rd, "ROUTING_PATH", tmp_path / "output" / "routing_decisions.json")


def _write_routing(tmp_path, decisions):
    out = tmp_path / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "routing_decisions.json").write_text(json.dumps({
        "generated_at": "2026-03-20T05:00:00Z",
        "decisions": decisions
    }), encoding="utf-8")


def test_no_triggered_decisions_exits_cleanly(monkeypatch, tmp_path):
    """No triggered decisions → no agent calls, exits 0."""
    _patch(monkeypatch, tmp_path)
    _write_routing(tmp_path, [
        {"audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
         "triggered": False, "trigger_reason": "", "formatter_agent": "rsm-formatter-agent",
         "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": False}
    ])
    called = []
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: called.append(d))
    rd.dispatch(mock=True)
    assert len(called) == 0


def test_triggered_decision_calls_formatter(monkeypatch, tmp_path):
    """Triggered decision → formatter invoked once."""
    _patch(monkeypatch, tmp_path)
    decision = {
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "trigger_reason": "weekly cadence",
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": False
    }
    _write_routing(tmp_path, [decision])
    called = []
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: called.append(d["audience"]))
    monkeypatch.setattr(rd, "_invoke_notifier", lambda mock: None)
    rd.dispatch(mock=True)
    assert called == ["rsm_apac"]


def test_already_delivered_skipped(monkeypatch, tmp_path):
    """Decision with delivered=true is skipped."""
    _patch(monkeypatch, tmp_path)
    decision = {
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "trigger_reason": "weekly cadence",
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": True
    }
    _write_routing(tmp_path, [decision])
    called = []
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: called.append(d))
    rd.dispatch(mock=True)
    assert len(called) == 0


def test_missing_routing_file_exits_gracefully(monkeypatch, tmp_path):
    """No routing_decisions.json → exits 0, no crash."""
    _patch(monkeypatch, tmp_path)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    # Don't write routing file
    rd.dispatch(mock=True)  # Should not raise


def test_dispatch_marks_delivered(monkeypatch, tmp_path):
    """After formatter succeeds, decision is marked delivered=true in routing file."""
    _patch(monkeypatch, tmp_path)
    decision = {
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "trigger_reason": "weekly cadence",
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/apac/rsm_brief_apac_2026-03-20.md", "delivered": False
    }
    _write_routing(tmp_path, [decision])
    monkeypatch.setattr(rd, "_invoke_formatter", lambda d, mock: None)
    monkeypatch.setattr(rd, "_invoke_notifier", lambda mock: None)
    rd.dispatch(mock=True)
    updated = json.loads((tmp_path / "output" / "routing_decisions.json").read_text())
    assert updated["decisions"][0]["delivered"] is True
