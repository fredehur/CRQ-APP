"""Tests for new server.py endpoints added in F-2."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_output, monkeypatch):
    """TestClient with OUTPUT patched to tmp_path.

    monkeypatch.setattr patches the module-level OUTPUT name. Endpoint functions
    reference OUTPUT at call time, so the patch takes effect without a reload.
    Do NOT call reload(server) — it would reset OUTPUT back to the real path.
    """
    import server
    monkeypatch.setattr(server, "OUTPUT", mock_output)
    return TestClient(server.app)


# ── /api/region/{region}/signals ─────────────────────────────────────────

def test_signals_returns_geo_and_cyber_keys(client, mock_output):
    signals_dir = mock_output / "regional" / "apac"
    signals_dir.mkdir(parents=True, exist_ok=True)
    geo = {"summary": "geo summary", "lead_indicators": ["indicator 1"], "dominant_pillar": "Geopolitical"}
    cyber = {"summary": "cyber summary", "threat_vector": "phishing", "target_assets": ["OT networks"]}
    (signals_dir / "geo_signals.json").write_text(json.dumps(geo), encoding="utf-8")
    (signals_dir / "cyber_signals.json").write_text(json.dumps(cyber), encoding="utf-8")

    resp = client.get("/api/region/APAC/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert "geo" in body
    assert "cyber" in body
    assert body["geo"]["summary"] == "geo summary"
    assert body["cyber"]["threat_vector"] == "phishing"


def test_signals_returns_nulls_when_files_missing(client):
    # Relies on mock_output not writing signal files for any region.
    # If conftest adds LATAM signal files, update this test.
    resp = client.get("/api/region/LATAM/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert body["geo"] is None
    assert body["cyber"] is None


def test_signals_unknown_region_returns_404(client):
    resp = client.get("/api/region/UNKNOWN/signals")
    assert resp.status_code == 404
    # Also verify the error body — FastAPI returns 404 for unregistered routes too,
    # so this test checks the handler's explicit validation, not just route absence.
    assert "error" in resp.json()


# ── /api/outputs/global-md ───────────────────────────────────────────────

def test_global_md_returns_markdown_string(client, mock_output):
    (mock_output / "global_report.md").write_text("# Global Report\n\nSummary here.", encoding="utf-8")
    resp = client.get("/api/outputs/global-md")
    assert resp.status_code == 200
    assert resp.json()["markdown"] == "# Global Report\n\nSummary here."


def test_global_md_returns_empty_when_missing(client):
    resp = client.get("/api/outputs/global-md")
    assert resp.status_code == 200
    assert resp.json()["markdown"] == ""


# ── /api/outputs/pdf ─────────────────────────────────────────────────────

def test_pdf_returns_404_when_missing(client):
    resp = client.get("/api/outputs/pdf")
    assert resp.status_code == 404


def test_pdf_returns_file_when_present(client, mock_output):
    (mock_output / "board_report.pdf").write_bytes(b"%PDF-1.4 fake")
    resp = client.get("/api/outputs/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# ── /api/outputs/pptx ────────────────────────────────────────────────────

def test_pptx_returns_404_when_missing(client):
    resp = client.get("/api/outputs/pptx")
    assert resp.status_code == 404


def test_pptx_returns_file_when_present(client, mock_output):
    (mock_output / "board_report.pptx").write_bytes(b"PK fake pptx")
    resp = client.get("/api/outputs/pptx")
    assert resp.status_code == 200
    assert "officedocument" in resp.headers["content-type"]
