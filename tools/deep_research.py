#!/usr/bin/env python3
"""Deep research module — wraps GPT Researcher with Claude + Tavily.

Usage (CLI):
    uv run python tools/deep_research.py APAC geo [--depth=standard]
    uv run python tools/deep_research.py AME cyber [--depth=quick]

Writes:
    output/regional/{region}/geo_signals.json   (overwrites shallow collector)
    output/regional/{region}/cyber_signals.json (overwrites shallow collector)

Requirements:
    gpt-researcher requires Python <=3.12 due to spacy/langchain compatibility.
    Install: uv pip install gpt-researcher "numpy>=2.4" langchain langchain-community
    After install, patch gpt_researcher/prompts.py and vector_store/vector_store.py
    to use langchain_core instead of langchain.docstore.
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Allow importing from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT = Path(__file__).resolve().parent.parent / "output"
VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

# Lazy import — gpt-researcher requires Python <=3.12; tests mock this
try:
    from gpt_researcher import GPTResearcher  # type: ignore
except ImportError:
    GPTResearcher = None  # type: ignore

# ── Depth presets ──────────────────────────────────────────────────────
DEPTH_CONFIG = {
    "quick":    {"max_subtopics": 2, "report_type": "summary_report"},
    "standard": {"max_subtopics": 3, "report_type": "research_report"},
    "deep":     {"max_subtopics": 5, "report_type": "research_report"},
}

# ── Query builders ─────────────────────────────────────────────────────
GEO_QUERY_TEMPLATE = (
    "Geopolitical risk analysis {region} wind energy manufacturing and service operations 2026. "
    "Focus: state actor intent, trade policy, regulatory shifts, supply chain exposure, "
    "infrastructure security threats relevant to wind turbine production and offshore wind farm operations."
)

CYBER_QUERY_TEMPLATE = (
    "Cyber threat intelligence {region} operational technology OT ICS wind energy sector 2026. "
    "Focus: active campaigns targeting energy infrastructure, manufacturing IP theft, "
    "ransomware groups, supply chain compromise, SCADA vulnerabilities in wind energy."
)


def build_query(region: str, signal_type: str) -> str:
    """Build research query for a region + signal type."""
    if signal_type == "geo":
        return GEO_QUERY_TEMPLATE.format(region=region)
    elif signal_type == "cyber":
        return CYBER_QUERY_TEMPLATE.format(region=region)
    raise ValueError(f"Unknown signal_type: {signal_type}")


# ── Extraction prompts ─────────────────────────────────────────────────
GEO_EXTRACTION_PROMPT = """You are extracting structured intelligence signals from a research report.

Region: {region}
Report:
{report}

Extract and return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sentence geopolitical threat summary for {region} wind energy operations",
  "lead_indicators": ["specific signal 1", "specific signal 2", "specific signal 3"],
  "dominant_pillar": "Geopolitical",
  "matched_topics": []
}}

Rules:
- summary must describe business impact on wind energy manufacturing or service delivery
- lead_indicators must be specific, factual signals from the report (not generic statements)
- dominant_pillar is always "Geopolitical" for geo signals
- matched_topics is always empty array (pipeline populates it separately)
- Return ONLY the JSON object, no markdown, no explanation
"""

CYBER_EXTRACTION_PROMPT = """You are extracting structured cyber threat signals from a research report.

Region: {region}
Report:
{report}

Extract and return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sentence cyber threat summary for {region} wind energy OT/ICS",
  "threat_vector": "primary attack vector or method",
  "target_assets": ["asset 1", "asset 2", "asset 3"],
  "matched_topics": []
}}

Rules:
- summary must describe the threat in business terms, not technical jargon
- threat_vector is the primary method: supply chain, phishing, insider, etc.
- target_assets are business assets at risk: OT networks, IP, telemetry systems, etc.
- matched_topics is always empty array
- Return ONLY the JSON object, no markdown, no explanation
"""

YOUTUBE_EXTRACTION_PROMPT = """You are extracting structured intelligence signals from YouTube video transcripts.

Region: {region}
Transcript content:
{report}

Extract and return ONLY valid JSON matching this exact schema:
{{
  "summary": "2-3 sentence synthesis of what analysts are saying about {region} wind energy risk",
  "lead_indicators": ["specific claim 1", "specific claim 2", "specific claim 3"],
  "dominant_pillar": "Geopolitical|Cyber",
  "matched_topics": []
}}

