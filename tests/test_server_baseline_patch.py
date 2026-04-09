import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point the app at a temp register file
    reg_dir = tmp_path / "data" / "registers"
    reg_dir.mkdir(parents=True)
    (reg_dir / "test_reg.json").write_text(json.dumps({
        "register_id": "test_reg",
        "display_name": "Test Reg",
        "scenarios": [
            {"scenario_id": "T-1", "scenario_name": "Ransomware",
             "value_at_cyber_risk_usd": 5_000_000, "probability_pct": 12.0},
        ],
    }), encoding="utf-8")
    monkeypatch.setenv("CRQ_REGISTERS_DIR", str(reg_dir))
    from server import app
    return TestClient(app)


def test_patch_baseline_happy_path(client):
    body = {
        "fin":  {"value_usd": 4_200_000, "low_usd": 1_800_000, "high_usd": 7_500_000,
                 "source_ids": ["verizon-dbir"], "notes": "ok"},
        "prob": {"annual_rate": 0.12, "low": 0.08, "high": 0.18,
                 "evidence_type": "frequency_rate", "source_ids": []},
    }
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["analyst_baseline"]["fin"]["value_usd"] == 4_200_000
    assert data["analyst_baseline"]["fin"]["updated_by"] == "analyst"
    assert data["analyst_baseline"]["fin"]["updated"]  # ISO date
    assert data["analyst_baseline"]["prob"]["evidence_type"] == "frequency_rate"


def test_patch_baseline_422_when_low_gt_value(client):
    body = {"fin": {"value_usd": 1_000_000, "low_usd": 5_000_000, "high_usd": 7_500_000}}
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json=body)
    assert r.status_code == 422


def test_patch_baseline_422_when_prob_out_of_range(client):
    body = {"prob": {"annual_rate": 1.5, "low": 0.08, "high": 0.18, "evidence_type": "frequency_rate"}}
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json=body)
    assert r.status_code == 422


def test_patch_baseline_422_when_empty_body(client):
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json={})
    assert r.status_code == 422


def test_patch_baseline_null_clears(client):
    client.patch("/api/registers/test_reg/scenarios/0/baseline", json={
        "fin": {"value_usd": 1, "low_usd": 1, "high_usd": 1}
    })
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json=None)
    assert r.status_code == 200
    assert r.json()["analyst_baseline"] is None


def test_patch_baseline_invalid_evidence_type(client):
    body = {"prob": {"annual_rate": 0.1, "low": 0.05, "high": 0.2, "evidence_type": "bogus"}}
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json=body)
    assert r.status_code == 422


def test_patch_baseline_notes_too_long(client):
    body = {"fin": {"value_usd": 1_000, "low_usd": 1_000, "high_usd": 1_000, "notes": "x" * 1001}}
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json=body)
    assert r.status_code == 422


def test_patch_baseline_orphan_source_id_accepted(client):
    body = {"fin": {"value_usd": 1_000, "low_usd": 500, "high_usd": 2_000, "source_ids": ["does-not-exist"]}}
    r = client.patch("/api/registers/test_reg/scenarios/0/baseline", json=body)
    assert r.status_code == 200
    assert r.json()["analyst_baseline"]["fin"]["source_ids"] == ["does-not-exist"]
