import json
from pathlib import Path
import pytest
from tools.briefs import pipeline_state


def test_global_run_id_reads_last_run_log(tmp_path, monkeypatch):
    log = tmp_path / "pipeline" / "last_run_log.json"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"run_id": "run-2026-04-21-0412"}))
    monkeypatch.setattr(pipeline_state, "PIPELINE_LOG", log)
    assert pipeline_state.global_run_id() == "run-2026-04-21-0412"


def test_global_run_id_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "PIPELINE_LOG", tmp_path / "nope.json")
    assert pipeline_state.global_run_id() is None


def test_region_run_id_reads_regional_meta(tmp_path, monkeypatch):
    meta = tmp_path / "regional" / "med" / "meta.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"run_id": "run-med-0412"}))
    monkeypatch.setattr(pipeline_state, "REGIONAL_ROOT", tmp_path / "regional")
    assert pipeline_state.region_run_id("med") == "run-med-0412"


def test_region_run_id_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "REGIONAL_ROOT", tmp_path / "regional")
    assert pipeline_state.region_run_id("med") is None


def test_current_run_id_routes_by_audience(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "global_run_id", lambda: "G")
    monkeypatch.setattr(pipeline_state, "region_run_id", lambda r: f"R-{r}")
    assert pipeline_state.current_run_id("ciso") == "G"
    assert pipeline_state.current_run_id("board") == "G"
    assert pipeline_state.current_run_id("rsm-med") == "R-med"


def test_current_run_id_unknown_audience_raises():
    with pytest.raises(ValueError):
        pipeline_state.current_run_id("unknown")


def test_write_region_meta_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_state, "REGIONAL_ROOT", tmp_path / "regional")
    pipeline_state.write_region_meta("med", "run-0412")
    assert pipeline_state.region_run_id("med") == "run-0412"
