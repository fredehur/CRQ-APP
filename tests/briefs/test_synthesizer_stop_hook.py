"""Tests for the rsm-weekly-synthesizer stop hook validator."""
from __future__ import annotations
import json
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "validators" / "rsm-weekly-synthesizer-output.py"


def _make_transcript(assistant_text: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    tmp.write(json.dumps({"role": "assistant", "content": assistant_text}) + "\n")
    tmp.close()
    return Path(tmp.name)


def _run_hook(transcript_path: Path) -> int:
    spec = importlib.util.spec_from_file_location(f"hook_{id(transcript_path)}", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    old_env = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    os.environ["CLAUDE_TRANSCRIPT_PATH"] = str(transcript_path)
    try:
        spec.loader.exec_module(mod)
        return mod.main()
    finally:
        if old_env is None:
            os.environ.pop("CLAUDE_TRANSCRIPT_PATH", None)
        else:
            os.environ["CLAUDE_TRANSCRIPT_PATH"] = old_env


def _valid_output(site_ids=("site-001",), ref_ids=("E1",)) -> dict:
    return {
        "headline": "Regional activity remained below threshold this week.",
        "sites_narrative": [
            {
                "site_id": sid,
                "standing_notes_synthesis": None,
                "pattern_framing": None,
                "cyber_callout_text": None,
            }
            for sid in site_ids
        ],
        "regional_cyber_standing_notes": None,
        "evidence_why_lines": {rid: "confirms low-level activity" for rid in ref_ids},
    }


def test_valid_output_passes():
    t = _make_transcript(json.dumps(_valid_output()))
    try:
        assert _run_hook(t) == 0
    finally:
        t.unlink(missing_ok=True)


def test_non_json_fails():
    t = _make_transcript("This is not JSON at all.")
    try:
        assert _run_hook(t) == 1
    finally:
        t.unlink(missing_ok=True)


def test_missing_headline_fails():
    data = _valid_output()
    del data["headline"]
    t = _make_transcript(json.dumps(data))
    try:
        assert _run_hook(t) == 1
    finally:
        t.unlink(missing_ok=True)


def test_extra_field_fails():
    data = _valid_output()
    data["unexpected_field"] = "oops"
    t = _make_transcript(json.dumps(data))
    try:
        assert _run_hook(t) == 1
    finally:
        t.unlink(missing_ok=True)


def test_forbidden_jargon_soc_budget_fails():
    data = _valid_output()
    data["headline"] = "The SOC budget was reviewed this week."
    t = _make_transcript(json.dumps(data))
    try:
        assert _run_hook(t) == 1
    finally:
        t.unlink(missing_ok=True)


def test_forbidden_jargon_blue_team_fails():
    data = _valid_output()
    data["sites_narrative"][0]["pattern_framing"] = "blue-team operations are ongoing."
    t = _make_transcript(json.dumps(data))
    try:
        assert _run_hook(t) == 1
    finally:
        t.unlink(missing_ok=True)


def test_missing_transcript_returns_zero():
    old_env = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    os.environ["CLAUDE_TRANSCRIPT_PATH"] = "/nonexistent/path/transcript.jsonl"
    try:
        spec = importlib.util.spec_from_file_location("hook_missing", HOOK_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.main() == 0
    finally:
        if old_env is None:
            os.environ.pop("CLAUDE_TRANSCRIPT_PATH", None)
        else:
            os.environ["CLAUDE_TRANSCRIPT_PATH"] = old_env


def test_json_in_code_fence_parses():
    data = _valid_output()
    wrapped = f"```json\n{json.dumps(data)}\n```"
    t = _make_transcript(wrapped)
    try:
        assert _run_hook(t) == 0
    finally:
        t.unlink(missing_ok=True)
