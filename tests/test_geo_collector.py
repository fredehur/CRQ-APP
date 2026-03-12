"""Tests for tools/geo_collector.py — geo signal collector."""
import json
import os
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    result = subprocess.run(
        [PYTHON, "tools/geo_collector.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd="c:/Users/frede/crq-agent-workspace/.worktrees/osint-toolchain"
    )
    return result.returncode, result.stdout, result.stderr


def read_output(region):
    path = f"output/regional/{region.lower()}/geo_signals.json"
    with open(f"c:/Users/frede/crq-agent-workspace/.worktrees/osint-toolchain/{path}", encoding="utf-8") as f:
        return json.load(f)


def test_apac_writes_geo_signals():
    code, _, err = run(["APAC", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = read_output("APAC")
    assert "summary" in data
    assert "lead_indicators" in data
    assert "dominant_pillar" in data
    assert isinstance(data["lead_indicators"], list)
    assert len(data["lead_indicators"]) >= 1
    assert data["dominant_pillar"] in {"Geopolitical", "Cyber", "Regulatory"}


def test_all_five_regions():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, _, err = run([region, "--mock"])
        assert code == 0, f"Failed for {region}: {err}"
        data = read_output(region)
        assert all(k in data for k in ["summary", "lead_indicators", "dominant_pillar"]), \
            f"{region}: missing keys in {list(data.keys())}"
        assert data["dominant_pillar"] in {"Geopolitical", "Cyber", "Regulatory"}, \
            f"{region}: bad dominant_pillar value '{data['dominant_pillar']}'"


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0


def test_invalid_region_exits_nonzero():
    code, _, _ = run(["INVALID", "--mock"])
    assert code != 0
