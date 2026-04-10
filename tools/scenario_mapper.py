#!/usr/bin/env python3
"""Scenario mapper — maps geo+cyber signals to master scenario, writes scenario_map.json.

Usage:
    scenario_mapper.py REGION [--mock]

    --mock is accepted for CLI consistency with other tools but has no effect here.
    scenario_mapper always reads signal files from disk (written by collectors).

Writes: output/regional/{region}/scenario_map.json
"""
import json
import os
import sys

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}


def load_master():
    with open("data/master_scenarios.json", encoding="utf-8") as f:
        data = json.load(f)
    return {s["incident_type"]: s for s in data["scenarios"]}


def load_signals(region):
    osint_path = f"output/regional/{region.lower()}/osint_signals.json"
    with open(osint_path, encoding="utf-8") as f:
        osint = json.load(f)
    # Split into geo and cyber for backward compat with build_signal_text
    geo = {"summary": osint.get("summary", ""), "lead_indicators": [i for i in osint.get("lead_indicators", []) if i.get("pillar") == "geo"]}
    cyber = {"summary": "", "lead_indicators": [i for i in osint.get("lead_indicators", []) if i.get("pillar") == "cyber"]}
    return geo, cyber


def _indicator_text(indicator) -> str:
    """Extract text from a lead_indicator (string or dict with 'text' key)."""
    if isinstance(indicator, dict):
        return indicator.get("text", "")
    return str(indicator)


def build_signal_text(geo, cyber):
    parts = [
        geo.get("summary", ""),
        " ".join(_indicator_text(i) for i in geo.get("lead_indicators", [])),
        cyber.get("summary", ""),
        cyber.get("threat_vector", ""),
        " ".join(cyber.get("target_assets", [])),
    ]
    return " ".join(parts).lower()


def score_scenarios(text, master):
    """Score each scenario by keyword matches in signal text."""
    scores = {}
    for name, scenario in master.items():
        score = 0
        # Use all string fields in the scenario as keyword sources
        for value in scenario.values():
            if isinstance(value, str):
                words = [w.lower() for w in value.split() if len(w) > 4]
                for word in words:
                    if word in text:
                        score += 1
        # Also check incident_type words directly
        for word in name.lower().split():
            if len(word) > 3 and word in text:
                score += 2
        scores[name] = score
    return scores


def pick_scenario(scores, master):
    """Return (top_scenario_name, confidence, financial_rank, rationale)."""
    top = max(scores, key=scores.get)
    top_score = scores[top]

    if top_score == 0:
        # No keyword match — fall back to System intrusion (conservative baseline)
        top = "System intrusion"
        confidence = "low"
        rationale = (
            f"No strong signal match found; defaulting to '{top}' "
            f"(highest financial impact scenario) as a conservative baseline."
        )
    else:
        if top_score >= 3:
            confidence = "high"
        elif top_score >= 1:
            confidence = "medium"
        else:
            confidence = "low"
        rationale = (
            f"Signal text matched {top_score} indicator(s) for '{top}', "
            f"which ranks #{master[top]['financial_rank']} by financial impact globally."
        )

    financial_rank = master[top]["financial_rank"]
    return top, confidence, financial_rank, rationale


def map_scenario(region):
    master = load_master()
    geo, cyber = load_signals(region)
    text = build_signal_text(geo, cyber)
    scores = score_scenarios(text, master)
    top, confidence, financial_rank, rationale = pick_scenario(scores, master)
    return {
        "top_scenario": top,
        "confidence": confidence,
        "financial_rank": financial_rank,
        "rationale": rationale,
    }


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: scenario_mapper.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    # --mock is accepted for CLI consistency with other tools but has no effect here.
    # scenario_mapper always reads signal files from disk (written by collectors).

    if region not in VALID_REGIONS:
        print(f"[scenario_mapper] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    result = map_scenario(region)

    out_path = f"output/regional/{region.lower()}/scenario_map.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[scenario_mapper] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
