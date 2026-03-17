#!/usr/bin/env python3
"""Post-run config suggestions — reads signal files, suggests new topics + channels.

Usage:
    uv run python tools/suggest_config.py

Writes: output/config_suggestions.json
Called automatically at end of pipeline run when signal files are present.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT = Path(__file__).resolve().parent.parent / "output"
REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]

SUGGESTION_PROMPT = """You are a geopolitical and cyber threat intelligence advisor for AeroGrid Wind Solutions.

Existing OSINT topics being tracked:
{existing_topics}

Current pipeline signals:
{signals_summary}

Based on the signals above, suggest:
1. Three new OSINT topics that would strengthen coverage
2. Three YouTube channels that would provide relevant intelligence

Return ONLY valid JSON:
{{
  "topics": [
    {{
      "id": "kebab-case-id",
      "type": "event|trend",
      "keywords": ["kw1", "kw2"],
      "regions": ["REGION"],
      "active": true,
      "rationale": "Why this topic matters to AeroGrid"
    }}
  ],
  "sources": [
    {{
      "channel_id": "UCxxx or @handle",
      "name": "Channel Name",
      "region_focus": ["REGION"],
      "topics": [],
      "rationale": "Why this channel is credible and relevant"
    }}
  ],
  "generated_at": "{timestamp}"
}}"""


async def suggest():
    import anthropic

    # Load existing topics
    topics_path = Path("data/osint_topics.json")
    existing_topics = json.loads(topics_path.read_text(encoding="utf-8")) if topics_path.exists() else []

    # Collect signal summaries from all regions
    signals = []
    for region in REGIONS:
        for sig_type in ("geo", "cyber"):
            path = OUTPUT / "regional" / region.lower() / f"{sig_type}_signals.json"
            if path.exists():
                try:
                    d = json.loads(path.read_text(encoding="utf-8"))
                    signals.append(f"{region} {sig_type}: {d.get('summary', '')[:200]}")
                except Exception:
                    pass

    if not signals:
        result = {"topics": [], "sources": [], "generated_at": datetime.now(timezone.utc).isoformat()}
        out_path = OUTPUT / "config_suggestions.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return

    prompt = SUGGESTION_PROMPT.format(
        existing_topics=json.dumps([t.get("id") for t in existing_topics], indent=2),
        signals_summary="\n".join(signals),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

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

    result = json.loads(raw)
    out_path = OUTPUT / "config_suggestions.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(suggest())
