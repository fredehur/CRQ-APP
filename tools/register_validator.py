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
import time
from dataclasses import dataclass, field
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
_PHASE1_SOURCE_CAP = 5  # limits Tavily API calls per scenario against known sources.db entries
_PHASE2_QUERY_CAP = 3   # max queries per dimension per scenario in Phase 2

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"


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
You are extracting incident frequency data from a cybersecurity industry report.

IMPORTANT: Most published cybersecurity reports contain prevalence rates — the percentage
of surveyed organizations that experienced an incident in a given year. These are NOT
per-organization annual probabilities. Extract them as-is and label their type accurately.

For each percentage figure found that relates to incident frequency or prevalence:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to
- probability_pct: the percentage value as a float
- evidence_subtype: one of:
    "prevalence_survey"    — % of surveyed organisations affected (most common in reports)
    "frequency_rate"       — incidents per organisation per year (rare, usually in ICS reports)
    "expert_estimate"      — stated as an expert judgement or model output
    "program_prevalence"   — % of orgs with a policy/program/control/awareness in place (NOT an incident rate)
    "unknown"              — cannot determine
- measures_incident: true if the figure counts incidents/breaches/attacks/compromises that actually occurred; false for policy adoption, program maturity, awareness, attitudinal surveys, or control presence (e.g. '% of orgs that have a program', '% aware of risk', '% planning to invest')
- note: brief description of what this percentage represents and its population
- raw_quote: the exact text excerpt (max 200 chars)
- context_tag: one of "asset_specific", "company_scale", "both", or "general"
  "asset_specific" if the source mentions OT/ICS/SCADA/industrial/wind/turbine/control system
  "company_scale" if the source mentions enterprise/large organization/sector-wide/>1000 employees
  "both" if it matches both criteria
  "general" if neither

IMPORTANT: Reject figures that describe program maturity, policy adoption, control presence, or attitudinal surveys (e.g. '% of orgs that have a policy', '% aware of risk', '% planning to invest'). Those are NOT incident frequency data. Label them "program_prevalence" and set measures_incident to false.

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

_SCENARIO_QUERY_PHRASES = {
    "Physical threat": "physical cyber sabotage attack",
    "Accidental disclosure": "accidental data exposure breach",
    "System failure": "cyber system outage disruption",
    "Defacement": "website defacement cyber attack",
    "Insider misuse": "insider threat incident data theft",
    "Scam or fraud": "business email compromise cyber fraud",
    "DoS attack": "denial of service cyber attack",
    "System intrusion": "cyber intrusion breach",
    "Ransomware": "ransomware attack incident",
}


# Evidence specificity tiers — lower = more specific
EVIDENCE_TIER_ASSET_SPECIFIC      = 1   # Named wind farm / asset-class incident data
EVIDENCE_TIER_SECTOR_SPECIFIC     = 2   # Energy utility sector benchmarks
EVIDENCE_TIER_TECHNOLOGY_SPECIFIC = 3   # OT/ICS technology class (no sector filter)
EVIDENCE_TIER_GENERAL             = 4   # Cross-industry (IBM CoDB, Verizon DBIR, etc.)

_EVIDENCE_TIER_LABELS = {
    1: "Asset-specific evidence",
    2: "Sector-specific evidence",
    3: "OT/technology evidence",
    4: "General industry evidence",
}


def _tier_entry(query: str, tier: int) -> dict:
    return {"query": query, "tier": tier, "tier_label": _EVIDENCE_TIER_LABELS[tier]}


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


# ---------------------------------------------------------------------------
# Phase 1: refresh known validated sources
# ---------------------------------------------------------------------------

