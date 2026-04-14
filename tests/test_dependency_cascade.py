"""Dependency graph traversal. Pure code, no LLM."""
import json
from pathlib import Path

from tools.poi_proximity import compute_cascade, _build_dependency_graph

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_kaohsiung_cascade_reaches_hamburg(monkeypatch):
    """Kaohsiung feeds_into Hamburg → cascade should warn Hamburg downstream."""
    monkeypatch.chdir(REPO_ROOT)
    result = compute_cascade("APAC", fixtures_only=True)
    cascades = result["cascading_impact_warnings"]
    assert any(
        c["trigger_site_id"] == "apac-kaohsiung-mfg"
        and "nce-hamburg-mfg" in c["downstream_site_ids"]
        for c in cascades
    )


def test_cascade_records_downstream_region_when_different(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = compute_cascade("APAC", fixtures_only=True)
    kao = next(
        c for c in result["cascading_impact_warnings"]
        if c["trigger_site_id"] == "apac-kaohsiung-mfg"
    )
    assert kao["downstream_region"] == "NCE"


def test_cascade_empty_for_region_with_no_events(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    result = compute_cascade("LATAM", fixtures_only=True)
    assert result["cascading_impact_warnings"] == []


def test_dependency_graph_handles_cycles_without_infinite_loop():
    sites = [
        {"site_id": "a", "region": "X", "feeds_into": ["b"]},
        {"site_id": "b", "region": "X", "feeds_into": ["a"]},
    ]
    graph = _build_dependency_graph(sites)
    from tools.poi_proximity import _walk_downstream
    visited = _walk_downstream("a", graph, max_depth=2)
    assert "a" in visited and "b" in visited


def test_cascade_depth_capped_at_two_hops():
    sites = [
        {"site_id": "a", "region": "X", "feeds_into": ["b"]},
        {"site_id": "b", "region": "X", "feeds_into": ["c"]},
        {"site_id": "c", "region": "X", "feeds_into": ["d"]},
        {"site_id": "d", "region": "X", "feeds_into": []},
    ]
    graph = _build_dependency_graph(sites)
    from tools.poi_proximity import _walk_downstream
    visited = _walk_downstream("a", graph, max_depth=2)
    assert "b" in visited
    assert "c" in visited
    assert "d" not in visited
