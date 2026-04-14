"""End-to-end: 5 regions × daily run in parallel via asyncio.gather, no contamination, all logged."""
import json
import time
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ALL_REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]


@pytest.fixture
def staged_pipeline(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr("tools.rsm_dispatcher.OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr("tools.rsm_dispatcher.DELIVERY_LOG_PATH", tmp_path / "delivery_log.json")
    for region in ALL_REGIONS:
        rd = tmp_path / "regional" / region.lower()
        rd.mkdir(parents=True)
        (rd / "data.json").write_text(json.dumps({"region": region,
            "primary_scenario": "n/a", "financial_rank": 0, "admiralty": "C3", "velocity": "stable"}))
        (rd / "osint_signals.json").write_text(json.dumps({"signals": []}))
    return tmp_path


def test_all_five_regions_run(staged_pipeline):
    from tools.rsm_dispatcher import dispatch_daily
    written = dispatch_daily(regions=None, mock=True)
    assert len(written) == 5
    assert {p.parent.name for p in written} == {r.lower() for r in ALL_REGIONS}


def test_no_cross_region_contamination_at_scale(staged_pipeline):
    """No brief in any region body names a site that belongs to a different region."""
    from tools.rsm_dispatcher import dispatch_daily
    sites = json.loads((REPO_ROOT / "data" / "aerowind_sites.json").read_text(encoding="utf-8"))["sites"]
    by_region = {}
    for s in sites:
        by_region.setdefault(s["region"], []).append(s["name"])

    written = dispatch_daily(regions=None, mock=True)
    for brief in written:
        region = brief.parent.name.upper()
        body = brief.read_text(encoding="utf-8")
        for other_region, names in by_region.items():
            if other_region == region:
                continue
            for name in names:
                assert name not in body, (
                    f"{brief.name} contains off-region site '{name}' (belongs to {other_region})"
                )


def test_all_deliveries_logged(staged_pipeline):
    from tools.rsm_dispatcher import dispatch_daily
    import tools.rsm_dispatcher as mod
    dispatch_daily(regions=None, mock=True)
    log_path = mod.DELIVERY_LOG_PATH
    rows = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 5
    assert {r["region"] for r in rows} == set(ALL_REGIONS)


def test_parallel_run_completes_under_serial_threshold(staged_pipeline):
    """5 regions in parallel should finish well under a sane upper bound."""
    from tools.rsm_dispatcher import dispatch_daily
    t0 = time.perf_counter()
    dispatch_daily(regions=None, mock=True)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"parallel daily took {elapsed:.2f}s — too slow"
