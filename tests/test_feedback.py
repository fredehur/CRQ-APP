"""Tests for tools/feedback_writer.py — Phase I Analyst Feedback Loop."""

import json
import sys
from pathlib import Path

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_run(tmp_path: Path, run_id: str, folder_name: str = None) -> Path:
    """Create a fake run folder under tmp_path/output/runs/."""
    folder_name = folder_name or "2026-03-16_171249Z"
    run_dir = tmp_path / "output" / "runs" / folder_name
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({"pipeline_id": run_id}), encoding="utf-8"
    )
    return run_dir


def _call_main(monkeypatch, tmp_path, argv):
    """Redirect REPO_ROOT and sys.argv, then call feedback_writer.main()."""
    import tools.feedback_writer as fw
    monkeypatch.setattr(fw, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["feedback_writer.py"] + argv)
    fw.main()


# ── Tests ─────────────────────────────────────────────────────────────────

def test_feedback_writer_creates_feedback_json(monkeypatch, tmp_path):
    """Call main with valid args → feedback.json created with one correct entry."""
    run_dir = _make_run(tmp_path, "crq-2026-03-16T171249Z")

    _call_main(monkeypatch, tmp_path, [
        "crq-2026-03-16T171249Z", "AME", "accurate",
        "--note", "Good signal quality",
        "--analyst", "fred",
    ])

    fb_path = run_dir / "feedback.json"
    assert fb_path.exists(), "feedback.json was not created"
    entries = json.loads(fb_path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    e = entries[0]
    assert e["region"] == "AME"
    assert e["rating"] == "accurate"
    assert e["note"] == "Good signal quality"
    assert e["analyst"] == "fred"
    assert "submitted_at" in e


def test_feedback_writer_appends_to_existing(monkeypatch, tmp_path):
    """Two successive calls → two entries in feedback.json."""
    run_dir = _make_run(tmp_path, "crq-2026-03-16T171249Z")

    _call_main(monkeypatch, tmp_path, ["crq-2026-03-16T171249Z", "AME", "accurate"])
    _call_main(monkeypatch, tmp_path, ["crq-2026-03-16T171249Z", "APAC", "overstated"])

    entries = json.loads((run_dir / "feedback.json").read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[0]["region"] == "AME"
    assert entries[1]["region"] == "APAC"


def test_feedback_writer_invalid_rating_exits_1(monkeypatch, tmp_path):
    """Invalid rating → sys.exit(1)."""
    _make_run(tmp_path, "crq-2026-03-16T171249Z")

    with pytest.raises(SystemExit) as exc:
        _call_main(monkeypatch, tmp_path, ["crq-2026-03-16T171249Z", "AME", "totally_wrong"])
    assert exc.value.code == 1


def test_feedback_writer_run_not_found_exits_1(monkeypatch, tmp_path):
    """Unknown run_id → sys.exit(1)."""
    # Create a run folder with a different ID
    _make_run(tmp_path, "crq-2026-03-16T171249Z")

    with pytest.raises(SystemExit) as exc:
        _call_main(monkeypatch, tmp_path, ["crq-NONEXISTENT", "AME", "accurate"])
    assert exc.value.code == 1


def test_summarize_mode_with_no_feedback_prints_nothing(monkeypatch, tmp_path, capsys):
    """--summarize with no feedback files → stdout is empty, exit 0."""
    # Create run folder with manifest but no feedback.json
    _make_run(tmp_path, "crq-2026-03-16T171249Z")

    import tools.feedback_writer as fw
    monkeypatch.setattr(fw, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["feedback_writer.py", "--summarize"])

    with pytest.raises(SystemExit) as exc:
        fw.main()
    assert exc.value.code == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == ""
