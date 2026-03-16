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


def run_mock_mode(region: str) -> None:
    """Delegate to existing collectors unchanged."""
    for collector in ("geo_collector", "cyber_collector"):
        subprocess.run(
            [sys.executable, f"tools/{collector}.py", region, "--mock"],
            check=True,
            cwd=REPO_ROOT,
        )


def run_live_mode(region: str) -> None:
    """Target-centric collection loop — 3 LLM calls."""
    raise NotImplementedError("Live mode not yet implemented")


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
