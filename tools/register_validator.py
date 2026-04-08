"""
register_validator.py — VaCR source validation pipeline.

For each scenario in the active register:
  Phase 1: Searches known validated sources in sources.db via Tavily site-search
  Phase 2: Runs register-contextualized OSINT for new benchmark reports
  Applies IQR outlier filter, then Sonnet produces per-scenario analyst recommendations.

Usage:
    uv run python tools/register_validator.py
"""

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import anthropic
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "sources.db"
REGISTERS_DIR = REPO_ROOT / "data" / "registers"
ACTIVE_REGISTER_PATH = REPO_ROOT / "data" / "active_register.json"
OUTPUT_PATH = REPO_ROOT / "output" / "validation" / "register_validation.json"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"


def _compute_scale_floor(register: dict) -> float:
    """Minimum plausible figure based on register VaCR values. Flags SMB-scale outliers."""
    vacr_values = [
        s.get("value_at_cyber_risk_usd", 0)
        for s in register.get("scenarios", [])
        if s.get("value_at_cyber_risk_usd")
    ]
    if not vacr_values:
        return 100_000.0
    return max(100_000.0, min(vacr_values) * 0.05)


def load_active_register() -> dict:
    active = json.loads(ACTIVE_REGISTER_PATH.read_text(encoding="utf-8"))
    register_id = active.get("register_id", "aerogrid_enterprise")
    path = REGISTERS_DIR / f"{register_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Web search primitive
# ---------------------------------------------------------------------------

def _search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search using Tavily if key available, else DuckDuckGo fallback."""
    import os
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_key:
        try:
            import requests
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": max_results, "search_depth": "basic"},
                timeout=20,
            )
            results = resp.json().get("results", [])
            return [{"title": r.get("title", ""), "content": r.get("content", ""), "url": r.get("url", "")} for r in results]
        except Exception as e:
            print(f"[register_validator] Tavily failed: {e}", file=sys.stderr)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "content": r.get("body", ""), "url": r.get("href", "")} for r in results]
    except Exception as e:
        print(f"[register_validator] DDG failed: {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Haiku figure extractors
# ---------------------------------------------------------------------------

_FIN_EXTRACTION_PROMPT = """\
You are extracting financial impact data from a cybersecurity industry report.

Extract all dollar-denominated financial impact figures for cyber incidents. For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to (e.g. "manufacturing", "energy", "all")
- cost_low_usd: lower bound in USD as integer (null if not stated)
- cost_median_usd: median or average in USD as integer (null if not stated)
- cost_high_usd: upper bound in USD as integer (null if not stated)
- note: brief description of what this figure represents
- raw_quote: the exact text excerpt (max 200 chars)
- context_tag: one of "asset_specific", "company_scale", "both", or "general"
  "asset_specific" if the source content mentions OT/ICS/SCADA/industrial/wind/turbine/control system
  "company_scale" if the source mentions enterprise/large organization/sector-wide/>1000 employees
  "both" if it matches both criteria
  "general" if neither
- smb_scale_flag: false

Return ONLY a JSON array. If no financial figures found, return [].

Text to analyze:
{raw_text}"""


def _extract_financial_figures(text: str, source_name: str) -> list[dict]:
    """Run Haiku over text to extract USD financial figures."""
    if not text.strip():
        return []
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": _FIN_EXTRACTION_PROMPT.format(raw_text=text[:10_000])}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        figures = json.loads(content.strip())
        for f in figures:
            f["_source_name"] = source_name
        return figures
    except Exception as e:
        print(f"[register_validator] Haiku fin extraction failed ({source_name[:40]}): {e}", file=sys.stderr)
        return []


_PROB_EXTRACTION_PROMPT = """\
You are extracting incident probability data from a cybersecurity industry report.

Extract all percentage figures that represent incident frequency or probability:
- Annual incident probability (% of organizations affected per year)
- Incident frequency rates
- Prevalence rates for cyber incidents

