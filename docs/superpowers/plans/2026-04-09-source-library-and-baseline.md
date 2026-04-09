# Source Library + Analyst Baseline + Run Summary Implementation Plan

**Goal:** Rename Source Audit → Source Library with OSINT / Benchmarks sub-tabs, add a two-layer analyst baseline (global source provenance + per-register figures) to `register_validator.py`, and surface a deterministic post-validation Run Summary card on the Risk Register tab.

**Architecture:** Pure code, zero new agents. `register_validator.py` gains `RunCounters` instrumentation, a `build_run_summary()` post-pass, and baseline threading into the existing Sonnet recommendation prompt. `server.py` gains three new endpoints plus a tiny `provenance_default()` helper. `static/app.js` + `index.html` get restructured: dead Risk Register source-registry code out, Source Library sub-tabs + baseline editor + run summary card in. Units are sequenced: Unit 1 (validator) → Unit 2 (endpoints) → Unit 3 (Source Library UI) → Unit 4 (Risk Register UI, depends on Unit 3's shared modal).

**Tech Stack:** Python 3 (uv) · FastAPI · SQLite (`data/sources.db`) · vanilla JS · pytest · Tavily search

**Spec:** `docs/superpowers/specs/2026-04-09-source-library-and-baseline-design.md`

---

## Unit 1 — Validator Backend (`tools/register_validator.py`)

### Task 1: Add `RunCounters` dataclass + wire into `main()`

**Goal:** Instrument figure-collection and IQR-filter points so the run summary can report `fin_extracted`, `prob_extracted`, `fin_after_iqr_filter`, `prob_after_iqr_filter`, `outliers_removed`.

**Files:**
- Modify: `tools/register_validator.py` (add class near top, thread into `validate_scenario` + `filter_outliers`)
- Test: `tests/test_register_validator_counters.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_register_validator_counters.py
from tools.register_validator import RunCounters, filter_outliers_with_counter


def test_run_counters_defaults_to_zero():
    c = RunCounters()
    assert c.fin_extracted == 0
    assert c.prob_extracted == 0
    assert c.fin_after_iqr_filter == 0
    assert c.prob_after_iqr_filter == 0
    assert c.outliers_removed == 0


def test_filter_outliers_with_counter_increments_removed():
    c = RunCounters()
    # 5 values — one obvious outlier
    filtered = filter_outliers_with_counter([10.0, 11.0, 12.0, 13.0, 999.0], c, dim="fin")
    assert c.fin_extracted == 5
    assert c.fin_after_iqr_filter == len(filtered)
    assert c.outliers_removed == 5 - len(filtered)


def test_filter_outliers_with_counter_fewer_than_4_no_filter():
    c = RunCounters()
    filtered = filter_outliers_with_counter([10.0, 11.0, 12.0], c, dim="prob")
    assert filtered == [10.0, 11.0, 12.0]
    assert c.prob_extracted == 3
    assert c.prob_after_iqr_filter == 3
    assert c.outliers_removed == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_register_validator_counters.py -v`
Expected: FAIL with `ImportError: cannot import name 'RunCounters'`

- [ ] **Step 3: Add `RunCounters` + `filter_outliers_with_counter` to `register_validator.py`**

Insert this block immediately after the `_PHASE2_QUERY_CAP = 3` constant (around line 33):

```python
from dataclasses import dataclass, field


@dataclass
class RunCounters:
    """Mutable counters shared across scenario validation to build run_summary.evidence."""
    fin_extracted: int = 0
    prob_extracted: int = 0
    fin_after_iqr_filter: int = 0
    prob_after_iqr_filter: int = 0
    outliers_removed: int = 0
    queried_source_ids: set = field(default_factory=set)
    matched_source_ids: set = field(default_factory=set)
```

Then, immediately after the existing `filter_outliers` function (around line 367), add:

```python
def filter_outliers_with_counter(values: list[float], counters: "RunCounters", dim: str) -> list[float]:
    """IQR filter that updates counters. `dim` is 'fin' or 'prob'."""
    incoming = len(values)
    if dim == "fin":
        counters.fin_extracted += incoming
    elif dim == "prob":
        counters.prob_extracted += incoming
    filtered = filter_outliers(values)
    kept = len(filtered)
    if dim == "fin":
        counters.fin_after_iqr_filter += kept
    elif dim == "prob":
        counters.prob_after_iqr_filter += kept
    counters.outliers_removed += (incoming - kept)
    return filtered
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_register_validator_counters.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Thread counters through `validate_scenario` + `main()`**

In `main()` (line 741), after `register = load_active_register()`, add:

```python
    counters = RunCounters()
    run_started_monotonic = time.monotonic()
```

Add `import time` to the import block at the top if not already present.

Change `validate_scenario` signature (line 574) from:
```python
def validate_scenario(conn, scenario, register):
```
to:
```python
def validate_scenario(conn, scenario, register, counters: RunCounters):
```

Inside `validate_scenario`, replace the two existing lines:
```python
    fin_values = filter_outliers(fin_values)
    prob_values = filter_outliers(prob_values)
```
with:
```python
    fin_values = filter_outliers_with_counter(fin_values, counters, dim="fin")
    prob_values = filter_outliers_with_counter(prob_values, counters, dim="prob")
```

Update the call site in `main()` (line 762) from:
```python
        result = validate_scenario(conn, scenario, register)
```
to:
```python
        result = validate_scenario(conn, scenario, register, counters)
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_register_validator_counters.py tools/register_validator.py
git commit -m "feat(validator): add RunCounters instrumentation for run_summary evidence counts"
```

---

### Task 2: Track queried + matched source IDs in `phase1_refresh_known_sources`

**Goal:** Populate `counters.queried_source_ids` (unique benchmark IDs submitted to Phase 1 Tavily) and `counters.matched_source_ids` (IDs that yielded at least one non-empty snippet).

**Files:**
- Modify: `tools/register_validator.py` (phase1_refresh_known_sources signature + body)
- Test: `tests/test_register_validator_counters.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_register_validator_counters.py`:

```python
def test_counters_track_queried_and_matched_sets():
    c = RunCounters()
    # simulate: 3 unique source IDs queried, 2 yielded results
    c.queried_source_ids.update({"verizon-dbir", "ibm-cost-data-breach", "enisa-threat-landscape"})
    c.matched_source_ids.update({"verizon-dbir", "ibm-cost-data-breach"})
    assert len(c.queried_source_ids) == 3
    assert len(c.matched_source_ids) == 2
    assert c.matched_source_ids.issubset(c.queried_source_ids)
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_register_validator_counters.py::test_counters_track_queried_and_matched_sets -v`
Expected: PASS (structurally — just confirms the set fields exist on the dataclass)

- [ ] **Step 3: Wire actual population in phase1**

In `register_validator.py`, change `phase1_refresh_known_sources` (line 252) signature from:
```python
def phase1_refresh_known_sources(conn, scenario):
```
to:
```python
def phase1_refresh_known_sources(conn, scenario, counters: "RunCounters"):
```

The function currently reads only `name, url, source_tags` from `sources_registry`. Extend the SQL to also read the source id (the source URL or a deterministic id derived from name). Since the existing schema doesn't have an obvious id, use the source `name` slug as the id. Add, inside the `for source in relevant[:_PHASE1_SOURCE_CAP]:` loop, right after `url = source["url"]`:

```python
        import re as _re
        source_id = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or name
        counters.queried_source_ids.add(source_id)
```

Then, after the `results = _search_web(...)` call and the figure-extraction loop, add:

```python
        if any(r.get("content", "").strip() for r in results):
            counters.matched_source_ids.add(source_id)
```

Update the call site in `validate_scenario` (line 593) from:
```python
    p1_fin, p1_prob = phase1_refresh_known_sources(conn, scenario)
```
to:
```python
    p1_fin, p1_prob = phase1_refresh_known_sources(conn, scenario, counters)
```

- [ ] **Step 4: Run full counters test file**

Run: `uv run pytest tests/test_register_validator_counters.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_register_validator_counters.py tools/register_validator.py
git commit -m "feat(validator): track queried + matched source IDs in phase1"
```

---

### Task 3: Add `build_run_summary()` post-pass

**Goal:** Deterministic function called at the end of `main()` that reads the prior `register_validation.json`, tallies verdicts, computes deltas, applies coverage-gap + baseline-usage rules, and returns the `run_summary` block.

**Files:**
- Modify: `tools/register_validator.py`
- Test: `tests/test_register_validator_run_summary.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_register_validator_run_summary.py`:

```python
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
    # Ransomware fin improved from insufficient → support
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_register_validator_run_summary.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_run_summary'`

- [ ] **Step 3: Implement `build_run_summary()`**

Append to `tools/register_validator.py` (after `check_source_versions`, before `validate_scenario`):

```python
# ---------------------------------------------------------------------------
# Run summary post-pass (pure code, no agent)
# ---------------------------------------------------------------------------

_VERDICT_NORMALIZE = {
    "supports": "support",
    "support": "support",
    "challenges": "challenge",
    "challenge": "challenge",
    "insufficient": "insufficient",
}


def _normalize_verdict(v: str) -> str:
    return _VERDICT_NORMALIZE.get((v or "").lower(), "insufficient")


def _tally_verdicts(results: list[dict]) -> dict:
    tally = {"support": 0, "challenge": 0, "insufficient": 0}
    for r in results:
        tally[_normalize_verdict(r.get("financial", {}).get("verdict"))] += 1
        tally[_normalize_verdict(r.get("probability", {}).get("verdict"))] += 1
    return tally


def _collect_cited_source_ids(results: list[dict]) -> set[str]:
    """Return the set of source IDs cited across all scenario results."""
    cited = set()
    for r in results:
        for dim in ("financial", "probability"):
            for bucket in ("registered_sources", "new_sources"):
                for s in r.get(dim, {}).get(bucket, []) or []:
                    # existing schema uses `name`; slug it to an ID
                    name = (s.get("name") or "").strip()
                    if name:
                        cited.add(re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    return cited


def build_run_summary(
    register: dict,
    current_results: list[dict],
    previous_path,
    counters: RunCounters,
    duration_seconds: int,
    val_sources: list[dict],
    orphan_source_warnings: list[dict],
) -> dict:
    """Deterministic post-validation run summary — no LLM calls."""
    from datetime import datetime, timezone
    import re as _re

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- previous run ---
    prior = None
    previous_run_id = None
    if previous_path:
        try:
            from pathlib import Path as _P
            p = _P(previous_path) if not isinstance(previous_path, _P) else previous_path
            if p.exists():
                prior = json.loads(p.read_text(encoding="utf-8"))
                previous_run_id = (prior.get("run_summary") or {}).get("run_id")
        except Exception:
            prior = None

    # --- verdicts ---
    current_tally = _tally_verdicts(current_results)
    previous_tally = None
    deltas = []
    if prior and prior.get("scenarios"):
        previous_tally = _tally_verdicts(prior["scenarios"])
        prior_by_scen = {s.get("scenario_name"): s for s in prior["scenarios"]}
        for r in current_results:
            name = r.get("scenario_name")
            prev = prior_by_scen.get(name, {})
            for dim, code in (("financial", "fin"), ("probability", "prob")):
                cur_v = _normalize_verdict(r.get(dim, {}).get("verdict"))
                prv_v = _normalize_verdict(prev.get(dim, {}).get("verdict")) if prev else None
                if prv_v and prv_v != cur_v:
                    improved = ["insufficient", "challenge", "support"]
                    direction = "improved" if improved.index(cur_v) > improved.index(prv_v) else "weakened"
                    deltas.append({
                        "scenario": name, "dim": code,
                        "from": prv_v, "to": cur_v, "direction": direction,
                    })

    # --- sources ---
    matched_ids = sorted(counters.matched_source_ids)
    val_sources_by_id = {s.get("id"): s for s in val_sources}

    def _src_tier(sid: str) -> str:
        s = val_sources_by_id.get(sid, {})
        return (s.get("admiralty_reliability") or s.get("tier") or "C").upper()

    def _src_name(sid: str) -> str:
        return val_sources_by_id.get(sid, {}).get("name", sid)

    prior_cited_ids = set()
    if prior:
        prior_cited_ids = set((prior.get("run_summary", {}) or {}).get("sources", {}).get("matched_ids") or [])
        if not prior_cited_ids:
            prior_cited_ids = _collect_cited_source_ids(prior.get("scenarios", []))

    current_cited_ids = _collect_cited_source_ids(current_results) | set(matched_ids)
    new_this_run = [
        {"id": sid, "name": _src_name(sid), "tier": _src_tier(sid)}
        for sid in sorted(current_cited_ids - prior_cited_ids)
    ] if prior else []
    dropped_this_run = [
        {"id": sid, "name": _src_name(sid) or sid, "reason": "not_cited"}
        for sid in sorted(prior_cited_ids - current_cited_ids)
    ] if prior else []

    by_tier: dict[str, int] = {}
    for sid in matched_ids:
        t = _src_tier(sid)
        by_tier[t] = by_tier.get(t, 0) + 1

    # --- coverage gaps (scenarios with verdict=insufficient AND source count ≤ 1) ---
    coverage_gaps = []
    for r in current_results:
        total_fin = len(r.get("financial", {}).get("registered_sources", []) or []) + \
                    len(r.get("financial", {}).get("new_sources", []) or [])
        total_prob = len(r.get("probability", {}).get("registered_sources", []) or []) + \
                     len(r.get("probability", {}).get("new_sources", []) or [])
        worst_total = min(total_fin, total_prob)
        if _normalize_verdict(r.get("financial", {}).get("verdict")) == "insufficient" and total_fin <= 1:
            coverage_gaps.append({
                "scenario": r.get("scenario_name"),
                "issue": "no benchmark sources tagged" if total_fin == 0 else "only 1 source — confidence LOW",
            })

    # --- baseline usage ---
    scenarios_with_baseline = sum(1 for r in current_results if r.get("analyst_baseline"))
    aligned = sum(
        1 for r in current_results
        if r.get("analyst_baseline") and r.get("baseline_alignment", {}).get("aggregate") == "aligned"
    )
    diverged = sum(
        1 for r in current_results
        if r.get("analyst_baseline") and r.get("baseline_alignment", {}).get("aggregate") == "diverged"
    )

    return {
        "run_id": run_id,
        "previous_run_id": previous_run_id,
        "register_id": register.get("register_id"),
        "register_name": register.get("display_name") or register.get("register_id"),
        "duration_seconds": int(duration_seconds),
        "scenarios": {
            "total": len(register.get("scenarios", [])),
            "validated": len(current_results),
            "skipped": len(register.get("scenarios", [])) - len(current_results),
        },
        "verdicts": {
            "current": current_tally,
            "previous": previous_tally,
            "deltas": deltas,
        },
        "sources": {
            "queried": len(counters.queried_source_ids),
            "matched": len(counters.matched_source_ids),
            "matched_ids": matched_ids,  # internal use for next-run delta
            "new_this_run": new_this_run,
            "dropped_this_run": dropped_this_run,
            "by_tier": by_tier,
        },
        "evidence": {
            "fin_extracted": counters.fin_extracted,
            "prob_extracted": counters.prob_extracted,
            "fin_after_iqr_filter": counters.fin_after_iqr_filter,
            "prob_after_iqr_filter": counters.prob_after_iqr_filter,
            "outliers_removed": counters.outliers_removed,
        },
        "coverage_gaps": coverage_gaps,
        "baseline_usage": {
            "scenarios_with_baseline": scenarios_with_baseline,
            "baseline_aligned_with_osint": aligned,
            "baseline_diverged_from_osint": diverged,
        },
        "errors": list(orphan_source_warnings),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_register_validator_run_summary.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_register_validator_run_summary.py tools/register_validator.py
git commit -m "feat(validator): add deterministic build_run_summary() post-pass"
```

---

### Task 4: Thread `analyst_baseline` through `validate_scenario` + Sonnet prompt

**Goal:** Read optional `analyst_baseline` from each scenario, compute range-overlap alignment against OSINT, inject baseline summary + alignment strings into the `_RECOMMENDATION_PROMPT`, pass the baseline through to the scenario result, and emit `baseline_orphan_source` entries for source IDs that don't resolve.

**Files:**
- Modify: `tools/register_validator.py` (alignment helpers, extended `_build_recommendation_sonnet`, extended `validate_scenario`, extended `_RECOMMENDATION_PROMPT`)
- Test: `tests/test_register_validator_baseline.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_register_validator_baseline.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_register_validator_baseline.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the helpers**

Append to `tools/register_validator.py` (right after `compute_verdict_confidence`, before `check_source_versions`):

```python
# ---------------------------------------------------------------------------
# Analyst baseline helpers (pure code, no agent)
# ---------------------------------------------------------------------------

def compute_baseline_alignment(baseline: dict | None, osint_range: list, kind: str) -> str:
    """
    Range-overlap test.
    kind='fin':  baseline uses low_usd / high_usd, osint_range is [min, max] in USD.
    kind='prob': baseline uses low / high (0..1 fraction), osint_range is [min, max] in percent.
    """
    if not baseline:
        return "n/a"
    if not osint_range or len(osint_range) < 2:
        return "n/a"
    try:
        if kind == "fin":
            b_low = float(baseline.get("low_usd") or baseline.get("value_usd") or 0)
            b_high = float(baseline.get("high_usd") or baseline.get("value_usd") or 0)
        else:  # prob
            # Convert baseline fraction → percent for comparison
            b_low = float(baseline.get("low") or baseline.get("annual_rate") or 0) * 100.0
            b_high = float(baseline.get("high") or baseline.get("annual_rate") or 0) * 100.0
        o_low, o_high = float(osint_range[0]), float(osint_range[1])
    except (TypeError, ValueError):
        return "n/a"
    if b_low > b_high or o_low > o_high:
        return "n/a"
    return "aligned" if max(b_low, o_low) <= min(b_high, o_high) else "diverged"


def format_baseline_summary(baseline: dict | None, kind: str) -> str:
    if not baseline:
        return "none"
    n_sources = len(baseline.get("source_ids") or [])
    src_word = "source" if n_sources == 1 else "sources"
    if kind == "fin":
        val = float(baseline.get("value_usd") or 0)
        lo = float(baseline.get("low_usd") or 0)
        hi = float(baseline.get("high_usd") or 0)
        def _m(x):
            return f"${x/1_000_000:.1f}M"
        return f"{_m(val)} [low {_m(lo)}, high {_m(hi)}], {n_sources} {src_word}"
    # prob
    rate = float(baseline.get("annual_rate") or 0)
    lo = float(baseline.get("low") or 0)
    hi = float(baseline.get("high") or 0)
    etype = baseline.get("evidence_type") or "unknown"
    return f"{rate:.2f}/yr [{lo:.2f}-{hi:.2f}], {etype}, {n_sources} {src_word}"


def resolve_baseline_orphans(scenario_name: str, baseline: dict, val_sources_by_id: dict) -> list[dict]:
    """Return a list of orphan warning dicts (empty list if all source IDs resolve)."""
    orphans = []
    for dim_name, dim_key in (("fin", "fin"), ("prob", "prob")):
        block = baseline.get(dim_name) or {}
        for sid in block.get("source_ids") or []:
            if sid not in val_sources_by_id:
                orphans.append({
                    "type": "baseline_orphan_source",
                    "scenario": scenario_name,
                    "dim": dim_key,
                    "source_id": sid,
                })
    return orphans
```

- [ ] **Step 4: Run helper tests**

Run: `uv run pytest tests/test_register_validator_baseline.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Extend `_RECOMMENDATION_PROMPT` + `_build_recommendation_sonnet`**

In `_RECOMMENDATION_PROMPT` (line 374), **append** (do not replace) these lines immediately before the final `"""`:

```
ANALYST BASELINE (optional, may be "none"):
  fin:  {baseline_fin_summary}
  prob: {baseline_prob_summary}
  alignment_fin:  {baseline_fin_alignment}
  alignment_prob: {baseline_prob_alignment}

If a baseline is present, your recommendation MUST acknowledge it explicitly:
- If baseline aligns with OSINT: cite the analyst's number as a corroborating signal.
- If baseline diverges from OSINT: name the divergence and which range you weight higher (with reason).
- Never silently override the baseline — the analyst put it there deliberately.
```

Change `_build_recommendation_sonnet` signature (line 408) from:
```python
def _build_recommendation_sonnet(scenario, register, fin, prob):
```
to:
```python
def _build_recommendation_sonnet(scenario, register, fin, prob, baseline: dict | None = None, alignment: dict | None = None):
```

Inside the function, immediately before the `prompt = _RECOMMENDATION_PROMPT.format(...)` call, add:

```python
    baseline = baseline or {}
    alignment = alignment or {"fin": "n/a", "prob": "n/a"}
    baseline_fin_summary = format_baseline_summary(baseline.get("fin"), kind="fin")
    baseline_prob_summary = format_baseline_summary(baseline.get("prob"), kind="prob")
```

Extend the `.format(...)` kwargs to include:
```python
        baseline_fin_summary=baseline_fin_summary,
        baseline_prob_summary=baseline_prob_summary,
        baseline_fin_alignment=alignment.get("fin", "n/a"),
        baseline_prob_alignment=alignment.get("prob", "n/a"),
```

- [ ] **Step 6: Thread baseline through `validate_scenario`**

In `validate_scenario` (line 574), after the verdicts are computed (~line 629, after `prob_verdict, prob_range = compute_verdict(...)`), add:

```python
    # --- analyst baseline pass-through + alignment ---
    baseline = scenario.get("analyst_baseline")
    alignment = {
        "fin":  compute_baseline_alignment(baseline.get("fin") if baseline else None,
                                           fin_range, kind="fin"),
        "prob": compute_baseline_alignment(baseline.get("prob") if baseline else None,
                                           prob_range, kind="prob"),
    }
    # Aggregate: "aligned" if neither diverged AND at least one aligned; "diverged" if any diverged
    dims = [alignment["fin"], alignment["prob"]]
    if "diverged" in dims:
        agg = "diverged"
    elif "aligned" in dims:
        agg = "aligned"
    else:
        agg = "n/a"
    alignment["aggregate"] = agg
```

Then change the call:
```python
    recommendation = _build_recommendation_sonnet(scenario, register, fin_result, prob_result)
```
to:
```python
    recommendation = _build_recommendation_sonnet(
        scenario, register, fin_result, prob_result,
        baseline=baseline, alignment=alignment,
    )
```

Finally, extend the return dict to include the baseline + alignment:
```python
    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "asset_context_note": asset_context_note,
        "recommendation": recommendation,
        "financial": fin_result,
        "probability": prob_result,
        "analyst_baseline": baseline,          # passthrough (may be None)
        "baseline_alignment": alignment,       # {fin, prob, aggregate}
    }
```

- [ ] **Step 7: Orphan collection + wire `build_run_summary` into `main()`**

In `main()` (line 741), replace the end of the function (starting from `# Track 3: version checks`) with:

```python
    # Track 3: version checks on known sources
    version_checks = check_source_versions(all_val_sources, _search_web)

    # Collect orphan baseline source warnings
    val_sources_by_id = {s.get("id"): s for s in all_val_sources}
    orphan_warnings: list[dict] = []
    for scenario in register["scenarios"]:
        b = scenario.get("analyst_baseline")
        if b:
            orphan_warnings.extend(
                resolve_baseline_orphans(scenario["scenario_name"], b, val_sources_by_id)
            )

    duration = int(time.monotonic() - run_started_monotonic)

    run_summary = build_run_summary(
        register=register,
        current_results=scenario_results,
        previous_path=OUTPUT_PATH,
        counters=counters,
        duration_seconds=duration,
        val_sources=all_val_sources,
        orphan_source_warnings=orphan_warnings,
    )

    output = {
        "register_id": register["register_id"],
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "run_summary": run_summary,
        "version_checks": version_checks,
        "scenarios": scenario_results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    register["last_validated_at"] = output["validated_at"]
    reg_path = REGISTERS_DIR / f"{register['register_id']}.json"
    reg_path.write_text(json.dumps(register, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[register_validator] Done -> {OUTPUT_PATH}")
    print(f"[register_validator] Run summary: {run_summary['scenarios']['validated']} scenarios, "
          f"{run_summary['sources']['matched']} sources matched, {len(orphan_warnings)} baseline orphans")
    conn.close()
```

**Important:** `build_run_summary` reads `OUTPUT_PATH` as "previous" **before** the write. Because `main()` reads once at the start of `build_run_summary` and then writes afterwards, this is safe.

- [ ] **Step 8: Run full validator test suite**

Run: `uv run pytest tests/test_register_validator_counters.py tests/test_register_validator_run_summary.py tests/test_register_validator_baseline.py -v`
Expected: PASS (all tests)

- [ ] **Step 9: Commit**

```bash
git add tests/test_register_validator_baseline.py tools/register_validator.py
git commit -m "feat(validator): thread analyst_baseline through Sonnet prompt + alignment"
```

---

## Unit 2 — Server Endpoints (`server.py`)

### Task 5: `PATCH /api/registers/{id}/scenarios/{idx}/baseline`

**Goal:** Accept a baseline block (or `null`), server-validate, server-stamp `updated`/`updated_by`, persist to the register file. Orphan `source_ids` accepted on write.

**Files:**
- Modify: `server.py` (add new route near existing `/api/risk-register/` routes)
- Test: `tests/test_server_baseline_patch.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_baseline_patch.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_server_baseline_patch.py -v`
Expected: FAIL with 404 or routing error (endpoint doesn't exist)

- [ ] **Step 3: Add the endpoint in `server.py`**

Near line 1310 (just after the existing `/api/validation/run-register` block), add:

```python
# ── API: Analyst Baseline ───────────────────────────────────────────────
_VALID_EVIDENCE_TYPES = {"frequency_rate", "prevalence_survey", "mixed", "expert_estimate", "unknown"}


def _registers_dir() -> Path:
    # allow tests to override via env var
    override = os.environ.get("CRQ_REGISTERS_DIR")
    return Path(override) if override else (BASE / "data" / "registers")


def _validate_baseline_block(body: dict | None) -> tuple[bool, str]:
    """Returns (ok, error_message). body may be None (clear)."""
    if body is None:
        return True, ""
    if not isinstance(body, dict):
        return False, "body must be object or null"
    fin = body.get("fin")
    prob = body.get("prob")
    if fin is None and prob is None:
        return False, "at least one of fin or prob must be present (send null to clear)"
    if fin is not None:
        for k in ("value_usd", "low_usd", "high_usd"):
            v = fin.get(k)
            if v is None or not isinstance(v, (int, float)) or v < 0:
                return False, f"fin.{k} must be a non-negative number"
        if not (fin["low_usd"] <= fin["value_usd"] <= fin["high_usd"]):
            return False, "fin: low_usd ≤ value_usd ≤ high_usd required"
        if len((fin.get("notes") or "")) > 1000:
            return False, "fin.notes exceeds 1000 chars"
    if prob is not None:
        for k in ("annual_rate", "low", "high"):
            v = prob.get(k)
            if v is None or not isinstance(v, (int, float)) or not (0 <= v <= 1):
                return False, f"prob.{k} must be a number in [0, 1]"
        if not (prob["low"] <= prob["annual_rate"] <= prob["high"]):
            return False, "prob: low ≤ annual_rate ≤ high required"
        if (prob.get("evidence_type") or "unknown") not in _VALID_EVIDENCE_TYPES:
            return False, f"prob.evidence_type must be one of {sorted(_VALID_EVIDENCE_TYPES)}"
        if len((prob.get("notes") or "")) > 1000:
            return False, "prob.notes exceeds 1000 chars"
    return True, ""


@app.patch("/api/registers/{register_id}/scenarios/{scenario_index}/baseline")
async def patch_analyst_baseline(register_id: str, scenario_index: int, request: Request):
    from datetime import date
    # Parse body — allow explicit null
    try:
        raw = await request.body()
        body = json.loads(raw.decode("utf-8")) if raw else None
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=422)

    ok, err = _validate_baseline_block(body)
    if not ok:
        return JSONResponse({"error": err}, status_code=422)

    reg_path = _registers_dir() / f"{register_id}.json"
    if not reg_path.exists():
        return JSONResponse({"error": f"register not found: {register_id}"}, status_code=404)
    register = json.loads(reg_path.read_text(encoding="utf-8"))
    scenarios = register.get("scenarios", [])
    if not (0 <= scenario_index < len(scenarios)):
        return JSONResponse({"error": "scenario_index out of range"}, status_code=404)

    today = date.today().isoformat()
    if body is None:
        scenarios[scenario_index]["analyst_baseline"] = None
    else:
        stamped: dict = {}
        for dim in ("fin", "prob"):
            block = body.get(dim)
            if block is not None:
                block = dict(block)
                block["updated"] = today
                block["updated_by"] = "analyst"
                block.setdefault("source_ids", [])
                block.setdefault("notes", "")
                stamped[dim] = block
        scenarios[scenario_index]["analyst_baseline"] = stamped

    _write_json_atomic(reg_path, register)
    return scenarios[scenario_index]
```

Add `from fastapi import Request` to the imports at the top of `server.py` if not already present, and add `import os` if not present.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_server_baseline_patch.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_server_baseline_patch.py server.py
git commit -m "feat(server): PATCH /api/registers/{id}/scenarios/{idx}/baseline"
```

---

### Task 6: `GET /api/source-library/osint` endpoint

**Goal:** Return the OSINT source list with effectiveness signals (cited_rate, lifecycle, run_delta) computed from `sources.db`, applying the global run-identity rule (`MAX(run_timestamp)` across all rows, distinct run-days).

**Files:**
- Modify: `server.py`
- Test: `tests/test_server_source_library_osint.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_source_library_osint.py`:

```python
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    db_path = tmp_path / "sources.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE sources_registry (
            id INTEGER PRIMARY KEY,
            name TEXT, domain TEXT, tier TEXT, type TEXT,
            collection_type TEXT DEFAULT 'osint',
            blocked INTEGER DEFAULT 0
        );
        CREATE TABLE source_appearances (
            source_id INTEGER,
            region TEXT,
            pillar TEXT,
            cited INTEGER,
            run_timestamp TEXT
        );
        INSERT INTO sources_registry VALUES
            (1, 'Reuters', 'reuters.com', 'A', 'news', 'osint', 0),
            (2, 'Blog X',  'blog.example.com', 'C', 'news', 'osint', 0);
        INSERT INTO source_appearances VALUES
            (1, 'APAC', 'geo',   1, '2026-04-09T08:00:00Z'),
            (1, 'MED',  'cyber', 1, '2026-04-08T08:00:00Z'),
            (1, 'MED',  'geo',   0, '2026-04-07T08:00:00Z'),
            (2, 'APAC', 'cyber', 0, '2026-03-01T08:00:00Z');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setenv("CRQ_SOURCES_DB", str(db_path))
    from server import app
    return TestClient(app)


def test_osint_endpoint_returns_sources(client_with_db):
    r = client_with_db.get("/api/source-library/osint")
    assert r.status_code == 200
    data = r.json()
    assert "sources" in data
    assert data["total"] == 2
    ids = {s["id"] for s in data["sources"]}
    assert ids == {1, 2}


def test_osint_cited_rate_computed(client_with_db):
    r = client_with_db.get("/api/source-library/osint")
    by_id = {s["id"]: s for s in r.json()["sources"]}
    reuters = by_id[1]
    assert reuters["appearance_count"] == 3
    assert reuters["cited_count"] == 2
    assert abs(reuters["cited_rate"] - 2/3) < 0.01
    assert "both" in reuters["pillar"] or reuters["pillar"] == "both"
    assert set(reuters["regions"]) == {"APAC", "MED"}


def test_osint_lifecycle_active_vs_stale(client_with_db):
    r = client_with_db.get("/api/source-library/osint")
    by_id = {s["id"]: s for s in r.json()["sources"]}
    assert by_id[1]["lifecycle"] == "active"
    assert by_id[2]["lifecycle"] == "stale"


def test_osint_region_filter(client_with_db):
    r = client_with_db.get("/api/source-library/osint?region=MED")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()["sources"]}
    assert ids == {1}
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_server_source_library_osint.py -v`
Expected: FAIL with 404

- [ ] **Step 3: Implement the endpoint in `server.py`**

Near the existing `/api/sources` routes (around line 1520), add:

```python
# ── API: Source Library (OSINT) ─────────────────────────────────────────

