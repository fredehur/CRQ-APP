from tools.register_validator import (
    compute_baseline_alignment,
    format_baseline_summary,
    resolve_baseline_orphans,
)


def test_alignment_aligned_when_ranges_overlap():
    baseline = {"low_usd": 3_000_000, "value_usd": 5_000_000, "high_usd": 8_000_000}
    osint_range = [4_000_000, 9_000_000]
    assert compute_baseline_alignment(baseline, osint_range, kind="fin") == "aligned"


def test_alignment_diverged_when_ranges_disjoint():
    baseline = {"low_usd": 1_000_000, "value_usd": 2_000_000, "high_usd": 3_000_000}
    osint_range = [5_000_000, 9_000_000]
    assert compute_baseline_alignment(baseline, osint_range, kind="fin") == "diverged"


def test_alignment_na_when_baseline_missing():
    assert compute_baseline_alignment(None, [1, 2], kind="fin") == "n/a"


def test_alignment_na_when_osint_empty():
    baseline = {"low_usd": 1, "value_usd": 2, "high_usd": 3}
    assert compute_baseline_alignment(baseline, [], kind="fin") == "n/a"


def test_prob_alignment_uses_annual_rate_fields():
    baseline = {"low": 0.08, "annual_rate": 0.12, "high": 0.18}
    osint_range_pct = [10.0, 15.0]  # percent — function converts baseline to pct
    assert compute_baseline_alignment(baseline, osint_range_pct, kind="prob") == "aligned"


def test_format_baseline_summary_fin_none():
    assert format_baseline_summary(None, kind="fin") == "none"


def test_format_baseline_summary_fin_present():
    b = {"value_usd": 4_200_000, "low_usd": 1_800_000, "high_usd": 7_500_000, "source_ids": ["a", "b"]}
    out = format_baseline_summary(b, kind="fin")
    assert "$4.2M" in out
    assert "1.8" in out
    assert "7.5" in out
    assert "2 sources" in out


def test_format_baseline_summary_prob_present():
    b = {"annual_rate": 0.12, "low": 0.08, "high": 0.18, "evidence_type": "frequency_rate", "source_ids": ["x"]}
    out = format_baseline_summary(b, kind="prob")
    assert "0.12" in out
    assert "frequency_rate" in out
    assert "1 source" in out


def test_resolve_baseline_orphans_flags_missing_ids():
    baseline = {
        "fin":  {"source_ids": ["verizon-dbir", "my-internal-2026"]},
        "prob": {"source_ids": ["dragos-ics-ot"]},
    }
    val_sources_by_id = {"verizon-dbir": {}, "dragos-ics-ot": {}}
    orphans = resolve_baseline_orphans(scenario_name="Ransomware", baseline=baseline, val_sources_by_id=val_sources_by_id)
    assert len(orphans) == 1
    assert orphans[0]["type"] == "baseline_orphan_source"
    assert orphans[0]["scenario"] == "Ransomware"
    assert orphans[0]["source_id"] == "my-internal-2026"
    assert orphans[0]["dim"] == "fin"