def phase1_refresh_known_sources(
    conn: sqlite3.Connection, scenario: dict, counters: "RunCounters"
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
    for source in relevant[:_PHASE1_SOURCE_CAP]:
        name = source["name"]
        url = source["url"]
        source_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or name
        counters.queried_source_ids.add(source_id)
        domain = urlparse(url).netloc if url else ""

        if domain:
            query = f'site:{domain} "{scenario["scenario_name"]}" 2024 2025'
        else:
            query = f'"{name}" "{scenario["scenario_name"]}" report 2024 2025'

        print(f"[register_validator] Phase 1 -- {name[:50]}: {query[:70]}", file=sys.stderr)
        results = _search_web(query, max_results=3)
        if any(r.get("content", "").strip() for r in results):
            counters.matched_source_ids.add(source_id)
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
  - Benchmark range from peer industry sources: {fin_range}
  - Verdict: {fin_verdict} ({fin_source_count} sources, data confidence: {fin_confidence})

Probability validation:
  - Register probability: {prob_pct}%
  - Benchmark range from industry sources: {prob_range}
  - Verdict: {prob_verdict} ({prob_source_count} sources, data confidence: {prob_confidence})
  - Evidence type: {prob_evidence_type}

IMPORTANT — PROBABILITY EVIDENCE:
- "prevalence_survey": figures are % of organisations surveyed that experienced the incident.
  These are NOT per-organisation annual frequencies. The probability verdict is directional
  only — state this explicitly in your note.
- "frequency_rate": figures are incidents per organisation per year — more directly comparable.
- "mixed": sources include both types — note the limitation.

Write a concise analyst note (2-3 sentences) addressing:
1. Whether the financial figure appears well-calibrated against peer sector data. If data
   confidence is "low", say the benchmark is from general sector sources, not asset-specific.
2. What the probability evidence type means for the reliability of that verdict.
3. If either verdict is "insufficient", what specific source types would strengthen this.

Tone: direct, no jargon, no financial advice language. Plain text only.

ANALYST BASELINE (optional, may be "none"):
  fin:  {baseline_fin_summary}
  prob: {baseline_prob_summary}
  alignment_fin:  {baseline_fin_alignment}
  alignment_prob: {baseline_prob_alignment}

If a baseline is present, your recommendation MUST acknowledge it explicitly:
- If baseline aligns with OSINT: cite the analyst's number as a corroborating signal.
- If baseline diverges from OSINT: name the divergence and which range you weight higher (with reason).
- Never silently override the baseline — the analyst put it there deliberately."""


def _build_recommendation_sonnet(
    scenario: dict,
    register: dict,
    fin: dict,
    prob: dict,
    baseline: dict | None = None,
    alignment: dict | None = None,
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

    baseline = baseline or {}
    alignment = alignment or {"fin": "n/a", "prob": "n/a"}
    baseline_fin_summary = format_baseline_summary(baseline.get("fin"), kind="fin")
    baseline_prob_summary = format_baseline_summary(baseline.get("prob"), kind="prob")

    prompt = _RECOMMENDATION_PROMPT.format(
        company_context=register.get("company_context", ""),
        scenario_name=scenario["scenario_name"],
        scenario_description=scenario.get("description", ""),
        vacr_usd=fin.get("vacr_figure_usd") or 0,
        fin_range=_fmt_fin_range(fin.get("benchmark_range_usd")),
        fin_verdict=fin.get("verdict", "insufficient"),
        fin_confidence=fin.get("verdict_confidence", "low"),
        fin_source_count=len(all_sources),
        prob_pct=prob.get("vacr_probability_pct") or 0,
        prob_range=_fmt_prob_range(prob.get("benchmark_range_pct")),
        prob_verdict=prob.get("verdict", "insufficient"),
        prob_confidence=prob.get("verdict_confidence", "low"),
        prob_source_count=len(prob_all_sources),
        prob_evidence_type=prob.get("evidence_type", "prevalence_survey"),
        baseline_fin_summary=baseline_fin_summary,
        baseline_prob_summary=baseline_prob_summary,
        baseline_fin_alignment=alignment.get("fin", "n/a"),
        baseline_prob_alignment=alignment.get("prob", "n/a"),
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
    if not benchmark_values:
        return "insufficient", []
    lo, hi = min(benchmark_values), max(benchmark_values)
    if vacr_value is None:
        return "insufficient", [lo, hi]
    midpoint = (lo + hi) / 2
    diff_pct = abs(vacr_value - midpoint) / midpoint if midpoint else 0
    if lo <= vacr_value <= hi or diff_pct <= 0.25:
        return "supports", [lo, hi]
    return "challenges", [lo, hi]


def compute_verdict_confidence(sources: list[dict]) -> str:
    """
    Deterministic confidence rating based on source context_tag values.
    high   — at least one source tagged asset_specific or both (OT/ICS data)
    medium — at least one source tagged company_scale (enterprise sector peer)
    low    — all sources are general (no sector or asset specificity)
    """
    tags = [s.get("context_tag", "general") for s in sources]
    if any(t in ("asset_specific", "both") for t in tags):
        return "high"
    if any(t == "company_scale" for t in tags):
        return "medium"
    return "low"


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
    best = max(1, min(4, int(best)))
    return best, _EVIDENCE_TIER_LABELS[best]


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
            # Convert baseline fraction -> percent for comparison
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
                current_year = datetime.now().year
                for year in range(edition_year + 1, current_year + 2):
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
            print(f"[register_validator] Version check failed ({name[:40]}): {e}", file=sys.stderr)
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
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- previous run ---
    prior = None
    previous_run_id = None
    if previous_path:
        try:
            p = Path(previous_path) if not isinstance(previous_path, Path) else previous_path
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

    # --- coverage gaps (scenarios with verdict=insufficient AND source count <= 1) ---
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


# ---------------------------------------------------------------------------
# Validate one scenario
# ---------------------------------------------------------------------------

def validate_scenario(
    conn: sqlite3.Connection,
    scenario: dict,
    register: dict,
    counters: RunCounters,
) -> dict:
    """
    Full two-phase validation for one scenario.
    Phase 1: known sources in sources.db -> Tavily site-search refresh.
    Phase 2: register-contextualized OSINT -> broader Tavily search.
    """
    scale_floor = _compute_scale_floor(register)

    # Dynamic cap: figures above 50x the register's highest VaCR are sector-wide aggregates
    max_vacr = max(
        (s.get("value_at_cyber_risk_usd") or 0 for s in register.get("scenarios", [])),
        default=10_000_000,
    )
    fin_cap = max(max_vacr * 50, 500_000_000)  # floor cap at $500M

    p1_fin, p1_prob = phase1_refresh_known_sources(conn, scenario, counters)
    p2_fin, p2_prob = phase2_osint_search(scenario, register)

    all_fin_figs = p1_fin + p2_fin
    all_prob_figs = p1_prob + p2_prob

    fin_values: list[float] = []
    for f in all_fin_figs:
        # Exclude enterprise/sector-wide aggregate figures — not per-site benchmarks
        if f.get("context_tag") == "company_scale":
            continue
        lo = f.get("cost_low_usd")
        med = f.get("cost_median_usd")
        hi = f.get("cost_high_usd")
        # A reported range is 2+ data points, not 1 — keep endpoints separate
        for val in (lo, med, hi):
            if val and float(val) <= fin_cap:
                fin_values.append(float(val))

    prob_values: list[float] = []
    for f in all_prob_figs:
        if f.get("evidence_subtype") not in (None, "prevalence_survey", "frequency_rate", "expert_estimate", "unknown"):
            continue
        if f.get("measures_incident") is False:  # explicit False; None = legacy = allow
            continue
        val = f.get("probability_pct")
        if val and float(val) <= 100.0:  # sanity cap
            prob_values.append(float(val))

    fin_values = filter_outliers_with_counter(fin_values, counters, dim="fin")
    prob_values = filter_outliers_with_counter(prob_values, counters, dim="prob")

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
                "evidence_tier": f.get("evidence_tier", EVIDENCE_TIER_GENERAL),
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
                "evidence_tier": f.get("evidence_tier", EVIDENCE_TIER_GENERAL),
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
        fin_range = []
    if total_prob_sources < 2 and prob_verdict != "insufficient":
        prob_verdict = "insufficient"
        prob_range = []

    fin_confidence = compute_verdict_confidence(fin_registered_out + fin_new_out)
    prob_confidence = compute_verdict_confidence(prob_registered_out + prob_new_out)

    fin_all_src = fin_registered_out + fin_new_out
    prob_all_src = prob_registered_out + prob_new_out
    fin_ceiling_tier, fin_ceiling_label = compute_evidence_ceiling(fin_all_src)
    prob_ceiling_tier, prob_ceiling_label = compute_evidence_ceiling(prob_all_src)
    baseline = scenario.get("analyst_baseline")
    fin_load_bearing = (fin_ceiling_tier == EVIDENCE_TIER_GENERAL and not (baseline and baseline.get("fin")))
    prob_load_bearing = (prob_ceiling_tier == EVIDENCE_TIER_GENERAL and not (baseline and baseline.get("prob")))

    # Probability evidence type: derived from what Haiku found
    prob_evidence_subtypes = {
        f.get("evidence_subtype", "unknown")
        for f in all_prob_figs
        if f.get("evidence_subtype") and f.get("evidence_subtype") != "unknown"
    }
    if not prob_evidence_subtypes or prob_evidence_subtypes == {"prevalence_survey"}:
        prob_evidence_type = "prevalence_survey"
    elif prob_evidence_subtypes == {"frequency_rate"}:
        prob_evidence_type = "frequency_rate"
    else:
        prob_evidence_type = "mixed"

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
        "evidence_ceiling_label": prob_ceiling_label,
        "analyst_baseline_load_bearing": prob_load_bearing,
        "evidence_type": prob_evidence_type,
        "benchmark_range_pct": prob_range,
        "registered_sources": prob_registered_out,
        "new_sources": prob_new_out,
    }

    # --- analyst baseline pass-through + alignment ---
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

    recommendation = _build_recommendation_sonnet(
        scenario, register, fin_result, prob_result,
        baseline=baseline, alignment=alignment,
    )

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    register = load_active_register()
    conn = sqlite3.connect(str(DB_PATH))

    counters = RunCounters()
    run_started_monotonic = time.monotonic()

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
        result = validate_scenario(conn, scenario, register, counters)
        scenario_results.append(result)
        fin_v = result["financial"]["verdict"]
        prob_v = result["probability"]["verdict"]
        print(f"  -> financial: {fin_v}  probability: {prob_v}")

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


if __name__ == "__main__":
    main()
