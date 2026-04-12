"""Tests for tools/feedback_summary.py — Phase I Feedback Aggregation."""

import json
import sys
from pathlib import Path

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_run(tmp_path: Path, folder_name: str, run_id: str, feedback: list | None = None) -> Path:
    """Create a fake run folder with optional feedback.json."""
    run_dir = tmp_path / "output" / "runs" / folder_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({"pipeline_id": run_id}), encoding="utf-8"
    )
    if feedback is not None:
        (run_dir / "feedback.json").write_text(
            json.dumps(feedback, ensure_ascii=False), encoding="utf-8"
        )
    return run_dir


def _run_summary(monkeypatch, tmp_path) -> dict:
    """Redirect REPO_ROOT and call build_summary()."""
    import tools.feedback_summary as fs
    monkeypatch.setattr(fs, "REPO_ROOT", tmp_path)
    return fs.build_summary()


def _run_main(monkeypatch, tmp_path, capsys) -> dict:
    """Run main() and return the written JSON."""
    import tools.feedback_summary as fs
    monkeypatch.setattr(fs, "REPO_ROOT", tmp_path)
    fs.main()
    out_path = tmp_path / "output" / "pipeline" / "feedback_trends.json"
    return json.loads(out_path.read_text(encoding="utf-8"))


# ── Tests ─────────────────────────────────────────────────────────────────

def test_no_runs_directory_writes_empty_summary(monkeypatch, tmp_path, capsys):
    """No output/runs/ directory → writes empty summary, exit 0."""
    result = _run_main(monkeypatch, tmp_path, capsys)

    assert result["total_runs_with_feedback"] == 0
    assert result["total_ratings"] == 0
    assert result["by_region"] == {}
    assert result["recent_notes"] == []
    assert "generated_at" in result

    captured = capsys.readouterr()
    assert "No feedback found" in captured.out


def test_runs_exist_but_no_feedback(monkeypatch, tmp_path):
    """Run folders exist but none have feedback.json → empty summary."""
    _make_run(tmp_path, "2026-03-16_100000Z", "crq-run-1")
    _make_run(tmp_path, "2026-03-16_110000Z", "crq-run-2")

    result = _run_summary(monkeypatch, tmp_path)

    assert result["total_runs_with_feedback"] == 0
    assert result["total_ratings"] == 0
    assert result["by_region"] == {}


def test_single_feedback_entry(monkeypatch, tmp_path):
    """One run with one feedback entry → correct counts."""
    _make_run(tmp_path, "2026-03-16_100000Z", "crq-run-1", feedback=[
        {"region": "AME", "rating": "accurate", "note": "Spot on", "analyst": "alice", "submitted_at": "2026-03-16T12:00:00Z"},
    ])

    result = _run_summary(monkeypatch, tmp_path)

    assert result["total_runs_with_feedback"] == 1
    assert result["total_ratings"] == 1
    assert result["by_region"]["AME"]["accurate"] == 1
    assert result["by_region"]["AME"]["total"] == 1
    assert result["by_region"]["AME"]["accuracy_rate"] == 1.0
    assert result["by_rating"]["accurate"] == 1
    assert result["by_rating"]["overstated"] == 0
    assert len(result["recent_notes"]) == 1
    assert result["recent_notes"][0]["run_id"] == "crq-run-1"
    assert result["recent_notes"][0]["note"] == "Spot on"


def test_multiple_runs_aggregation(monkeypatch, tmp_path):
    """Multiple runs with multiple entries → correct aggregation."""
    _make_run(tmp_path, "2026-03-16_100000Z", "crq-run-1", feedback=[
        {"region": "AME", "rating": "accurate", "note": "", "analyst": "alice", "submitted_at": "2026-03-16T10:00:00Z"},
        {"region": "APAC", "rating": "overstated", "note": "Too alarming", "analyst": "bob", "submitted_at": "2026-03-16T10:05:00Z"},
    ])
    _make_run(tmp_path, "2026-03-16_120000Z", "crq-run-2", feedback=[
        {"region": "AME", "rating": "understated", "note": "Missed key signal", "analyst": "carol", "submitted_at": "2026-03-16T12:00:00Z"},
        {"region": "AME", "rating": "accurate", "note": "", "analyst": "alice", "submitted_at": "2026-03-16T12:05:00Z"},
        {"region": "MED", "rating": "false_positive", "note": "", "analyst": "dave", "submitted_at": "2026-03-16T12:10:00Z"},
    ])

    result = _run_summary(monkeypatch, tmp_path)

    assert result["total_runs_with_feedback"] == 2
    assert result["total_ratings"] == 5

    # by_region checks
    assert result["by_region"]["AME"]["accurate"] == 2
    assert result["by_region"]["AME"]["understated"] == 1
    assert result["by_region"]["AME"]["total"] == 3
    assert result["by_region"]["AME"]["accuracy_rate"] == pytest.approx(2 / 3)

    assert result["by_region"]["APAC"]["overstated"] == 1
    assert result["by_region"]["APAC"]["total"] == 1
    assert result["by_region"]["APAC"]["accuracy_rate"] == 0.0

    assert result["by_region"]["MED"]["false_positive"] == 1

    # by_rating checks
    assert result["by_rating"]["accurate"] == 2
    assert result["by_rating"]["overstated"] == 1
    assert result["by_rating"]["understated"] == 1
    assert result["by_rating"]["false_positive"] == 1


def test_recent_notes_max_10_newest_first(monkeypatch, tmp_path):
    """recent_notes: only entries with non-empty note, max 10, newest-first."""
    # Create 12 entries with notes and 3 without
    entries = []
    for i in range(15):
        note = f"Note {i}" if i < 12 else ""
        entries.append({
            "region": "AME",
            "rating": "accurate",
            "note": note,
            "analyst": "tester",
            "submitted_at": f"2026-03-16T{10 + i:02d}:00:00Z",
        })

    _make_run(tmp_path, "2026-03-16_100000Z", "crq-run-1", feedback=entries)

    result = _run_summary(monkeypatch, tmp_path)

    # Only entries with notes (12), capped at 10
    assert len(result["recent_notes"]) == 10

    # All have non-empty notes
    for n in result["recent_notes"]:
        assert n["note"] != ""

    # Newest first
    timestamps = [n["submitted_at"] for n in result["recent_notes"]]
    assert timestamps == sorted(timestamps, reverse=True)

    # The newest noted entry is Note 11 (at hour 21)
    assert result["recent_notes"][0]["note"] == "Note 11"
