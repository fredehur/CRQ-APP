"""Tests for tools/notifier.py — Phase L"""
import json
from pathlib import Path
import pytest
import tools.notifier as nt


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(nt, "OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(nt, "DELIVERY_LOG_PATH", tmp_path / "output" / "delivery_log.jsonl")
    monkeypatch.setattr(nt, "MOCK_DELIVERY_DIR", tmp_path / "output" / "mock_delivery")


def _write_routing(tmp_path, decisions):
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    path = tmp_path / "output" / "routing_decisions.json"
    path.write_text(json.dumps({"generated_at": "2026-03-20T05:00:00Z", "decisions": decisions}), encoding="utf-8")
    return path


def _write_brief(tmp_path, brief_path, content="Test brief content"):
    p = tmp_path / brief_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_mock_delivery_writes_to_mock_dir(monkeypatch, tmp_path):
    """--mock writes brief copy to mock_delivery/ instead of sending email."""
    _patch(monkeypatch, tmp_path)
    brief_rel = "output/regional/apac/rsm_brief_apac_2026-03-20.md"
    _write_brief(tmp_path, brief_rel, "AEROWIND // APAC INTSUM")
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_apac", "region": "APAC", "product": "weekly_intsum",
        "triggered": True, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": str(tmp_path / brief_rel),
    }])
    nt.notify(routing_path, mock=True)
    mock_dir = tmp_path / "output" / "mock_delivery"
    assert mock_dir.exists()
    files = list(mock_dir.glob("*.md"))
    assert len(files) == 1
    assert "AEROWIND" in files[0].read_text(encoding="utf-8")


def test_delivery_log_written(monkeypatch, tmp_path):
    """Each delivery attempt appends a JSONL record to delivery_log.jsonl."""
    _patch(monkeypatch, tmp_path)
    brief_rel = "output/regional/ame/rsm_brief_ame_2026-03-20.md"
    _write_brief(tmp_path, brief_rel, "AEROWIND // AME INTSUM")
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_ame", "region": "AME", "product": "weekly_intsum",
        "triggered": True, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": str(tmp_path / brief_rel),
    }])
    nt.notify(routing_path, mock=True)
    log_path = tmp_path / "output" / "delivery_log.jsonl"
    assert log_path.exists()
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["audience"] == "rsm_ame"
    assert entry["region"] == "AME"
    assert entry["product"] == "weekly_intsum"
    assert entry["status"] in ("delivered", "failed")
    assert "timestamp" in entry


def test_skips_not_triggered(monkeypatch, tmp_path):
    """Decisions with triggered=False are not delivered."""
    _patch(monkeypatch, tmp_path)
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_nce", "region": "NCE", "product": "weekly_intsum",
        "triggered": False, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": "output/regional/nce/rsm_brief_nce_2026-03-20.md",
    }])
    nt.notify(routing_path, mock=True)
    mock_dir = tmp_path / "output" / "mock_delivery"
    assert not mock_dir.exists() or len(list(mock_dir.glob("*.md"))) == 0


def test_missing_brief_file_logs_failed(monkeypatch, tmp_path):
    """Brief file missing → logs status=failed, does not crash."""
    _patch(monkeypatch, tmp_path)
    routing_path = _write_routing(tmp_path, [{
        "audience": "rsm_latam", "region": "LATAM", "product": "flash",
        "triggered": True, "delivered": False,
        "formatter_agent": "rsm-formatter-agent",
        "brief_path": str(tmp_path / "output" / "regional" / "latam" / "rsm_flash_does_not_exist.md"),
    }])
    nt.notify(routing_path, mock=True)
    log_path = tmp_path / "output" / "delivery_log.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["status"] == "failed"
    assert entry["error"] is not None
