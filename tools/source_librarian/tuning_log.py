"""Append-only JSONL log of auto-tune iterations per register."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TUNING_LOG_DIR = REPO_ROOT / "data" / "research_intents" / "tuning_log"


def append_event(register_id: str, event: dict[str, Any]) -> None:
    """Append one JSONL line to the tuning log for this register."""
    from . import tuning_log as _mod
    log_dir = _mod.TUNING_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{register_id}.jsonl"
    with open(path, mode="a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_log(register_id: str) -> list[dict[str, Any]]:
    """Return all log entries for a register, oldest first."""
    from . import tuning_log as _mod
    path = _mod.TUNING_LOG_DIR / f"{register_id}.jsonl"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries
