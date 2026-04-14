"""OSINT physical collector — mirrors cyber collector pattern. --mock path only."""
import json
from pathlib import Path
import pytest

from tools.osint_physical_collector import collect

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def chdir_repo(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)


def test_mock_collect_returns_signals_for_med(chdir_repo, tmp_path, monkeypatch):
    import tools.osint_physical_collector as mod
    monkeypatch.setattr(mod, "OUTPUT_ROOT", tmp_path)
    data = collect("MED", mock=True)
    assert data["region"] == "MED"
    assert "signals" in data
    assert isinstance(data["signals"], list)


def test_signal_shape_has_required_fields(chdir_repo, tmp_path, monkeypatch):
    import tools.osint_physical_collector as mod
    monkeypatch.setattr(mod, "OUTPUT_ROOT", tmp_path)
    data = collect("MED", mock=True)
    if data["signals"]:
        sig = data["signals"][0]
        assert "signal_id" in sig
        assert "title" in sig
        assert "category" in sig
        assert "pillar" in sig
        assert sig["pillar"] == "physical"
        assert "location" in sig


def test_writes_to_expected_path(chdir_repo, tmp_path, monkeypatch):
    import tools.osint_physical_collector as mod
    monkeypatch.setattr(mod, "OUTPUT_ROOT", tmp_path)
    collect("APAC", mock=True)
    assert (tmp_path / "regional" / "apac" / "osint_physical_signals.json").exists()


def test_invalid_region_raises(chdir_repo):
    with pytest.raises(ValueError):
        collect("XXX", mock=True)
