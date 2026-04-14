"""rsm_dispatcher --weekly: full INTSUM with new sections."""
import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def chdir_repo(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)


def test_weekly_mock_brief_contains_region(chdir_repo, tmp_path, monkeypatch):
    """The mock weekly brief via _invoke_formatter must at least include the region."""
    from tools.rsm_dispatcher import _invoke_formatter
    monkeypatch.setattr("tools.rsm_dispatcher.OUTPUT_ROOT", tmp_path)
    out_dir = tmp_path / "regional" / "apac"
    out_dir.mkdir(parents=True)
    brief_path = out_dir / "rsm_brief_apac_2026-04-14.md"
    decision = {
        "region": "APAC", "product": "weekly_intsum",
        "brief_path": str(brief_path), "audience": "rsm_apac",
    }
    _invoke_formatter(decision, mock=True)
    assert brief_path.exists()
    body = brief_path.read_text(encoding="utf-8")
    assert "APAC" in body
    assert "weekly_intsum" in body.lower() or "INTSUM" in body or "[MOCK]" in body
