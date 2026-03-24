import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

import server
from server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _patch_output(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "OUTPUT", tmp_path / "output")


def _make_rsm_files(tmp_path, region, intsum=True, flash=False):
    """Create stub RSM brief files under tmp_path/output/regional/{region}/"""
    r = region.lower()
    base = tmp_path / "output" / "regional" / r
    base.mkdir(parents=True, exist_ok=True)
    if intsum:
        (base / f"rsm_brief_{r}_2026-03-20.md").write_text(
            f"AEROWIND // {region} INTSUM // WK12-2026\n█ SITUATION\nAll clear.",
            encoding="utf-8",
        )
    if flash:
        (base / f"rsm_flash_{r}_2026-03-20-1400z.md").write_text(
            f"AEROWIND // {region} FLASH // 2026-03-20 14:00Z\nTRIGGER: test",
            encoding="utf-8",
        )


def test_rsm_status_all_missing(tmp_path):
    r = client.get("/api/rsm/status")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"APAC", "AME", "LATAM", "MED", "NCE"}
    for v in data.values():
        assert v["has_flash"] is False
        assert v["has_intsum"] is False


def test_rsm_status_intsum_present(tmp_path):
    _make_rsm_files(tmp_path, "APAC", intsum=True, flash=False)
    r = client.get("/api/rsm/status")
    assert r.status_code == 200
    data = r.json()
    assert data["APAC"]["has_intsum"] is True
    assert data["APAC"]["has_flash"] is False
    assert data["AME"]["has_intsum"] is False


def test_rsm_status_flash_present(tmp_path):
    _make_rsm_files(tmp_path, "AME", intsum=True, flash=True)
    r = client.get("/api/rsm/status")
    assert r.status_code == 200
    data = r.json()
    assert data["AME"]["has_flash"] is True
    assert data["AME"]["has_intsum"] is True
