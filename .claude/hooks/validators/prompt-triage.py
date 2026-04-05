#!/usr/bin/env python3
"""
UserPromptSubmit hook — protocol reminder + CRQ pipeline task detection.

Always emits the engineering protocol line.
If the prompt contains pipeline-related keywords, also emits a /prime-crq reminder.

Always exits 0 — never blocks a prompt.
"""
import json
import sys

PROTOCOL_LINE = (
    "[PROTOCOL] Teams=ON | Opus orchestrates | Sonnet builds+validates | "
    "Parallel by default | Run /prime-dev before build tasks | Full rules: CLAUDE.md > Engineering Protocol"
)

PIPELINE_REMINDER = (
    "[CRQ] Pipeline task detected — run /prime-crq if not loaded this session."
)

PIPELINE_KEYWORDS = {
    "agent", "agents",
    "hook", "hooks",
    "pipeline",
    "data.json",
    "gatekeeper",
    "regional-analyst", "regional analyst",
    "global-builder", "global builder",
    "global-validator", "global validator",
    "rsm-formatter", "rsm formatter",
    "geo_signals", "cyber_signals",
    "scenario_map", "signal_clusters",
    "run-crq", "run crq", "/run-crq",
    "crq-region", "/crq-region",
    "collector", "scenario mapper",
    "stop hook", "stop-hook",
    "jargon-auditor", "jargon auditor",
    "json-auditor",
    "validate_global_report",
    "admiralty",
    "vacr", "vaCR",
    "gatekeeper_decision",
    "report.md",
    "trend_brief", "run_manifest",
    "regional analyst", "regional-analyst",
    "phase 1", "phase 2", "phase 3", "phase 4", "phase 5",
}


def is_pipeline_task(prompt: str) -> bool:
    lower = prompt.lower()
    return any(kw.lower() in lower for kw in PIPELINE_KEYWORDS)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print(PROTOCOL_LINE)
        sys.exit(0)

    prompt = data.get("prompt", "")

    print(PROTOCOL_LINE)

    if is_pipeline_task(prompt):
        print(PIPELINE_REMINDER)

    sys.exit(0)


if __name__ == "__main__":
    main()
