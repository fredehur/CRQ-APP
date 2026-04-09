import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    vs_path = tmp_path / "validation_sources.json"
    vs_path.write_text(json.dumps({"sources": []}), encoding="utf-8")
    monkeypatch.setenv("CRQ_VALIDATION_SOURCES", str(vs_path))
    from server import app
    return TestClient(app)


def test_add_defaults_provenance_to_analyst(client):
    r = client.post("/api/validation/sources/add", json={
        "url": "https://example.com/x", "name": "My Report",
        "sector_tags": ["energy"], "scenario_tags": ["Ransomware"],
    })
    assert r.status_code == 200
    # Fetch back
    r2 = client.get("/api/validation/sources")
    srcs = r2.json()["sources"]
    assert len(srcs) == 1
    assert srcs[0]["provenance"] == "analyst"


def test_add_accepts_explicit_reliability_and_year(client):
    r = client.post("/api/validation/sources/add", json={
        "url": "https://example.com/y", "name": "Vendor Report",
        "admiralty_reliability": "A", "edition_year": 2025,
        "provenance": "vendor",
    })
    assert r.status_code == 200
    srcs = client.get("/api/validation/sources").json()["sources"]
    src = next(s for s in srcs if s["name"] == "Vendor Report")
    assert src["admiralty_reliability"] == "A"
    assert src["edition_year"] == 2025
    assert src["provenance"] == "vendor"
