"""Generate audience-specific cards from a regional brief using Haiku.

Usage:
    uv run python tools/generate_audience_cards.py <REGION> [--mock]

Reads:
    output/regional/{region_lower}/report.md
    output/regional/{region_lower}/data.json

Writes:
    output/regional/{region_lower}/audience_cards.json

Exits 0 on success, 1 on error.
"""

import json
import os
import sys
from pathlib import Path

REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

MOCK_CARDS = {
    "sales": {
        "title": "Sales Talking Points",
        "bullets": [
            "Current threat conditions in this region are elevated but do not affect delivery schedules at this time.",
            "Customers may raise concerns about energy sector disruptions — our contingency sourcing arrangements remain intact.",
            "No immediate impact on contract timelines or pricing structures.",
        ],
    },
    "ops": {
        "title": "Operations Signal",
        "signal": "Elevated threat activity has been identified in this region with potential implications for operational continuity.",
        "action": "Verify backup procedures for key scheduling and logistics systems are current and tested.",
    },
    "executive": {
        "title": "Executive Summary",
        "vacr_exposure": 0,
        "scenario": "Unknown",
        "financial_rank": 0,
        "assessment": "This region carries financial exposure consistent with the identified scenario. Pipeline continues to monitor for escalation.",
    },
}


def load_report(region_lower: str) -> str:
    path = Path(f"output/regional/{region_lower}/report.md")
    if not path.exists():
        print(f"ERROR: report.md not found at {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def load_data(region_lower: str) -> dict:
    path = Path(f"output/regional/{region_lower}/data.json")
    if not path.exists():
        print(f"ERROR: data.json not found at {path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def call_haiku(region: str, report: str, data: dict) -> dict:
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not available", file=sys.stderr)
        sys.exit(1)

    vacr = data.get("vacr_exposure_usd", 0)
    scenario = data.get("primary_scenario", "Unknown")
    financial_rank = data.get("financial_rank", 0)

    prompt = f"""You are a Strategic Geopolitical & Cyber Risk Analyst for AeroGrid Wind Solutions, a global wind turbine manufacturer and service company.

You have just read the regional intelligence brief for {region}. Your task is to produce three short audience-specific cards from this brief.

BRIEF:
{report}

KEY FACTS:
- VaCR exposure: ${vacr:,}
- Primary scenario: {scenario}
- Financial impact rank: #{financial_rank}

Produce a JSON object with exactly this structure. No markdown, no commentary, pure JSON:

{{
  "sales": {{
    "title": "Sales Talking Points",
    "bullets": ["<bullet 1>", "<bullet 2>", "<bullet 3>"]
  }},
  "ops": {{
    "title": "Operations Signal",
    "signal": "<one sentence: what is the specific operational risk to AeroGrid assets in this region>",
    "action": "<one sentence: what should ops teams verify or watch for>"
  }},
  "executive": {{
    "title": "Executive Summary",
    "vacr_exposure": {vacr},
    "scenario": "{scenario}",
    "financial_rank": {financial_rank},
    "assessment": "<2 sentences max: financial exposure and trajectory for a board audience>"
  }}
}}

RULES:
- Zero technical jargon (no CVEs, IPs, hashes, TTPs, MITRE, lateral movement, C2)
- Zero SOC language
- Zero budget or procurement advice
- Sales bullets: plain language, what a sales rep needs to know for customer conversations
- Ops signal: asset-specific, operationally framed (reference specific AeroGrid site types if evident from the brief)
- Executive assessment: lead with the dollar figure, end with trajectory
- All content must be derived from the brief — do not invent facts"""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return json.loads(raw)


def write_cards(region_lower: str, region: str, cards: dict) -> None:
    output = {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "region": region,
        "cards": cards,
    }
    out_dir = Path(f"output/regional/{region_lower}")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "audience_cards.tmp"
    tmp.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_dir / "audience_cards.json")
    print(f"Audience cards written: output/regional/{region_lower}/audience_cards.json")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: generate_audience_cards.py <REGION> [--mock]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args

    if region not in REGIONS:
        print(f"ERROR: Unknown region '{region}'. Valid: {', '.join(sorted(REGIONS))}", file=sys.stderr)
        sys.exit(1)

    region_lower = region.lower()

    if mock:
        data = load_data(region_lower) if Path(f"output/regional/{region_lower}/data.json").exists() else {}
        cards = dict(MOCK_CARDS)
        cards["executive"] = dict(cards["executive"])
        cards["executive"]["vacr_exposure"] = data.get("vacr_exposure_usd", 0)
        cards["executive"]["scenario"] = data.get("primary_scenario", "Unknown")
        cards["executive"]["financial_rank"] = data.get("financial_rank", 0)
        write_cards(region_lower, region, cards)
        return

    report = load_report(region_lower)
    data = load_data(region_lower)

    try:
        cards = call_haiku(region, report, data)
    except json.JSONDecodeError as e:
        print(f"ERROR: Haiku returned invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    write_cards(region_lower, region, cards)


if __name__ == "__main__":
    main()
