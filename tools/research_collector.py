#!/usr/bin/env python3
"""Target-centric OSINT research collector.

Usage:
    uv run python tools/research_collector.py <REGION> [--mock]

Mock mode: delegates to geo_collector.py + cyber_collector.py (unchanged behaviour).
Live mode: 3-pass target-centric loop using Anthropic API.

Writes (live mode only):
    output/regional/{region}/research_scratchpad.json  — audit trail
    output/regional/{region}/geo_signals.json          — same schema as geo_collector
    output/regional/{region}/cyber_signals.json        — same schema as cyber_collector
"""
import anthropic
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
REPO_ROOT = Path(__file__).resolve().parent.parent


def _call_llm(prompt: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 1024) -> dict:
    """Call Anthropic API, parse JSON response. Raises ValueError on bad JSON."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON (model={model}): {text[:200]!r}") from exc


def form_working_theory(region: str, crq_data: dict, topics: list, company_profile: dict) -> dict:
    """LLM Call 1: Form a CRQ-grounded working theory for the region.

    Returns dict with: scenario_name, vacr_usd, hypothesis, active_topics, geo_queries, cyber_queries
    """
    scenario = crq_data.get(region, [{}])[0]
    scenario_name = scenario.get("scenario_name", "Unknown")
    vacr = scenario.get("value_at_cyber_risk_usd", 0)

    active_topics = [
        {"id": t["id"], "label": t["label"]}
        for t in topics
        if t.get("active") and region in t.get("regions", [])
    ]

    prompt = f"""You are forming a target-centric intelligence collection hypothesis.

REGION: {region}
CRQ SCENARIO: {scenario_name}
VALUE AT CYBER RISK: ${vacr:,}
COMPANY: {company_profile.get("industry", "Wind Energy")} operator
CROWN JEWELS: {json.dumps(company_profile.get("crown_jewels", []))}
ACTIVE TOPICS FOR THIS REGION: {json.dumps(active_topics)}

Form a working theory: is there evidence that the {scenario_name} scenario is materializing in {region}?

Return ONLY valid JSON (no markdown fences):
{{
  "hypothesis": "One paragraph — state the hypothesis grounded in the dollar exposure and what evidence would confirm or deny it",
  "geo_queries": ["geopolitical query 1", "geopolitical query 2", "geopolitical query 3"],
  "cyber_queries": ["cyber threat query 1", "cyber threat query 2", "cyber threat query 3"]
}}

geo_queries: focus on geopolitical drivers, regulatory change, state actor intent.
cyber_queries: focus on cyber incidents, threat actor activity, OT/ICS targeting.
All queries must be specific to {region}, the scenario, and wind energy context. Minimum 2 per list."""

    result = _call_llm(prompt)
    return {
        "scenario_name": scenario_name,
        "vacr_usd": vacr,
        "hypothesis": result["hypothesis"],
        "active_topics": active_topics,
        "geo_queries": result["geo_queries"],
        "cyber_queries": result["cyber_queries"],
    }


def run_search_pass(region: str, queries: list[str], query_type: str) -> list[dict]:
    """Run queries via osint_search.py with the given type. Returns deduplicated results.

    Args:
        query_type: "geo" or "cyber" — passed as --type flag to osint_search.py
    """
    seen_urls: set[str] = set()
    results: list[dict] = []

    for query in queries:
        proc = subprocess.run(
            [sys.executable, "tools/osint_search.py", region, query, "--type", query_type],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        try:
            items = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for item in items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append(item)

    return results


def assess_gaps(region: str, working_theory: dict, results: list[dict]) -> dict:
    """LLM Call 2: Assess evidence against the working theory. Identify gaps.

    Returns dict with: gap_assessment, gaps_identified, follow_up_queries,
                       follow_up_query_type, run_pass_2
    """
    snippets_text = "\n".join(
        f"- [{r.get('title', '')}] {r.get('summary', '')}"
        for r in results[:15]
    )

    prompt = f"""You are assessing intelligence collection coverage.

