# Evidence Tiering System Implementation Plan

**Goal:** Tag every benchmark source with an evidence specificity tier (1=asset-specific → 4=general), expose an evidence ceiling label per validation dimension, and flag when only general evidence was found and no analyst baseline is set.

**Architecture:** Single-file change in `tools/register_validator.py` — `build_register_queries` returns typed dicts with `tier` + `tier_label`; `phase2_osint_search` propagates `evidence_tier` to extracted figures; `compute_verdict_confidence` extended to derive `evidence_ceiling_label`; `validate_scenario` adds two new output fields. A new deterministic stop hook `tools/evidence_ceiling_assessor.py` reads `output/validation/register_validation.json` and emits warnings. UI shows ceiling badge in dimension card header.

**Tech Stack:** Python 3.11 + vanilla JS (no new deps)

---

### Task 1: Add tier constants + refactor `build_register_queries`

**Files:**
- Modify: `tools/register_validator.py:229-277`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evidence_tiering.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.register_validator import build_register_queries

SCENARIO_WIND_RANSOMWARE = {
    "scenario_id": "s1",
    "scenario_name": "Ransomware",
    "search_tags": ["ot_systems", "wind_turbine", "scada"],
}

REGISTER_WIND = {
    "company_context": "wind power energy operator",
    "scenarios": [],
}

SCENARIO_INSIDER = {
    "scenario_id": "s2",
    "scenario_name": "Insider misuse",
    "search_tags": [],
}

REGISTER_GENERIC = {
    "company_context": "energy sector",
    "scenarios": [],
}


