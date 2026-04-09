"""
evidence_ceiling_assessor.py — deterministic stop hook for evidence specificity.

Reads output/validation/register_validation.json and emits:
  output/validation/evidence_ceiling.json

Warnings:
  - Any dimension where evidence_ceiling_label == "General industry evidence"
    - severity "critical" when analyst_baseline_load_bearing=True (no baseline set)
    - severity "advisory" when baseline exists but evidence is still general-only

Exit codes:
  0 — pass (no critical load-bearing warnings)
  1 — fail (at least one critical dimension: general evidence + no analyst baseline)

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
    best_tier_seen = 4  # start at worst (most general)

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

    s = result["summary"]
    print(f"[evidence_ceiling_assessor] {s['total_dimensions']} dimensions assessed", file=sys.stderr)
    print(
        f"[evidence_ceiling_assessor] Best ceiling: {s['best_ceiling_label']} (tier {s['best_ceiling_tier']})",
        file=sys.stderr,
    )
    for w in result["warnings"]:
        sev = "WARN" if w["severity"] == "advisory" else "CRITICAL"
        print(f"[evidence_ceiling_assessor] [{sev}] {w['message']}", file=sys.stderr)

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