def _sources_db_path() -> Path:
    override = os.environ.get("CRQ_SOURCES_DB")
    return Path(override) if override else (BASE / "data" / "sources.db")


def _osint_run_identity(conn: sqlite3.Connection) -> tuple[str | None, str | None, list[str]]:
    """
    Returns (current_run_ts, previous_run_ts, recent_run_days_desc[:3]) per spec §3.
    Uses MAX(run_timestamp) globally; distinct run-days drive "≤3 runs" lifecycle.
    """
    rows = conn.execute(
        "SELECT DISTINCT substr(run_timestamp, 1, 10) AS run_day "
        "FROM source_appearances ORDER BY run_day DESC LIMIT 3"
    ).fetchall()
    run_days = [r[0] for r in rows]
    current_ts = conn.execute(
        "SELECT MAX(run_timestamp) FROM source_appearances"
    ).fetchone()[0]
    prev_ts = None
    if len(run_days) >= 2:
        prev_ts = conn.execute(
            "SELECT MAX(run_timestamp) FROM source_appearances "
            "WHERE substr(run_timestamp, 1, 10) = ?",
            (run_days[1],),
        ).fetchone()[0]
    return current_ts, prev_ts, run_days


@app.get("/api/source-library/osint")
async def get_source_library_osint(
    region: str | None = None,
    tier: str | None = None,
    pillar: str | None = None,
    lifecycle: str | None = None,
    search: str | None = None,
):
    import sqlite3 as _sq
    db_path = _sources_db_path()
    if not db_path.exists():
        return {"total": 0, "filtered": 0, "current_run_id": None,
                "previous_run_id": None, "sources": []}
    conn = _sq.connect(str(db_path))
    try:
        current_ts, prev_ts, recent_days = _osint_run_identity(conn)
        rows = conn.execute("""
            SELECT sr.id, sr.name, sr.domain, sr.tier, sr.type, sr.blocked,
                   COUNT(sa.rowid) AS appearances,
                   SUM(CASE WHEN sa.cited=1 THEN 1 ELSE 0 END) AS cited_count,
                   MIN(sa.run_timestamp) AS first_seen,
                   MAX(sa.run_timestamp) AS last_seen,
                   GROUP_CONCAT(DISTINCT sa.region) AS regions,
                   GROUP_CONCAT(DISTINCT sa.pillar) AS pillars
              FROM sources_registry sr
              LEFT JOIN source_appearances sa ON sa.source_id = sr.id
             WHERE COALESCE(sr.collection_type, 'osint') = 'osint'
             GROUP BY sr.id
        """).fetchall()
    finally:
        conn.close()

    def _collapse_pillar(raw: str | None) -> str:
        if not raw:
            return "none"
        parts = {p for p in raw.split(",") if p}
        if parts == {"geo"}:  return "geo"
        if parts == {"cyber"}: return "cyber"
        return "both"

    def _lifecycle(last_seen: str | None, blocked: int) -> str:
        if blocked:
            return "blocked"
        if not last_seen or not recent_days:
            return "stale"
        return "active" if last_seen[:10] in recent_days else "stale"

    sources = []
    for row in rows:
        (sid, name, domain, tier_v, type_v, blocked,
         appearances, cited, first_seen, last_seen, regions_raw, pillars_raw) = row
        appearances = appearances or 0
        cited = cited or 0
        cited_rate = (cited / appearances) if appearances else None
        regions_list = sorted(set((regions_raw or "").split(","))) if regions_raw else []
        regions_list = [r for r in regions_list if r]

        # run_delta: count in current run-day minus count in previous run-day
        run_delta = None
        if current_ts and prev_ts:
            cur_day, prev_day = current_ts[:10], prev_ts[:10]
            c2 = _sq.connect(str(db_path))
            try:
                cur_n = c2.execute(
                    "SELECT COUNT(*) FROM source_appearances WHERE source_id=? AND substr(run_timestamp,1,10)=?",
                    (sid, cur_day),
                ).fetchone()[0]
                prev_n = c2.execute(
                    "SELECT COUNT(*) FROM source_appearances WHERE source_id=? AND substr(run_timestamp,1,10)=?",
                    (sid, prev_day),
                ).fetchone()[0]
                run_delta = cur_n - prev_n
            finally:
                c2.close()

        sources.append({
            "id": sid,
            "name": name,
            "domain": domain,
            "tier": tier_v or "C",
            "type": type_v or "news",
            "pillar": _collapse_pillar(pillars_raw),
            "regions": regions_list,
            "appearance_count": appearances,
            "cited_count": cited,
            "cited_rate": cited_rate,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "lifecycle": _lifecycle(last_seen, blocked),
            "run_delta": run_delta,
            "blocked": bool(blocked),
        })

    total = len(sources)
    # Server-side filters
    def _keep(s: dict) -> bool:
        if region and region not in s["regions"]: return False
        if tier and (s["tier"] or "").upper() != tier.upper(): return False
        if pillar and s["pillar"] != pillar: return False
        if lifecycle and s["lifecycle"] != lifecycle: return False
        if search:
            q = search.lower()
            if q not in (s["name"] or "").lower() and q not in (s["domain"] or "").lower():
                return False
        return True

    filtered = [s for s in sources if _keep(s)]
    filtered.sort(key=lambda s: (-(s["cited_rate"] or 0), -(s["appearance_count"] or 0)))

    return {
        "total": total,
        "filtered": len(filtered),
        "current_run_id": current_ts,
        "previous_run_id": prev_ts,
        "sources": filtered,
    }
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_server_source_library_osint.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_server_source_library_osint.py server.py
git commit -m "feat(server): GET /api/source-library/osint with effectiveness signals"
```

---

### Task 7: `GET /api/source-library/benchmarks` endpoint

**Goal:** Return benchmark sources for the active register, with lazy-defaulted `provenance`, coverage matrix, and `coverage_summary` (omitted when `show_all=true`).

**Files:**
- Modify: `server.py`
- Test: `tests/test_server_source_library_benchmarks.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_source_library_benchmarks.py`:

```python
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    (data_dir / "registers").mkdir(parents=True)
    (data_dir / "registers" / "wpp.json").write_text(json.dumps({
        "register_id": "wpp",
        "display_name": "Wind Power Plant",
        "scenarios": [
            {"scenario_name": "Ransomware",       "search_tag": "Ransomware"},
            {"scenario_name": "System intrusion", "search_tag": "System intrusion"},
            {"scenario_name": "Phishing",         "search_tag": "Phishing"},
        ],
    }), encoding="utf-8")
    (data_dir / "validation_sources.json").write_text(json.dumps({
        "sources": [
            {"id": "verizon-dbir", "name": "Verizon DBIR", "url": "https://verizon.com",
             "admiralty_reliability": "A", "edition_year": 2024, "cadence": "annual",
             "sector_tags": ["all"], "scenario_tags": ["Ransomware", "System intrusion"]},
            {"id": "analyst-one",  "name": "Analyst One", "url": "https://ex.com",
             "admiralty_reliability": "B", "edition_year": 2025, "cadence": "annual",
             "sector_tags": ["energy"], "scenario_tags": ["Phishing"],
             "provenance": "analyst"},
        ]
    }), encoding="utf-8")
    monkeypatch.setenv("CRQ_REGISTERS_DIR", str(data_dir / "registers"))
    monkeypatch.setenv("CRQ_VALIDATION_SOURCES", str(data_dir / "validation_sources.json"))
    from server import app
    return TestClient(app)


