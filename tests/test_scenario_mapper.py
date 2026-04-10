"""Tests for tools/scenario_mapper.py — scenario mapper."""
import json
import subprocess
import sys

PYTHON = sys.executable


def run(args):
    result = subprocess.run(
        [PYTHON, "tools/scenario_mapper.py"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd="c:/Users/frede/crq-agent-workspace/.worktrees/osint-toolchain"
    )
    return result.returncode, result.stdout, result.stderr


def read_output(region):
    path = f"c:/Users/frede/crq-agent-workspace/.worktrees/osint-toolchain/output/regional/{region.lower()}/scenario_map.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_master():
    with open("c:/Users/frede/crq-agent-workspace/.worktrees/osint-toolchain/data/master_scenarios.json", encoding="utf-8") as f:
        data = json.load(f)
    return {s["incident_type"]: s for s in data["scenarios"]}


def setup_region(region):
    """Run osint_collector first so osint_signals.json exists."""
    result = subprocess.run(
        [PYTHON, "tools/osint_collector.py", region, "--mock"],
        capture_output=True, text=True, encoding="utf-8",
        cwd="c:/Users/frede/crq-agent-workspace"
    )
    assert result.returncode == 0, (
        f"osint_collector failed for {region}: {result.stderr}"
    )


def test_apac_writes_scenario_map():
    setup_region("APAC")
    code, _, err = run(["APAC", "--mock"])
    assert code == 0, f"stderr: {err}"
    data = read_output("APAC")
    assert "top_scenario" in data


def test_scenario_map_schema():
    setup_region("APAC")
    run(["APAC", "--mock"])
    data = read_output("APAC")
    assert all(k in data for k in ["top_scenario", "confidence", "financial_rank", "rationale"]), \
        f"Missing keys: {list(data.keys())}"
    assert data["confidence"] in {"high", "medium", "low"}
    master = load_master()
    assert data["top_scenario"] in master, f"Unknown scenario: '{data['top_scenario']}'"
    expected_rank = master[data["top_scenario"]]["financial_rank"]
    assert data["financial_rank"] == expected_rank, \
        f"financial_rank mismatch: got {data['financial_rank']}, expected {expected_rank}"


def test_all_five_regions():
    master = load_master()
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        setup_region(region)
        code, _, err = run([region, "--mock"])
        assert code == 0, f"Failed for {region}: {err}"
        data = read_output(region)
        assert all(k in data for k in ["top_scenario", "confidence", "financial_rank", "rationale"]), \
            f"{region}: missing keys in {list(data.keys())}"
        assert data["top_scenario"] in master, f"{region}: unknown scenario '{data['top_scenario']}'"
        assert data["confidence"] in {"high", "medium", "low"}, f"{region}: bad confidence"
        expected = master[data["top_scenario"]]["financial_rank"]
        assert data["financial_rank"] == expected, \
            f"{region}: financial_rank mismatch (got {data['financial_rank']}, expected {expected})"


def test_no_args_exits_nonzero():
    code, _, _ = run([])
    assert code != 0


def test_invalid_region_exits_nonzero():
    code, _, _ = run(["INVALID"])
    assert code != 0
