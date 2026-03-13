#!/usr/bin/env python3
"""Fire-and-forget telemetry event sender.

Usage:
    uv run python tools/send_event.py <EVENT_TYPE> <AGENT_ID> '<JSON_PAYLOAD>'

Sends HTTP POST to http://localhost:8000/internal/event.
Swallows all connection errors — pipeline must never block on telemetry.
Always appends to system_trace.log via audit_logger regardless of server availability.
"""
import json
import os
import sys
import urllib.error
import urllib.request

SERVER_URL = "http://localhost:8000/internal/event"


def send_event(event_type: str, agent_id: str, payload: dict) -> None:
    """Send telemetry event. Never raises from HTTP failures."""
    # Always log to trace file (audit trail is authoritative)
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from audit_logger import log_event
    log_event(event_type, f"agent={agent_id} payload={json.dumps(payload)}")

    # Fire-and-forget POST (best effort — connection errors are swallowed)
    try:
        body = json.dumps({
            "event_type": event_type,
            "agent_id": agent_id,
            "payload": payload,
        }).encode("utf-8")
        req = urllib.request.Request(
            SERVER_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, OSError):
        pass  # server not running — silent failure


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: send_event.py <EVENT_TYPE> <AGENT_ID> '<JSON_PAYLOAD>'", file=sys.stderr)
        sys.exit(1)

    event_type = sys.argv[1]
    agent_id = sys.argv[2]
    try:
        payload = json.loads(sys.argv[3])
    except json.JSONDecodeError:
        payload = {"raw": sys.argv[3]}

    send_event(event_type, agent_id, payload)


if __name__ == "__main__":
    main()