def test_benchmarks_default_scoped_to_register(client):
    r = client.get("/api/source-library/benchmarks?register=wpp")
    assert r.status_code == 200
    d = r.json()
    assert d["register_id"] == "wpp"
    assert set(d["scenarios"]) == {"Ransomware", "System intrusion", "Phishing"}
    # Both sources intersect with register → both returned
    ids = {s["id"] for s in d["sources"]}
    assert ids == {"verizon-dbir", "analyst-one"}


def test_benchmarks_provenance_lazy_default(client):
    r = client.get("/api/source-library/benchmarks?register=wpp")
    by_id = {s["id"]: s for s in r.json()["sources"]}
    assert by_id["verizon-dbir"]["provenance"] == "vendor"
    assert by_id["analyst-one"]["provenance"] == "analyst"


def test_benchmarks_matrix_set_intersection(client):
    r = client.get("/api/source-library/benchmarks?register=wpp")
    m = r.json()["matrix"]
    assert m["Ransomware"]["verizon-dbir"] is True
    assert m["Phishing"]["verizon-dbir"] is False
    assert m["Phishing"]["analyst-one"] is True


def test_benchmarks_coverage_summary_flags_gaps(client):
    r = client.get("/api/source-library/benchmarks?register=wpp")
    cs = r.json()["coverage_summary"]
    # Phishing has 1 source (analyst-one)
    assert "Phishing" in cs["scenarios_with_one_source"]
    assert cs["uncovered_count"] == 0
    assert cs["thinly_covered_count"] == 1


