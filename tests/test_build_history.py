"""Tests for tools/build_history.py — Phase J"""

import json
from pathlib import Path

import pytest

import tools.build_history as bh


# ── Helpers ────────────────────────────────────────────────────────────────

def _patch(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    history_file = tmp_path / "history.json"
    monkeypatch.setattr(bh, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(bh, "HISTORY_FILE", history_file)
    return runs_dir, history_file


def _write_manifest(runs_dir: Path, folder: str, manifest: dict) -> Path:
    run_dir = runs_dir / folder
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


def _write_data_json(run_dir: Path, region: str, data: dict) -> None:
    d = run_dir / "regional" / region.lower()
    d.mkdir(parents=True, exist_ok=True)
    (d / "data.json").write_text(json.dumps(data), encoding="utf-8")


# ── Tests ──────────────────────────────────────────────────────────────────

def test_empty_runs_dir(tmp_path, monkeypatch):
    """Empty runs dir → writes history.json with empty region lists, no crash."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    runs_dir.mkdir()
    bh.build_history()
    assert history_file.exists()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    assert "regions" in data
    assert "drift" in data
    for region in bh.KNOWN_REGIONS:
        assert data["regions"][region] == []


def test_manifest_only_fallback(tmp_path, monkeypatch):
    """Single run with no data.json → uses manifest fields, no crash."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    manifest = {
        "pipeline_id": "crq-test-001",
        "run_timestamp": "2026-03-10T08:00:00Z",
        "regions": {
            "AME": {"status": "escalated", "severity": "CRITICAL", "vacr_usd": 22000000},
        },
    }
    _write_manifest(runs_dir, "2026-03-10_080000Z", manifest)
    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    entry = data["regions"]["AME"][0]
    assert entry["run_id"] == "crq-test-001"
    assert entry["run_folder"] == "2026-03-10_080000Z"
    assert entry["severity"] == "CRITICAL"
    assert entry["vacr_usd"] == 22000000
    assert entry["status"] == "escalated"
    assert entry["timestamp"] == "2026-03-10T08:00:00Z"


def test_data_json_enrichment(tmp_path, monkeypatch):
    """data.json fields override manifest fallback values."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    manifest = {
        "pipeline_id": "crq-rich",
        "run_timestamp": "2026-03-16T17:00:00Z",
        "regions": {"AME": {"status": "escalated", "severity": "HIGH", "vacr_usd": 5000000}},
    }
    run_dir = _write_manifest(runs_dir, "2026-03-16_170000Z", manifest)
    _write_data_json(run_dir, "AME", {
        "status": "escalated",
        "severity": "CRITICAL",
        "severity_score": 3,
        "vacr_exposure_usd": 22000000,
        "primary_scenario": "Ransomware",
        "velocity": "accelerating",
        "dominant_pillar": "Cyber",
        "signal_type": "Event",
        "financial_rank": 1,
        "timestamp": "2026-03-16T17:07:35Z",
    })
    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    entry = data["regions"]["AME"][0]
    # data.json values win
    assert entry["severity"] == "CRITICAL"
    assert entry["vacr_usd"] == 22000000
    assert entry["primary_scenario"] == "Ransomware"
    assert entry["velocity"] == "accelerating"
    assert entry["dominant_pillar"] == "Cyber"
    assert entry["signal_type"] == "Event"
    assert entry["financial_rank"] == 1
    assert entry["timestamp"] == "2026-03-16T17:07:35Z"


def test_multiple_runs_sorted_chronologically(tmp_path, monkeypatch):
    """Multiple runs → per-region list sorted oldest→newest."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    _write_manifest(runs_dir, "2026-03-16_171249Z", {
        "pipeline_id": "crq-new", "run_timestamp": "2026-03-16T17:12:49Z",
        "regions": {"AME": {"status": "escalated", "severity": "HIGH", "vacr_usd": 18000000}},
    })
    _write_manifest(runs_dir, "2026-03-09_125038Z", {
        "pipeline_id": "crq-old", "run_timestamp": "2026-03-09T12:50:38Z",
        "regions": {"AME": {"status": "escalated", "severity": "CRITICAL", "vacr_usd": 22000000}},
    })
    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    entries = data["regions"]["AME"]
    assert len(entries) == 2
    assert entries[0]["run_id"] == "crq-old"
    assert entries[1]["run_id"] == "crq-new"


def test_severity_score_mapping(tmp_path, monkeypatch):
    """Severity strings map to correct numeric scores."""
    assert bh._severity_score("CRITICAL") == 3
    assert bh._severity_score("HIGH") == 2
    assert bh._severity_score("MEDIUM") == 1
    assert bh._severity_score("LOW") == 0
    assert bh._severity_score("") == 0
    assert bh._severity_score(None) == 0


