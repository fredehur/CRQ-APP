import json

from tools.register_validator import build_run_summary, RunCounters


def test_build_run_summary_first_run_null_prev(tmp_path):
    counters = RunCounters(
        fin_extracted=10, prob_extracted=6,
        fin_after_iqr_filter=8, prob_after_iqr_filter=5, outliers_removed=3,
    )
    counters.queried_source_ids.update({"verizon-dbir", "ibm-cost-data-breach"})
    counters.matched_source_ids.add("verizon-dbir")

    register = {
        "register_id": "wind_power_plant",
        "display_name": "Wind Power Plant",
        "scenarios": [
            {"scenario_name": "Ransomware",        "search_tags": ["ransomware"]},
            {"scenario_name": "System intrusion",  "search_tags": ["system_intrusion"]},
        ],
    }
    current_results = [
        {"scenario_name": "Ransomware",       "financial": {"verdict": "supports"},     "probability": {"verdict": "insufficient"}},
        {"scenario_name": "System intrusion", "financial": {"verdict": "insufficient"}, "probability": {"verdict": "insufficient"}},
    ]
    val_sources = [
        {"id": "verizon-dbir",        "name": "Verizon DBIR",   "tier": "A", "admiralty_reliability": "A"},
        {"id": "ibm-cost-data-breach","name": "IBM",            "tier": "A", "admiralty_reliability": "A"},
    ]

    summary = build_run_summary(
        register=register,
        current_results=current_results,
        previous_path=tmp_path / "does_not_exist.json",
        counters=counters,
        duration_seconds=142,
        val_sources=val_sources,
        orphan_source_warnings=[],
    )

    assert summary["run_id"]  # ISO8601 string, non-empty
    assert summary["previous_run_id"] is None
    assert summary["register_id"] == "wind_power_plant"
    assert summary["register_name"] == "Wind Power Plant"
    assert summary["duration_seconds"] == 142
    assert summary["scenarios"] == {"total": 2, "validated": 2, "skipped": 0}
    assert summary["verdicts"]["current"] == {"support": 1, "challenge": 0, "insufficient": 3}
    assert summary["verdicts"]["previous"] is None
    assert summary["verdicts"]["deltas"] == []
    assert summary["sources"]["queried"] == 2
    assert summary["sources"]["matched"] == 1
    assert summary["sources"]["new_this_run"] == []
    assert summary["sources"]["dropped_this_run"] == []
    assert summary["sources"]["by_tier"] == {"A": 1}  # matched set only
    assert summary["evidence"] == {
        "fin_extracted": 10, "prob_extracted": 6,
        "fin_after_iqr_filter": 8, "prob_after_iqr_filter": 5, "outliers_removed": 3,
    }
    assert summary["errors"] == []


def test_build_run_summary_computes_deltas_from_prior(tmp_path):
    counters = RunCounters()
    prior = {
        "register_id": "wind_power_plant",
        "run_summary": {
            "run_id": "2026-04-08T09:11:47Z",
            "verdicts": {"current": {"support": 0, "challenge": 0, "insufficient": 4}},
            "sources": {"matched_ids": ["old-source"]},
        },
        "scenarios": [
            {"scenario_name": "Ransomware",
             "financial": {"verdict": "insufficient"}, "probability": {"verdict": "insufficient"}},
            {"scenario_name": "System intrusion",
             "financial": {"verdict": "insufficient"}, "probability": {"verdict": "insufficient"}},
        ],
    }
    prior_path = tmp_path / "register_validation.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")

    register = {
        "register_id": "wind_power_plant",
        "display_name": "Wind Power Plant",
        "scenarios": [
            {"scenario_name": "Ransomware", "search_tags": []},
            {"scenario_name": "System intrusion", "search_tags": []},
        ],
    }
    current_results = [
        {"scenario_name": "Ransomware",       "financial": {"verdict": "supports"},     "probability": {"verdict": "insufficient"}},
        {"scenario_name": "System intrusion", "financial": {"verdict": "insufficient"}, "probability": {"verdict": "insufficient"}},
    ]
    counters.matched_source_ids.add("verizon-dbir")

    summary = build_run_summary(
        register=register,
        current_results=current_results,
        previous_path=prior_path,
        counters=counters,
        duration_seconds=100,
        val_sources=[{"id": "verizon-dbir", "name": "Verizon DBIR", "admiralty_reliability": "A"}],
        orphan_source_warnings=[],
    )

    assert summary["previous_run_id"] == "2026-04-08T09:11:47Z"
    # Ransomware fin improved from insufficient -> support
    deltas = summary["verdicts"]["deltas"]
    assert any(
        d["scenario"] == "Ransomware" and d["dim"] == "fin"
        and d["from"] == "insufficient" and d["to"] == "support"
        and d["direction"] == "improved"
        for d in deltas
    )
    assert summary["sources"]["new_this_run"] == [{"id": "verizon-dbir", "name": "Verizon DBIR", "tier": "A"}]
    assert summary["sources"]["dropped_this_run"] == [{"id": "old-source", "name": "old-source", "reason": "not_cited"}]


def test_build_run_summary_normalizes_verdict_case():
    # existing code uses 'supports'/'challenges' — summary must normalize to support/challenge
    counters = RunCounters()
    register = {"register_id": "r", "display_name": "R", "scenarios": [{"scenario_name": "X", "search_tags": []}]}
    current = [{"scenario_name": "X", "financial": {"verdict": "challenges"}, "probability": {"verdict": "supports"}}]
    summary = build_run_summary(
        register=register, current_results=current, previous_path=None,
        counters=counters, duration_seconds=1, val_sources=[], orphan_source_warnings=[],
    )
    assert summary["verdicts"]["current"]["challenge"] == 1
    assert summary["verdicts"]["current"]["support"] == 1
    assert summary["verdicts"]["current"]["insufficient"] == 0
