"""Tests for --window date-range parameter in osint_collector.py."""
import json
import os
import subprocess
import sys

PYTHON = sys.executable
CWD = "c:/Users/frede/crq-agent-workspace"


def run_osint_collector(args):
    result = subprocess.run(
        [PYTHON, "tools/osint_collector.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=CWD,
    )
    return result.returncode, result.stdout, result.stderr


def test_window_valid_accepted():
    """Valid --window values must be accepted."""
    for window in ["1d", "7d", "30d", "90d"]:
        code, out, err = run_osint_collector(["APAC", "--mock", "--window", window])
        assert code == 0, f"--window {window} failed with exit {code}: {err}"


def test_window_omitted_still_works():
    """Omitting --window should still succeed (backward-compatible)."""
    code, out, err = run_osint_collector(["APAC", "--mock"])
    assert code == 0, f"Omitting --window failed: {err}"


def test_osint_collector_writes_signal_file():
    """osint_collector --mock must write osint_signals.json with required fields."""
    code, out, err = run_osint_collector(["APAC", "--mock", "--window", "7d"])
    assert code == 0, f"osint_collector --window 7d failed: {err}"
    out_path = os.path.join(CWD, "output/regional/apac/osint_signals.json")
    assert os.path.exists(out_path), "osint_signals.json was not written"
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert "summary" in data
    assert "lead_indicators" in data
    assert "dominant_pillar" in data
