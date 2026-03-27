#!/usr/bin/env python3
"""
PreToolUse telemetry hook.

Logs filesystem-mutating tool invocations to output/tool_trace.log.
Only tracks Write and Edit tool calls — ignores Read, Bash, and all others
to avoid flooding the log with noise.

Always exits 0 — never blocks a tool call.
"""
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

WATCHED_TOOLS = {"Write", "Edit", "NotebookEdit"}

BASE = Path(__file__).resolve().parents[3]
LOG = BASE / "output" / "tool_trace.log"


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in WATCHED_TOOLS:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", tool_input.get("path", "unknown"))

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] PRE_TOOL | {tool_name} | {file_path}\n"

    try:
        os.makedirs(LOG.parent, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # telemetry must never block

    sys.exit(0)


if __name__ == "__main__":
    main()