Rules:
- summary must synthesise analyst opinion, not just describe the video topic
- lead_indicators must be specific, attributable claims from the transcript
- dominant_pillar: "Geopolitical" if primarily about politics/state actors/trade; "Cyber" if primarily about attacks/threats
- matched_topics is always empty array (pipeline populates it separately)
- Write for a business executive, not a security engineer
- Return ONLY the JSON object, no markdown, no explanation
"""

EXTRACTION_PROMPTS = {"geo": GEO_EXTRACTION_PROMPT, "cyber": CYBER_EXTRACTION_PROMPT, "youtube": YOUTUBE_EXTRACTION_PROMPT}


# ── Validation ─────────────────────────────────────────────────────────
def _validate_geo_signals(data: dict) -> dict:
    required = {"summary", "lead_indicators", "dominant_pillar", "matched_topics"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing keys in geo signals: {missing}")
    return data


def _validate_cyber_signals(data: dict) -> dict:
    required = {"summary", "threat_vector", "target_assets", "matched_topics"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing keys in cyber signals: {missing}")
    return data


def _validate_youtube_signals(data: dict) -> dict:
    required = {"summary", "lead_indicators", "dominant_pillar", "matched_topics"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Missing keys in youtube signals: {missing}")
    return data


VALIDATORS = {"geo": _validate_geo_signals, "cyber": _validate_cyber_signals, "youtube": _validate_youtube_signals}


# ── Haiku extraction ───────────────────────────────────────────────────
async def _extract_with_haiku(
    report: str,
    signal_type: str,
    region: str,
) -> dict:
    """Call Claude Haiku to extract structured signals from markdown report."""
    import anthropic

    client = anthropic.AsyncAnthropic()
    prompt = EXTRACTION_PROMPTS[signal_type].format(
        region=region,
        report=report[:8000],  # cap tokens
    )
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    return VALIDATORS[signal_type](data)


# ── Core async function ────────────────────────────────────────────────
async def run_deep_research(
    region: str,
    signal_type: str,
    depth: str = "standard",
    on_progress=None,
) -> dict:
    """
    Run deep research for a region + signal type.
    Writes output file and returns signals dict.
    """
    if GPTResearcher is None:
        raise ImportError(
            "gpt-researcher is not installed or requires Python <=3.12. "
            "Install: uv pip install gpt-researcher 'numpy>=2.4'"
        )

    if region not in VALID_REGIONS:
        raise ValueError(f"Unknown region: {region}")
    if signal_type not in ("geo", "cyber"):
        raise ValueError(f"Unknown signal_type: {signal_type}")
    if depth not in DEPTH_CONFIG:
        raise ValueError(f"Unknown depth: {depth}. Use quick|standard|deep")

    cfg = DEPTH_CONFIG[depth]
    query = build_query(region, signal_type)

    # Progress helper
    async def _progress(msg: str):
        if on_progress:
            await on_progress(msg)

    await _progress(f"generating sub-queries ({depth} mode, {cfg['max_subtopics']} subtopics)...")

    researcher = GPTResearcher(
        query=query,
        report_type=cfg["report_type"],
        report_source="web",
        max_subtopics=cfg["max_subtopics"],
        verbose=False,
    )

    # Wire GPT Researcher's own progress to our callback
    async def gpt_progress(msg):
        await _progress(f"searching — {str(msg)[:80]}")

    await researcher.conduct_research(on_progress=gpt_progress)
    await _progress("synthesising report...")

    report = await researcher.write_report()
    await _progress("extracting signals...")

    signals = await _extract_with_haiku(report, signal_type, region)
    await _progress("done ✓")

    # Write output file
    out_dir = OUTPUT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{signal_type}_signals.json"
    out_path.write_text(json.dumps(signals, indent=2, ensure_ascii=False), encoding="utf-8")

    return signals


# ── CLI entry point ────────────────────────────────────────────────────
def cli_main(args=None):
    if args is None:
        args = sys.argv[1:]

    if len(args) < 2:
        print("Usage: deep_research.py REGION geo|cyber [--depth=standard]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    signal_type = args[1].lower()
    depth = "standard"
    for a in args[2:]:
        if a.startswith("--depth="):
            depth = a.split("=", 1)[1]

    async def _run():
        print(f"[deep_research] {region} {signal_type} depth={depth}", flush=True)

        async def progress(msg):
            print(f"[deep_research] {region} {signal_type} — {msg}", flush=True)

        result = await run_deep_research(region, signal_type, depth=depth, on_progress=progress)
        print(json.dumps(result, indent=2))
        return result

    asyncio.run(_run())


if __name__ == "__main__":
    cli_main()
