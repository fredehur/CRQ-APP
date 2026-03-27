import pytest
from fastapi.testclient import TestClient
import json
import os
from server import app

client = TestClient(app)


def test_clusters_endpoint_no_data():
    """Returns empty clusters object when signal_clusters.json does not exist."""
    r = client.get("/api/region/LATAM/clusters")
    assert r.status_code == 200
    body = r.json()
    assert "region" in body
    assert body["region"] == "LATAM"


def test_clusters_endpoint_invalid_region():
    """Returns 404 for unknown region."""
    r = client.get("/api/region/INVALID/clusters")
    assert r.status_code == 404


def test_run_all_accepts_window_param():
    """POST /api/run/all accepts window query param without error."""
    r = client.post("/api/run/all?mode=tools&window=7d")
    # May return 409 if pipeline is running — that's fine, it means the endpoint accepted the param
    assert r.status_code in (200, 409)


def test_run_all_rejects_invalid_window():
    """POST /api/run/all rejects invalid window value."""
    r = client.post("/api/run/all?mode=tools&window=99x")
    assert r.status_code == 422  # FastAPI validation error


def test_run_region_accepts_window_param():
    """POST /api/run/region/LATAM accepts window query param without error."""
    r = client.post("/api/run/region/LATAM?mode=tools&window=30d")
    assert r.status_code in (200, 409)


def test_run_region_rejects_invalid_window():
    """POST /api/run/region/APAC rejects invalid window value."""
    r = client.post("/api/run/region/APAC?mode=tools&window=bad")
    assert r.status_code == 422


# ── Feedback endpoints ────────────────────────────────────────────────────

def test_get_feedback_unknown_run_returns_404():
    """GET /api/feedback/{run_id} for an unknown run_id returns 404."""
    r = client.get("/api/feedback/nonexistent-run-id-xyz")
    assert r.status_code == 404


def test_get_feedback_returns_empty_list_when_no_feedback(tmp_path, monkeypatch):
    """GET /api/feedback/{run_id} returns [] when run exists but has no feedback.json."""
    import server
    runs_dir = tmp_path / "output" / "runs" / "2026-03-27_100000Z"
    runs_dir.mkdir(parents=True)
    manifest = {"pipeline_id": "crq-test-run-001"}
    (runs_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(server, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(server, "BASE", tmp_path)

    r = client.get("/api/feedback/crq-test-run-001")
    assert r.status_code == 200
    assert r.json() == []


def test_post_feedback_rejects_invalid_rating(tmp_path, monkeypatch):
    """POST /api/feedback/{run_id} returns 400 for an invalid rating."""
    import server
    runs_dir = tmp_path / "output" / "runs" / "2026-03-27_100000Z"
    runs_dir.mkdir(parents=True)
    manifest = {"pipeline_id": "crq-test-run-002"}
    (runs_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(server, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(server, "BASE", tmp_path)

    r = client.post(
        "/api/feedback/crq-test-run-002",
        json={"region": "APAC", "rating": "garbage"},
    )
    assert r.status_code == 400


def test_post_feedback_rejects_invalid_region(tmp_path, monkeypatch):
    """POST /api/feedback/{run_id} returns 400 for an invalid region."""
    import server
    runs_dir = tmp_path / "output" / "runs" / "2026-03-27_100000Z"
    runs_dir.mkdir(parents=True)
    manifest = {"pipeline_id": "crq-test-run-003"}
    (runs_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(server, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(server, "BASE", tmp_path)

    r = client.post(
        "/api/feedback/crq-test-run-003",
        json={"region": "INVALID", "rating": "accurate"},
    )
    assert r.status_code == 400


def test_post_and_get_feedback_roundtrip(tmp_path, monkeypatch):
    """POST then GET feedback returns the submitted entry."""
    import server
    runs_dir = tmp_path / "output" / "runs" / "2026-03-27_100000Z"
    runs_dir.mkdir(parents=True)
    manifest = {"pipeline_id": "crq-test-run-004"}
    (runs_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    monkeypatch.setattr(server, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(server, "BASE", tmp_path)

    post_r = client.post(
        "/api/feedback/crq-test-run-004",
        json={"region": "AME", "rating": "overstated", "note": "Severity too high"},
    )
    assert post_r.status_code == 200
    assert post_r.json()["ok"] is True

    get_r = client.get("/api/feedback/crq-test-run-004")
    assert get_r.status_code == 200
    entries = get_r.json()
    assert len(entries) == 1
    assert entries[0]["region"] == "AME"
    assert entries[0]["rating"] == "overstated"
    assert entries[0]["note"] == "Severity too high"


def test_post_feedback_unknown_run_returns_404():
    """POST /api/feedback/{run_id} for an unknown run_id returns 404."""
    r = client.post(
        "/api/feedback/nonexistent-run-xyz",
        json={"region": "APAC", "rating": "accurate"},
    )
    assert r.status_code == 404
