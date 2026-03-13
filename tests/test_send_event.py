"""Tests for E-3 — send_event.py telemetry tool."""
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

PROJECT_ROOT = r"c:/Users/frede/crq-agent-workspace/.worktrees/phase-e"

# Ensure tools/ is importable
_tools_dir = os.path.join(PROJECT_ROOT, "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

import send_event as se
import audit_logger as al


def test_send_event_silent_when_server_offline(monkeypatch):
    """send_event() exits without raising when server is not running."""
    monkeypatch.setattr(se, "SERVER_URL", "http://localhost:19999/internal/event")
    monkeypatch.setattr(al, "log_event", lambda event_type, message: None)
    # Should not raise
    se.send_event("TEST_EVENT", "test-agent", {"test": True})


def test_send_event_calls_log_event(monkeypatch):
    """send_event() calls log_event with the correct event_type."""
    monkeypatch.setattr(se, "SERVER_URL", "http://localhost:19999/internal/event")

    log_calls = []
    monkeypatch.setattr(al, "log_event", lambda event_type, message: log_calls.append(event_type))

    se.send_event("AGENT_STOP", "test-agent", {"exit_code": 0})

    assert len(log_calls) == 1
    assert log_calls[0] == "AGENT_STOP"


def test_internal_event_endpoint():
    """POST /internal/event returns 200 and {"ok": true} when server is running."""
    payload = json.dumps({
        "event_type": "AGENT_STOP",
        "agent_id": "test-agent",
        "payload": {"exit_code": 0},
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "http://localhost:8000/internal/event",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
            assert body.get("ok") is True
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        pytest.skip("server not running — skipping live endpoint test")
