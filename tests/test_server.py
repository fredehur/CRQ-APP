"""Tests for new server.py endpoints added in F-2."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_output, monkeypatch):
    """TestClient with OUTPUT (and derived PIPELINE/DELIVERABLES) patched to tmp_path.

    monkeypatch.setattr patches the module-level names. Endpoint functions
    reference these at call time, so the patch takes effect without a reload.
    Do NOT call reload(server) — it would reset them back to the real paths.
    """
    import server
    monkeypatch.setattr(server, "OUTPUT", mock_output)
    monkeypatch.setattr(server, "PIPELINE", mock_output / "pipeline")
    monkeypatch.setattr(server, "DELIVERABLES", mock_output / "deliverables")
    (mock_output / "pipeline").mkdir(parents=True, exist_ok=True)
    (mock_output / "deliverables").mkdir(parents=True, exist_ok=True)
    return TestClient(server.app)


# ── /api/region/{region}/signals ─────────────────────────────────────────

def test_signals_returns_geo_and_cyber_keys(client, mock_output):
    signals_dir = mock_output / "regional" / "apac"
    signals_dir.mkdir(parents=True, exist_ok=True)
    osint = {
        "summary": "osint summary",
        "threat_vector": "phishing",
        "lead_indicators": [
            {"pillar": "geo", "text": "geo indicator"},
            {"pillar": "cyber", "text": "cyber indicator"},
        ],
    }
    (signals_dir / "osint_signals.json").write_text(json.dumps(osint), encoding="utf-8")

    resp = client.get("/api/region/APAC/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert "geo" in body
    assert "cyber" in body
    # Handler spreads osint into both pillars and partitions lead_indicators by pillar.
    assert body["geo"]["summary"] == "osint summary"
    assert body["cyber"]["threat_vector"] == "phishing"
    assert len(body["geo"]["lead_indicators"]) == 1
    assert body["geo"]["lead_indicators"][0]["pillar"] == "geo"
    assert len(body["cyber"]["lead_indicators"]) == 1
    assert body["cyber"]["lead_indicators"][0]["pillar"] == "cyber"


def test_signals_returns_empty_indicators_when_files_missing(client):
    """When osint_signals.json is absent the handler returns empty dicts, not nulls."""
    resp = client.get("/api/region/LATAM/signals")
    assert resp.status_code == 200
    body = resp.json()
    # Handler always returns dicts with empty lead_indicators — never null.
    assert body["geo"]["lead_indicators"] == []
    assert body["cyber"]["lead_indicators"] == []


def test_signals_unknown_region_returns_404(client):
    resp = client.get("/api/region/UNKNOWN/signals")
    assert resp.status_code == 404
    # Also verify the error body — FastAPI returns 404 for unregistered routes too,
    # so this test checks the handler's explicit validation, not just route absence.
    assert "error" in resp.json()


# ── /api/outputs/global-md ───────────────────────────────────────────────

def test_global_md_returns_markdown_string(client, mock_output):
    (mock_output / "pipeline" / "global_report.md").write_text(
        "# Global Report\n\nSummary here.", encoding="utf-8"
    )
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
    (mock_output / "deliverables" / "board_report.pdf").write_bytes(b"%PDF-1.4 fake")
    resp = client.get("/api/outputs/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# ── /api/outputs/pptx ────────────────────────────────────────────────────

def test_pptx_returns_404_when_missing(client):
    resp = client.get("/api/outputs/pptx")
    assert resp.status_code == 404


def test_pptx_returns_file_when_present(client, mock_output):
    (mock_output / "deliverables" / "board_report.pptx").write_bytes(b"PK fake pptx")
    resp = client.get("/api/outputs/pptx")
    assert resp.status_code == 200
    assert "officedocument" in resp.headers["content-type"]