REGION: {region}
WORKING THEORY: {working_theory['hypothesis']}
SCENARIO: {working_theory['scenario_name']} (${working_theory['vacr_usd']:,} exposure)

EVIDENCE COLLECTED ({len(results)} results):
{snippets_text}

Assess: does the collected evidence adequately address the working theory?
- Is there a wind energy or sector-specific signal?
- Are there gaps (e.g., no sector signal, no recent events, no cyber-specific indicator)?
- If gaps exist, what 1-3 targeted follow-up queries would fill them?
- Should they be geo type (geopolitical) or cyber type?

Return ONLY valid JSON (no markdown fences):
{{
  "gap_assessment": "2-3 sentence assessment of evidence quality against the theory",
  "gaps_identified": ["gap1", "gap2"],
  "follow_up_queries": ["targeted query 1"],
  "follow_up_query_type": "geo",
  "run_pass_2": true
}}

Set run_pass_2 to false if 3+ corroborating sources address the scenario (sufficient).
Set run_pass_2 to true if significant gaps remain. Maximum 3 follow_up_queries."""

    result = _call_llm(prompt)
    required = {"gap_assessment", "gaps_identified", "follow_up_queries", "follow_up_query_type", "run_pass_2"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"assess_gaps: LLM response missing required keys: {missing}")
    return result


def synthesize_signals(
    region: str, working_theory: dict, results: list[dict]
) -> tuple[dict, dict, dict]:
    """LLM Call 3 (Sonnet): Synthesize all results into geo + cyber signal schemas.

    Returns: (geo_signals, cyber_signals, conclusion)
    """
    snippets_text = "\n".join(
        f"- [{r.get('title', '')}] ({r.get('url', '')}) {r.get('summary', '')}"
        for r in results[:20]
    )
    topic_ids = [t["id"] for t in working_theory.get("active_topics", [])]

    prompt = f"""You are synthesizing OSINT collection into structured intelligence signals.

REGION: {region}
WORKING THEORY: {working_theory['hypothesis']}
SCENARIO: {working_theory['scenario_name']} (${working_theory['vacr_usd']:,})
ACTIVE TOPICS: {json.dumps(topic_ids)}

COLLECTED EVIDENCE ({len(results)} results):
{snippets_text}

Synthesize this into structured intelligence. Separate the geopolitical context (WHY) from the cyber vector (HOW).

Return ONLY valid JSON (no markdown fences):
{{
  "geo_signals": {{
    "summary": "2-3 sentence geopolitical context",
    "lead_indicators": ["indicator 1", "indicator 2", "indicator 3"],
    "dominant_pillar": "Geopolitical",
    "matched_topics": ["topic-id-if-matched"]
  }},
  "cyber_signals": {{
    "summary": "2-3 sentence cyber threat summary",
    "threat_vector": "How the threat reaches the organisation",
    "target_assets": ["asset 1", "asset 2"],
    "dominant_pillar": "Cyber",
    "matched_topics": ["topic-id-if-matched"]
  }},
  "conclusion": {{
    "theory_confirmed": true,
    "confidence_rationale": "Evidence quality assessment — sources, corroboration, contradictions",
    "suggested_admiralty": "B2",
    "signal_type": "event|trend|mixed",
    "dominant_pillar": "Geo|Cyber"
  }}
}}

