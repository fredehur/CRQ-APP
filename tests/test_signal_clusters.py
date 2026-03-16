import json
import subprocess
import sys
import tempfile
import os


VALID_CLUSTER = {
    "region": "AME",
    "timestamp": "2026-03-16T09:00:00Z",
    "window_used": "7d",
    "total_signals": 2,
    "sources_queried": 10,
    "clusters": [
        {
            "name": "Grid disruption cluster",
            "pillar": "Cyber",
            "convergence": 2,
            "sources": [
                {"name": "Reuters", "headline": "Grid warning issued"},
                {"name": "CISA", "headline": "Energy sector alert"},
            ]
        }
    ]
}

CLEAR_CLUSTER = {
    "region": "LATAM",
    "timestamp": "2026-03-16T09:00:00Z",
    "window_used": "7d",
    "total_signals": 0,
    "sources_queried": 8,
    "clusters": []
}


def run_validator(data):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, "tools/validate_signal_clusters.py", path],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return r
    finally:
        os.unlink(path)


def test_valid_escalated_schema():
    r = run_validator(VALID_CLUSTER)
    assert r.returncode == 0, r.stderr


def test_valid_clear_schema():
    r = run_validator(CLEAR_CLUSTER)
    assert r.returncode == 0, r.stderr


def test_missing_required_key():
    bad = {**VALID_CLUSTER}
    del bad["sources_queried"]
    r = run_validator(bad)
    assert r.returncode != 0


def test_invalid_pillar():
    bad = {**VALID_CLUSTER, "clusters": [{**VALID_CLUSTER["clusters"][0], "pillar": "Unknown"}]}
    r = run_validator(bad)
    assert r.returncode != 0


def test_missing_source_headline():
    bad_source = {"name": "Reuters"}  # missing headline
    bad = {**VALID_CLUSTER, "clusters": [{**VALID_CLUSTER["clusters"][0], "sources": [bad_source]}]}
    r = run_validator(bad)
    assert r.returncode != 0


def test_invalid_convergence_type():
    """convergence must be int, not float or string."""
    bad_cluster = {**VALID_CLUSTER["clusters"][0], "convergence": "3"}  # string, not int
    bad = {**VALID_CLUSTER, "clusters": [bad_cluster]}
    r = run_validator(bad)
    assert r.returncode != 0


def test_signal_clusters_written_after_mock_run():
    """After running collectors + scenario_mapper in mock mode, signal_clusters.json
    should exist at the expected path once the agent instruction is live.
    This test is intentionally skipped in CI unless a full mock run has been executed.
    """
    path = "output/regional/ame/signal_clusters.json"
    if not os.path.exists(path):
        import pytest
        pytest.skip("signal_clusters.json not present — run /crq-region AME first")
    r = subprocess.run(
        [sys.executable, "tools/validate_signal_clusters.py", path],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    assert r.returncode == 0, r.stderr
