"""
register_validator.py — VaCR source validation pipeline.

For each scenario in the active register:
  1. Queries sources.db for existing sources with quantitative data matching search_tags
  2. Uses web research to find new quantitative sources (monetary or probability figures)
  3. Writes output/validation/register_validation.json

Usage:
    uv run python tools/register_validator.py
"""

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "sources.db"
REGISTERS_DIR = REPO_ROOT / "data" / "registers"
ACTIVE_REGISTER_PATH = REPO_ROOT / "data" / "active_register.json"
OUTPUT_PATH = REPO_ROOT / "output" / "validation" / "register_validation.json"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_active_register() -> dict:
    active = json.loads(ACTIVE_REGISTER_PATH.read_text(encoding="utf-8"))
    register_id = active.get("register_id", "aerogrid_enterprise")
    path = REGISTERS_DIR / f"{register_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def query_existing_sources(conn: sqlite3.Connection, search_tags: list[str]) -> list[dict]:
    """Find sources in sources_registry with quantitative data overlapping search_tags."""
    rows = conn.execute(
        "SELECT name, url, source_tags, quantitative_figure, credibility_tier "
        "FROM sources_registry WHERE has_quantitative_data = 1"
    ).fetchall()
    results = []
    for name, url, tags_json, figure, tier in rows:
        try:
            source_tags = json.loads(tags_json or "[]")
        except Exception:
            source_tags = []
        overlap = set(source_tags) & set(search_tags)
        if overlap:
            results.append({"name": name, "url": url or "", "quantitative_figure": figure or "",
                            "credibility_tier": tier, "is_new": False})
    return results


def discover_new_sources(client: anthropic.Anthropic, scenario: dict) -> list[dict]:
    """Ask Claude to identify quantitative sources for a scenario. Returns source list."""
    tags = ", ".join(scenario.get("search_tags", []))
    prompt = (
        f"You are a cyber risk intelligence analyst searching for QUANTITATIVE sources "
        f"(sources with actual dollar figures or probability percentages) for this scenario:\n\n"
        f"Scenario: {scenario['scenario_name']}\n"
        f"Description: {scenario.get('description', '')}\n"
        f"Tags: {tags}\n\n"
        f"List up to 5 real published reports or studies that contain ACTUAL financial impact figures "
        f"(USD) or incident probability percentages for this scenario type. "
        f"Only include sources where you are confident the financial or probability data exists.\n\n"
        f"Return ONLY a JSON array. Each item: "
        f"{{\"name\": str, \"url\": str, \"figure_financial\": str|null, \"figure_probability\": str|null, "
        f"\"figure_type\": str, \"sector\": str, \"improvement_note\": str}}\n\n"
        f"improvement_note = why this source adds value beyond generic benchmarks.\n"
        f"JSON array only — no markdown, no explanation."
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    sources = json.loads(text.strip())
    for s in sources:
        s["is_new"] = True
    return sources


def _parse_usd(figure_str: str | None) -> float | None:
    """Extract a USD float from a string like '$14.5M' or '$14,500,000'."""
    if not figure_str:
        return None
    s = figure_str.replace(",", "").upper()
    m = re.search(r"\$?([\d.]+)\s*([MB]?)", s)
    if not m:
        return None
    val = float(m.group(1))
    suffix = m.group(2)
    if suffix == "M":
        val *= 1_000_000
    elif suffix == "B":
        val *= 1_000_000_000
    return val


def _parse_pct(figure_str: str | None) -> float | None:
    if not figure_str:
        return None
    m = re.search(r"([\d.]+)\s*%", figure_str)
    return float(m.group(1)) if m else None


def compute_verdict(vacr_value: float | None, benchmark_values: list[float]) -> tuple[str, list[float]]:
    """Returns (verdict, [min, max]) where verdict is supports|challenges|insufficient."""
    if not benchmark_values or len(benchmark_values) < 2:
        return "insufficient", []
    lo, hi = min(benchmark_values), max(benchmark_values)
    if vacr_value is None:
        return "insufficient", [lo, hi]
    # Challenges if vacr is outside the range by more than 25%
    midpoint = (lo + hi) / 2
    diff_pct = abs(vacr_value - midpoint) / midpoint if midpoint else 0
    if lo <= vacr_value <= hi or diff_pct <= 0.25:
        return "supports", [lo, hi]
    return "challenges", [lo, hi]


def validate_scenario(
    conn: sqlite3.Connection,
    client: anthropic.Anthropic,
    scenario: dict,
) -> dict:
    search_tags = scenario.get("search_tags", [])
    existing = query_existing_sources(conn, search_tags)
    new_sources = discover_new_sources(client, scenario)

    # Financial dimension
    vacr_usd = scenario.get("value_at_cyber_risk_usd")
    fin_values = []
    fin_existing = []
    for s in existing:
        val = _parse_usd(s.get("quantitative_figure"))
        if val:
            fin_values.append(val)
            fin_existing.append({**s, "figure_usd": val})
    fin_new = []
    for s in new_sources:
        val = _parse_usd(s.get("figure_financial"))
        if val:
            fin_values.append(val)
            fin_new.append({**s, "figure_usd": val})
    fin_verdict, fin_range = compute_verdict(vacr_usd, fin_values)
    fin_rec = _build_recommendation("financial", fin_verdict, vacr_usd, fin_range, fin_new)

    # Probability dimension
    vacr_pct = scenario.get("probability_pct")
    prob_values = []
    prob_existing = []
    for s in existing:
        val = _parse_pct(s.get("quantitative_figure"))
        if val:
            prob_values.append(val)
            prob_existing.append({**s, "figure_pct": val})
    prob_new = []
    for s in new_sources:
        val = _parse_pct(s.get("figure_probability"))
        if val:
            prob_values.append(val)
            prob_new.append({**s, "figure_pct": val})
    prob_verdict, prob_range = compute_verdict(vacr_pct, prob_values)
    prob_rec = _build_recommendation("probability", prob_verdict, vacr_pct, prob_range, prob_new)

    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "financial": {
            "vacr_figure_usd": vacr_usd,
            "verdict": fin_verdict,
            "benchmark_range_usd": fin_range,
            "existing_sources": fin_existing,
            "new_sources": fin_new,
            "recommendation": fin_rec,
        },
        "probability": {
            "vacr_probability_pct": vacr_pct,
            "verdict": prob_verdict,
            "benchmark_range_pct": prob_range,
            "existing_sources": prob_existing,
            "new_sources": prob_new,
            "recommendation": prob_rec,
        },
    }


