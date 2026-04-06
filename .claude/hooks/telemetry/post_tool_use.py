#!/usr/bin/env python3
"""
PostToolUse telemetry hook.

Logs two categories of events to output/logs/tool_trace.log:
  1. Bash tool calls that exit with a non-zero code (failures)
  2. Write/Edit completions (confirming the file was written)

This provides the diagnostic trail needed to understand agent failures
without re-running the pipeline.

Always exits 0 — never interferes with tool results.
"""
import json
import sys
import os
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
LOG = BASE / "output" / "logs" / "tool_trace.log"

EXIT_CODE_RE = re.compile(r"exit code[:\s]+(\d+)", re.IGNORECASE)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", "")
    response_str = str(tool_response)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = None

    if tool_name == "Bash":
        # Detect failure: look for non-zero exit code in response
        match = EXIT_CODE_RE.search(response_str)
        if match and match.group(1) != "0":
            cmd = str(tool_input.get("command", ""))[:120]
            line = (
                f"[{ts}] TOOL_FAIL | Bash | exit={match.group(1)} | "
                f"cmd={cmd!r}\n"
            )
        # Also catch stderr-heavy responses as a heuristic
        elif "error" in response_str.lower()[:200] and "exit" not in response_str.lower()[:200]:
            cmd = str(tool_input.get("command", ""))[:80]
            line = (
                f"[{ts}] TOOL_WARN | Bash | possible error | "
                f"cmd={cmd!r}\n"
            )

    elif tool_name in ("Write", "Edit", "NotebookEdit"):
        file_path = tool_input.get("file_path", tool_input.get("path", "unknown"))
        line = f"[{ts}] TOOL_DONE | {tool_name} | {file_path}\n"

    if line:
        try:
            os.makedirs(LOG.parent, exist_ok=True)
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass  # telemetry must never block

    sys.exit(0)


if __name__ == "__main__":
    main()