def test_benchmarks_show_all_omits_coverage_summary(client):
    r = client.get("/api/source-library/benchmarks?register=wpp&show_all=true")
    assert "coverage_summary" not in r.json()
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_server_source_library_benchmarks.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the endpoint**

Add to `server.py` immediately after the OSINT endpoint from Task 6:

```python
# ── API: Source Library (Benchmarks) ────────────────────────────────────

def _validation_sources_path() -> Path:
    override = os.environ.get("CRQ_VALIDATION_SOURCES")
    return Path(override) if override else (BASE / "data" / "validation_sources.json")


def _provenance_default(src: dict) -> str:
    return src.get("provenance") or "vendor"


@app.get("/api/source-library/benchmarks")
async def get_source_library_benchmarks(register: str | None = None, show_all: bool = False):
    reg_dir = _registers_dir()
    reg_path = reg_dir / f"{register}.json" if register else None
    register_obj = None
    register_scenario_tags: set[str] = set()
    scenario_names: list[str] = []
    if reg_path and reg_path.exists():
        register_obj = json.loads(reg_path.read_text(encoding="utf-8"))
        for sc in register_obj.get("scenarios", []):
            tag = sc.get("search_tag") or sc.get("scenario_name")
            if tag:
                register_scenario_tags.add(tag)
                scenario_names.append(tag)

    vs_path = _validation_sources_path()
    raw = json.loads(vs_path.read_text(encoding="utf-8")) if vs_path.exists() else {"sources": []}
    all_sources = raw.get("sources", [])

    # Filter sources by register intersection unless show_all
    def _intersects(src: dict) -> bool:
        tags = set(src.get("scenario_tags") or [])
        return bool(tags & register_scenario_tags)

    filtered = all_sources if show_all else [s for s in all_sources if _intersects(s)]

    # Shape each source
    shaped = []
    for s in filtered:
        shaped.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "url": s.get("url"),
            "reliability": s.get("admiralty_reliability") or s.get("tier") or "C",
            "edition_year": s.get("edition_year"),
            "cadence": s.get("cadence"),
            "sector_tags": s.get("sector_tags", []),
            "scenario_tags": s.get("scenario_tags", []),
            "provenance": _provenance_default(s),
            "covered_scenarios": sorted(set(s.get("scenario_tags") or []) & register_scenario_tags),
            "last_checked": s.get("last_checked"),
            "cited_in_current_run": [],  # populated from register_validation.json below
        })

    # Attach cited_in_current_run from the most recent register_validation.json
    val_path = BASE / "output" / "validation" / "register_validation.json"
    if val_path.exists():
        try:
            val = json.loads(val_path.read_text(encoding="utf-8"))
            val_reg_id = val.get("register_id")
            run_id = (val.get("run_summary") or {}).get("run_id")
            for r in val.get("scenarios", []):
                scen = r.get("scenario_name")
                for dim in ("financial", "probability"):
                    for bucket in ("registered_sources", "new_sources"):
                        for used in r.get(dim, {}).get(bucket, []) or []:
                            used_name = (used.get("name") or "").strip()
                            for sh in shaped:
                                if sh["name"] and used_name.lower().startswith(sh["name"].lower()[:20]):
                                    sh["cited_in_current_run"].append({
                                        "register_id": val_reg_id,
                                        "scenario": scen,
                                        "run_id": run_id,
                                    })
        except Exception:
            pass

    # Coverage matrix (scenarios × sources), scoped to the active register
    matrix = {
        scen_tag: {s["id"]: scen_tag in (s.get("scenario_tags") or []) for s in filtered}
        for scen_tag in scenario_names
    }

    response: dict = {
        "register_id": register,
        "register_name": (register_obj or {}).get("display_name"),
        "scenarios": scenario_names,
        "sources": shaped,
        "matrix": matrix,
    }

    if not show_all and register_scenario_tags:
        with_zero = [t for t in scenario_names if not any(matrix[t].values())]
        with_one  = [t for t in scenario_names if sum(1 for v in matrix[t].values() if v) == 1]
        response["coverage_summary"] = {
            "scenarios_with_zero_sources": with_zero,
            "scenarios_with_one_source":  with_one,
            "uncovered_count": len(with_zero),
            "thinly_covered_count": len(with_one),
        }

    return response
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_server_source_library_benchmarks.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_server_source_library_benchmarks.py server.py
git commit -m "feat(server): GET /api/source-library/benchmarks with coverage matrix"
```

---

### Task 8: Extend `POST /api/validation/sources/add` to accept analyst fields

**Goal:** The existing endpoint accepts `url, name, cadence, sector_tags, scenario_tags` but hardcodes `admiralty_reliability="C"`. Extend it to accept `admiralty_reliability`, `edition_year`, and `provenance` (defaulting `provenance="analyst"` when a UI source adds without specifying).

**Files:**
- Modify: `server.py:1123-1151`
- Test: `tests/test_server_validation_sources_add.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_validation_sources_add.py`:

```python
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    vs_path = tmp_path / "validation_sources.json"
    vs_path.write_text(json.dumps({"sources": []}), encoding="utf-8")
    monkeypatch.setenv("CRQ_VALIDATION_SOURCES", str(vs_path))
    from server import app
    return TestClient(app)


def test_add_defaults_provenance_to_analyst(client):
    r = client.post("/api/validation/sources/add", json={
        "url": "https://example.com/x", "name": "My Report",
        "sector_tags": ["energy"], "scenario_tags": ["Ransomware"],
    })
    assert r.status_code == 200
    # Fetch back
    r2 = client.get("/api/validation/sources")
    srcs = r2.json()["sources"]
    assert len(srcs) == 1
    assert srcs[0]["provenance"] == "analyst"


def test_add_accepts_explicit_reliability_and_year(client):
    r = client.post("/api/validation/sources/add", json={
        "url": "https://example.com/y", "name": "Vendor Report",
        "admiralty_reliability": "A", "edition_year": 2025,
        "provenance": "vendor",
    })
    assert r.status_code == 200
    srcs = client.get("/api/validation/sources").json()["sources"]
    src = next(s for s in srcs if s["name"] == "Vendor Report")
    assert src["admiralty_reliability"] == "A"
    assert src["edition_year"] == 2025
    assert src["provenance"] == "vendor"
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_server_validation_sources_add.py -v`
Expected: FAIL on `provenance` assertion (field not emitted).

- [ ] **Step 3: Modify `add_validation_source` + `get_validation_sources`**

In `server.py:1110-1114`, modify `get_validation_sources` to honour the env override:

```python
@app.get("/api/validation/sources")
async def get_validation_sources():
    path = _validation_sources_path()
    data = _read_json(path)
    # Lazy-default provenance on read
    if data and data.get("sources"):
        for s in data["sources"]:
            s.setdefault("provenance", "vendor")
    return data or {"sources": []}
```

In `server.py:1123-1151`, modify `add_validation_source`:

```python
@app.post("/api/validation/sources/add")
async def add_validation_source(body: dict):
    """Manually add a source to the trusted registry."""
    import re
    url = body.get("url", "").strip()
    name = body.get("name", "").strip()
    if not url or not name:
        return JSONResponse({"error": "url and name required"}, status_code=400)

    sources_path = _validation_sources_path()
    sources_data = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.exists() else {"sources": []}
    if any(s["url"] == url for s in sources_data.get("sources", [])):
        return JSONResponse({"error": "Source URL already in registry"}, status_code=409)

    source_id = re.sub(r"[^a-z0-9]+", "-", name[:40].lower()).strip("-")
    new_source = {
        "id": source_id,
        "name": name,
        "url": url,
        "cadence": body.get("cadence", "annual"),
        "admiralty_reliability": body.get("admiralty_reliability", "C"),
        "edition_year": body.get("edition_year"),
        "sector_tags": body.get("sector_tags", []),
        "scenario_tags": body.get("scenario_tags", []),
        "provenance": body.get("provenance", "analyst"),
        "last_checked": None,
        "last_new_content": None,
    }
    sources_data["sources"].append(new_source)
    _write_json_atomic(sources_path, sources_data)
    return {"ok": True, "source_id": source_id}
```

Also modify `delete_validation_source` (line 1154-1166) to use `_validation_sources_path()` instead of the hard-coded `BASE / "data" / "validation_sources.json"`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_server_validation_sources_add.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add tests/test_server_validation_sources_add.py server.py
git commit -m "feat(server): accept provenance/reliability/edition in source add"
```

---

### Task 9: Verify `/api/register-validation/results` exposes `run_summary`

**Goal:** The existing endpoint (line 1286) already passes through the JSON file verbatim. Since Unit 1 now emits `run_summary` as a top-level key, no code change is needed — but we add a smoke test to lock in the contract.

**Files:**
- Modify: (none)
- Test: `tests/test_server_register_validation_results.py` (create)

- [ ] **Step 1: Write the test**

Create `tests/test_server_register_validation_results.py`:

```python
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    out_dir = tmp_path / "output" / "validation"
    out_dir.mkdir(parents=True)
    (out_dir / "register_validation.json").write_text(json.dumps({
        "register_id": "wpp",
        "run_summary": {
            "run_id": "2026-04-09T14:22:08Z",
            "register_id": "wpp",
            "verdicts": {"current": {"support": 2, "challenge": 0, "insufficient": 5}},
            "sources": {"queried": 7, "matched": 3, "by_tier": {"A": 2, "B": 1}},
        },
        "scenarios": [],
    }), encoding="utf-8")
    monkeypatch.setenv("CRQ_VALIDATION_DIR", str(out_dir))
    # server.VALIDATION already points at output/validation — we symlink via env is not
    # ideal; instead, write directly into the real output/validation as part of the test.
    # Tests in this repo run from repo root, so we write the file to the actual path.
    real = tmp_path.parent  # noqa
    from server import VALIDATION
    VALIDATION.mkdir(parents=True, exist_ok=True)
    (VALIDATION / "register_validation.json").write_text(json.dumps({
        "register_id": "wpp",
        "run_summary": {"run_id": "2026-04-09T14:22:08Z", "verdicts": {"current": {}}, "sources": {}},
        "scenarios": [],
    }), encoding="utf-8")
    from server import app
    return TestClient(app)


def test_register_validation_results_exposes_run_summary(client):
    r = client.get("/api/register-validation/results")
    assert r.status_code == 200
    body = r.json()
    assert "run_summary" in body
    assert body["run_summary"]["run_id"] == "2026-04-09T14:22:08Z"
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_server_register_validation_results.py -v`
Expected: PASS (passthrough endpoint is unchanged — this test locks in the contract)

- [ ] **Step 3: Commit**

```bash
git add tests/test_server_register_validation_results.py
git commit -m "test(server): lock in run_summary passthrough in results endpoint"
```

---

## Unit 3 — Source Library UI (`static/index.html` + `static/app.js`)

### Task 10: Rename nav tab + add sub-tab markup in `index.html`

**Goal:** Rename `Source Audit` → `Source Library` and add the OSINT / Benchmarks pill selector.

**Files:**
- Modify: `static/index.html:804` (nav tab label)
- Modify: `static/index.html:1128` (tab body)

- [ ] **Step 1: Rename the nav label**

In `static/index.html:804`, change:
```html
<div class="nav-tab" id="nav-sources"  onclick="switchTab('sources')">Source Audit</div>
```
to:
```html
<div class="nav-tab" id="nav-sources"  onclick="switchTab('sources')">Source Library</div>
```

- [ ] **Step 2: Add sub-tab pill selector at the top of `#tab-sources`**

