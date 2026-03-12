"""Tests for tools/osint_search.py — OSINT search primitive."""
import json
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    result = subprocess.run(
        [PYTHON, "tools/osint_search.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd="c:/Users/frede/crq-agent-workspace/.worktrees/osint-toolchain"
    )
    return result.returncode, result.stdout, result.stderr


def test_mock_geo_returns_valid_json_array():
    code, out, err = run(["APAC", "wind energy supply chain", "--type", "geo", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) >= 1
    for item in data:
        assert "title" in item
        assert "summary" in item


def test_mock_cyber_returns_valid_json_array():
    code, out, err = run(["APAC", "OT security threats", "--type", "cyber", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) >= 1


def test_all_five_regions_geo():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, out, err = run([region, "test query", "--type", "geo", "--mock"])
        assert code == 0, f"Region {region} failed: {err}"
        data = json.loads(out)
        assert isinstance(data, list), f"{region}: expected list"


def test_all_five_regions_cyber():
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        code, out, err = run([region, "test query", "--type", "cyber", "--mock"])
        assert code == 0, f"Region {region} failed: {err}"
        data = json.loads(out)
        assert isinstance(data, list), f"{region}: expected list"


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0


def test_invalid_region_exits_nonzero():
    code, _, _ = run(["INVALID", "query", "--type", "geo", "--mock"])
    assert code != 0


def test_missing_type_exits_nonzero():
    code, _, _ = run(["APAC", "query", "--mock"])
    assert code != 0


def test_invalid_type_exits_nonzero():
    code, _, _ = run(["APAC", "query", "--type", "financial", "--mock"])
    assert code != 0
