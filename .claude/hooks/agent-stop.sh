#!/usr/bin/env bash
# Stop hook — fires AGENT_STOP telemetry event when a Claude Code agent stops

EVENT_TYPE="AGENT_STOP"
AGENT_ID="${CLAUDE_AGENT_ID:-unknown}"
EXIT_CODE="${CLAUDE_EXIT_CODE:-0}"

uv run python tools/send_event.py "$EVENT_TYPE" "$AGENT_ID" \
  "{\"exit_code\": $EXIT_CODE}" 2>/dev/null || true

exit 0