For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to
- probability_pct: the percentage value as a float
- note: brief description of what this percentage represents
- raw_quote: the exact text excerpt (max 200 chars)
- context_tag: one of "asset_specific", "company_scale", "both", or "general"
  "asset_specific" if the source content mentions OT/ICS/SCADA/industrial/wind/turbine/control system
  "company_scale" if the source mentions enterprise/large organization/sector-wide/>1000 employees
  "both" if it matches both criteria
  "general" if neither
- smb_scale_flag: false

Return ONLY a JSON array. If no probability figures found, return [].

Text to analyze:
{raw_text}"""


def _extract_probability_figures(text: str, source_name: str) -> list[dict]:
    """Run Haiku over text to extract incident probability percentages."""
    if not text.strip():
        return []
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": _PROB_EXTRACTION_PROMPT.format(raw_text=text[:10_000])}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        figures = json.loads(content.strip())
        for f in figures:
            f["_source_name"] = source_name
        return figures
    except Exception as e:
        print(f"[register_validator] Haiku prob extraction failed ({source_name[:40]}): {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Register-contextualized query builder
# ---------------------------------------------------------------------------

def _build_sector_queries(scenario: dict, register: dict) -> dict:
    """Build broad sector queries. Context applied at extraction, not search time."""
    name = scenario["scenario_name"]
    context = register.get("company_context", "energy sector")
    sector = "energy sector"
    if "wind" in context.lower():
        sector = "energy sector wind power"
    elif "manufacturing" in context.lower():
        sector = "manufacturing energy sector"
    financial = f"{name} financial cost impact {sector} operator USD 2024 2025"
    probability = f"{name} incident rate probability annual {sector} 2024 2025"
    return {"financial": financial, "probability": probability}


# ---------------------------------------------------------------------------
# Phase 1: refresh known validated sources
# ---------------------------------------------------------------------------

def phase1_refresh_known_sources(
    conn: sqlite3.Connection, scenario: dict
) -> tuple[list[dict], list[dict]]:
    """
    Phase 1: For each known validated source in sources.db matching this scenario's tags,
    run a targeted Tavily search to find new/updated reports from that source.
    Returns (fin_figures, prob_figures) — each item has phase=1.
    """
    search_tags = set(scenario.get("search_tags", []))
    rows = conn.execute(
        "SELECT name, url, source_tags FROM sources_registry WHERE has_quantitative_data = 1"
    ).fetchall()

    relevant = []
    for name, url, tags_json in rows:
        try:
            tags = set(json.loads(tags_json or "[]"))
        except Exception:
            tags = set()
        if tags & search_tags:
            relevant.append({"name": name, "url": url or ""})

    fin_figures, prob_figures = [], []
    for source in relevant[:5]:
        name = source["name"]
        url = source["url"]
        domain = urlparse(url).netloc if url else ""

        if domain:
            query = f'site:{domain} "{scenario["scenario_name"]}" 2024 2025'
        else:
            query = f'"{name}" "{scenario["scenario_name"]}" report 2024 2025'

        print(f"[register_validator] Phase 1 -- {name[:50]}: {query[:70]}", file=sys.stderr)
        results = _search_web(query, max_results=3)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or name
            src_url = r.get("url") or url

            for fig in _extract_financial_figures(content, src_name):
                fig["phase"] = 1
                fig["source_url"] = src_url
                fin_figures.append(fig)

            for fig in _extract_probability_figures(content, src_name):
                fig["phase"] = 1
                fig["source_url"] = src_url
                prob_figures.append(fig)

    return fin_figures, prob_figures


# ---------------------------------------------------------------------------
# Phase 2: register-contextualized OSINT
# ---------------------------------------------------------------------------

def phase2_osint_search(
    scenario: dict, register: dict
) -> tuple[list[dict], list[dict]]:
    """
    Phase 2: Register-contextualized OSINT — broader Tavily search for new benchmark reports.
    Queries are shaped by register.company_context and scenario search_tags.
    Returns (fin_figures, prob_figures) — each item has phase=2.
    """
    queries = _build_sector_queries(scenario, register)
    fin_figures, prob_figures = [], []

    for query in [queries["financial"]]:
        print(f"[register_validator] Phase 2 fin -- {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_financial_figures(content, src_name):
                fig["phase"] = 2
                fig["source_url"] = r.get("url", "")
                fin_figures.append(fig)

    for query in [queries["probability"]]:
        print(f"[register_validator] Phase 2 prob -- {query[:80]}", file=sys.stderr)
        results = _search_web(query, max_results=4)
        for r in results:
            content = r.get("content", "")
            src_name = r.get("title") or r.get("url", "")
            for fig in _extract_probability_figures(content, src_name):
                fig["phase"] = 2
                fig["source_url"] = r.get("url", "")
                prob_figures.append(fig)

    return fin_figures, prob_figures


# ---------------------------------------------------------------------------
# Outlier filter
# ---------------------------------------------------------------------------

def filter_outliers(values: list[float]) -> list[float]:
    """
    Remove statistical outliers using the IQR method.
    Requires at least 4 values to filter — returns input unchanged if fewer.
    Never returns an empty list.
    """
    if len(values) < 4:
        return values
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[(3 * n) // 4]
    iqr = q3 - q1
    if iqr == 0:
        return values
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    filtered = [v for v in sorted_vals if lo <= v <= hi]
    return filtered if filtered else values


# ---------------------------------------------------------------------------
# Sonnet recommendation
# ---------------------------------------------------------------------------

_RECOMMENDATION_PROMPT = """\
You are a cyber risk analyst reviewing VaCR (Value at Cyber Risk) validation results.

