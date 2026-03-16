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
