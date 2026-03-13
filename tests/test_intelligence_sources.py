"""Tests for E-2 Intelligence Provenance — intelligence_sources.json generation."""
import json
import os
import subprocess
import sys
import pytest

PROJECT_ROOT = r"c:/Users/frede/crq-agent-workspace/.worktrees/phase-e"
PYTHON = sys.executable


def _run(script, args):
    return subprocess.run(
        [PYTHON, f"tools/{script}"] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=PROJECT_ROOT,
    )


def _read_intel(region):
    path = os.path.join(PROJECT_ROOT, "output", "regional", region.lower(), "intelligence_sources.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_geo_signals(region):
    path = os.path.join(PROJECT_ROOT, "output", "regional", region.lower(), "geo_signals.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_cyber_signals(region):
    path = os.path.join(PROJECT_ROOT, "output", "regional", region.lower(), "cyber_signals.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_geo_collector_writes_geo_sources():
    """geo_collector writes intelligence_sources.json with geo_sources with correct fields."""
    rc = _run("geo_collector.py", ["APAC", "--mock"]).returncode
    assert rc == 0
    intel = _read_intel("APAC")
    assert "geo_sources" in intel
    assert isinstance(intel["geo_sources"], list)
    assert len(intel["geo_sources"]) > 0
    first = intel["geo_sources"][0]
    for field in ("title", "snippet", "source", "published_date", "mock"):
        assert field in first, f"missing field: {field}"
    assert first["mock"] is True


def test_cyber_collector_extends_with_cyber_sources():
    """cyber_collector extends intelligence_sources.json with cyber_sources while preserving geo_sources."""
    _run("geo_collector.py", ["APAC", "--mock"])
    _run("cyber_collector.py", ["APAC", "--mock"])
    intel = _read_intel("APAC")
    assert "geo_sources" in intel, "geo_sources must be preserved"
    assert "cyber_sources" in intel
    assert len(intel["cyber_sources"]) > 0


def test_cyber_collector_guard_missing_geo_sources():
    """cyber_collector writes cyber_sources only (no exception) when geo_sources key is absent."""
    intel_path = os.path.join(PROJECT_ROOT, "output", "regional", "nce", "intelligence_sources.json")
    os.makedirs(os.path.dirname(intel_path), exist_ok=True)
    # Write a file with no geo_sources key
    with open(intel_path, "w", encoding="utf-8") as f:
        json.dump({"region": "NCE", "collected_at": "2026-01-01T00:00:00Z"}, f)
    result = _run("cyber_collector.py", ["NCE", "--mock"])
    assert result.returncode == 0, f"Should not crash: {result.stderr}"
    intel = _read_intel("NCE")
    assert "cyber_sources" in intel


def test_geo_signals_schema_unchanged():
    """geo_signals.json schema is unchanged after E-2 geo_collector run."""
    _run("geo_collector.py", ["APAC", "--mock"])
    signals = _read_geo_signals("APAC")
    for key in ("summary", "lead_indicators", "dominant_pillar"):
        assert key in signals, f"geo_signals missing key: {key}"


def test_cyber_signals_schema_unchanged():
    """cyber_signals.json schema is unchanged after E-2 cyber_collector run."""
    _run("cyber_collector.py", ["APAC", "--mock"])
    signals = _read_cyber_signals("APAC")
    for key in ("summary", "threat_vector", "target_assets"):
        assert key in signals, f"cyber_signals missing key: {key}"


def test_geo_collector_collect_returns_tuple():
    """collect() in geo_collector returns a tuple (normalized_dict, raw_articles)."""
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))
    # Need to import from worktree
    import importlib, importlib.util
    spec = importlib.util.spec_from_file_location(
        "geo_collector",
        os.path.join(PROJECT_ROOT, "tools", "geo_collector.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.collect("APAC", mock=True)
    assert isinstance(result, tuple), "collect() must return a tuple"
    assert len(result) == 2
    normalized, raw = result
    assert isinstance(normalized, dict)
    assert isinstance(raw, list)