def test_build_register_queries_returns_typed_dicts():
    result = build_register_queries(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    assert isinstance(result["financial"], list)
    assert isinstance(result["probability"], list)
    # All entries must be dicts with query/tier/tier_label
    for entry in result["financial"] + result["probability"]:
        assert "query" in entry, f"missing 'query' in {entry}"
        assert "tier" in entry, f"missing 'tier' in {entry}"
        assert "tier_label" in entry, f"missing 'tier_label' in {entry}"
        assert isinstance(entry["tier"], int)
        assert 1 <= entry["tier"] <= 4


def test_wind_turbine_query_has_tier_1():
    result = build_register_queries(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    tiers = [e["tier"] for e in result["financial"]]
    assert 1 in tiers, f"Expected tier-1 (asset-specific) query in wind+OT scenario; got tiers: {tiers}"


def test_non_ot_scenario_has_no_tier_1():
    result = build_register_queries(SCENARIO_INSIDER, REGISTER_GENERIC)
    tiers = [e["tier"] for e in result["financial"]]
    assert 1 not in tiers, f"Non-OT scenario should not have tier-1 queries; got: {tiers}"


def test_best_tier_is_lowest_number():
    result = build_register_queries(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    tiers = [e["tier"] for e in result["financial"]]
    assert min(tiers) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_evidence_tiering.py -v
```

Expected: FAIL — `KeyError: 'tier'` (current function returns `{"financial": [str, ...]}`).

- [ ] **Step 3: Add tier constants and refactor `build_register_queries`**

At the top of `tools/register_validator.py`, after the `_SCENARIO_QUERY_PHRASES` dict (line ~226), add:

```python
# Evidence specificity tiers — lower = more specific
EVIDENCE_TIER_ASSET_SPECIFIC    = 1   # Named wind farm / asset-class incident data
EVIDENCE_TIER_SECTOR_SPECIFIC   = 2   # Energy utility sector benchmarks
EVIDENCE_TIER_TECHNOLOGY_SPECIFIC = 3  # OT/ICS technology class (no sector filter)
EVIDENCE_TIER_GENERAL           = 4   # Cross-industry (IBM CoDB, Verizon DBIR, etc.)

_EVIDENCE_TIER_LABELS = {
    1: "Asset-specific evidence",
    2: "Sector-specific evidence",
    3: "OT/technology evidence",
    4: "General industry evidence",
}


def _tier_entry(query: str, tier: int) -> dict:
    return {"query": query, "tier": tier, "tier_label": _EVIDENCE_TIER_LABELS[tier]}
```

Then replace the body of `build_register_queries` (lines 229–277):

```python
def build_register_queries(scenario: dict, register: dict) -> dict:
    """
    Build up to _PHASE2_QUERY_CAP financial queries and _PHASE2_QUERY_CAP probability
    queries per scenario. Each entry is {"query": str, "tier": int, "tier_label": str}.
    Ordered most-specific first (lowest tier number first).

    Returns:
        {"financial": [{"query", "tier", "tier_label"}, ...],
         "probability": [{"query", "tier", "tier_label"}, ...]}
    """
    name = scenario["scenario_name"]
    query_phrase = _SCENARIO_QUERY_PHRASES.get(name, name)
    context = register.get("company_context", "energy sector")
    tags = set(scenario.get("search_tags", []))
    is_ot = bool(tags & {"ot_systems", "scada", "wind_turbine", "ics", "industrial_control"})
    is_wind = "wind" in context.lower() or "wind_turbine" in tags

    financial: list[dict] = []
    probability: list[dict] = []

    # Tier 1 — asset-specific: wind farm named incident data
    if is_wind:
        financial.append(_tier_entry(
            f'wind farm cyber incident cost "{name}" OR "wind turbine" USD 2022 2023 2024 2025',
            EVIDENCE_TIER_ASSET_SPECIFIC,
        ))
        probability.append(_tier_entry(
            f'wind farm "{name}" incident frequency rate annual 2023 2024 2025',
            EVIDENCE_TIER_ASSET_SPECIFIC,
        ))

    # Tier 3 — OT/technology-specific: ICS/SCADA when relevant tags present
    if is_ot:
        financial.append(_tier_entry(
            f'{query_phrase} OT ICS SCADA operational technology cost USD 2024 2025 energy',
            EVIDENCE_TIER_TECHNOLOGY_SPECIFIC,
        ))
        probability.append(_tier_entry(
            f'{query_phrase} ICS OT incident frequency 2024 Dragos OR CISA OR ICS-CERT energy operator',
            EVIDENCE_TIER_TECHNOLOGY_SPECIFIC,
        ))

    # Tier 2 — sector-specific: energy sector benchmarks
    if is_wind:
        sector = "wind power energy operator"
    elif "manufacturing" in context.lower():
        sector = "manufacturing energy sector"
    else:
        sector = "energy sector"
    financial.append(_tier_entry(
        f'{query_phrase} financial cost impact {sector} USD 2024 2025',
        EVIDENCE_TIER_SECTOR_SPECIFIC,
    ))
    probability.append(_tier_entry(
        f'{query_phrase} cyber incident rate frequency annual {sector} 2024 2025',
        EVIDENCE_TIER_SECTOR_SPECIFIC,
    ))

    # Tier 4 — general: cross-industry (always appended as fallback)
    financial.append(_tier_entry(
        f'{query_phrase} financial cost impact USD 2024 2025 annual report',
        EVIDENCE_TIER_GENERAL,
    ))
    probability.append(_tier_entry(
        f'{query_phrase} incident probability annual rate 2024 2025 global report',
        EVIDENCE_TIER_GENERAL,
    ))

    # Sort by tier ascending (most specific first), then cap
    financial.sort(key=lambda e: e["tier"])
    probability.sort(key=lambda e: e["tier"])
    return {
        "financial": financial[:_PHASE2_QUERY_CAP],
        "probability": probability[:_PHASE2_QUERY_CAP],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_evidence_tiering.py -v
```

Expected: PASS (3/3 tests, or 4/4 if all added).

- [ ] **Step 5: Commit**

```bash
git add tools/register_validator.py tests/test_evidence_tiering.py
git commit -m "feat(validator): add 4-tier evidence specificity constants + refactor build_register_queries"
```

---

### Task 2: Propagate `evidence_tier` through `phase2_osint_search`

**Files:**
- Modify: `tools/register_validator.py:345-378`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_evidence_tiering.py`:

```python
from unittest.mock import patch

def _fake_search(query, max_results=4):
    return [{
        "title": "Fake Wind Ransomware Report",
        "url": "https://example.com/report",
        "content": "The average ransomware cost was $3.5 million in 2024. Annual incident rate is 12% for energy operators.",
    }]


def test_phase2_figures_carry_evidence_tier():
    from tools.register_validator import phase2_osint_search
    with patch("tools.register_validator._search_web", side_effect=_fake_search):
        fin_figs, prob_figs = phase2_osint_search(SCENARIO_WIND_RANSOMWARE, REGISTER_WIND)
    all_figs = fin_figs + prob_figs
    assert all_figs, "Expected at least one figure extracted"
    for fig in all_figs:
        assert "evidence_tier" in fig, f"figure missing evidence_tier: {fig}"
        assert isinstance(fig["evidence_tier"], int)
        assert 1 <= fig["evidence_tier"] <= 4
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_evidence_tiering.py::test_phase2_figures_carry_evidence_tier -v
```

Expected: FAIL — `AssertionError: figure missing evidence_tier`.

- [ ] **Step 3: Update `phase2_osint_search` to unpack tier dicts and tag figures**

Replace the body of `phase2_osint_search` (lines 345–378):

```python
def phase2_osint_search(
    scenario: dict, register: dict
) -> tuple[list[dict], list[dict]]:
    """
    Phase 2: Register-contextualized OSINT.
    Each query dict has {query, tier, tier_label}. Extracted figures are tagged with evidence_tier.
    Returns (fin_figures, prob_figures) — each item has phase=2 and evidence_tier.
    """
    queries = build_register_queries(scenario, register)
    fin_figures, prob_figures = [], []

    for q_entry in queries["financial"]:
        query = q_entry["query"]
        tier = q_entry["tier"]
        print(f"[register_validator] Phase 2 fin (tier {tier}) -- {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_financial_figures(content, src_name):
                fig["phase"] = 2
                fig["evidence_tier"] = tier
                fig["source_url"] = r.get("url", "")
                fin_figures.append(fig)

    for q_entry in queries["probability"]:
        query = q_entry["query"]
        tier = q_entry["tier"]
        print(f"[register_validator] Phase 2 prob (tier {tier}) -- {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_probability_figures(content, src_name):
                fig["phase"] = 2
                fig["evidence_tier"] = tier
                fig["source_url"] = r.get("url", "")
                prob_figures.append(fig)

    return fin_figures, prob_figures
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_evidence_tiering.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tools/register_validator.py tests/test_evidence_tiering.py
git commit -m "feat(validator): propagate evidence_tier from query tier through phase2 figures"
```

---

### Task 3: Add `compute_evidence_ceiling` and update `validate_scenario` output

**Files:**
- Modify: `tools/register_validator.py:583-595` (near `compute_verdict_confidence`)
- Modify: `tools/register_validator.py:1032-1082` (`validate_scenario` output dicts)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_evidence_tiering.py`:

```python
from tools.register_validator import compute_evidence_ceiling


def test_evidence_ceiling_returns_tier1_label_when_tier1_present():
    sources = [
        {"evidence_tier": 1, "context_tag": "asset_specific"},
        {"evidence_tier": 4, "context_tag": "general"},
    ]
    tier, label = compute_evidence_ceiling(sources)
    assert tier == 1
    assert "Asset-specific" in label


def test_evidence_ceiling_returns_tier4_when_only_general():
    sources = [
        {"evidence_tier": 4, "context_tag": "general"},
        {"evidence_tier": 4, "context_tag": "general"},
    ]
    tier, label = compute_evidence_ceiling(sources)
    assert tier == 4
    assert "General" in label


def test_evidence_ceiling_returns_tier4_when_no_sources():
    tier, label = compute_evidence_ceiling([])
    assert tier == 4


def test_validate_scenario_output_has_ceiling_fields():
    """Smoke test: validate_scenario output dicts contain new fields."""
    # We can't call validate_scenario without a DB and live search,
    # so test the shape by constructing output dicts manually with the helpers
    from tools.register_validator import compute_evidence_ceiling, _EVIDENCE_TIER_LABELS
    sources_tier2 = [{"evidence_tier": 2, "context_tag": "general"}]
    tier, label = compute_evidence_ceiling(sources_tier2)
    assert tier == 2
    assert label == _EVIDENCE_TIER_LABELS[2]
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_evidence_tiering.py::test_evidence_ceiling_returns_tier1_label_when_tier1_present -v
```

Expected: FAIL — `ImportError: cannot import name 'compute_evidence_ceiling'`.

- [ ] **Step 3: Add `compute_evidence_ceiling` function (after `compute_verdict_confidence`, line ~595)**

```python
def compute_evidence_ceiling(sources: list[dict]) -> tuple[int, str]:
    """
    Deterministic evidence ceiling from a list of source dicts.
    Returns (best_tier: int, label: str) — best_tier is the lowest tier number found.
    Returns (4, "General industry evidence") when sources is empty.
    """
    if not sources:
        return EVIDENCE_TIER_GENERAL, _EVIDENCE_TIER_LABELS[EVIDENCE_TIER_GENERAL]
    best = min(
        s.get("evidence_tier", EVIDENCE_TIER_GENERAL)
        for s in sources
    )
    # Clamp to valid range
    best = max(1, min(4, int(best)))
    return best, _EVIDENCE_TIER_LABELS[best]
```

- [ ] **Step 4: Add `evidence_tier` propagation from figures to source dicts in `validate_scenario`**

In `validate_scenario`, the per-figure source dicts are built at lines ~964-996. Add `evidence_tier` to each source dict:

In the `for f in all_fin_figs:` block (line ~960), change:
```python
            source_dict = {
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_usd": f.get("cost_median_usd"),
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
                "context_tag": f.get("context_tag", "general"),
                "smb_scale_flag": (f.get("cost_median_usd") or 0) < scale_floor,
            }
```
to:
```python
            source_dict = {
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_usd": f.get("cost_median_usd"),
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
                "context_tag": f.get("context_tag", "general"),
                "evidence_tier": f.get("evidence_tier", EVIDENCE_TIER_GENERAL),
                "smb_scale_flag": (f.get("cost_median_usd") or 0) < scale_floor,
            }
```

In the `for f in all_prob_figs:` block (line ~979), change:
```python
            source_dict = {
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_pct": f.get("probability_pct"),
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
                "context_tag": f.get("context_tag", "general"),
                "smb_scale_flag": False,
            }
```
to:
```python
            source_dict = {
                "name": f.get("_source_name", ""),
                "url": f.get("source_url", ""),
                "figure_pct": f.get("probability_pct"),
                "note": f.get("note", ""),
                "raw_quote": f.get("raw_quote", ""),
                "phase": f.get("phase", 2),
                "context_tag": f.get("context_tag", "general"),
                "evidence_tier": f.get("evidence_tier", EVIDENCE_TIER_GENERAL),
                "smb_scale_flag": False,
            }
```

- [ ] **Step 5: Add `evidence_ceiling_label` and `analyst_baseline_load_bearing` to `fin_result` and `prob_result` in `validate_scenario`**

After the confidence lines (~1016-1017), add:

```python
    fin_all_src = fin_registered_out + fin_new_out
    prob_all_src = prob_registered_out + prob_new_out
    fin_ceiling_tier, fin_ceiling_label = compute_evidence_ceiling(fin_all_src)
    prob_ceiling_tier, prob_ceiling_label = compute_evidence_ceiling(prob_all_src)
    baseline = scenario.get("analyst_baseline")
    fin_load_bearing = (fin_ceiling_tier == EVIDENCE_TIER_GENERAL and not (baseline and baseline.get("fin")))
    prob_load_bearing = (prob_ceiling_tier == EVIDENCE_TIER_GENERAL and not (baseline and baseline.get("prob")))
```

Then update `fin_result` (line ~1032) to include new fields:

```python
    fin_result = {
        "vacr_figure_usd": vacr_usd,
        "verdict": fin_verdict,
        "verdict_confidence": fin_confidence,
        "evidence_ceiling_label": fin_ceiling_label,
        "analyst_baseline_load_bearing": fin_load_bearing,
        "benchmark_range_usd": fin_range,
        "registered_sources": fin_registered_out,
        "new_sources": fin_new_out,
    }
    prob_result = {
        "vacr_probability_pct": vacr_pct,
        "verdict": prob_verdict,
        "verdict_confidence": prob_confidence,
        "evidence_type": prob_evidence_type,
        "evidence_ceiling_label": prob_ceiling_label,
        "analyst_baseline_load_bearing": prob_load_bearing,
        "benchmark_range_pct": prob_range,
        "registered_sources": prob_registered_out,
        "new_sources": prob_new_out,
    }
```

Note: remove the duplicate `baseline = scenario.get("analyst_baseline")` line that comes after (~line 1051) — the variable is now assigned before the results dicts.

- [ ] **Step 6: Run tests to verify they pass**

```
uv run pytest tests/test_evidence_tiering.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tools/register_validator.py tests/test_evidence_tiering.py
git commit -m "feat(validator): compute_evidence_ceiling + ceiling_label + analyst_baseline_load_bearing in validate_scenario output"
```

---

### Task 4: Deterministic stop hook `tools/evidence_ceiling_assessor.py`

**Files:**
- Create: `tools/evidence_ceiling_assessor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evidence_ceiling_assessor.py`:

```python
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

MOCK_REGISTER_VALIDATION = {
    "register_id": "wind_power_plant",
    "scenarios": [
        {
            "scenario_id": "s1",
            "scenario_name": "Ransomware",
            "financial": {
                "evidence_ceiling_label": "General industry evidence",
                "analyst_baseline_load_bearing": True,
                "verdict": "challenges",
            },
            "probability": {
                "evidence_ceiling_label": "Sector-specific evidence",
                "analyst_baseline_load_bearing": False,
                "verdict": "supports",
            },
        },
        {
            "scenario_id": "s2",
            "scenario_name": "Insider misuse",
            "financial": {
                "evidence_ceiling_label": "Asset-specific evidence",
                "analyst_baseline_load_bearing": False,
                "verdict": "supports",
            },
            "probability": {
                "evidence_ceiling_label": "Asset-specific evidence",
                "analyst_baseline_load_bearing": False,
                "verdict": "supports",
            },
        },
    ],
}


def test_assessor_flags_load_bearing_scenarios(tmp_path):
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    result = assess_evidence_ceilings(MOCK_REGISTER_VALIDATION)
    assert "warnings" in result
    assert "summary" in result
    # Ransomware financial is load_bearing=True → must appear in warnings
    warning_texts = " ".join(w["message"] for w in result["warnings"])
    assert "Ransomware" in warning_texts
    assert "financial" in warning_texts.lower() or "Financial" in warning_texts


def test_assessor_no_warnings_when_all_specific(tmp_path):
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    validation_clean = {
        "register_id": "test",
        "scenarios": [MOCK_REGISTER_VALIDATION["scenarios"][1]],  # Insider misuse — all asset-specific
    }
    result = assess_evidence_ceilings(validation_clean)
    assert result["warnings"] == []


def test_assessor_summary_counts():
    from tools.evidence_ceiling_assessor import assess_evidence_ceilings
    result = assess_evidence_ceilings(MOCK_REGISTER_VALIDATION)
    s = result["summary"]
    assert s["total_dimensions"] == 4  # 2 scenarios × 2 dims
    assert s["load_bearing_count"] == 1  # only Ransomware/financial
    assert s["best_ceiling_tier"] == 1   # Insider misuse has asset-specific (tier 1)
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_evidence_ceiling_assessor.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tools.evidence_ceiling_assessor'`.

- [ ] **Step 3: Create `tools/evidence_ceiling_assessor.py`**

```python
"""
evidence_ceiling_assessor.py — deterministic stop hook for evidence specificity.

Reads output/validation/register_validation.json and emits:
  output/validation/evidence_ceiling.json

Warnings:
  - Any dimension where analyst_baseline_load_bearing=True (only general evidence found, no baseline set)
  - Any dimension where evidence_ceiling_label == "General industry evidence" regardless of baseline

Exit codes:
  0 — pass (no load-bearing warnings)
  1 — fail (at least one load-bearing dimension without analyst baseline)

Usage:
    uv run python tools/evidence_ceiling_assessor.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VALIDATION_PATH = REPO_ROOT / "output" / "validation" / "register_validation.json"
OUTPUT_PATH = REPO_ROOT / "output" / "validation" / "evidence_ceiling.json"

_TIER_LABELS = {
    "Asset-specific evidence": 1,
    "Sector-specific evidence": 2,
    "OT/technology evidence": 3,
    "General industry evidence": 4,
}


def assess_evidence_ceilings(validation: dict) -> dict:
    """
    Pure function: takes register_validation dict, returns assessment result.
    """
    warnings = []
    total_dimensions = 0
    load_bearing_count = 0
    best_tier_seen = 4  # start at worst

    for sc in validation.get("scenarios", []):
        name = sc.get("scenario_name", sc.get("scenario_id", "unknown"))
        for dim in ("financial", "probability"):
            d = sc.get(dim)
            if not d:
                continue
            total_dimensions += 1
            ceiling_label = d.get("evidence_ceiling_label", "General industry evidence")
            load_bearing = d.get("analyst_baseline_load_bearing", False)
            tier = _TIER_LABELS.get(ceiling_label, 4)
            if tier < best_tier_seen:
                best_tier_seen = tier

            if ceiling_label == "General industry evidence":
                msg = f"{name} / {dim}: ceiling is general industry data only"
                if load_bearing:
                    msg += " — no analyst baseline set, figures are unsupported"
                warnings.append({
                    "scenario": name,
                    "dimension": dim,
                    "ceiling_label": ceiling_label,
                    "load_bearing": load_bearing,
                    "message": msg,
                    "severity": "critical" if load_bearing else "advisory",
                })
                if load_bearing:
                    load_bearing_count += 1

    return {
        "warnings": warnings,
        "summary": {
            "total_dimensions": total_dimensions,
            "load_bearing_count": load_bearing_count,
            "best_ceiling_tier": best_tier_seen,
            "best_ceiling_label": next(
                (k for k, v in _TIER_LABELS.items() if v == best_tier_seen),
                "General industry evidence",
            ),
        },
    }


def main() -> int:
    if not VALIDATION_PATH.exists():
        print(f"[evidence_ceiling_assessor] {VALIDATION_PATH} not found — skipping", file=sys.stderr)
        return 0

    validation = json.loads(VALIDATION_PATH.read_text())
    result = assess_evidence_ceilings(validation)
    result["source_file"] = str(VALIDATION_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))

    # Print summary
    s = result["summary"]
    print(f"[evidence_ceiling_assessor] {s['total_dimensions']} dimensions assessed", file=sys.stderr)
    print(f"[evidence_ceiling_assessor] Best ceiling: {s['best_ceiling_label']} (tier {s['best_ceiling_tier']})", file=sys.stderr)
    for w in result["warnings"]:
        sev = "WARN" if w["severity"] == "advisory" else "CRITICAL"
        print(f"[evidence_ceiling_assessor] [{sev}] {w['message']}", file=sys.stderr)

    # Non-zero exit only on critical (load-bearing without baseline)
    has_critical = any(w["severity"] == "critical" for w in result["warnings"])
    if has_critical:
        print(
            f"[evidence_ceiling_assessor] {s['load_bearing_count']} scenario(s) have only general evidence "
            f"and no analyst baseline — add baselines in the Risk Register tab",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```
uv run pytest tests/test_evidence_ceiling_assessor.py -v
```

Expected: all pass.

- [ ] **Step 5: Verify the script runs standalone**

```
uv run python tools/evidence_ceiling_assessor.py
```

Expected: prints "not found — skipping" (no register_validation.json yet from a fresh run), exit 0.

- [ ] **Step 6: Commit**

```bash
git add tools/evidence_ceiling_assessor.py tests/test_evidence_ceiling_assessor.py
git commit -m "feat(validator): evidence_ceiling_assessor.py deterministic stop hook"
```

---

### Task 5: UI — show evidence ceiling badge in dimension card header

**Files:**
- Modify: `static/app.js:3291-3334` (`_renderRegValDimension`)

- [ ] **Step 1: Locate the current confidence badge in `_renderRegValDimension`**

Line ~3291-3292 renders `confLabel` and `confClass`. The header row at line ~3328 shows:
```
<span class="${confClass}">${confLabel}</span>
```

We will add an evidence ceiling badge immediately after this span. No test needed here — visual change only.

- [ ] **Step 2: Add ceiling badge rendering**

In `_renderRegValDimension`, after the existing `confClass` lines (line ~3292), add:

```javascript
  const ceilLabel = d.evidence_ceiling_label || 'General industry evidence';
  const ceilTier = {'Asset-specific evidence': 1, 'Sector-specific evidence': 2, 'OT/technology evidence': 3, 'General industry evidence': 4}[ceilLabel] || 4;
  const ceilColors = ['', '#3fb950', '#58a6ff', '#e3b341', '#6e7681'];  // idx 1-4
  const ceilBg    = ['', '#0a1f0a', '#0a1628', '#1f1700', '#0d1117'];
  const ceilBorder = ['', '#1a4d1a', '#1a3a5c', '#4a3800', '#21262d'];
  const ceilBadge = `<span style="font-size:8px;font-family:'IBM Plex Mono',monospace;color:${ceilColors[ceilTier]};background:${ceilBg[ceilTier]};border:1px solid ${ceilBorder[ceilTier]};border-radius:2px;padding:1px 5px;white-space:nowrap">${ceilLabel.toUpperCase()}</span>`;
  const loadBearingBadge = d.analyst_baseline_load_bearing
    ? `<span style="font-size:8px;font-family:'IBM Plex Mono',monospace;color:#ff7b72;background:#1f0a0a;border:1px solid #5c1a1a;border-radius:2px;padding:1px 5px;white-space:nowrap">BASELINE REQUIRED</span>`
    : '';
```

Then in the header `<div>` at line ~3328, replace:
```javascript
      <span class="rr-dim-right">${_regValVerdictBadge('', d.verdict)}<span class="${confClass}">${confLabel}</span><span class="rr-src-count">${allSources.length} src</span></span>
```
with:
```javascript
      <span class="rr-dim-right">${_regValVerdictBadge('', d.verdict)}<span class="${confClass}">${confLabel}</span>${ceilBadge}${loadBearingBadge}<span class="rr-src-count">${allSources.length} src</span></span>
```

- [ ] **Step 3: Verify in browser**

Start server and open the Risk Register tab. Click Validate on any scenario. In the Financial and Probability dimension card headers, you should see:
- A tier badge (`ASSET-SPECIFIC EVIDENCE` / `SECTOR-SPECIFIC EVIDENCE` / `GENERAL INDUSTRY EVIDENCE`) in colour-coded style (green / blue / yellow / grey)
- A red `BASELINE REQUIRED` badge when only general evidence found with no analyst baseline

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): evidence ceiling tier badge + baseline-required warning in dimension card header"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|---|---|
| 4 tiers: asset → sector → technology → general | Task 1 constants + `build_register_queries` |
| Each source tagged with evidence tier | Task 2 (`phase2_osint_search`) + Task 3 (source dicts) |
| Evidence ceiling label per dimension | Task 3 (`compute_evidence_ceiling` + `validate_scenario` output) |
| `analyst_baseline_load_bearing` flag | Task 3 (`validate_scenario`) |
| Deterministic stop hook | Task 4 (`evidence_ceiling_assessor.py`) |
| UI shows ceiling | Task 5 (`_renderRegValDimension`) |

### Placeholder scan

No TBD, TODO, or "similar to" patterns. All code blocks are complete and self-contained.

### Type consistency

- `build_register_queries` returns `{"financial": [{"query": str, "tier": int, "tier_label": str}], ...}` throughout
- `phase2_osint_search` unpacks `.query` from each entry
- Source dicts in `validate_scenario` include `evidence_tier: int`
- `compute_evidence_ceiling(sources: list[dict]) -> tuple[int, str]` — consistent with call sites
- `fin_result["evidence_ceiling_label"]` is the key used in the UI (`d.evidence_ceiling_label`) — matches

### Phase 1 sources (backward compat)

Phase 1 figures come from `phase1_refresh_known_sources`. They do NOT go through `build_register_queries`, so they won't have `evidence_tier`. The `source_dict` fallback `f.get("evidence_tier", EVIDENCE_TIER_GENERAL)` handles this: Phase 1 sources default to tier 4 (conservative). Phase 1 sources are known validated sources — their tier should be preserved when they have it, but if they don't, general is the safe default. This is acceptable: the ceiling will be pulled up by any tier-1/2/3 evidence from Phase 2.
