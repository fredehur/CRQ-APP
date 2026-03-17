"""Tests for tools/build_history.py"""

import json
import importlib
from pathlib import Path

import pytest

import tools.build_history as bh


def _write_manifest(runs_dir: Path, folder: str, manifest: dict) -> None:
    run_dir = runs_dir / folder
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _reload_with_paths(monkeypatch, runs_dir: Path, history_file: Path):
    """Redirect module-level path constants and reload."""
    monkeypatch.setattr(bh, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(bh, "HISTORY_FILE", history_file)


# ---------------------------------------------------------------------------
# Test 1 — empty runs dir
# ---------------------------------------------------------------------------

def test_empty_runs_dir(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    history_file = tmp_path / "history.json"

    _reload_with_paths(monkeypatch, runs_dir, history_file)

    bh.build_history()

    assert history_file.exists()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    assert data["run_count"] == 0
    assert "regions" in data
    # All known regions should be present with empty arrays
    for region in bh.KNOWN_REGIONS:
        assert region in data["regions"]
        assert data["regions"][region] == []


# ---------------------------------------------------------------------------
# Test 2 — single run produces correct schema
# ---------------------------------------------------------------------------

def test_single_run_produces_correct_schema(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    history_file = tmp_path / "history.json"

    manifest = {
        "pipeline_id": "crq-test-001",
        "run_timestamp": "2026-03-10T08:00:00Z",
        "total_vacr_exposure_usd": 44700000,
        "regions": {
            "APAC": {
                "status": "escalated",
                "severity": "HIGH",
                "vacr_usd": 18500000,
                "admiralty": "B2",
                "velocity": "stable",
                "dominant_pillar": "Geopolitical",
            },
            "AME": {
                "status": "escalated",
                "severity": "CRITICAL",
                "vacr_usd": 22000000,
                "admiralty": "A1",
                "velocity": "accelerating",
                "dominant_pillar": "Cyber",
            },
        },
    }
    _write_manifest(runs_dir, "2026-03-10_080000Z", manifest)
    _reload_with_paths(monkeypatch, runs_dir, history_file)

    bh.build_history()

    data = json.loads(history_file.read_text(encoding="utf-8"))

    # Top-level schema
    assert data["run_count"] == 1
    assert "generated_at" in data
    assert "regions" in data

    # APAC entry
    apac_entries = data["regions"]["APAC"]
    assert len(apac_entries) == 1
    entry = apac_entries[0]
    assert entry["timestamp"] == "2026-03-10T08:00:00Z"
    assert entry["pipeline_id"] == "crq-test-001"
    assert entry["severity"] == "HIGH"
    assert entry["vacr_usd"] == 18500000
    assert entry["status"] == "escalated"
    assert entry["admiralty"] == "B2"
    assert entry["velocity"] == "stable"
    assert entry["dominant_pillar"] == "Geopolitical"

    # AME entry
    assert len(data["regions"]["AME"]) == 1


# ---------------------------------------------------------------------------
# Test 3 — multiple runs sorted chronologically
# ---------------------------------------------------------------------------

def test_multiple_runs_sorted_chronologically(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    history_file = tmp_path / "history.json"

    older_manifest = {
        "pipeline_id": "crq-old",
        "run_timestamp": "2026-03-09T12:50:38Z",
        "regions": {
            "AME": {
                "status": "escalated",
                "severity": "CRITICAL",
                "vacr_usd": 22000000,
                "admiralty": "B2",
                "velocity": "stable",
                "dominant_pillar": "Cyber",
            }
        },
    }
    newer_manifest = {
        "pipeline_id": "crq-new",
        "run_timestamp": "2026-03-16T17:12:49Z",
        "regions": {
            "AME": {
                "status": "escalated",
                "severity": "HIGH",
                "vacr_usd": 18000000,
                "admiralty": "A1",
                "velocity": "improving",
                "dominant_pillar": "Cyber",
            }
        },
    }

    # Write newer folder first to ensure sorting is by folder name, not insertion order
    _write_manifest(runs_dir, "2026-03-16_171249Z", newer_manifest)
    _write_manifest(runs_dir, "2026-03-09_125038Z", older_manifest)

    _reload_with_paths(monkeypatch, runs_dir, history_file)

    bh.build_history()

    data = json.loads(history_file.read_text(encoding="utf-8"))
    ame_entries = data["regions"]["AME"]

    assert len(ame_entries) == 2
    # Oldest first
    assert ame_entries[0]["timestamp"] == "2026-03-09T12:50:38Z"
    assert ame_entries[0]["pipeline_id"] == "crq-old"
    assert ame_entries[1]["timestamp"] == "2026-03-16T17:12:49Z"
    assert ame_entries[1]["pipeline_id"] == "crq-new"


# ---------------------------------------------------------------------------
# Test 4 — missing region fields handled gracefully
# ---------------------------------------------------------------------------

def test_missing_region_fields_handled_gracefully(tmp_path, monkeypatch):
    runs_dir = tmp_path / "runs"
    history_file = tmp_path / "history.json"

    # Region entry deliberately missing admiralty, velocity, dominant_pillar
    manifest = {
        "pipeline_id": "crq-sparse",
        "run_timestamp": "2026-03-12T10:00:00Z",
        "regions": {
            "MED": {
                "status": "escalated",
                "severity": "MEDIUM",
                "vacr_usd": 4200000,
                # admiralty, velocity, dominant_pillar are absent
            }
        },
    }
    _write_manifest(runs_dir, "2026-03-12_100000Z", manifest)
    _reload_with_paths(monkeypatch, runs_dir, history_file)

    # Must not raise
    bh.build_history()

    data = json.loads(history_file.read_text(encoding="utf-8"))
    med_entries = data["regions"]["MED"]
    assert len(med_entries) == 1
    entry = med_entries[0]

    # Missing fields should default to empty string or falsy value, not raise
    assert entry["admiralty"] in ("", None)
    assert entry["velocity"] in ("", None)
    assert entry["dominant_pillar"] in ("", None)
    # Present fields should be correct
    assert entry["severity"] == "MEDIUM"
    assert entry["status"] == "escalated"
