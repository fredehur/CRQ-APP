import json
from pathlib import Path


def test_append_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path)
    from tools.source_librarian.tuning_log import append_event, read_log

    e1 = {"ts": "2026-04-20T10:00:00Z", "register_id": "wp", "scenario_id": "WP-001",
           "run_id": "r1", "iteration": 1, "event": "proposed",
           "diff": {"add_threat_terms": ["OT ransomware"]}, "reasoning": "too narrow",
           "validator_verdict": "approved", "cost_usd": 0.01}
    e2 = {**e1, "event": "rerun_result", "candidates_discovered": 3,
          "t1_t2_count": 0, "best_rejection": {"url": "x", "reason": "tier"}, "cost_usd": 0.02}

    append_event("wp", e1)
    append_event("wp", e2)

    log = read_log("wp")
    assert len(log) == 2
    assert log[0]["event"] == "proposed"
    assert log[1]["event"] == "rerun_result"


def test_append_is_truly_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path)
    from tools.source_librarian.tuning_log import append_event, read_log

    for i in range(5):
        append_event("wp", {"iteration": i, "event": "proposed"})

    log = read_log("wp")
    assert len(log) == 5
    for i, entry in enumerate(log):
        assert entry["iteration"] == i


def test_read_log_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", tmp_path)
    from tools.source_librarian.tuning_log import read_log
    assert read_log("no_register") == []


def test_creates_directory_on_first_write(tmp_path, monkeypatch):
    log_dir = tmp_path / "nested" / "tuning"
    monkeypatch.setattr("tools.source_librarian.tuning_log.TUNING_LOG_DIR", log_dir)
    from tools.source_librarian.tuning_log import append_event
    append_event("wp", {"event": "test"})
    assert (log_dir / "wp.jsonl").exists()
