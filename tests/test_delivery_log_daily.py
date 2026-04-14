"""delivery_log.json must record every daily brief — even empty stubs — with region + cadence."""
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dispatch_daily_writes_delivery_log_row(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    from tools.rsm_dispatcher import dispatch_daily
    monkeypatch.setattr("tools.rsm_dispatcher.OUTPUT_ROOT", tmp_path)
    log_path = tmp_path / "delivery_log.json"
    monkeypatch.setattr("tools.rsm_dispatcher.DELIVERY_LOG_PATH", log_path)

    for region in ["apac", "med"]:
        rd = tmp_path / "regional" / region
        rd.mkdir(parents=True)
        (rd / "data.json").write_text(json.dumps({"region": region.upper(),
            "primary_scenario": "n/a", "financial_rank": 0, "admiralty": "C3", "velocity": "stable"}))
        (rd / "osint_signals.json").write_text(json.dumps({"signals": []}))

    dispatch_daily(regions=["APAC", "MED"], mock=True)

    assert log_path.exists()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    regions_logged = {r["region"] for r in rows}
    assert regions_logged == {"APAC", "MED"}
    cadences = {r["cadence"] for r in rows}
    assert cadences == {"daily"}
    statuses = {r["status"] for r in rows}
    assert "stub" in statuses or "delivered" in statuses
