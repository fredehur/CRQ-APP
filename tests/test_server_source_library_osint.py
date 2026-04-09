import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    db_path = tmp_path / "sources.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE sources_registry (
            id INTEGER PRIMARY KEY,
            name TEXT, domain TEXT, tier TEXT, type TEXT,
            collection_type TEXT DEFAULT 'osint',
            blocked INTEGER DEFAULT 0
        );
        CREATE TABLE source_appearances (
            source_id INTEGER,
            region TEXT,
            pillar TEXT,
            cited INTEGER,
            run_timestamp TEXT
        );
        INSERT INTO sources_registry VALUES
            (1, 'Reuters', 'reuters.com', 'A', 'news', 'osint', 0),
            (2, 'Blog X',  'blog.example.com', 'C', 'news', 'osint', 0);
        INSERT INTO source_appearances VALUES
            (1, 'APAC', 'geo',   1, '2026-04-09T08:00:00Z'),
            (1, 'MED',  'cyber', 1, '2026-04-08T08:00:00Z'),
            (1, 'MED',  'geo',   0, '2026-04-07T08:00:00Z'),
            (2, 'APAC', 'cyber', 0, '2026-03-01T08:00:00Z');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setenv("CRQ_SOURCES_DB", str(db_path))
    from server import app
    return TestClient(app)


def test_osint_endpoint_returns_sources(client_with_db):
    r = client_with_db.get("/api/source-library/osint")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data
    assert data["total"] == 2
    ids = {s["id"] for s in data["sources"]}
    assert ids == {1, 2}


def test_osint_cited_rate_computed(client_with_db):
    r = client_with_db.get("/api/source-library/osint")
    by_id = {s["id"]: s for s in r.json()["sources"]}
    reuters = by_id[1]
    assert reuters["appearance_count"] == 3
    assert reuters["cited_count"] == 2
    assert abs(reuters["cited_rate"] - 2/3) < 0.01
    assert "both" in reuters["pillar"] or reuters["pillar"] == "both"
    assert set(reuters["regions"]) == {"APAC", "MED"}


def test_osint_lifecycle_active_vs_stale(client_with_db):
    r = client_with_db.get("/api/source-library/osint")
    by_id = {s["id"]: s for s in r.json()["sources"]}
    assert by_id[1]["lifecycle"] == "active"
    assert by_id[2]["lifecycle"] == "stale"


def test_osint_region_filter(client_with_db):
    r = client_with_db.get("/api/source-library/osint?region=MED")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()["sources"]}
    assert ids == {1}
