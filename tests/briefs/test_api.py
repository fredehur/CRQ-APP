"""HTTP tests for `/api/briefs/*` endpoints — Phase 3+4 Reports tab redesign."""
from __future__ import annotations
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import app
from tools.briefs import storage as briefs_storage


client = TestClient(app)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_archive_with_ciso(tmp_path, monkeypatch):
    """Monkeypatch ARCHIVE_ROOT and seed two versions for `ciso`.

    Two versions are recorded >1s apart so version_ts differs at the second.
    """
    archive = tmp_path / "archive"
    monkeypatch.setattr(briefs_storage, "ARCHIVE_ROOT", archive)
    for i in range(2):
        pdf = tmp_path / f"p{i}.pdf"
        pdf.write_bytes(b"%PDF-fake-" + str(i).encode())
        png = tmp_path / f"p{i}.png"
        png.write_bytes(b"\x89PNG-fake-" + str(i).encode())
        briefs_storage.record_version(
            audience_id="ciso",
            pdf_tmp_path=pdf,
            thumbnail_tmp_path=png,
            pipeline_run_id="run-1",
            narrated=False,
            generated_by="api",
            metadata={"month": "2026-04"},
        )
        if i == 0:
            time.sleep(1.1)
    yield archive


@pytest.fixture
def tmp_archive_with_rsm_med(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    monkeypatch.setattr(briefs_storage, "ARCHIVE_ROOT", archive)
    yield archive


# ── Task 13: list + meta + versions ──────────────────────────────────────

def test_list_audiences_returns_all_seven():
    r = client.get("/api/briefs/")
    assert r.status_code == 200
    data = r.json()
    ids = {a["id"] for a in data}
    assert ids == {
        "ciso", "board",
        "rsm-apac", "rsm-ame", "rsm-latam", "rsm-med", "rsm-nce",
    }
    ciso = next(a for a in data if a["id"] == "ciso")
    assert "latest_meta" in ciso
    assert "versions" in ciso
    assert ciso["canNarrate"] is False
    rsm = next(a for a in data if a["id"] == "rsm-med")
    assert rsm["canNarrate"] is True


def test_meta_unknown_audience_returns_404():
    r = client.get("/api/briefs/unknown/meta")
    assert r.status_code == 404


def test_versions_empty_archive_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(briefs_storage, "ARCHIVE_ROOT", tmp_path / "archive")
    r = client.get("/api/briefs/ciso/versions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert r.json() == []


def test_meta_returns_latest_when_no_version_arg(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["narrated"] is False
    assert body["generated_by"] == "api"


def test_versions_stale_flag_only_on_latest(tmp_archive_with_ciso):
    # All seeded versions have pipeline_run_id="run-1"; real current_run_id
    # probably != "run-1" on the test host → latest might be stale, but
    # prior versions must be stale=False regardless.
    r = client.get("/api/briefs/ciso/versions")
    assert r.status_code == 200
    metas = r.json()
    assert len(metas) == 2
    assert metas[1]["stale"] is False


# ── Task 14: pdf + thumbnail ─────────────────────────────────────────────

def test_get_pdf_latest(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "attachment" not in r.headers.get("content-disposition", "")


def test_get_pdf_download_has_human_filename(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/pdf?download=1")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "ciso_" in cd


def test_get_pdf_specific_version(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/versions")
    assert r.status_code == 200
    older = r.json()[-1]["version_ts"]
    compact = older.replace("-", "").replace(":", "")
    r2 = client.get(f"/api/briefs/ciso/pdf?version={compact}")
    assert r2.status_code == 200
    assert r2.headers["content-type"] == "application/pdf"


def test_get_pdf_unknown_version_404(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/pdf?version=20000101T000000Z")
    assert r.status_code == 404


def test_get_pdf_unknown_audience_404():
    r = client.get("/api/briefs/unknown/pdf")
    assert r.status_code == 404


def test_get_thumbnail_serves_png(tmp_archive_with_ciso):
    r = client.get("/api/briefs/ciso/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


# ── Task 15: regenerate ──────────────────────────────────────────────────

def test_regenerate_creates_new_version(tmp_archive_with_ciso, monkeypatch):
    async def fake_render(brief, data, pdf, thumbnail_path=None):
        pdf.write_bytes(b"%PDF-fake")
        if thumbnail_path:
            thumbnail_path.write_bytes(b"\x89PNG-fake")

    monkeypatch.setattr("tools.briefs.renderer.render_pdf", fake_render)

    before = len(client.get("/api/briefs/ciso/versions").json())
    r = client.post("/api/briefs/ciso/regenerate", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "new_version" in body
    assert "versions" in body

    after = len(client.get("/api/briefs/ciso/versions").json())
    assert after == before + 1


def test_regenerate_rsm_with_narrate(tmp_archive_with_rsm_med, monkeypatch):
    captured: dict = {}

    async def fake_render(brief, data, pdf, thumbnail_path=None):
        pdf.write_bytes(b"%PDF")
        if thumbnail_path:
            thumbnail_path.write_bytes(b"\x89PNG")

    def fake_load(region, week_of=None, narrate=False):
        captured["narrate"] = narrate
        from tools.briefs.data._rsm_mock import rsm_med_w17_mock
        return rsm_med_w17_mock(), None

    monkeypatch.setattr("tools.briefs.renderer.render_pdf", fake_render)
    monkeypatch.setattr("tools.briefs.data.rsm.load_rsm_data", fake_load)

    r = client.post("/api/briefs/rsm-med/regenerate", json={"narrate": True})
    assert r.status_code == 200, r.text
    assert captured["narrate"] is True
    latest = client.get("/api/briefs/rsm-med/meta").json()
    assert latest["narrated"] is True


def test_regenerate_unknown_audience_404():
    r = client.post("/api/briefs/unknown/regenerate", json={})
    assert r.status_code == 404
