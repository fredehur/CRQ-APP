"""Tests for tools/cyber_collector.py — cyber signal collector."""
import json
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    result = subprocess.run(
        [PYTHON, "tools/cyber_collector.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd="c:/Users/frede/crq-agent-workspace/.worktrees/phase-e"
    )
    return result.returncode, result.stdout, result.stderr


def read_output(region):
    path = f"c:/Users/frede/crq-agent-workspace/.worktrees/phase-e/output/regional/{region.lower()}/cyber_signals.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_apac_writes_cyber_signals():
    code, _, err = run(["APAC", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = read_output("APAC")
    assert "summary" in data
    assert "threat_vector" in data
    assert "target_assets" in data
    assert isinstance(data["target_assets"], list)
    assert len(data["target_assets"]) >= 1


def test_all_five_regions():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, _, err = run([region, "--mock"])
        assert code == 0, f"Failed for {region}: {err}"
        data = read_output(region)
        assert all(k in data for k in ["summary", "threat_vector", "target_assets"]), \
            f"{region}: missing keys in {list(data.keys())}"
        assert isinstance(data["target_assets"], list), f"{region}: target_assets not a list"
        assert len(data["target_assets"]) >= 1, f"{region}: target_assets must have >= 1 item"


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0


def test_invalid_region_exits_nonzero():
    code, _, _ = run(["INVALID", "--mock"])
    assert code != 0