signal_type must be one of: event, trend, mixed.
Only include topic IDs from the ACTIVE TOPICS list in matched_topics."""

    # Use Sonnet for synthesis — quality-critical step
    result = _call_llm(prompt, model="claude-sonnet-4-6", max_tokens=2048)

    # Validate required keys in each sub-dict
    geo_required = {"summary", "lead_indicators", "dominant_pillar", "matched_topics"}
    cyber_required = {"summary", "threat_vector", "target_assets", "dominant_pillar", "matched_topics"}
    conclusion_required = {"theory_confirmed", "confidence_rationale", "suggested_admiralty", "signal_type", "dominant_pillar"}

    for section, required in [("geo_signals", geo_required), ("cyber_signals", cyber_required), ("conclusion", conclusion_required)]:
        if section not in result:
            raise ValueError(f"synthesize_signals: LLM response missing section: {section}")
        missing = required - result[section].keys()
        if missing:
            raise ValueError(f"synthesize_signals: {section} missing keys: {missing}")

    return result["geo_signals"], result["cyber_signals"], result["conclusion"]


def _load_json(path: str | Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_output_dir(region: str) -> Path:
    p = Path("output/regional") / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_mock_mode(region: str) -> None:
    """Delegate to existing collectors unchanged."""
    for collector in ("geo_collector", "cyber_collector"):
        subprocess.run(
            [sys.executable, f"tools/{collector}.py", region, "--mock"],
            check=True,
            cwd=REPO_ROOT,
        )


def run_live_mode(region: str) -> None:
    """Target-centric collection loop — 3 bounded LLM calls."""
    crq_data = _load_json("data/mock_crq_database.json")
    topics = _load_json("data/osint_topics.json")
    company_profile = _load_json("data/company_profile.json")
    out_dir = get_output_dir(region)

    # --- LLM Call 1: Form working theory ---
    working_theory = form_working_theory(region, crq_data, topics, company_profile)

    # --- Pass 1: Initial geo + cyber collection ---
    pass_1_geo = run_search_pass(region, working_theory["geo_queries"], "geo")
    pass_1_cyber = run_search_pass(region, working_theory["cyber_queries"], "cyber")
    pass_1_results = pass_1_geo + pass_1_cyber

    # --- LLM Call 2: Assess gaps ---
    gap_data = assess_gaps(region, working_theory, pass_1_results)

    # --- Pass 2: Fill gaps (if needed) ---
    pass_2_results: list[dict] = []
    if gap_data.get("run_pass_2") and gap_data.get("follow_up_queries"):
        query_type = gap_data.get("follow_up_query_type", "cyber")
        pass_2_results = run_search_pass(region, gap_data["follow_up_queries"], query_type)

    all_results = pass_1_results + pass_2_results

    # --- LLM Call 3: Synthesize (Sonnet) ---
    geo_signals, cyber_signals, conclusion = synthesize_signals(region, working_theory, all_results)

    # --- Enrich with metadata ---
    collected_at = datetime.now(timezone.utc).isoformat()
    geo_signals.update({"region": region, "collected_at": collected_at})
    cyber_signals.update({"region": region, "collected_at": collected_at})

    # --- Write outputs ---
    _write_json(out_dir / "geo_signals.json", geo_signals)
    _write_json(out_dir / "cyber_signals.json", cyber_signals)

    scratchpad = {
        "region": region,
        "collected_at": collected_at,
        "working_theory": working_theory,
        "collection": {
            "pass_1_result_count": len(pass_1_results),
            "gap_assessment": gap_data.get("gap_assessment", ""),
            "gaps_identified": gap_data.get("gaps_identified", []),
            "pass_2_queries": gap_data.get("follow_up_queries", []),
            "pass_2_result_count": len(pass_2_results),
            "total_result_count": len(all_results),
        },
        "conclusion": conclusion,
    }
    _write_json(out_dir / "research_scratchpad.json", scratchpad)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: research_collector.py <REGION> [--mock]", file=sys.stderr)
        sys.exit(1)

    region = sys.argv[1].upper()
    if region not in VALID_REGIONS:
        print(f"Invalid region: {region}. Valid: {VALID_REGIONS}", file=sys.stderr)
        sys.exit(1)

    mock = "--mock" in sys.argv

    if mock:
        run_mock_mode(region)
    else:
        run_live_mode(region)


if __name__ == "__main__":
    main()
