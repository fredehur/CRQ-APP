#!/usr/bin/env python3
"""Discovery agent — find new OSINT topics and YouTube channels.

Usage:
    uv run python tools/discover.py topics "OT cyber attacks energy sector"
    uv run python tools/discover.py sources "geopolitical risk wind energy APAC"

Output: JSON array of suggested topics or sources (stdout).
Used by: /api/discover/topics and /api/discover/sources endpoints.

Requirements:
    gpt-researcher requires Python <=3.12.
    Fallback: if gpt-researcher is unavailable, uses Claude Haiku directly with Tavily search.
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research import DEPTH_CONFIG

TOPIC_QUERY_TEMPLATE = (
    "Research: {query}. "
    "Focus on events, trends, or threat actors relevant to wind energy manufacturing "
    "and service delivery. Find 3-5 specific trackable topics."
)

SOURCE_QUERY_TEMPLATE = (
    "Find credible YouTube channels covering: {query}. "
    "Focus on geopolitical analysts, energy sector experts, cybersecurity researchers. "
    "Channels must be active in 2025-2026."
)

TOPIC_EXTRACTION_PROMPT = """Extract suggested OSINT tracking topics from this research.

Query: {query}
Report: {report}

Return ONLY a JSON array of 3-5 topic suggestions:
[
  {{
    "id": "kebab-case-id",
    "type": "event|trend",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "regions": ["APAC"],
    "active": true,
    "rationale": "One sentence explaining relevance to AeroGrid wind energy operations"
  }}
]

Return ONLY the JSON array, no markdown."""

SOURCE_EXTRACTION_PROMPT = """Extract suggested YouTube channel sources from this research.

Query: {query}
Report: {report}

Return ONLY a JSON array of 3-5 channel suggestions:
[
  {{
    "channel_id": "UCxxxxxxxxxx or @handle",
    "name": "Channel Name",
    "region_focus": ["APAC"],
    "topics": [],
    "rationale": "One sentence explaining credibility and relevance"
  }}
]

Return ONLY the JSON array, no markdown."""


async def _discover_with_gpt_researcher(discover_type: str, query: str, depth: str) -> list:
    """Run discovery via GPT Researcher (requires Python <=3.12)."""
    from gpt_researcher import GPTResearcher  # type: ignore
    import anthropic

    cfg = DEPTH_CONFIG[depth]
    full_query = TOPIC_QUERY_TEMPLATE.format(query=query) if discover_type == "topics" \
        else SOURCE_QUERY_TEMPLATE.format(query=query)

    researcher = GPTResearcher(
        query=full_query,
        report_type=cfg["report_type"],
        report_source="web",
        max_subtopics=cfg["max_subtopics"],
        verbose=False,
    )
    await researcher.conduct_research()
    report = await researcher.write_report()

    prompt = (TOPIC_EXTRACTION_PROMPT if discover_type == "topics" else SOURCE_EXTRACTION_PROMPT)
    prompt = prompt.format(query=query, report=report[:6000])

    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


async def _discover_with_haiku(discover_type: str, query: str) -> list:
    """Fallback: direct Claude Haiku call (no GPT Researcher required)."""
    import anthropic

    client = anthropic.AsyncAnthropic()

    if discover_type == "topics":
        sys_prompt = (
            "You are an OSINT topic advisor for AeroGrid Wind Solutions, a global wind turbine "
            "manufacturer and service company. You recommend intelligence tracking topics based "
            "on geopolitical and cyber threat context relevant to wind energy operations."
        )
        user_prompt = (
            f"Suggest 3-5 OSINT tracking topics for: {query}\n\n"
            "Return ONLY a JSON array:\n"
            "[\n"
            '  {{\n'
            '    "id": "kebab-case-id",\n'
            '    "type": "event|trend",\n'
            '    "keywords": ["keyword1", "keyword2", "keyword3"],\n'
            '    "regions": ["APAC"],\n'
            '    "active": true,\n'
            '    "rationale": "Why this matters to AeroGrid"\n'
            '  }}\n'
            "]"
        )
    else:
        sys_prompt = (
            "You are an intelligence source advisor. You recommend credible YouTube channels "
            "that cover geopolitical risk, energy sector news, and cybersecurity relevant to "
            "a global wind energy company."
        )
        user_prompt = (
            f"Suggest 3-5 YouTube channels for: {query}\n\n"
            "Return ONLY a JSON array:\n"
            "[\n"
            '  {{\n'
            '    "channel_id": "UCxxxxxxxxxx or @handle",\n'
            '    "name": "Channel Name",\n'
            '    "region_focus": ["APAC"],\n'
            '    "topics": [],\n'
            '    "rationale": "Why this channel is credible and relevant"\n'
            '  }}\n'
            "]"
        )

    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=sys_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


async def discover(discover_type: str, query: str, depth: str = "quick") -> list:
    """Run discovery and return structured suggestions.

    Tries GPT Researcher first; falls back to direct Haiku call if unavailable.
    """
    try:
        from gpt_researcher import GPTResearcher  # noqa: F401
        return await _discover_with_gpt_researcher(discover_type, query, depth)
    except ImportError:
        # gpt-researcher not available on Python 3.13+ — use Haiku fallback
        return await _discover_with_haiku(discover_type, query)


def main():
    if len(sys.argv) < 3:
        print("Usage: discover.py topics|sources <query> [--depth=quick]", file=sys.stderr)
        sys.exit(1)

    discover_type = sys.argv[1]
    query = sys.argv[2]
    depth = "quick"
    for a in sys.argv[3:]:
        if a.startswith("--depth="):
            depth = a.split("=", 1)[1]

    results = asyncio.run(discover(discover_type, query, depth=depth))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