Immediately after line 1128 (`<div id="tab-sources" ...>`), insert:

```html
  <!-- Sub-tab pills -->
  <div id="sl-subtabs" style="display:flex;gap:8px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #21262d">
    <button id="sl-sub-osint" class="sl-subtab sl-subtab-active"
            onclick="switchSourceLibrarySubtab('osint')"
            style="padding:6px 14px;border-radius:14px;border:1px solid #30363d;background:#161b22;color:#c9d1d9;font-size:11px;cursor:pointer">
      OSINT <span id="sl-count-osint" style="color:#6e7681;margin-left:4px">(—)</span>
    </button>
    <button id="sl-sub-benchmarks" class="sl-subtab"
            onclick="switchSourceLibrarySubtab('benchmarks')"
            style="padding:6px 14px;border-radius:14px;border:1px solid #30363d;background:#0d1117;color:#8b949e;font-size:11px;cursor:pointer">
      Benchmarks <span id="sl-count-benchmarks" style="color:#6e7681;margin-left:4px">(—)</span>
    </button>
  </div>

  <!-- OSINT sub-tab body wrapper (existing source registry content lives inside) -->
  <div id="sl-body-osint"></div>

  <!-- Benchmarks sub-tab body -->
  <div id="sl-body-benchmarks" style="display:none">
    <div id="sl-bench-header" style="display:flex;gap:12px;align-items:center;margin-bottom:10px;font-size:11px">
      <span style="color:#6e7681">Register:</span>
      <select id="sl-bench-register" onchange="loadSourceLibraryBenchmarks()"
              style="background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 8px;font-size:11px"></select>
      <span style="color:#6e7681;margin-left:auto">View:</span>
      <button id="sl-bench-view-list"   class="sl-view-btn sl-view-active" onclick="switchBenchmarkView('list')">Source list</button>
      <button id="sl-bench-view-matrix" class="sl-view-btn" onclick="switchBenchmarkView('matrix')">Coverage matrix</button>
      <label style="color:#8b949e;margin-left:12px"><input type="checkbox" id="sl-bench-showall" onchange="loadSourceLibraryBenchmarks()"> Show all</label>
      <button onclick="window.openAddBenchmarkSourceModal()"
              style="margin-left:8px;padding:4px 10px;font-size:10px;color:#3fb950;background:#0a1a0a;border:1px solid #238636;border-radius:2px;cursor:pointer">+ Add source</button>
    </div>
    <div id="sl-bench-body"></div>
  </div>

  <!-- Shared modal: + Add benchmark source -->
  <div id="sl-add-source-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:100;align-items:center;justify-content:center">
    <div style="background:#0d1117;border:1px solid #30363d;padding:20px;border-radius:6px;min-width:420px;max-width:520px">
      <div style="font-size:12px;color:#c9d1d9;font-weight:600;margin-bottom:12px">Add Benchmark Source</div>
      <div id="sl-add-source-form"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px">
        <button onclick="closeAddBenchmarkSourceModal()" style="padding:5px 12px;font-size:11px;background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:2px;cursor:pointer">Cancel</button>
        <button onclick="submitAddBenchmarkSource()" style="padding:5px 12px;font-size:11px;background:#1a3a1a;color:#3fb950;border:1px solid #238636;border-radius:2px;cursor:pointer">Save</button>
      </div>
    </div>
  </div>
```

Keep the existing `src-stats-line`, filter bar, and source registry table that currently live inside `#tab-sources` — they will move inside `#sl-body-osint` in the next task. For now, wrap the existing content in a wrapper so we can relocate it.

- [ ] **Step 3: Wrap existing OSINT content**

Find the block inside `#tab-sources` that contains `src-stats-line`, filter dropdowns, and `src-table-body`. Wrap that entire existing block with the `sl-body-osint` div by adding an opening `<div id="sl-body-osint">` before the block and a closing `</div>` after it. **Do NOT remove any existing markup** — only add the wrapper. The goal is to keep the current page working, and have a scoped container for the OSINT view.

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): Source Library sub-tab markup (OSINT + Benchmarks)"
```

---

### Task 11: Sub-tab switcher + refactor `loadSources()` → `loadSourceLibraryOSINT()`

**Goal:** Wire the sub-tab pills to toggle between OSINT and Benchmarks bodies. Refactor the existing `renderSources()` into `loadSourceLibraryOSINT()`, preserving behaviour but reading from `/api/source-library/osint`.

**Files:**
- Modify: `static/app.js:1368` (tab switch dispatch), `static/app.js:3432` (renderSources → loadSourceLibraryOSINT)

- [ ] **Step 1: Add the sub-tab switcher**

Append to `static/app.js` (near the end of the source-library helper section — ok to place after `renderSources`):

```javascript
// ── Source Library sub-tabs ────────────────────────────────────
let _slActiveSubtab = 'osint';

function switchSourceLibrarySubtab(which) {
  _slActiveSubtab = which;
  const osintBtn = $('sl-sub-osint');
  const benchBtn = $('sl-sub-benchmarks');
  const osintBody = $('sl-body-osint');
  const benchBody = $('sl-body-benchmarks');
  if (which === 'osint') {
    osintBtn?.classList.add('sl-subtab-active');
    benchBtn?.classList.remove('sl-subtab-active');
    if (osintBtn) { osintBtn.style.background = '#161b22'; osintBtn.style.color = '#c9d1d9'; }
    if (benchBtn) { benchBtn.style.background = '#0d1117'; benchBtn.style.color = '#8b949e'; }
    if (osintBody) osintBody.style.display = '';
    if (benchBody) benchBody.style.display = 'none';
    loadSourceLibraryOSINT();
  } else {
    benchBtn?.classList.add('sl-subtab-active');
    osintBtn?.classList.remove('sl-subtab-active');
    if (benchBtn) { benchBtn.style.background = '#161b22'; benchBtn.style.color = '#c9d1d9'; }
    if (osintBtn) { osintBtn.style.background = '#0d1117'; osintBtn.style.color = '#8b949e'; }
    if (osintBody) osintBody.style.display = 'none';
    if (benchBody) benchBody.style.display = '';
    loadSourceLibraryBenchmarks();
  }
}
```

- [ ] **Step 2: Rename `renderSources` → `loadSourceLibraryOSINT` (add alias)**

Append to `static/app.js` right before the existing `async function renderSources() {` line (do NOT delete `renderSources`; we keep it as an alias so callers still work):

```javascript
async function loadSourceLibraryOSINT() {
  // Prefer the new endpoint — fall back to the old one if it's not deployed yet
  const statsEl = document.getElementById('src-stats-line');
  const body = document.getElementById('src-table-body');
  if (!body) return;
  body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">Loading...</div>';

  const region   = document.getElementById('src-filter-region')?.value   || '';
  const tier     = document.getElementById('src-filter-tier')?.value     || '';
  const search   = document.getElementById('src-search')?.value?.trim()  || '';

  const params = new URLSearchParams();
  if (region) params.set('region', region);
  if (tier)   params.set('tier',   tier);
  if (search) params.set('search', search);

  const data = await fetchJSON(`/api/source-library/osint?${params}`);
  if (!data) {
    body.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load sources.</div>';
    return;
  }
  if (statsEl) {
    statsEl.textContent = `${data.total} sources · ${data.filtered} shown · run ${(data.current_run_id||'').slice(0,10)}`;
  }
  const countPill = document.getElementById('sl-count-osint');
  if (countPill) countPill.textContent = `(${data.total})`;

  if (!data.sources.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No sources found.</div>';
    return;
  }
  _renderSourceLibraryOSINTTable(data.sources);
}

function _renderSourceLibraryOSINTTable(sources) {
  const body = document.getElementById('src-table-body');
  const rows = sources.map((s, i) => {
    const tier = _tierBadge(s.tier);
    const regions = (s.regions || []).join(', ') || '—';
    const cited = s.cited_rate != null ? `${Math.round(s.cited_rate * 100)}%` : '—';
    const delta = s.run_delta == null ? '—'
      : s.run_delta > 0 ? `<span style="color:#3fb950">↑ +${s.run_delta}</span>`
      : s.run_delta < 0 ? `<span style="color:#f85149">↓ ${s.run_delta}</span>`
      : '—';
    const lifecycle = s.lifecycle === 'active' ? `<span style="color:#3fb950">Active</span>`
      : s.lifecycle === 'blocked' ? `<span style="color:#f85149">Blocked</span>`
      : `<span style="color:#8b949e">Stale</span>`;
    return `<tr style="border-bottom:1px solid #21262d;font-size:11px">
      <td style="padding:6px 8px;color:#6e7681">${i + 1}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${esc(s.name || s.domain || '—')}</td>
      <td style="padding:6px 8px">${tier}</td>
      <td style="padding:6px 8px;color:#8b949e">${esc(s.type || '—')}</td>
      <td style="padding:6px 8px;color:#8b949e">${s.pillar || '—'}</td>
      <td style="padding:6px 8px;color:#8b949e">${esc(regions)}</td>
      <td style="padding:6px 8px;color:#c9d1d9;text-align:right">${s.appearance_count}</td>
      <td style="padding:6px 8px;color:#c9d1d9;text-align:right">${cited}</td>
      <td style="padding:6px 8px;color:#8b949e">${s.last_seen ? s.last_seen.slice(0, 10) : '—'}</td>
      <td style="padding:6px 8px;text-align:right">${delta}</td>
      <td style="padding:6px 8px">${lifecycle}</td>
    </tr>`;
  }).join('');
  body.innerHTML = `<table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="text-align:left;color:#6e7681;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid #30363d">
        <th style="padding:8px">#</th><th style="padding:8px">Source</th>
        <th style="padding:8px">Tier</th><th style="padding:8px">Type</th>
        <th style="padding:8px">Pillar</th><th style="padding:8px">Regions</th>
        <th style="padding:8px;text-align:right">Runs</th><th style="padding:8px;text-align:right">Cited %</th>
        <th style="padding:8px">Last seen</th><th style="padding:8px;text-align:right">Δ vs prev</th>
        <th style="padding:8px">Status</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
  <div style="font-size:9px;color:#6e7681;padding:6px 2px">Runs/Cited %/Regions/Last seen are <strong>lifetime</strong>. Δ vs prev is <strong>per-run</strong>.</div>`;
}
```

- [ ] **Step 3: Hook the switcher into `switchTab` (line 1368)**

Change:
```javascript
  if (tab === 'sources')  renderSources();
```
to:
```javascript
  if (tab === 'sources')  switchSourceLibrarySubtab(_slActiveSubtab);
```

- [ ] **Step 4: Manually smoke test**

```bash
uv run uvicorn server:app --host 127.0.0.1 --port 8001 &
# (Orchestrator runs this via Bash)
curl -s http://127.0.0.1:8001/api/source-library/osint | python -m json.tool | head -40
```
Expected: valid JSON response (may be empty list if local sources.db is empty).

Then in browser at http://127.0.0.1:8001: click `Source Library` → verify the OSINT sub-tab renders without console errors.

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): sub-tab switcher + refactor OSINT load onto new endpoint"
```

---

### Task 12: Benchmarks source list view

**Goal:** Populate the register dropdown, fetch `/api/source-library/benchmarks`, render the source list table with covered-scenarios column + cited-in-current-run.

**Files:**
- Modify: `static/app.js` (append new helpers)

- [ ] **Step 1: Implement the loader**

Append to `static/app.js`:

```javascript
// ── Source Library Benchmarks ──────────────────────────────────
let _slBenchView = 'list';         // 'list' | 'matrix'
let _slBenchData = null;

async function loadSourceLibraryBenchmarks() {
  const reg = document.getElementById('sl-bench-register')?.value || '';
  const showAll = document.getElementById('sl-bench-showall')?.checked || false;
  const body = document.getElementById('sl-bench-body');
  if (!body) return;
  body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">Loading...</div>';

  // Populate register dropdown if empty
  const sel = document.getElementById('sl-bench-register');
  if (sel && sel.options.length === 0) {
    const regs = await fetchJSON('/api/registers') || [];
    sel.innerHTML = regs.map(r =>
      `<option value="${esc(r.register_id)}">${esc(r.display_name || r.register_id)}</option>`
    ).join('');
  }

  const params = new URLSearchParams();
  if (reg) params.set('register', reg);
  if (showAll) params.set('show_all', 'true');

  const data = await fetchJSON(`/api/source-library/benchmarks?${params}`);
  if (!data) {
    body.innerHTML = '<div style="color:#f85149;font-size:11px;padding:12px">Failed to load benchmarks.</div>';
    return;
  }
  _slBenchData = data;
  const countPill = document.getElementById('sl-count-benchmarks');
  if (countPill) countPill.textContent = `(${(data.sources || []).length})`;

  if (_slBenchView === 'matrix') {
    renderBenchmarkMatrix(data);
  } else {
    _renderBenchmarkList(data, showAll);
  }
}

function _renderBenchmarkList(data, showAll) {
  const body = document.getElementById('sl-bench-body');
  if (!data.sources.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No benchmark sources match this register.</div>';
    return;
  }
  const scenColHeader = showAll ? 'Scenario tags covered' : 'Scenarios in this register';
  const rows = data.sources.map((s, i) => {
    const provBadge = s.provenance === 'analyst'
      ? `<span style="font-size:9px;background:#3a2a0a;color:#e3b341;border:1px solid #6b4e0a;padding:1px 5px;border-radius:2px;margin-left:4px">analyst</span>`
      : '';
    const scenList = showAll ? (s.scenario_tags || []) : (s.covered_scenarios || []);
    const cited = (s.cited_in_current_run || []).length > 0
      ? (s.cited_in_current_run || []).map(c => esc(c.scenario)).join(', ')
      : '<span style="color:#484f58">—</span>';
    return `<tr style="border-bottom:1px solid #21262d;font-size:11px">
      <td style="padding:6px 8px;color:#6e7681">${i + 1}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${esc(s.name)}${provBadge}</td>
      <td style="padding:6px 8px">${_tierBadge(s.reliability)}</td>
      <td style="padding:6px 8px;color:#8b949e">${s.edition_year || '—'}</td>
      <td style="padding:6px 8px;color:#8b949e">${esc(s.cadence || '—')}</td>
      <td style="padding:6px 8px;color:#8b949e">${esc((s.sector_tags || []).join(', ') || '—')}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${esc(scenList.join(', ') || '—')}</td>
      <td style="padding:6px 8px;color:#8b949e">${s.last_checked ? s.last_checked.slice(0, 10) : '—'}</td>
      <td style="padding:6px 8px;color:#c9d1d9">${cited}</td>
    </tr>`;
  }).join('');

  body.innerHTML = `<table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="text-align:left;color:#6e7681;font-size:10px;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid #30363d">
        <th style="padding:8px">#</th><th style="padding:8px">Source</th>
        <th style="padding:8px">Reliability</th><th style="padding:8px">Edition</th>
        <th style="padding:8px">Cadence</th><th style="padding:8px">Sectors</th>
        <th style="padding:8px">${scenColHeader}</th><th style="padding:8px">Last checked</th>
        <th style="padding:8px">Cited in current run</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function switchBenchmarkView(view) {
  _slBenchView = view;
  const listBtn = document.getElementById('sl-bench-view-list');
  const matrixBtn = document.getElementById('sl-bench-view-matrix');
  const showAllEl = document.getElementById('sl-bench-showall');
  // When matrix view is active, grey out show_all (matrix is always register-scoped)
  if (view === 'matrix') {
    if (showAllEl) { showAllEl.disabled = true; showAllEl.checked = false; }
    matrixBtn?.classList.add('sl-view-active');
    listBtn?.classList.remove('sl-view-active');
  } else {
    if (showAllEl) showAllEl.disabled = false;
    listBtn?.classList.add('sl-view-active');
    matrixBtn?.classList.remove('sl-view-active');
  }
  loadSourceLibraryBenchmarks();
}
```

- [ ] **Step 2: Manually smoke test**

In browser at http://127.0.0.1:8001: click `Source Library` → `Benchmarks`. Expected: the `Wind Power Plant` register is pre-selected and the table renders the 2 sources from `data/validation_sources.json` that intersect with the wind power scenarios (Verizon + Mandiant at minimum).

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): benchmarks sub-tab source list view"
```

---

### Task 13: Benchmarks coverage matrix view

**Goal:** Render a scenarios-×-sources grid with ✓ cells, row/column totals, and ⚠ flags for scenarios with ≤ 1 source.

**Files:**
- Modify: `static/app.js` (append)

- [ ] **Step 1: Implement `renderBenchmarkMatrix`**

Append to `static/app.js`:

```javascript
function renderBenchmarkMatrix(data) {
  const body = document.getElementById('sl-bench-body');
  const scenarios = data.scenarios || [];
  const sources = data.sources || [];
  if (!scenarios.length || !sources.length) {
    body.innerHTML = '<div style="color:#6e7681;font-size:11px;padding:12px">No register or no sources.</div>';
    return;
  }
  const matrix = data.matrix || {};
  const perScenarioCount = (scen) => sources.filter(s => matrix[scen] && matrix[scen][s.id]).length;
  const perSourceCount   = (sid)  => scenarios.filter(scen => matrix[scen] && matrix[scen][sid]).length;

  const headerCells = sources.map(s =>
    `<th style="padding:6px;font-size:10px;color:#8b949e;writing-mode:vertical-rl;transform:rotate(180deg);min-width:26px">${esc(s.name)}</th>`
  ).join('');
  const rows = scenarios.map(scen => {
    const count = perScenarioCount(scen);
    const warn = count <= 1 ? ' ⚠' : '';
    const cells = sources.map(s => {
      const on = matrix[scen] && matrix[scen][s.id];
      return on
        ? `<td style="padding:6px;text-align:center;color:#3fb950">✓</td>`
        : `<td style="padding:6px;text-align:center;color:#484f58">·</td>`;
    }).join('');
    const warnColor = count === 0 ? '#f85149' : count === 1 ? '#e3b341' : '#c9d1d9';
    return `<tr style="border-bottom:1px solid #21262d;font-size:11px">
      <td style="padding:6px;color:#c9d1d9;white-space:nowrap">${esc(scen)}</td>
      ${cells}
      <td style="padding:6px;text-align:right;color:${warnColor};font-weight:600">${count}/${sources.length}${warn}</td>
    </tr>`;
  }).join('');

  const footerCells = sources.map(s =>
    `<td style="padding:6px;text-align:center;color:#8b949e">${perSourceCount(s.id)}/${scenarios.length}</td>`
  ).join('');

  body.innerHTML = `<table style="border-collapse:collapse;margin-top:4px">
    <thead>
      <tr style="border-bottom:1px solid #30363d">
        <th style="padding:6px;text-align:left;color:#6e7681;font-size:10px;text-transform:uppercase">Scenario</th>
        ${headerCells}
        <th style="padding:6px;color:#6e7681;font-size:10px;text-transform:uppercase">Coverage</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
    <tfoot>
      <tr style="border-top:1px solid #30363d">
        <td style="padding:6px;color:#6e7681;font-size:10px;text-transform:uppercase">Coverage</td>
        ${footerCells}
        <td></td>
      </tr>
    </tfoot>
  </table>
  ${data.coverage_summary
    ? `<div style="font-size:10px;color:#8b949e;padding:8px 2px">
        ⚠ Gaps: ${data.coverage_summary.uncovered_count} uncovered, ${data.coverage_summary.thinly_covered_count} thinly covered</div>`
    : ''}`;
}
```

- [ ] **Step 2: Smoke test**

Click `Source Library` → `Benchmarks` → `Coverage matrix`. Expected: the wind power scenarios render as rows, benchmark sources as columns, ✓ cells match the `scenario_tags` data.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): benchmarks coverage matrix view"
```

---

### Task 14: `+ Add new source` modal — expose on `window`

**Goal:** A shared modal that opens from both the Benchmarks sub-tab and (in Unit 4) the baseline picker. Must be exposed as `window.openAddBenchmarkSourceModal(opts)`.

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Implement the modal**

Append to `static/app.js`:

```javascript
// ── Shared: Add benchmark source modal ─────────────────────────
let _slAddSourceOnSave = null;

