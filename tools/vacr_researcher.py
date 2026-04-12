#!/usr/bin/env python3
"""VaCR Benchmark Researcher — searches industry sources per scenario and reasons against current VaCR.

Usage:
    uv run python tools/vacr_researcher.py <incident_type> <current_vacr_usd> [--sector energy|manufacturing]

Writes: output/pipeline/vacr_research.json (appends/updates this scenario's entry)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_FILE = REPO_ROOT / "output" / "pipeline" / "vacr_research.json"

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

EXTRACTION_PROMPT = """\
You are extracting financial impact data from a cybersecurity industry report.

Extract all dollar-denominated financial impact figures for cyber incidents. For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to (e.g. "manufacturing", "energy", "all")
- cost_low_usd: lower bound in USD as integer (null if not stated)
- cost_median_usd: median or average in USD as integer (null if not stated)
- cost_high_usd: upper bound in USD as integer (null if not stated)
- note: brief description of what this figure represents
- raw_quote: the exact text excerpt this came from (max 200 chars)

Return ONLY a JSON array. If no financial figures found, return [].

Text to analyze:
{raw_text}"""

REASONING_PROMPT = """\
You are a cyber risk quantification analyst reviewing benchmark data against a company's VaCR (Value at Cyber Risk) estimate.

Scenario: {incident_type}
Sector: {sector}
Current VaCR: ${current_vacr_usd:,}

Benchmark findings from industry sources:
{findings_text}

For each finding, assess whether it supports (↑ suggests higher), challenges (↓ suggests lower), or is inconclusive (→) relative to the current VaCR.
Then write a one-sentence agent_summary across all findings.

Return a JSON object:
{{
  "findings": [
    {{
      "source": "<source name>",
      "quote": "<exact quote, max 150 chars>",
      "figure_usd": <median figure as integer, or null>,
      "direction": "↑ or ↓ or → or ?",
      "assessment": "<one sentence>"
    }}
  ],
  "overall_direction": "↑ or ↓ or → or ?",
  "agent_summary": "<one sentence summarising all evidence>"
}}

If no findings provided, return {{"findings": [], "overall_direction": "?", "agent_summary": "No benchmark data found for this scenario."}}
"""


def _search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search using Tavily if key available, else DuckDuckGo."""
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
            return [{"title": r.get("title", ""), "content": r.get("content", ""), "url": r.get("url", ""), "score": r.get("score", 0.0)} for r in results]
        except Exception as e:
            print(f"[vacr-researcher] Tavily failed: {e}", file=sys.stderr)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "content": r.get("body", ""), "url": r.get("href", "")} for r in results]
    except Exception as e:
        print(f"[vacr-researcher] DDG failed: {e}", file=sys.stderr)
        return []


def _extract_figures(text: str, source_name: str) -> list[dict]:
    """Run Haiku over text to extract financial figures."""
    if not text.strip():
        return []
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(raw_text=text[:12_000])}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        figures = json.loads(content)
        for f in figures:
            f["_source_name"] = source_name
            f["_source_url"] = ""
        return figures
    except Exception as e:
        print(f"[vacr-researcher] Haiku extraction failed for {source_name}: {e}", file=sys.stderr)
        return []


def _reason_against_vacr(incident_type: str, current_vacr_usd: int, sector: str, all_figures: list[dict]) -> dict:
    """Run Sonnet to reason whether findings support/challenge the VaCR."""
    if not all_figures:
        findings_text = "No benchmark figures found."
    else:
        lines = []
        for f in all_figures[:20]:  # cap at 20 figures
            src = f.get("_source_name", "Unknown source")
            note = f.get("note", "")
            quote = f.get("raw_quote", "")
            median = f.get("cost_median_usd")
            tag = f.get("scenario_tag", "")
            lines.append(f"- {src}: {tag} | median=${median:,} | {note} | \"{quote}\"" if median else f"- {src}: {tag} | {note} | \"{quote}\"")
        findings_text = "\n".join(lines)

    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": REASONING_PROMPT.format(
                incident_type=incident_type,
                sector=sector,
                current_vacr_usd=current_vacr_usd,
                findings_text=findings_text,
            )}],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        print(f"[vacr-researcher] Sonnet reasoning failed: {e}", file=sys.stderr)
        return {
            "findings": [],
            "overall_direction": "?",
            "agent_summary": f"Reasoning failed: {e}",
        }


def research_scenario(incident_type: str, current_vacr_usd: int, sector: str = "energy") -> dict:
    """Full pipeline for one scenario. Returns result dict."""
    print(f"[vacr-researcher] Researching: {incident_type} (VaCR ${current_vacr_usd:,})", file=sys.stderr)

    # Build queries targeting known benchmark sources
    queries = [
        f'"{incident_type}" cost {sector} 2024 2025 site:ibm.com OR site:verizon.com OR site:mandiant.com',
        f'"{incident_type}" financial impact manufacturing energy 2024 benchmark',
        f'"{incident_type}" average cost USD million 2024 2025 industry report',
    ]

    from tools.firecrawl_scraper import scrape_urls as _firecrawl_scrape

    all_figures = []
    for query in queries:
        print(f"[vacr-researcher]   Searching: {query[:80]}...", file=sys.stderr)
        results = _search_web(query, max_results=4)

        # Scrape top 3 by Tavily score if scores are present (Tavily path only)
        if results and any(r.get("score") for r in results):
            top3 = sorted(results, key=lambda r: r.get("score", 0.0), reverse=True)[:3]
            snippet_lookup = {r["url"]: r.get("content", "") for r in top3}
            score_lookup = {r["url"]: r.get("score", 0.0) for r in top3}
            scraped = _firecrawl_scrape(
                [r["url"] for r in top3],
                snippet_lookup,
                score_lookup,
            )
            for r, s in zip(top3, scraped):
                r["content"] = s["content"]

        for r in results:
            content = r.get("content", "")
            source_name = r.get("title") or r.get("url", "Unknown")
            figures = _extract_figures(content, source_name)
            # Only keep figures matching this scenario type
            relevant = [f for f in figures if incident_type.lower() in f.get("scenario_tag", "").lower()
                        or f.get("scenario_tag", "") == incident_type]
            all_figures.extend(relevant)

    reasoning = _reason_against_vacr(incident_type, current_vacr_usd, sector, all_figures)

    result = {
        "incident_type": incident_type,
        "current_vacr_usd": current_vacr_usd,
        "sector": sector,
        "direction": reasoning.get("overall_direction", "?"),
        "findings": reasoning.get("findings", []),
        "agent_summary": reasoning.get("agent_summary", ""),
        "researched_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def _update_output(result: dict) -> None:
    """Append/replace this scenario's result in output/pipeline/vacr_research.json."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {"generated_at": None, "results": []}

    # Replace existing entry for this incident_type or append
    results = [r for r in existing.get("results", []) if r.get("incident_type") != result["incident_type"]]
    results.append(result)
    existing["results"] = results
    existing["generated_at"] = datetime.now(timezone.utc).isoformat()
    OUTPUT_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: vacr_researcher.py <incident_type> <current_vacr_usd> [--sector energy|manufacturing]", file=sys.stderr)
        sys.exit(1)
    incident_type = sys.argv[1]
    current_vacr_usd = int(sys.argv[2])
    sector = "energy"
    if "--sector" in sys.argv:
        idx = sys.argv.index("--sector")
        sector = sys.argv[idx + 1]
    result = research_scenario(incident_type, current_vacr_usd, sector)
    _update_output(result)
    print(json.dumps(result, indent=2))
