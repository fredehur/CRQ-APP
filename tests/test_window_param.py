"""Tests for --window date-range parameter across OSINT tool chain."""
import json
import os
import subprocess
import sys

PYTHON = sys.executable
CWD = "c:/Users/frede/crq-agent-workspace"


def run_osint(args):
    result = subprocess.run(
        [PYTHON, "tools/osint_search.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=CWD,
    )
    return result.returncode, result.stdout, result.stderr


def run_geo(args):
    result = subprocess.run(
        [PYTHON, "tools/geo_collector.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=CWD,
    )
    return result.returncode, result.stdout, result.stderr


def run_cyber(args):
    result = subprocess.run(
        [PYTHON, "tools/cyber_collector.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=CWD,
    )
    return result.returncode, result.stdout, result.stderr


# ── Task 1: osint_search.py --window tests ──────────────────────────────────

def test_window_valid_accepted():
    """Valid --window values must be accepted and return JSON results in mock mode."""
    for window in ["1d", "7d", "30d", "90d"]:
        code, out, err = run_osint(
            ["APAC", "wind energy supply chain", "--type", "geo", "--mock", "--window", window]
        )
        assert code == 0, f"--window {window} failed with exit {code}: {err}"
        data = json.loads(out)
        assert isinstance(data, list), f"--window {window}: expected list, got {type(data)}"


def test_window_invalid_exits_nonzero():
    """Invalid --window value must cause exit code 1."""
    code, _, err = run_osint(
        ["APAC", "wind energy supply chain", "--type", "geo", "--mock", "--window", "bad"]
    )
    assert code != 0, "Expected non-zero exit for invalid --window value"


def test_window_omitted_still_works():
    """Omitting --window should still return valid results (backward-compatible)."""
    code, out, err = run_osint(
        ["APAC", "wind energy supply chain", "--type", "geo", "--mock"]
    )
    assert code == 0, f"Omitting --window failed: {err}"
    data = json.loads(out)
    assert isinstance(data, list)


# ── Task 2: geo_collector.py and cyber_collector.py --window passthrough ────

def test_geo_collector_window_passthrough():
    """geo_collector.py --window 7d must succeed and write geo_signals.json."""
    code, out, err = run_geo(["APAC", "--mock", "--window", "7d"])
    assert code == 0, f"geo_collector --window 7d failed: {err}"
    out_path = os.path.join(CWD, "output/regional/apac/geo_signals.json")
    assert os.path.exists(out_path), "geo_signals.json was not written"
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert "summary" in data
    assert "lead_indicators" in data


def test_cyber_collector_window_passthrough():
    """cyber_collector.py --window 7d must succeed and write cyber_signals.json."""
    code, out, err = run_cyber(["APAC", "--mock", "--window", "7d"])
    assert code == 0, f"cyber_collector --window 7d failed: {err}"
    out_path = os.path.join(CWD, "output/regional/apac/cyber_signals.json")
    assert os.path.exists(out_path), "cyber_signals.json was not written"
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    assert "summary" in data
    assert "threat_vector" in data