Register context: {company_context}
Scenario: {scenario_name}
Description: {scenario_description}

Financial validation:
  - Register VaCR: ${vacr_usd:,}
  - Benchmark range from industry sources: {fin_range}
  - Verdict: {fin_verdict} ({fin_source_count} sources found)

Probability validation:
  - Register probability: {prob_pct}%
  - Benchmark range from industry sources: {prob_range}
  - Verdict: {prob_verdict} ({prob_source_count} sources found)

Write a concise analyst note (2-3 sentences) addressing:
1. Whether the register figures appear well-calibrated for this specific organisation type
2. What the benchmark evidence suggests about direction of revision, if any
3. If verdict is "insufficient", what source types would strengthen this validation

Tone: direct, no jargon, no financial advice language. Plain text only."""


def _build_recommendation_sonnet(
    scenario: dict,
    register: dict,
    fin: dict,
    prob: dict,
) -> str:
    """Generate a Sonnet analyst recommendation paragraph for this scenario."""
    def _fmt_fin_range(r):
        if not r:
            return "no benchmark data found"
        return f"${r[0]:,.0f} - ${r[1]:,.0f}"

    def _fmt_prob_range(r):
        if not r:
            return "no benchmark data found"
        return f"{r[0]:.1f}% - {r[1]:.1f}%"

    all_sources = fin.get("registered_sources", []) + fin.get("new_sources", [])
    prob_all_sources = prob.get("registered_sources", []) + prob.get("new_sources", [])

    prompt = _RECOMMENDATION_PROMPT.format(
        company_context=register.get("company_context", ""),
        scenario_name=scenario["scenario_name"],
        scenario_description=scenario.get("description", ""),
        vacr_usd=fin.get("vacr_figure_usd") or 0,
        fin_range=_fmt_fin_range(fin.get("benchmark_range_usd")),
        fin_verdict=fin.get("verdict", "insufficient"),
        fin_source_count=len(all_sources),
        prob_pct=prob.get("vacr_probability_pct") or 0,
        prob_range=_fmt_prob_range(prob.get("benchmark_range_pct")),
        prob_verdict=prob.get("verdict", "insufficient"),
        prob_source_count=len(prob_all_sources),
    )
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"[register_validator] Sonnet recommendation failed: {e}", file=sys.stderr)
        parts = []
        if fin.get("benchmark_range_usd"):
            r = fin["benchmark_range_usd"]
            parts.append(f"Financial {fin['verdict']}: benchmark ${r[0]:,.0f}-${r[1]:,.0f} vs VaCR ${fin.get('vacr_figure_usd', 0):,.0f}.")
        else:
            parts.append("Insufficient financial benchmark sources.")
        if prob.get("benchmark_range_pct"):
            r = prob["benchmark_range_pct"]
            parts.append(f"Probability {prob['verdict']}: benchmark {r[0]:.1f}-{r[1]:.1f}% vs {prob.get('vacr_probability_pct', 0)}%.")
        else:
            parts.append("Insufficient probability benchmark sources.")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Core: numeric helpers and verdict
# ---------------------------------------------------------------------------

def _parse_usd(figure_str: str | None) -> float | None:
    if not figure_str:
        return None
    s = str(figure_str).replace(",", "").upper()
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
    m = re.search(r"([\d.]+)\s*%", str(figure_str))
    return float(m.group(1)) if m else None


def compute_verdict(vacr_value: float | None, benchmark_values: list[float]) -> tuple[str, list[float]]:
    if not benchmark_values or len(benchmark_values) < 2:
        return "insufficient", []
    lo, hi = min(benchmark_values), max(benchmark_values)
    if vacr_value is None:
        return "insufficient", [lo, hi]
    midpoint = (lo + hi) / 2
    diff_pct = abs(vacr_value - midpoint) / midpoint if midpoint else 0
    if lo <= vacr_value <= hi or diff_pct <= 0.25:
        return "supports", [lo, hi]
    return "challenges", [lo, hi]


# ---------------------------------------------------------------------------
# Track 3: check source versions
# ---------------------------------------------------------------------------

def check_source_versions(sources: list, web_search_fn) -> list:
    """Track 3: check if newer editions exist for known sources."""
    version_checks = []
    for source in sources:
        source_id = source.get("id", source.get("name", "").lower().replace(" ", "-"))
        name = source.get("name", "")
        edition_year = source.get("edition_year", 2024)
        query = f"{name} {edition_year + 1} annual report"
        try:
            results = web_search_fn(query, max_results=3)
            newer_year = None
            newer_url = None
            for r in results:
                title = r.get("title", "") + " " + r.get("snippet", r.get("content", ""))
                for year in [2025, 2026]:
                    if str(year) in title and year > edition_year:
                        newer_year = year
                        newer_url = r.get("url", r.get("link", ""))
                        break
                if newer_year:
                    break
            version_checks.append({
                "source_id": source_id,
                "name": name,
                "edition_year": edition_year,
                "newer_version_found": newer_year is not None,
                "newer_year": newer_year,
                "url": newer_url,
            })
        except Exception as e:
            version_checks.append({
                "source_id": source_id,
                "name": name,
                "edition_year": edition_year,
                "newer_version_found": False,
                "newer_year": None,
                "url": None,
            })
    return version_checks


# ---------------------------------------------------------------------------
# Validate one scenario
# ---------------------------------------------------------------------------

def validate_scenario(
    conn: sqlite3.Connection,
    scenario: dict,
    register: dict,
) -> dict:
    """
    Full two-phase validation for one scenario.
    Phase 1: known sources in sources.db -> Tavily site-search refresh.
    Phase 2: register-contextualized OSINT -> broader Tavily search.
    """
    scale_floor = _compute_scale_floor(register)

    p1_fin, p1_prob = phase1_refresh_known_sources(conn, scenario)
    p2_fin, p2_prob = phase2_osint_search(scenario, register)

    all_fin_figs = p1_fin + p2_fin
    all_prob_figs = p1_prob + p2_prob

    fin_values: list[float] = []
    for f in all_fin_figs:
        val = f.get("cost_median_usd")
        if not val:
            lo = f.get("cost_low_usd") or 0
            hi = f.get("cost_high_usd") or 0
            val = (lo + hi) / 2 if (lo or hi) else None
        if val:
            fin_values.append(float(val))

    prob_values: list[float] = []
    for f in all_prob_figs:
        val = f.get("probability_pct")
        if val:
            prob_values.append(float(val))

    fin_values = filter_outliers(fin_values)
    prob_values = filter_outliers(prob_values)

    vacr_usd = scenario.get("value_at_cyber_risk_usd")
    vacr_pct = scenario.get("probability_pct")

    fin_verdict, fin_range = compute_verdict(vacr_usd, fin_values)
    prob_verdict, prob_range = compute_verdict(vacr_pct, prob_values)

    # Split sources into registered (phase 1) vs new (phase 2)
    seen_fin, seen_prob = set(), set()
    fin_registered_out, fin_new_out = [], []
    prob_registered_out, prob_new_out = [], []

    for f in all_fin_figs:
        key = (f.get("_source_name", "") or "")[:60]
        if key and key not in seen_fin:
            seen_fin.add(key)
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
            if f.get("phase") == 1:
                fin_registered_out.append(source_dict)
            else:
                fin_new_out.append(source_dict)

    for f in all_prob_figs:
        key = (f.get("_source_name", "") or "")[:60]
        if key and key not in seen_prob:
            seen_prob.add(key)
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
            if f.get("phase") == 1:
                prob_registered_out.append(source_dict)
            else:
                prob_new_out.append(source_dict)

    # asset_context_note
    all_sources_combined = fin_registered_out + fin_new_out + prob_registered_out + prob_new_out
    has_asset_specific = any(
        s.get("context_tag") in ("asset_specific", "both")
        for s in all_sources_combined
    )
    asset_context_note = "" if has_asset_specific else "No OT/asset-specific quantitative data found — company-scale sources only."

    # INSUFFICIENT only when total sources < 2
    total_fin_sources = len(fin_registered_out) + len(fin_new_out)
    total_prob_sources = len(prob_registered_out) + len(prob_new_out)
    if total_fin_sources < 2 and fin_verdict != "insufficient":
        fin_verdict = "insufficient"
    if total_prob_sources < 2 and prob_verdict != "insufficient":
        prob_verdict = "insufficient"

    fin_result = {
        "vacr_figure_usd": vacr_usd,
        "verdict": fin_verdict,
        "benchmark_range_usd": fin_range,
        "registered_sources": fin_registered_out,
        "new_sources": fin_new_out,
        "recommendation": "",
    }
    prob_result = {
        "vacr_probability_pct": vacr_pct,
        "verdict": prob_verdict,
        "benchmark_range_pct": prob_range,
        "registered_sources": prob_registered_out,
        "new_sources": prob_new_out,
        "recommendation": "",
    }

    recommendation = _build_recommendation_sonnet(scenario, register, fin_result, prob_result)
    fin_result["recommendation"] = recommendation
    prob_result["recommendation"] = recommendation

    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "asset_context_note": asset_context_note,
        "financial": fin_result,
        "probability": prob_result,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    register = load_active_register()
    conn = sqlite3.connect(str(DB_PATH))

    print(f"[register_validator] Active register: {register['register_id']}")
    print(f"[register_validator] Context: {register.get('company_context', '')[:80]}")
    print(f"[register_validator] Scenarios: {len(register['scenarios'])}")

    # Load validation sources for version checks
    val_sources_path = REPO_ROOT / "data" / "validation_sources.json"
    all_val_sources = []
    if val_sources_path.exists():
        try:
            all_val_sources = json.loads(val_sources_path.read_text(encoding="utf-8")).get("sources", [])
        except Exception:
            pass

    scenario_results = []
    for scenario in register["scenarios"]:
        print(f"[register_validator] Validating: {scenario['scenario_id']} - {scenario['scenario_name']}")
        result = validate_scenario(conn, scenario, register)
        scenario_results.append(result)
        fin_v = result["financial"]["verdict"]
        prob_v = result["probability"]["verdict"]
        print(f"  -> financial: {fin_v}  probability: {prob_v}")

    # Track 3: version checks on known sources
    version_checks = check_source_versions(all_val_sources, _search_web)

    output = {
        "register_id": register["register_id"],
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "version_checks": version_checks,
        "scenarios": scenario_results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    register["last_validated_at"] = output["validated_at"]
    reg_path = REGISTERS_DIR / f"{register['register_id']}.json"
    reg_path.write_text(json.dumps(register, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[register_validator] Done -> {OUTPUT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