def _build_recommendation(
    dimension: str, verdict: str, vacr: float | None, benchmark: list[float], new_sources: list
) -> str:
    if verdict == "insufficient":
        return f"Insufficient quantitative sources found. Manual research recommended."
    lo, hi = benchmark[0], benchmark[1]
    fmt = (lambda v: f"${v:,.0f}") if dimension == "financial" else (lambda v: f"{v:.1f}%")
    base = f"Benchmark range: {fmt(lo)} – {fmt(hi)}."
    if verdict == "supports":
        return f"{base} Figure {fmt(vacr)} is within benchmark range. No revision indicated."
    direction = "below" if (vacr or 0) < lo else "above"
    note = ""
    if new_sources:
        note = f" New source '{new_sources[0].get('name', '')}' provides {dimension} data."
    return f"{base} Figure {fmt(vacr)} is {direction} benchmark range. Consider revising.{note}"


def main():
    register = load_active_register()
    conn = sqlite3.connect(str(DB_PATH))
    client = anthropic.Anthropic()

    print(f"[register_validator] Active register: {register['register_id']}")
    print(f"[register_validator] Scenarios: {len(register['scenarios'])}")

    scenario_results = []
    for scenario in register["scenarios"]:
        print(f"[register_validator] Validating: {scenario['scenario_id']} — {scenario['scenario_name']}")
        result = validate_scenario(conn, client, scenario)
        scenario_results.append(result)
        fin_v = result["financial"]["verdict"]
        prob_v = result["probability"]["verdict"]
        print(f"  → financial: {fin_v}  probability: {prob_v}")

    output = {
        "register_id": register["register_id"],
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenario_results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Update last_validated_at on the register file
    register["last_validated_at"] = output["validated_at"]
    reg_path = REGISTERS_DIR / f"{register['register_id']}.json"
    reg_path.write_text(json.dumps(register, indent=2), encoding="utf-8")

    print(f"[register_validator] Done → {OUTPUT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