window.openAddBenchmarkSourceModal = function (opts) {
  opts = opts || {};
  _slAddSourceOnSave = typeof opts.onSave === 'function' ? opts.onSave : null;
  const modal = document.getElementById('sl-add-source-modal');
  const form = document.getElementById('sl-add-source-form');
  if (!modal || !form) return;
  form.innerHTML = `
    <div style="display:grid;gap:8px;font-size:11px;color:#c9d1d9">
      <label>Name <input id="sl-as-name" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>URL  <input id="sl-as-url"  style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Reliability
        <select id="sl-as-rel" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px">
          <option value="A">A</option><option value="B" selected>B</option><option value="C">C</option>
        </select>
      </label>
      <label>Edition year <input id="sl-as-year" type="number" value="2025" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Cadence <input id="sl-as-cad" value="annual" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Scenario tags (comma-separated) <input id="sl-as-scen" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
      <label>Sector tags (comma-separated) <input id="sl-as-sect" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:4px 6px"></label>
    </div>`;
  modal.style.display = 'flex';
};

function closeAddBenchmarkSourceModal() {
  const modal = document.getElementById('sl-add-source-modal');
  if (modal) modal.style.display = 'none';
  _slAddSourceOnSave = null;
}

async function submitAddBenchmarkSource() {
  const body = {
    name: document.getElementById('sl-as-name')?.value?.trim() || '',
    url:  document.getElementById('sl-as-url')?.value?.trim() || '',
    admiralty_reliability: document.getElementById('sl-as-rel')?.value || 'B',
    edition_year: parseInt(document.getElementById('sl-as-year')?.value || '2025', 10),
    cadence: document.getElementById('sl-as-cad')?.value || 'annual',
    scenario_tags: (document.getElementById('sl-as-scen')?.value || '').split(',').map(x => x.trim()).filter(Boolean),
    sector_tags:   (document.getElementById('sl-as-sect')?.value || '').split(',').map(x => x.trim()).filter(Boolean),
    provenance: 'analyst',
  };
  if (!body.name || !body.url) {
    alert('Name and URL are required');
    return;
  }
  const res = await fetch('/api/validation/sources/add', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert('Failed to add source: ' + (err.error || res.status));
    return;
  }
  const result = await res.json();
  const newId = result.source_id;
  closeAddBenchmarkSourceModal();
  if (_slActiveSubtab === 'benchmarks') loadSourceLibraryBenchmarks();
  if (_slAddSourceOnSave) _slAddSourceOnSave(newId);
}
```

- [ ] **Step 2: Smoke test**

Click `Source Library` → `Benchmarks` → `+ Add source`. Verify the modal opens, saving posts to the API, the new source appears in the list with an `analyst` badge, and the modal closes.

Open the browser console and verify `typeof window.openAddBenchmarkSourceModal === 'function'` returns `true`.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): shared + Add benchmark source modal exposed on window"
```

---

## Unit 4 — Risk Register Cleanup + Run Summary Card + Baseline Editor

### Task 15: Delete dead Risk Register source registry code

**Goal:** Remove the bottom panel from the Risk Register tab and the 6 dead JS functions.

**Files:**
- Modify: `static/index.html:1105-1123` (delete bottom panel)
- Modify: `static/app.js:2858-3052` (delete 6 dead functions)

- [ ] **Step 1: Remove the bottom panel HTML**

In `static/index.html`, delete lines 1105-1123 (the `<!-- Source Registry (full-width, collapsed by default) -->` block through the closing `</div>` at 1123). Leave the `</div>` at 1125 in place — that's the `#tab-register` wrapper close.

- [ ] **Step 2: Remove the dead functions from `static/app.js`**

Delete the following functions entirely from `static/app.js:2858-3052`:
- `toggleSourceRegistry`
- `loadValSources`
- `submitAddSource`
- `deleteValSource`
- `loadValCandidates`
- `promoteCandidate`
- `dismissCandidate`

Also remove the two calls at lines 2569-2570 (`loadValSources(); loadValCandidates();`) — these are inside whatever function initialises the Risk Register tab. After deletion, confirm no remaining references to any of those function names exist.

- [ ] **Step 3: Verify no broken references**

Run: (orchestrator) `grep -n "loadValSources\|toggleSourceRegistry\|submitAddSource\|deleteValSource\|loadValCandidates\|promoteCandidate\|dismissCandidate" static/app.js static/index.html`
Expected: no output.

- [ ] **Step 4: Manually smoke test**

Reload the app, open the Risk Register tab. Expected: no console errors, no dangling bottom panel, matrix + scenario detail still render.

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "refactor(ui): remove dead Risk Register source-registry code"
```

---

### Task 16: Run summary card slot + `renderRunSummary()`

**Goal:** A card rendered above the matrix that reflects the latest `run_summary` block from `/api/register-validation/results`.

**Files:**
- Modify: `static/index.html` (add slot above matrix)
- Modify: `static/app.js` (add `renderRunSummary`)

- [ ] **Step 1: Add the card slot in `index.html`**

In `static/index.html`, find `<div id="register-bar">` (line 825) and locate the closing `</div>` of its associated section. Immediately after the `register-bar` closes (before `<div id="val-progress">` at line 1095), insert:

```html
  <div id="rr-run-summary-card" style="flex-shrink:0;margin:0 16px 10px 16px"></div>
```

- [ ] **Step 2: Implement `renderRunSummary()`**

Append to `static/app.js` (inside the risk-register helpers block):

```javascript
// ── Risk Register: run summary card ───────────────────────────
async function loadAndRenderRunSummary() {
  const data = await fetchJSON('/api/register-validation/results');
  const slot = document.getElementById('rr-run-summary-card');
  if (!slot) return;
  if (!data || !data.run_summary) { slot.innerHTML = ''; return; }
  renderRunSummary(data.run_summary);
}

function _runSummaryDeltaSign(cur, prev) {
  if (prev == null) return '';
  const d = (cur || 0) - (prev || 0);
  if (d === 0) return `<span style="color:#6e7681">(–)</span>`;
  const c = d > 0 ? '#3fb950' : '#f85149';
  return `<span style="color:${c}">(${d > 0 ? '+' : ''}${d})</span>`;
}

