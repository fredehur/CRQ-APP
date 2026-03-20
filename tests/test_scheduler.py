"""Tests for tools/scheduler.py — Phase L"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
import tools.scheduler as sc


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "CONFIG_PATH", tmp_path / "schedule_config.json")
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "output" / ".scheduler_state.json")


def _write_config(tmp_path, jobs):
    (tmp_path / "schedule_config.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


# _cron_due tests — all branches of the function

def test_never_run_is_always_due():
    """None last_run → always due, regardless of cron."""
    now = datetime(2026, 3, 17, 6, 0, tzinfo=timezone.utc)  # Monday
    assert sc._cron_due("0 */6 * * *", None, now) is True


def test_every_6h_due_when_elapsed():
    """'0 */6 * * *' — due after 6h elapsed."""
    now = datetime(2026, 3, 17, 6, 0, tzinfo=timezone.utc)
    last = (now - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 */6 * * *", last, now) is True


def test_every_6h_not_due_within_interval():
    """'0 */6 * * *' — not due if only 3h elapsed."""
    now = datetime(2026, 3, 17, 6, 0, tzinfo=timezone.utc)
    last = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 */6 * * *", last, now) is False


def test_half_hour_offset_due_when_elapsed():
    """'30 */6 * * *' — due after 6h elapsed (offset is in cron minute, not interval)."""
    now = datetime(2026, 3, 17, 6, 30, tzinfo=timezone.utc)
    last = (now - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("30 */6 * * *", last, now) is True


def test_half_hour_offset_not_due_too_soon():
    """'30 */6 * * *' — not due if only 2h elapsed."""
    now = datetime(2026, 3, 17, 6, 30, tzinfo=timezone.utc)
    last = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("30 */6 * * *", last, now) is False


def test_weekly_monday_due_when_correct_day():
    """'0 5 * * 1' — due on Monday 05:00 UTC if not run this week."""
    now = datetime(2026, 3, 16, 5, 0, tzinfo=timezone.utc)  # Monday
    last = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 5 * * 1", last, now) is True


def test_weekly_monday_not_due_on_wrong_day():
    """'0 5 * * 1' — not due on Tuesday."""
    now = datetime(2026, 3, 17, 5, 0, tzinfo=timezone.utc)  # Tuesday
    last = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sc._cron_due("0 5 * * 1", last, now) is False


def test_state_written_after_run(monkeypatch, tmp_path):
    """After run_once, state file is written with job's last-run timestamp."""
    _patch(monkeypatch, tmp_path)
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    _write_config(tmp_path, [
        {"id": "test_job", "command": "echo ok", "regions": None, "cron": "0 */1 * * *",
         "description": "test"}
    ])
    sc.run_once()
    state_path = tmp_path / "output" / ".scheduler_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "test_job" in state
