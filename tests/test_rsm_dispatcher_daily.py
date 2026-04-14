"""rsm_dispatcher --daily: per-region brief, empty stub on quiet day, full brief on populated day."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def chdir_repo(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)


def test_dispatcher_daily_writes_brief_for_populated_region(chdir_repo, tmp_path, monkeypatch):
    from tools.rsm_dispatcher import dispatch_daily
    monkeypatch.setattr("tools.rsm_dispatcher.OUTPUT_ROOT", tmp_path)
    med = tmp_path / "regional" / "med"
    med.mkdir(parents=True)
    (med / "data.json").write_text(json.dumps({
        "region": "MED", "primary_scenario": "Port disruption", "financial_rank": 2,
        "admiralty": "B2", "velocity": "stable"
    }))
    (med / "osint_signals.json").write_text(json.dumps({"signals": [{"id": "x"}]}))

    written = dispatch_daily(regions=["MED"], mock=True)
    assert any("med" in str(p).lower() for p in written)
    assert all(p.exists() for p in written)


def test_dispatcher_daily_writes_empty_stub_when_no_signals(chdir_repo, tmp_path, monkeypatch):
    from tools.rsm_dispatcher import dispatch_daily
    monkeypatch.setattr("tools.rsm_dispatcher.OUTPUT_ROOT", tmp_path)
    latam = tmp_path / "regional" / "latam"
    latam.mkdir(parents=True)
    (latam / "data.json").write_text(json.dumps({
        "region": "LATAM", "primary_scenario": "n/a", "financial_rank": 0,
        "admiralty": "C3", "velocity": "stable"
    }))
    (latam / "osint_signals.json").write_text(json.dumps({"signals": []}))

    written = dispatch_daily(regions=["LATAM"], mock=True)
    assert len(written) == 1
    body = written[0].read_text(encoding="utf-8")
    assert "Nothing to escalate. Next check 24h." in body
    assert "NEW: 0 EVT" in body


def test_dispatcher_daily_runs_all_five_regions_in_parallel(chdir_repo, tmp_path, monkeypatch):
    from tools.rsm_dispatcher import dispatch_daily
    monkeypatch.setattr("tools.rsm_dispatcher.OUTPUT_ROOT", tmp_path)
    for region in ["apac", "ame", "latam", "med", "nce"]:
        rd = tmp_path / "regional" / region
        rd.mkdir(parents=True)
        (rd / "data.json").write_text(json.dumps({
            "region": region.upper(), "primary_scenario": "n/a",
            "financial_rank": 0, "admiralty": "C3", "velocity": "stable"
        }))
        (rd / "osint_signals.json").write_text(json.dumps({"signals": []}))

    written = dispatch_daily(regions=None, mock=True)
    assert len(written) == 5
    region_names = {p.parent.name for p in written}
    assert region_names == {"apac", "ame", "latam", "med", "nce"}


def test_no_cross_region_contamination(chdir_repo, tmp_path, monkeypatch):
    """No brief in any region body names sites from other regions."""
    from tools.rsm_dispatcher import dispatch_daily
    monkeypatch.setattr("tools.rsm_dispatcher.OUTPUT_ROOT", tmp_path)
    for region in ["apac", "med"]:
        rd = tmp_path / "regional" / region
        rd.mkdir(parents=True)
        (rd / "data.json").write_text(json.dumps({"region": region.upper(),
            "primary_scenario": "n/a", "financial_rank": 0, "admiralty": "C3", "velocity": "stable"}))
        (rd / "osint_signals.json").write_text(json.dumps({"signals": []}))
    written = dispatch_daily(regions=["APAC", "MED"], mock=True)
    apac_brief = next(p for p in written if "apac" in str(p).lower())
    med_brief = next(p for p in written if "med" in str(p).lower())
    assert "Casablanca" not in apac_brief.read_text(encoding="utf-8")
    assert "Kaohsiung" not in med_brief.read_text(encoding="utf-8")
