#!/usr/bin/env python3
"""VaCR Benchmark Researcher — researches industry sources per scenario and reasons against current VaCR.

Usage:
    uv run python tools/vacr_researcher.py <incident_type> <current_vacr_usd> [--sector energy|manufacturing]

Writes: output/pipeline/vacr_research.json (appends/updates this scenario's entry)
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_FILE = REPO_ROOT / "output" / "pipeline" / "vacr_research.json"

SONNET_MODEL = "claude-sonnet-4-6"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dimension", "note", "raw_quote", "source_name", "source_url"],
                "properties": {
                    "dimension":              {"type": "string", "enum": ["financial", "probability"]},
                    "cost_low_usd":           {"type": ["number", "null"]},
                    "cost_median_usd":        {"type": ["number", "null"]},
                    "cost_high_usd":          {"type": ["number", "null"]},
                    "probability_low_pct":    {"type": ["number", "null"]},
                    "probability_median_pct": {"type": ["number", "null"]},
                    "probability_high_pct":   {"type": ["number", "null"]},
                    "note":        {"type": "string"},
                    "raw_quote":   {"type": "string"},
                    "source_name": {"type": "string"},
                    "source_url":  {"type": "string"},
                },
            },
        }
    },
    "required": ["figures"],
}

_RESEARCH_TIMEOUT_S = 180
_RESEARCH_POLL_INTERVAL_S = 5

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


def _research_tavily(incident_type: str, sector: str) -> list[dict]:
    """Submit a Tavily Research job and poll until complete. Returns figures list."""
    import os
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    query = (
        f"{incident_type} financial cost incident rate probability "
        f"{sector} sector renewable energy operator USD 2024 2025"
    )
    task = client.research(input=query, model="mini", output_schema=OUTPUT_SCHEMA)
    request_id = task["request_id"]
    deadline = time.monotonic() + _RESEARCH_TIMEOUT_S
    while time.monotonic() < deadline:
        result = client.get_research(request_id)
        if result.get("status") == "completed":
            structured = result.get("structured_output")
            if not structured or "figures" not in structured:
                raise ValueError(
                    f"Tavily research completed but returned no structured_output "
                    f"for {incident_type!r} (request_id={request_id})"
                )
            return structured["figures"]
        time.sleep(_RESEARCH_POLL_INTERVAL_S)
    raise TimeoutError(
        f"Tavily research timed out after {_RESEARCH_TIMEOUT_S}s (request_id={request_id})"
    )


def _reason_against_vacr(incident_type: str, current_vacr_usd: int, sector: str, all_figures: list[dict]) -> dict:
    """Run Sonnet to reason whether findings support/challenge the VaCR."""
    if not all_figures:
        findings_text = "No benchmark figures found."
    else:
        lines = []
        for f in all_figures[:20]:
            src = f.get("source_name", "Unknown source")
            note = f.get("note", "")
            quote = f.get("raw_quote", "")
            median = f.get("cost_median_usd")
            dimension = f.get("dimension", "financial")
            if median:
                lines.append(f"- {src}: {dimension} | median=${median:,} | {note} | \"{quote}\"")
            else:
                lines.append(f"- {src}: {dimension} | {note} | \"{quote}\"")
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

    figures = _research_tavily(incident_type, sector)
    reasoning = _reason_against_vacr(incident_type, current_vacr_usd, sector, figures)

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
