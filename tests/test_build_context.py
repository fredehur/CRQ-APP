"""Tests for tools/build_context.py — Phase M"""

import json
import sys
from pathlib import Path

import pytest

import tools.build_context as bc


# ── Helpers ────────────────────────────────────────────────────────────────

MINIMAL_FOOTPRINT = {
    "APAC": {
        "summary": "Primary manufacturing region.",
        "headcount": 3200,
        "sites": [
            {"name": "Kaohsiung Manufacturing Hub", "country": "TW", "type": "manufacturing", "criticality": "primary"},
            {"name": "Shanghai Service Hub",         "country": "CN", "type": "service",       "criticality": "high"},
        ],
        "crown_jewels": ["Series 7 production line", "SCADA network TW-01"],
        "supply_chain_dependencies": ["Taiwanese semiconductor components"],
        "key_contracts": ["TEPCO 5yr turbine supply agreement"],
        "notes": "",
        "stakeholders": [
            {"role": "APAC RSM", "email": "rsm-apac@aerowind.com", "notify_on": ["escalated"]}
        ],
    }
}


def _write_footprint(tmp_path: Path, data: dict) -> Path:
    fp = tmp_path / "regional_footprint.json"
    fp.write_text(json.dumps(data), encoding="utf-8")
    return fp


def _patch(monkeypatch, tmp_path: Path, data: dict):
    fp = _write_footprint(tmp_path, data)
    output_dir = tmp_path / "output"
    monkeypatch.setattr(bc, "FOOTPRINT_FILE", fp)
    monkeypatch.setattr(bc, "OUTPUT_DIR", output_dir)
    return fp, output_dir


# ── Tests ──────────────────────────────────────────────────────────────────

def test_valid_region_writes_file(monkeypatch, tmp_path):
    """APAC → context_block.txt created at correct path."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("APAC")
    assert (output_dir / "regional" / "apac" / "context_block.txt").exists()


def test_output_contains_site_names(monkeypatch, tmp_path):
    """Block includes site names from footprint."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "Kaohsiung Manufacturing Hub" in text
    assert "Shanghai Service Hub" in text


def test_output_contains_headcount(monkeypatch, tmp_path):
    """Headcount rendered as formatted number (3,200)."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "3,200" in text


def test_gatekeeper_summary_format(monkeypatch, tmp_path):
    """build_gatekeeper_summary() returns one-liner with criticality."""
    _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    summary = bc.build_gatekeeper_summary(MINIMAL_FOOTPRINT["APAC"], "APAC")
    assert "APAC" in summary
    assert "3,200" in summary
    assert "PRIMARY" in summary or "primary" in summary.lower()
    assert "Kaohsiung" in summary


def test_unknown_region_exits_1(monkeypatch, tmp_path, capsys):
    """Unknown region → exit 1 with stderr message."""
    _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    with pytest.raises(SystemExit) as exc:
        bc.build_context("UNKNOWN")
    assert exc.value.code == 1


def test_missing_footprint_file_exits_1(monkeypatch, tmp_path):
    """No regional_footprint.json → exit 1."""
    monkeypatch.setattr(bc, "FOOTPRINT_FILE", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(bc, "OUTPUT_DIR", tmp_path / "output")
    with pytest.raises(SystemExit) as exc:
        bc.build_context("APAC")
    assert exc.value.code == 1


def test_empty_region_writes_empty_block(monkeypatch, tmp_path):
    """Region absent from file → empty context_block.txt, exit 0."""
    _, output_dir = _patch(monkeypatch, tmp_path, MINIMAL_FOOTPRINT)
    bc.build_context("NCE")  # NCE not in MINIMAL_FOOTPRINT
    block = (output_dir / "regional" / "nce" / "context_block.txt").read_text(encoding="utf-8")
    assert block == ""


def test_notes_field_appended_verbatim(monkeypatch, tmp_path):
    """Notes text appears unchanged in output block."""
    data = json.loads(json.dumps(MINIMAL_FOOTPRINT))
    data["APAC"]["notes"] = "Major turbine order Q2 — supply chain under pressure."
    _, output_dir = _patch(monkeypatch, tmp_path, data)
    bc.build_context("APAC")
    text = (output_dir / "regional" / "apac" / "context_block.txt").read_text(encoding="utf-8")
    assert "Major turbine order Q2 — supply chain under pressure." in text
