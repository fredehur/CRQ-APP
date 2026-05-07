"""Integration tests for `tools.build_pdf` CLI.

These tests invoke the CLI as a subprocess. They are slow — they actually render
a PDF via Playwright. They are marked as integration tests; skip with `-k "not build_pdf"`
if needed.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.integration
def test_build_pdf_archives_by_default(tmp_path, monkeypatch):
    """With no --out and no --no-archive, CLI writes to the archive and exits 0."""
    monkeypatch.setenv("BRIEFS_RETENTION", "5")
    result = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf",
         "--brief", "rsm", "--region", "MED", "--mock"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # Confirm something was written under output/deliverables/archive/rsm-med/
    archive_dir = REPO_ROOT / "output" / "deliverables" / "archive" / "rsm-med"
    assert archive_dir.exists(), f"archive dir missing: {archive_dir}"
    pdfs = list(archive_dir.glob("*.pdf"))
    assert pdfs, "no PDF archived"


@pytest.mark.integration
def test_build_pdf_no_archive_flag(tmp_path):
    """--no-archive + --out writes only to the out path."""
    out = tmp_path / "ad_hoc.pdf"
    result = subprocess.run(
        [sys.executable, "-m", "tools.build_pdf",
         "--brief", "rsm", "--region", "MED", "--mock",
         "--out", str(out), "--no-archive"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert out.stat().st_size > 0