function renderRunSummary(s) {
  const slot = document.getElementById('rr-run-summary-card');
  if (!slot) return;
  const collapsedKey = 'rr-run-summary-collapsed';
  const isCollapsed = localStorage.getItem(collapsedKey) === 'true';

  const cur = s.verdicts?.current || {};
  const prev = s.verdicts?.previous || null;
  const deltas = s.verdicts?.deltas || [];
  const gaps = s.coverage_gaps || [];
  const bu = s.baseline_usage || {};
  const evi = s.evidence || {};
  const src = s.sources || {};
  const newHtml = (src.new_this_run || []).map(n => esc(n.name)).join(', ') || '—';
  const dropHtml = (src.dropped_this_run || []).map(n => esc(n.name)).join(', ') || '—';
  const byTier = Object.entries(src.by_tier || {}).map(([t, n]) => `${t}:${n}`).join(' · ');

  const dateLabel = s.run_id ? s.run_id.replace('T', ' ').replace('Z', '') : '—';
  const durLabel = s.duration_seconds ? `${Math.floor(s.duration_seconds / 60)}m ${s.duration_seconds % 60}s` : '';

  if (isCollapsed) {
    slot.innerHTML = `<div onclick="_toggleRunSummaryCard()" style="cursor:pointer;background:#0d1117;border:1px solid #21262d;padding:8px 14px;font-size:11px;color:#8b949e;border-radius:4px">
      Last run ${dateLabel} — ${cur.support || 0} SUPPORT, ${cur.challenge || 0} CHALLENGE, ${cur.insufficient || 0} INSUF · ${deltas.length} changes · ${gaps.length} gaps · ▸
    </div>`;
    return;
  }

  const deltaRows = deltas.map(d => {
    const arrow = d.direction === 'improved' ? '↑' : '↓';
    const color = d.direction === 'improved' ? '#3fb950' : '#f85149';
    return `<div onclick="_scrollToScenario('${esc(d.scenario)}')" style="cursor:pointer;color:${color};font-size:10px">${arrow} ${esc(d.scenario)} (${d.dim}): ${d.from} → ${d.to.toUpperCase()}</div>`;
  }).join('') || '<div style="color:#484f58;font-size:10px">No verdict changes.</div>';

  const gapRows = gaps.map(g =>
    `<div onclick="_jumpToCoverageMatrix('${esc(g.scenario)}')" style="cursor:pointer;color:#e3b341;font-size:10px">⚠ ${esc(g.scenario)} — ${esc(g.issue)}</div>`
  ).join('') || '<div style="color:#484f58;font-size:10px">No gaps.</div>';

  slot.innerHTML = `<div style="background:#0d1117;border:1px solid #21262d;border-radius:4px">
    <div onclick="_toggleRunSummaryCard()" style="cursor:pointer;display:flex;justify-content:space-between;padding:8px 14px;border-bottom:1px solid #21262d">
      <span style="font-size:11px;color:#c9d1d9;font-weight:600">Last validation run</span>
      <span style="font-size:10px;color:#6e7681">${dateLabel} ${durLabel ? '· ' + durLabel : ''} ▾</span>
    </div>
    <div style="padding:10px 14px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;font-size:11px">
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Verdicts</div>
        <div style="color:#3fb950">SUPPORT <strong>${cur.support || 0}</strong> ${_runSummaryDeltaSign(cur.support, prev?.support)}</div>
        <div style="color:#f85149">CHALLENGE <strong>${cur.challenge || 0}</strong> ${_runSummaryDeltaSign(cur.challenge, prev?.challenge)}</div>
        <div style="color:#8b949e">INSUF. <strong>${cur.insufficient || 0}</strong> ${_runSummaryDeltaSign(cur.insufficient, prev?.insufficient)}</div>
      </div>
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Sources</div>
        <div style="color:#c9d1d9">${src.matched || 0}/${src.queried || 0} matched</div>
        <div style="color:#8b949e;font-size:10px">${byTier || '—'}</div>
        <div style="color:#8b949e;font-size:10px">+ ${newHtml} · − ${dropHtml}</div>
      </div>
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Evidence</div>
        <div style="color:#c9d1d9">Fin: ${evi.fin_after_iqr_filter || 0}/${evi.fin_extracted || 0}</div>
        <div style="color:#c9d1d9">Prob: ${evi.prob_after_iqr_filter || 0}/${evi.prob_extracted || 0}</div>
        <div style="color:#8b949e;font-size:10px">${evi.outliers_removed || 0} outliers cut</div>
      </div>
    </div>
    <div style="padding:10px 14px;border-top:1px solid #21262d;display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Gaps</div>
        ${gapRows}
      </div>
      <div>
        <div style="color:#6e7681;font-size:9px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">Changes</div>
        ${deltaRows}
      </div>
    </div>
    <div style="padding:8px 14px;border-top:1px solid #21262d;font-size:10px;color:#8b949e">
      Baseline: ${bu.scenarios_with_baseline || 0} scenarios · ${bu.baseline_aligned_with_osint || 0} aligned · ${bu.baseline_diverged_from_osint || 0} diverged
    </div>
  </div>`;
}

function _toggleRunSummaryCard() {
  const k = 'rr-run-summary-collapsed';
  localStorage.setItem(k, localStorage.getItem(k) === 'true' ? 'false' : 'true');
  loadAndRenderRunSummary();
}

function _scrollToScenario(name) {
  const rows = document.querySelectorAll('#rr-scenario-list [data-scenario-name]');
  for (const el of rows) {
    if (el.getAttribute('data-scenario-name') === name) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.click();
      return;
    }
  }
}

function _jumpToCoverageMatrix(scenarioName) {
  switchTab('sources');
  switchSourceLibrarySubtab('benchmarks');
  _slBenchView = 'matrix';
  loadSourceLibraryBenchmarks();
}
```

- [ ] **Step 3: Call `loadAndRenderRunSummary()` from the risk register init**

Find the Risk Register tab init in `static/app.js` (the function that currently runs when `switchTab('register')` fires — it's the code near line 2569 that used to call `loadValSources/loadValCandidates`). Add after the register matrix rendering:

```javascript
  loadAndRenderRunSummary();
```

- [ ] **Step 4: Smoke test**

Reload the app, open the Risk Register tab. Expected: the card renders above the matrix populated from the last real validation run.

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(ui): Risk Register run summary card"
```

---

### Task 17: Analyst baseline editor in scenario detail panel

**Goal:** Collapsible block below the description editor in `_renderScenarioDetail`. Holds form state across modal opens. Uses the `+ Add from library` picker that calls `window.openAddBenchmarkSourceModal` for inline source creation.

**Files:**
- Modify: `static/app.js:2624` (_renderScenarioDetail)

- [ ] **Step 1: Implement baseline editor helpers**

Append to `static/app.js`:

```javascript
// ── Baseline editor ─────────────────────────────────────────────
let _baselineDraft = null;  // { registerId, scenarioIndex, fin, prob }

function _baselineKey(regId, idx) { return `${regId}::${idx}`; }

function renderBaselineEditor(scenario, valScenario, registerId, scenarioIndex) {
  const existing = scenario.analyst_baseline || null;
  const draft = (_baselineDraft && _baselineDraft.key === _baselineKey(registerId, scenarioIndex))
    ? _baselineDraft : { key: _baselineKey(registerId, scenarioIndex), fin: existing?.fin || null, prob: existing?.prob || null };
  _baselineDraft = draft;

  const expanded = !!existing;
  const finB = draft.fin || {};
  const probB = draft.prob || {};

  return `<div id="bl-editor-wrap" style="margin:10px 0;border:1px solid #21262d;border-radius:3px">
    <div onclick="_toggleBaselineEditor()" style="cursor:pointer;padding:6px 10px;font-size:10px;color:#8b949e;text-transform:uppercase;letter-spacing:0.05em;background:#161b22">
      Analyst Baseline ${existing ? '◆' : ''} <span id="bl-toggle-arrow">${expanded ? '▾' : '▸'}</span>
    </div>
    <div id="bl-editor-body" style="display:${expanded ? 'block' : 'none'};padding:10px 12px;font-size:11px">

      <div style="color:#8b949e;font-size:10px;margin-bottom:4px">Impact (USD)</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:6px">
        <label style="font-size:10px;color:#6e7681">Mid <input id="bl-fin-val" type="number" value="${finB.value_usd || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">Low <input id="bl-fin-lo"  type="number" value="${finB.low_usd   || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">High<input id="bl-fin-hi"  type="number" value="${finB.high_usd  || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
      </div>
      <div id="bl-fin-sources" style="margin-bottom:4px">${_renderBaselineSourceChips(finB.source_ids || [], 'fin')}</div>
      <button onclick="_openBaselineSourcePicker('fin')" style="font-size:10px;padding:3px 10px;background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:2px;cursor:pointer">+ Add from library</button>
      <input id="bl-fin-notes" placeholder="Notes…" value="${esc(finB.notes || '')}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px;margin:6px 0">

      <div style="color:#8b949e;font-size:10px;margin-top:10px;margin-bottom:4px">Probability (annual, 0..1)</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:6px">
        <label style="font-size:10px;color:#6e7681">Mid <input id="bl-prob-val" type="number" step="0.01" value="${probB.annual_rate || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">Low <input id="bl-prob-lo"  type="number" step="0.01" value="${probB.low || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
        <label style="font-size:10px;color:#6e7681">High<input id="bl-prob-hi"  type="number" step="0.01" value="${probB.high || ''}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px"></label>
      </div>
      <label style="font-size:10px;color:#6e7681">Evidence type
        <select id="bl-prob-evt" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px">
          ${['frequency_rate','prevalence_survey','mixed','expert_estimate','unknown']
            .map(v => `<option value="${v}" ${probB.evidence_type===v?'selected':''}>${v}</option>`).join('')}
        </select>
      </label>
      <div id="bl-prob-sources" style="margin:6px 0 4px 0">${_renderBaselineSourceChips(probB.source_ids || [], 'prob')}</div>
      <button onclick="_openBaselineSourcePicker('prob')" style="font-size:10px;padding:3px 10px;background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:2px;cursor:pointer">+ Add from library</button>
      <input id="bl-prob-notes" placeholder="Notes…" value="${esc(probB.notes || '')}" style="width:100%;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:3px 5px;font-size:11px;margin:6px 0">

      <div style="display:flex;gap:8px;margin-top:10px">
        <button onclick="saveBaseline('${esc(registerId)}', ${scenarioIndex})" style="padding:5px 12px;font-size:11px;background:#1a3a1a;color:#3fb950;border:1px solid #238636;border-radius:2px;cursor:pointer">Save baseline</button>
        <button onclick="clearBaseline('${esc(registerId)}', ${scenarioIndex})" style="padding:5px 12px;font-size:11px;background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:2px;cursor:pointer">Clear</button>
      </div>
    </div>
  </div>`;
}

function _renderBaselineSourceChips(sourceIds, dim) {
  if (!sourceIds.length) return '<span style="color:#484f58;font-size:10px">No sources</span>';
  return sourceIds.map(id => {
    const known = (window._baselineKnownIds || new Set()).has(id);
    const style = known
      ? 'background:#161b22;color:#c9d1d9;border:1px solid #30363d'
      : 'background:#2a0a0a;color:#8b949e;border:1px solid #6b2222;text-decoration:line-through';
    const warn = known ? '' : ' <span style="color:#f85149;font-size:9px">(missing)</span>';
    return `<span style="${style};padding:2px 6px;border-radius:2px;font-size:10px;margin-right:4px;cursor:pointer" onclick="_removeBaselineSource('${esc(id)}', '${dim}')">${esc(id)}${warn} ×</span>`;
  }).join('');
}

function _toggleBaselineEditor() {
  const body = document.getElementById('bl-editor-body');
  const arrow = document.getElementById('bl-toggle-arrow');
  if (!body) return;
  const isOpen = body.style.display !== 'none';
  body.style.display = isOpen ? 'none' : 'block';
  if (arrow) arrow.textContent = isOpen ? '▸' : '▾';
}

function _openBaselineSourcePicker(dim) {
  // Minimal picker: fetch /api/validation/sources, show prompt-style list.
  // The "+ Add new source" button inside the picker calls window.openAddBenchmarkSourceModal.
  fetchJSON('/api/validation/sources').then(data => {
    const sources = (data && data.sources) || [];
    const options = sources.map(s => `${s.id} — ${s.name}`).join('\n');
    const picked = prompt(
      `Paste a source ID from the list below, or type "+" to add a new source:\n\n${options}`,
      ''
    );
    if (!picked) return;
    if (picked === '+') {
      window.openAddBenchmarkSourceModal({ onSave: (newId) => _addBaselineSource(newId, dim) });
      return;
    }
    _addBaselineSource(picked.trim(), dim);
  });
}

function _addBaselineSource(id, dim) {
  if (!_baselineDraft) return;
  _baselineDraft[dim] = _baselineDraft[dim] || {};
  const ids = _baselineDraft[dim].source_ids || [];
  if (!ids.includes(id)) ids.push(id);
  _baselineDraft[dim].source_ids = ids;
  const el = document.getElementById(`bl-${dim}-sources`);
  if (el) el.innerHTML = _renderBaselineSourceChips(ids, dim);
}

function _removeBaselineSource(id, dim) {
  if (!_baselineDraft || !_baselineDraft[dim]) return;
  _baselineDraft[dim].source_ids = (_baselineDraft[dim].source_ids || []).filter(x => x !== id);
  const el = document.getElementById(`bl-${dim}-sources`);
  if (el) el.innerHTML = _renderBaselineSourceChips(_baselineDraft[dim].source_ids, dim);
}

async function saveBaseline(registerId, scenarioIndex) {
  const finVal = parseFloat(document.getElementById('bl-fin-val')?.value || '');
  const finLo  = parseFloat(document.getElementById('bl-fin-lo')?.value  || '');
  const finHi  = parseFloat(document.getElementById('bl-fin-hi')?.value  || '');
  const probVal = parseFloat(document.getElementById('bl-prob-val')?.value || '');
  const probLo  = parseFloat(document.getElementById('bl-prob-lo')?.value  || '');
  const probHi  = parseFloat(document.getElementById('bl-prob-hi')?.value  || '');

  const body = {};
  if (!isNaN(finVal) && !isNaN(finLo) && !isNaN(finHi)) {
    if (!(finLo <= finVal && finVal <= finHi)) { alert('Fin: low ≤ mid ≤ high required'); return; }
    body.fin = {
      value_usd: finVal, low_usd: finLo, high_usd: finHi,
      source_ids: _baselineDraft?.fin?.source_ids || [],
      notes: document.getElementById('bl-fin-notes')?.value || '',
    };
  }
  if (!isNaN(probVal) && !isNaN(probLo) && !isNaN(probHi)) {
    if (!(0 <= probLo && probHi <= 1)) { alert('Prob: values must be in [0, 1]'); return; }
    if (!(probLo <= probVal && probVal <= probHi)) { alert('Prob: low ≤ mid ≤ high required'); return; }
    body.prob = {
      annual_rate: probVal, low: probLo, high: probHi,
      evidence_type: document.getElementById('bl-prob-evt')?.value || 'unknown',
      source_ids: _baselineDraft?.prob?.source_ids || [],
      notes: document.getElementById('bl-prob-notes')?.value || '',
    };
  }
  if (!body.fin && !body.prob) { alert('Enter at least one of fin or prob'); return; }

  const res = await fetch(`/api/registers/${registerId}/scenarios/${scenarioIndex}/baseline`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert('Save failed: ' + (err.error || res.status));
    return;
  }
  _baselineDraft = null;
  // Reload the register to reflect the new baseline
  if (typeof loadRegister === 'function') loadRegister(registerId);
}

async function clearBaseline(registerId, scenarioIndex) {
  if (!confirm('Clear baseline for this scenario?')) return;
  const res = await fetch(`/api/registers/${registerId}/scenarios/${scenarioIndex}/baseline`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(null),
  });
  if (!res.ok) { alert('Clear failed'); return; }
  _baselineDraft = null;
  if (typeof loadRegister === 'function') loadRegister(registerId);
}
```