def test_severity_score_in_output(tmp_path, monkeypatch):
    """severity_score field is correctly computed in output."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    _write_manifest(runs_dir, "2026-03-10_080000Z", {
        "pipeline_id": "crq-sev", "run_timestamp": "2026-03-10T08:00:00Z",
        "regions": {"APAC": {"status": "escalated", "severity": "HIGH", "vacr_usd": 18500000}},
    })
    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    assert data["regions"]["APAC"][0]["severity_score"] == 2


def test_drift_detection_same_scenario(tmp_path, monkeypatch):
    """3 runs with same scenario → drift entry with consecutive_runs=3."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    for i, folder in enumerate(["2026-03-10_000000Z", "2026-03-11_000000Z", "2026-03-12_000000Z"]):
        run_dir = _write_manifest(runs_dir, folder, {
            "pipeline_id": f"crq-{i}", "run_timestamp": f"2026-03-{10+i:02d}T00:00:00Z",
            "regions": {"AME": {"status": "escalated", "severity": "CRITICAL", "vacr_usd": 22000000}},
        })
        _write_data_json(run_dir, "AME", {
            "status": "escalated", "severity": "CRITICAL",
            "vacr_exposure_usd": 22000000, "primary_scenario": "Ransomware",
            "timestamp": f"2026-03-{10+i:02d}T00:00:00Z",
        })
    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    assert "AME" in data["drift"]
    assert data["drift"]["AME"]["consecutive_runs"] == 3
    assert data["drift"]["AME"]["current_scenario"] == "Ransomware"
    assert "3 consecutive runs" in data["drift"]["AME"]["note"]


def test_drift_not_triggered_for_single_run(tmp_path, monkeypatch):
    """1 run → no drift entry."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    run_dir = _write_manifest(runs_dir, "2026-03-10_000000Z", {
        "pipeline_id": "crq-solo", "run_timestamp": "2026-03-10T00:00:00Z",
        "regions": {"AME": {"status": "escalated", "severity": "CRITICAL", "vacr_usd": 22000000}},
    })
    _write_data_json(run_dir, "AME", {
        "status": "escalated", "severity": "CRITICAL",
        "vacr_exposure_usd": 22000000, "primary_scenario": "Ransomware",
        "timestamp": "2026-03-10T00:00:00Z",
    })
    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    assert "AME" not in data["drift"]


def test_drift_resets_on_scenario_change(tmp_path, monkeypatch):
    """2 runs same then 1 different → drift count is 1 (excluded)."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    scenarios = ["Ransomware", "Ransomware", "Insider misuse"]
    for i, (folder, scenario) in enumerate(zip(
        ["2026-03-10_000000Z", "2026-03-11_000000Z", "2026-03-12_000000Z"], scenarios
    )):
        run_dir = _write_manifest(runs_dir, folder, {
            "pipeline_id": f"crq-{i}", "run_timestamp": f"2026-03-{10+i:02d}T00:00:00Z",
            "regions": {"AME": {"status": "escalated", "severity": "CRITICAL", "vacr_usd": 22000000}},
        })
        _write_data_json(run_dir, "AME", {
            "status": "escalated", "severity": "CRITICAL",
            "vacr_exposure_usd": 22000000, "primary_scenario": scenario,
            "timestamp": f"2026-03-{10+i:02d}T00:00:00Z",
        })
    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    # Newest scenario is "Insider misuse" for only 1 run → excluded from drift
    assert "AME" not in data["drift"]


def test_corrupt_manifest_skipped(tmp_path, monkeypatch):
    """Corrupt manifest JSON is skipped gracefully; valid run still written."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    # Valid run
    _write_manifest(runs_dir, "2026-03-10_000000Z", {
        "pipeline_id": "crq-good", "run_timestamp": "2026-03-10T00:00:00Z",
        "regions": {"AME": {"status": "clear", "severity": "LOW", "vacr_usd": 0}},
    })
    # Corrupt run
    corrupt_dir = runs_dir / "2026-03-09_000000Z"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "run_manifest.json").write_text("{NOT VALID JSON", encoding="utf-8")

    bh.build_history()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    # Only 1 valid entry for AME
    assert len(data["regions"]["AME"]) == 1
    assert data["regions"]["AME"][0]["run_id"] == "crq-good"


def test_atomic_write(tmp_path, monkeypatch):
    """Output is valid JSON and no .tmp file left behind."""
    runs_dir, history_file = _patch(monkeypatch, tmp_path)
    runs_dir.mkdir()
    bh.build_history()
    assert history_file.exists()
    assert not history_file.with_suffix(".tmp").exists()
    # Must be parseable JSON
    data = json.loads(history_file.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
