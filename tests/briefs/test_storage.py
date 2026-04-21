import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.briefs import storage


def _make_tmp_artifacts(tmp_path):
    pdf = tmp_path / "render.pdf"
    png = tmp_path / "render.png"
    pdf.write_bytes(b"%PDF-1.4 fake")
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return pdf, png


# --- Task 2: helpers + VersionRecord --------------------------------------

def test_compact_iso_roundtrip():
    iso = "2026-04-21T04:12:00Z"
    compact = storage.iso_to_compact(iso)
    assert compact == "20260421T041200Z"
    assert storage.compact_to_iso(compact) == iso


def test_compact_iso_roundtrip_with_millis():
    iso = "2026-04-21T04:12:00.123Z"
    compact = storage.iso_to_compact(iso)
    assert compact == "20260421T041200.123Z"
    assert storage.compact_to_iso(compact) == iso


def test_utc_now_iso_shape():
    now = storage.utc_now_iso()
    assert now.endswith("Z")
    parsed = datetime.strptime(now, "%Y-%m-%dT%H:%M:%S.%fZ")
    assert parsed.tzinfo is None  # naive, treated as UTC by convention


def test_version_record_fields():
    rec = storage.VersionRecord(
        audience_id="ciso",
        version_ts="2026-04-21T04:12:00Z",
        pipeline_run_id="run-0412",
        narrated=False,
        generated_by="manual",
        metadata={},
        pdf_path=Path("/x.pdf"),
        thumbnail_path=Path("/x.png"),
    )
    assert rec.version_ts == "2026-04-21T04:12:00Z"
    assert rec.narrated is False


# --- Task 3: record_version ------------------------------------------------

def test_record_version_moves_artifacts_and_writes_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)

    rec = storage.record_version(
        audience_id="ciso",
        pdf_tmp_path=pdf,
        thumbnail_tmp_path=png,
        pipeline_run_id="run-0412",
        narrated=False,
        generated_by="api",
        metadata={"month": "2026-04"},
    )

    assert rec.audience_id == "ciso"
    assert rec.pdf_path.exists()
    assert rec.thumbnail_path.exists()
    sidecar = rec.pdf_path.with_suffix(".json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["pipeline_run_id"] == "run-0412"
    assert data["narrated"] is False
    # tmp files are consumed
    assert not pdf.exists()
    assert not png.exists()


def test_record_version_sidecar_last_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)

    def boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(storage, "_write_sidecar", boom)
    with pytest.raises(OSError):
        storage.record_version(
            audience_id="ciso",
            pdf_tmp_path=pdf,
            thumbnail_tmp_path=png,
            pipeline_run_id=None,
            narrated=False,
            generated_by="api",
            metadata={},
        )
    # Nothing should linger in the archive
    audience_dir = tmp_path / "archive" / "ciso"
    if audience_dir.exists():
        assert list(audience_dir.iterdir()) == []


# --- Task 4: list_versions / get_latest / get_specific --------------------

def test_list_versions_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    for _ in range(3):
        pdf, png = _make_tmp_artifacts(tmp_path)
        storage.record_version("ciso", pdf, png, None, False, "api", {})
        # spread timestamps (file mtime is based on utc_now_iso, one-second granularity)
        time.sleep(1.1)

    versions = storage.list_versions("ciso")
    assert len(versions) == 3
    assert versions[0].version_ts > versions[1].version_ts > versions[2].version_ts


def test_list_versions_skips_orphans(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    # create one complete version
    pdf, png = _make_tmp_artifacts(tmp_path)
    storage.record_version("ciso", pdf, png, None, False, "api", {})
    # drop an orphan pdf (no sidecar)
    (tmp_path / "archive" / "ciso" / "20990101T000000Z.pdf").write_bytes(b"orphan")

    versions = storage.list_versions("ciso")
    assert len(versions) == 1


def test_get_latest_returns_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)
    first = storage.record_version("ciso", pdf, png, None, False, "api", {})
    time.sleep(1.1)
    pdf, png = _make_tmp_artifacts(tmp_path)
    second = storage.record_version("ciso", pdf, png, None, False, "api", {})
    latest = storage.get_latest("ciso")
    assert latest.version_ts == second.version_ts


def test_get_latest_empty_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    assert storage.get_latest("ciso") is None


def test_get_specific_returns_record(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)
    rec = storage.record_version("ciso", pdf, png, None, False, "api", {})
    hit = storage.get_specific("ciso", rec.version_ts)
    assert hit == rec
    miss = storage.get_specific("ciso", "2000-01-01T00:00:00Z")
    assert miss is None


# --- Task 5: prune + sweep edge cases --------------------------------------

def test_prune_keeps_newest_n(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    monkeypatch.setattr(storage, "RETENTION", 3)
    # record 5 versions
    for _ in range(5):
        pdf, png = _make_tmp_artifacts(tmp_path)
        storage.record_version("ciso", pdf, png, None, False, "api", {})
        time.sleep(1.1)
    # record_version calls prune internally; after 5 records, only 3 should remain
    versions = storage.list_versions("ciso")
    assert len(versions) == 3


def test_prune_retention_zero_keeps_all(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    monkeypatch.setattr(storage, "RETENTION", 0)
    for _ in range(4):
        pdf, png = _make_tmp_artifacts(tmp_path)
        storage.record_version("ciso", pdf, png, None, False, "api", {})
        time.sleep(1.1)
    assert len(storage.list_versions("ciso")) == 4


def test_sweep_orphans_standalone(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    d = tmp_path / "archive" / "ciso"
    d.mkdir(parents=True)
    (d / "20260421T041200Z.pdf").write_bytes(b"orphan")
    (d / "20260421T041200Z.png").write_bytes(b"orphan")
    # no sidecar
    removed = storage.sweep_orphans("ciso")
    assert removed == 2
    assert not list(d.iterdir())


def test_sweep_orphans_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    # audience dir doesn't exist
    assert storage.sweep_orphans("ciso") == 0


def test_stale_when_pipeline_run_id_is_null(tmp_path, monkeypatch):
    """Manual renders (pipeline_run_id=None) are never stale."""
    monkeypatch.setattr(storage, "ARCHIVE_ROOT", tmp_path / "archive")
    pdf, png = _make_tmp_artifacts(tmp_path)
    rec = storage.record_version("ciso", pdf, png, None, False, "manual", {})
    assert rec.pipeline_run_id is None
    # Stale computation lives in server layer; here we assert the stored null survives
    hit = storage.get_latest("ciso")
    assert hit.pipeline_run_id is None