- [ ] **Step 2: Insert the editor into `_renderScenarioDetail`**

In `_renderScenarioDetail` (around line 2624), immediately after the description editor render and before the dimension cards, add:

```javascript
  const registerId = (window._activeRegisterId) || '';
  const scenarioIndex = (window._activeScenarioIndex != null) ? window._activeScenarioIndex : 0;
  const baselineHtml = renderBaselineEditor(scenario, valScenario, registerId, scenarioIndex);
```

Then include `${baselineHtml}` in the detail panel HTML where appropriate (between description editor and the impact/probability cards).

If `window._activeRegisterId` / `window._activeScenarioIndex` don't already exist, set them in the functions that mark a scenario active (search for where the scenario detail is shown — set `window._activeRegisterId = ...; window._activeScenarioIndex = ...;` right before calling `_renderScenarioDetail`).

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): analyst baseline editor in scenario detail panel"
```

---

### Task 18: Baseline row in dimension cards + orphan chip rendering

**Goal:** Extend `_renderRegValDimension` (line 3365) to insert a `Baseline (you): …` row above the OSINT range when present, with a `◆` marker and strikethrough chips for orphan IDs.

**Files:**
- Modify: `static/app.js:3365` (`_renderRegValDimension`)

- [ ] **Step 1: Extend the function**

Find `_renderRegValDimension(scenId, dim, d, versionChecks)` (line 3365). Change its signature to accept the scenario's analyst baseline block:

```javascript
function _renderRegValDimension(scenId, dim, d, versionChecks, baseline) {
```

Inside, after the verdict header but **before** the OSINT range row, add:

```javascript
  let baselineRow = '';
  if (baseline) {
    if (dim === 'financial' && baseline.fin) {
      const b = baseline.fin;
      const fmt = (x) => `$${(x/1_000_000).toFixed(1)}M`;
      baselineRow = `<div style="padding:4px 10px;color:#e3b341;font-size:11px">
        Baseline (you): ${fmt(b.value_usd)} [${fmt(b.low_usd)}–${fmt(b.high_usd)}] ◆
      </div>`;
    } else if (dim === 'probability' && baseline.prob) {
      const b = baseline.prob;
      baselineRow = `<div style="padding:4px 10px;color:#e3b341;font-size:11px">
        Baseline (you): ${(b.annual_rate*100).toFixed(1)}% [${(b.low*100).toFixed(1)}%–${(b.high*100).toFixed(1)}%] ◆ <span style="color:#6e7681;font-size:10px">(${b.evidence_type})</span>
      </div>`;
    }
  }
```

Inject `${baselineRow}` at the right place in the dimension card HTML (immediately above the `${rangeRow}` / benchmark range output).

Update the two call sites in `_renderScenarioDetail` (lines 2654-2655) to pass the baseline:

```javascript
    const finHtml = _renderRegValDimension(scenario.scenario_id, 'financial',   valScenario.financial,   versionChecks, scenario.analyst_baseline);
    const probHtml = _renderRegValDimension(scenario.scenario_id, 'probability', valScenario.probability, versionChecks, scenario.analyst_baseline);
```

- [ ] **Step 2: Populate `window._baselineKnownIds` on load**

In the function that loads `/api/validation/sources` (or at the top of `renderBaselineEditor`), build a Set of known source IDs so orphan chips render correctly. Append to `static/app.js`:

```javascript
async function refreshBaselineKnownIds() {
  const data = await fetchJSON('/api/validation/sources');
  window._baselineKnownIds = new Set(((data && data.sources) || []).map(s => s.id));
}
```

Call `refreshBaselineKnownIds()` on Risk Register tab load (right before `loadAndRenderRunSummary()`).

- [ ] **Step 3: Smoke test**

Open a scenario with a baseline (create one via the editor if needed). Expected: the IMPACT card shows a golden `Baseline (you): $4.2M [...] ◆` row above the OSINT range; probability likewise. Set a source_id that doesn't exist in `validation_sources.json`, reload, expected: strikethrough chip with red `(missing)` tag.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): baseline row in dimension cards + orphan chip rendering"
```

---

## Unit 5 — End-to-End Smoke Test

### Task 19: Full pipeline smoke test

**Goal:** Run the full validator + server + UI stack against the `wind_power_plant` register fixture and confirm every piece of the spec lights up.

**Files:** none (this is a verification task)

- [ ] **Step 1: Add a fixture baseline to the wind power register**

Edit `data/registers/wind_power_plant.json` — on the `Ransomware` scenario (WP-002), add:

```json
      "analyst_baseline": {
        "fin": {
          "value_usd": 4200000, "low_usd": 1800000, "high_usd": 7500000,
          "source_ids": ["verizon-dbir", "nonexistent-orphan-fixture"],
          "notes": "Mid-case from 2025 Q4 incident response cost",
          "updated": "2026-04-09", "updated_by": "analyst"
        },
        "prob": {
          "annual_rate": 0.12, "low": 0.08, "high": 0.18,
          "evidence_type": "frequency_rate",
          "source_ids": ["dragos-ics-ot"],
          "notes": "Energy sector base rate", "updated": "2026-04-09", "updated_by": "analyst"
        }
      },
```

- [ ] **Step 2: Run the validator**

Run: `uv run python tools/register_validator.py`
Expected stdout ends with `[register_validator] Run summary: 7 scenarios, N sources matched, 1 baseline orphans`.

- [ ] **Step 3: Verify `run_summary` in output**

Run: `uv run python -c "import json; d=json.load(open('output/validation/register_validation.json')); print(json.dumps(d['run_summary'], indent=2))"`

Expected: a full `run_summary` block with `baseline_usage.scenarios_with_baseline ≥ 1`, `errors` containing a `baseline_orphan_source` entry for `nonexistent-orphan-fixture`, and non-zero `evidence` counters.

- [ ] **Step 4: Start the server and hit each endpoint**

Run:
```bash
uv run uvicorn server:app --host 127.0.0.1 --port 8001 &
sleep 2
curl -s "http://127.0.0.1:8001/api/register-validation/results" | python -m json.tool | grep -A2 run_summary | head -10
curl -s "http://127.0.0.1:8001/api/source-library/osint?tier=A" | python -m json.tool | head -20
curl -s "http://127.0.0.1:8001/api/source-library/benchmarks?register=wind_power_plant" | python -m json.tool | head -40
curl -s -X PATCH "http://127.0.0.1:8001/api/registers/wind_power_plant/scenarios/0/baseline" \
  -H "Content-Type: application/json" \
  -d '{"fin":{"value_usd":1000000,"low_usd":500000,"high_usd":2000000}}' | python -m json.tool
```

Expected: all four curls return 200 with well-formed JSON. The PATCH response includes `analyst_baseline.fin.updated` and `updated_by: analyst`.

- [ ] **Step 5: Open the UI and click through**

In browser at http://127.0.0.1:8001:
- Risk Register tab → run summary card renders with all three top sections (Verdicts / Sources / Evidence) + Gaps + Changes + Baseline line
- Click Ransomware scenario → baseline editor shows `◆` with golden baseline row in IMPACT + PROBABILITY cards; orphan chip `nonexistent-orphan-fixture` rendered with strikethrough
- Click a delta row in the run summary → matrix scrolls to that scenario
- Click a gap row → jumps to Source Library → Benchmarks → Coverage matrix
- Source Library → OSINT sub-tab loads with filters working
- Source Library → Benchmarks → Source list + Coverage matrix both render; `+ Add source` opens the modal; posted source appears in the list

- [ ] **Step 6: Kill the server, commit the fixture**

```bash
kill %1 2>/dev/null
git add data/registers/wind_power_plant.json
git commit -m "test(fixture): add baseline + orphan ref to wind power register for smoke test"
```

- [ ] **Step 7: Run the entire Python test suite**

Run: `uv run pytest tests/test_register_validator_counters.py tests/test_register_validator_run_summary.py tests/test_register_validator_baseline.py tests/test_server_baseline_patch.py tests/test_server_source_library_osint.py tests/test_server_source_library_benchmarks.py tests/test_server_validation_sources_add.py tests/test_server_register_validation_results.py -v`
Expected: all tests pass.

---

## Self-Review Notes

**Spec coverage check:**
- Section 1 (architecture) — covered by Unit 1–4
- Section 2 (tab rename + sub-tabs) — Task 10, 11
- Section 3 (OSINT sub-tab) — Task 6 (endpoint), Task 11 (UI)
- Section 4 (Benchmarks sub-tab + matrix + CRUD) — Task 7, 12, 13, 14, 8
- Section 5 (Analyst baseline two layers + editor + dimension row + PATCH) — Task 4 (validator), Task 5 (PATCH), Task 17 (editor), Task 18 (dim row + orphans)
- Section 6 (Run summary card + computation + instrumentation) — Task 1, 2, 3 (backend), Task 16 (UI)
- Section 7 (Risk Register cleanup) — Task 15
- Section 8 (data flows) — implicit in task sequencing
- Section 9 (boundary check) — enforced by design: all new logic is pure code, Sonnet prompt is only extended via deterministic substitution
- Section 10 (build sequence) — mapped to Tasks 1–19
- Section 11 (no changes) — respected
- Section 12 (known limitations) — acknowledged, no new work
- Section 13 (open questions) — none

**Types / naming consistency check:**
- `RunCounters` consistently named across Task 1, 2, 3, 4
- `build_run_summary()` consistently named
- `compute_baseline_alignment()`, `format_baseline_summary()`, `resolve_baseline_orphans()` consistently named
- `window.openAddBenchmarkSourceModal` consistent between Task 14 (defined) and Task 17 (called)
- `loadSourceLibraryOSINT` / `loadSourceLibraryBenchmarks` / `switchSourceLibrarySubtab` / `switchBenchmarkView` all consistent
- `renderRunSummary` / `loadAndRenderRunSummary` / `_toggleRunSummaryCard` consistent
- `_baselineKnownIds` set as `window._baselineKnownIds` in Task 18, consumed by `_renderBaselineSourceChips` in Task 17 — name matches

**No placeholders:** every code step contains the actual code. Every command step shows exact expected output characterisation.

**Granularity check:** each task is scoped to one file area and produces a testable or viewable artifact. TDD used for Python (Tasks 1–9). UI tasks (10–18) use manual smoke tests, which is appropriate for this codebase — there is no JS test infrastructure.
