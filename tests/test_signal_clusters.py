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


def test_json_auditor_requires_synthesis_brief():
    """json-auditor.py fails if synthesis_brief is missing."""
    import tempfile, os
    label = "test_synthesis_missing"
    retry_file = f"output/.retries/{label}_json.retries"
    os.makedirs("output/.retries", exist_ok=True)
    missing_brief = {
        "total_vacr_exposure": 1000000,
        "executive_summary": "A" * 50,
        "regional_threats": []
        # synthesis_brief intentionally absent
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(missing_brief, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, ".claude/hooks/validators/json-auditor.py", path, label],
            capture_output=True, text=True
        )
        assert r.returncode == 2, f"Expected exit 2 (audit fail), got {r.returncode}. stderr: {r.stderr}"
    finally:
        os.unlink(path)
        if os.path.exists(retry_file):
            os.remove(retry_file)


def test_json_auditor_passes_with_synthesis_brief():
    """json-auditor.py passes when synthesis_brief is present and long enough."""
    import tempfile, os
    label = "test_synthesis_present"
    retry_file = f"output/.retries/{label}_json.retries"
    os.makedirs("output/.retries", exist_ok=True)
    with_brief = {
        "total_vacr_exposure": 1000000,
        "executive_summary": "A" * 50,
        "synthesis_brief": "Cross-regional pattern identified. Two regions show convergence on grid infrastructure threats.",
        "regional_threats": []
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(with_brief, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, ".claude/hooks/validators/json-auditor.py", path, label],
            capture_output=True, text=True
        )
        assert r.returncode == 0, f"Expected exit 0, got {r.returncode}. stderr: {r.stderr}"
    finally:
        os.unlink(path)
        if os.path.exists(retry_file):
            os.remove(retry_file)


def test_json_auditor_rejects_short_synthesis_brief():
    """synthesis_brief shorter than 30 chars should fail."""
    import tempfile, os
    label = "test_synthesis_short"
    retry_file = f"output/.retries/{label}_json.retries"
    os.makedirs("output/.retries", exist_ok=True)
    short_brief = {
        "total_vacr_exposure": 1000000,
        "executive_summary": "A" * 50,
        "synthesis_brief": "Too short.",   # 10 chars — below 30-char floor
        "regional_threats": []
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(short_brief, f)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, ".claude/hooks/validators/json-auditor.py", path, label],
            capture_output=True, text=True
        )
        assert r.returncode == 2, f"Expected exit 2, got {r.returncode}. stderr: {r.stderr}"
    finally:
        os.unlink(path)
        if os.path.exists(retry_file):
            os.remove(retry_file)


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
