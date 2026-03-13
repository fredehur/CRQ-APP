#!/usr/bin/env bash
# PostToolUse hook — fires TOOL_FAILURE telemetry event when a tool exits non-zero

EXIT_CODE="${CLAUDE_EXIT_CODE:-0}"

# Only fire on non-zero exit
if [ "$EXIT_CODE" != "0" ]; then
  TOOL_NAME="${CLAUDE_TOOL_NAME:-unknown}"
  AGENT_ID="${CLAUDE_AGENT_ID:-unknown}"

  uv run python tools/send_event.py "TOOL_FAILURE" "$AGENT_ID" \
    "{\"tool\": \"$TOOL_NAME\", \"exit_code\": $EXIT_CODE}" 2>/dev/null || true
fi

exit 0
