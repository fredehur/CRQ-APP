#!/usr/bin/env python3
"""Unified OSINT collector — replaces research_collector.py with single-file output.

Usage:
    uv run python tools/osint_collector.py <REGION> [--mock] [--window 7d]

Mock mode: reads {region}_osint.json fixture directly.
Live mode: 3-pass target-centric loop using Anthropic API.

Writes:
    output/regional/{region}/osint_signals.json   — unified geo+cyber indicators
    output/regional/{region}/osint_scratchpad.json — audit trail
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


def _generate_signal_id(region: str, pillar: str, sequence: int) -> str:
    return f"osint:tavily:{region.lower()}-{pillar.lower()}-{sequence:03d}"


def _enrich_indicators_with_ids(indicators: list, region: str, pillar: str, sources: list) -> list:
    """Convert plain string indicators to dicts with signal_id, source_url, and pillar."""
    enriched = []
    for i, indicator in enumerate(indicators):
        if isinstance(indicator, dict):
            # Already enriched (idempotent) — ensure pillar is set
            indicator.setdefault("pillar", pillar)
            enriched.append(indicator)
            continue
        source_url = sources[0]["url"] if sources else ""
        source_name = sources[0]["name"] if sources else ""
        enriched.append({
            "text": indicator,
            "signal_id": _generate_signal_id(region, pillar, i + 1),
            "source_url": source_url,
            "source_name": source_name,
            "pillar": pillar,
        })
    return enriched


sys.path.insert(0, str(Path(__file__).parent.parent))
# Canonical implementation lives in collection_gate.py
from tools.collection_gate import check_collection_quality  # noqa: F401 — re-exported for back-compat

_JUNK_DOMAINS = {
    "raw.githubusercontent.com",
    "git.selfmade.ninja",
    "codalab.org",
    "downloads.cs.stanford.edu",
    "facebook.com",
}
_JUNK_SUBSTRINGS = {"/vocab", "wordlist", "SecLists", "sitemap", "Vital_articles", "vocab_wiki"}


def _load_blocked_urls() -> set:
    """Load dynamically blocked URLs from the analyst-managed flat file."""
    blocked_file = Path(__file__).resolve().parent.parent / "data" / "blocked_urls.txt"
    if not blocked_file.exists():
        return set()
    try:
        return {line.strip() for line in blocked_file.read_text(encoding="utf-8").splitlines() if line.strip()}
    except Exception:
        return set()


_BLOCKED_URLS: set = _load_blocked_urls()


def _is_junk_url(url: str) -> bool:
    """Return True if the URL is a known low-quality or irrelevant source."""
    if url in _BLOCKED_URLS:
        return True
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
    except Exception:
        return False
    if domain in _JUNK_DOMAINS:
        return True
    for sub in _JUNK_SUBSTRINGS:
        if sub in url:
            return True
    if url.lower().endswith(".xml"):
        return True
    return False


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
    required = {"hypothesis", "geo_queries", "cyber_queries"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"form_working_theory: LLM response missing required keys: {missing}")
    if len(result["geo_queries"]) < 2 or len(result["cyber_queries"]) < 2:
        raise ValueError(
            f"form_working_theory: LLM returned too few queries "
            f"(geo={len(result['geo_queries'])}, cyber={len(result['cyber_queries'])}). Minimum 2 each."
        )
    return {
        "scenario_name": scenario_name,
        "vacr_usd": vacr,
        "hypothesis": result["hypothesis"],
        "active_topics": active_topics,
        "geo_queries": result["geo_queries"],
        "cyber_queries": result["cyber_queries"],
    }


def run_search_pass(region: str, queries: list[str], query_type: str, window: str | None = None) -> list[dict]:
    """Run queries via osint_search.py with the given type. Returns deduplicated results.

    Args:
        query_type: "geo" or "cyber" — passed as --type flag to osint_search.py
        window: optional time window string (e.g. "7d") forwarded to osint_search.py
    """
    seen_urls: set[str] = set()
    results: list[dict] = []

    for query in queries:
        cmd = [sys.executable, "tools/osint_search.py", region, query, "--type", query_type]
        if window:
            cmd += ["--window", window]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=REPO_ROOT)
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
    region: str, working_theory: dict, results: list[dict], source_note: str = ""
) -> tuple[dict, dict, dict]:
    """LLM Call 3 (Sonnet): Synthesize all results into geo + cyber signal schemas.

    Returns: (geo_signals, cyber_signals, conclusion)
    """
    snippets_text = "\n".join(
        f"- [{r.get('title', '')}] ({r.get('url', '')}) published:{r.get('published_date', '') or 'unknown'} {r.get('summary', '')}"
        for r in results[:20]
    )
    topic_ids = [t["id"] for t in working_theory.get("active_topics", [])]

    prompt = f"""You are synthesizing OSINT collection into structured intelligence signals.

REGION: {region}
WORKING THEORY: {working_theory['hypothesis']}
SCENARIO: {working_theory['scenario_name']} (${working_theory['vacr_usd']:,})
ACTIVE TOPICS: {json.dumps(topic_ids)}

{f"SOURCE NOTE: {source_note}{chr(10)}{chr(10)}" if source_note else ""}COLLECTED EVIDENCE ({len(results)} results):
{snippets_text}

Synthesize this into structured intelligence. Separate the geopolitical context (WHY) from the cyber vector (HOW).

Return ONLY valid JSON (no markdown fences):
{{
  "geo_signals": {{
    "summary": "2-3 sentence geopolitical context",
    "lead_indicators": ["indicator 1", "indicator 2", "indicator 3"],
    "dominant_pillar": "Geopolitical",
    "matched_topics": ["topic-id-if-matched"],
    "sources": [
      {{"name": "<publication or organisation name derived from article title/domain>", "url": "<exact URL from the collected results>", "published_date": "<date from the published: field above, or null if unknown>"}}
    ]
  }},
  "cyber_signals": {{
    "summary": "2-3 sentence cyber threat summary",
    "lead_indicators": ["named threat actor or group 1", "specific confirmed incident (target, method, outcome) 2", "documented attack vector or campaign 3"],
    "dominant_pillar": "Cyber",
    "matched_topics": ["topic-id-if-matched"],
    "sources": [
      {{"name": "<publication or organisation name derived from article title/domain>", "url": "<exact URL from the collected results>", "published_date": "<date from the published: field above, or null if unknown>"}}
    ]
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
Only include topic IDs from the ACTIVE TOPICS list in matched_topics.
cyber_signals.lead_indicators must contain discrete, attributable items — each must be one of:
  a named threat actor or group (e.g. "APT41 targeting OT networks in {region}"),
  a specific confirmed incident with named target, method, and outcome, or
  a documented attack vector or active campaign observed in the evidence.
Do not use generic statements. If named actors or incidents are absent from the evidence, note that explicitly as an indicator.
For sources in both geo_signals and cyber_signals:
  - Include only sources whose URL appears in the COLLECTED EVIDENCE list above.
  - Derive name from the article title and domain — e.g. reuters.com → "Reuters", unit42.paloaltonetworks.com → "Unit 42 (Palo Alto)", cisa.gov → "CISA", asd.gov.au → "Australian Signals Directorate".
  - Include only sources that directly informed at least one lead_indicator — not every URL in the pool.
  - Maximum 10 sources per signal type.
  - No invented names — name must be derivable from the actual URL domain or article title."""

    # Use Sonnet for synthesis — quality-critical step.
    # 8192 tokens accommodates worst-case output: 2 pillars × (summary + 3 indicators
    # + up to 10 sources with URLs) + conclusion. 2048 truncated mid-string on high-signal regions.
    result = _call_llm(prompt, model="claude-sonnet-4-6", max_tokens=8192)

    # Validate required keys in each sub-dict
    geo_required = {"summary", "lead_indicators", "dominant_pillar", "matched_topics"}
    cyber_required = {"summary", "lead_indicators", "dominant_pillar", "matched_topics"}
    conclusion_required = {"theory_confirmed", "confidence_rationale", "suggested_admiralty", "signal_type", "dominant_pillar"}

    for section, required in [("geo_signals", geo_required), ("cyber_signals", cyber_required), ("conclusion", conclusion_required)]:
        if section not in result:
            raise ValueError(f"synthesize_signals: LLM response missing section: {section}")
        missing = required - result[section].keys()
        if missing:
            raise ValueError(f"synthesize_signals: {section} missing keys: {missing}")

    geo_src = len(result["geo_signals"].get("sources", []))
    cyber_src = len(result["cyber_signals"].get("sources", []))
    print(f"[synthesize_signals] {region}: {geo_src} geo sources, {cyber_src} cyber sources extracted")
    return result["geo_signals"], result["cyber_signals"], result["conclusion"]


def _load_json(path: str | Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_output_dir(region: str) -> Path:
    p = REPO_ROOT / "output" / "regional" / region.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_mock_mode(region: str, window: str | None = None) -> None:
    """Read unified osint fixture directly — no subprocess delegation."""
    fixture_path = REPO_ROOT / "data" / "mock_osint_fixtures" / f"{region.lower()}_osint.json"
    out_dir = get_output_dir(region)

    if fixture_path.exists():
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        _write_json(out_dir / "osint_signals.json", data)
        print(f"[osint_collector] mock: wrote {out_dir / 'osint_signals.json'} from fixture")
    else:
        print(f"[osint_collector] ERROR: no fixture at {fixture_path}", file=sys.stderr)
        sys.exit(1)


def run_live_mode(region: str, window: str | None = None) -> None:
    """Target-centric collection loop — 3 bounded LLM calls. Writes unified osint_signals.json."""
    crq_data = _load_json(REPO_ROOT / "data/mock_crq_database.json")
    topics = _load_json(REPO_ROOT / "data/osint_topics.json")
    company_profile = _load_json(REPO_ROOT / "data/company_profile.json")
    out_dir = get_output_dir(region)

    # --- LLM Call 1: Form working theory ---
    working_theory = form_working_theory(region, crq_data, topics, company_profile)

    # --- Pass 1: Initial geo + cyber collection ---
    pass_1_geo = run_search_pass(region, working_theory["geo_queries"], "geo", window)
    pass_1_cyber = run_search_pass(region, working_theory["cyber_queries"], "cyber", window)
    pass_1_results = pass_1_geo + pass_1_cyber

    # --- LLM Call 2: Assess gaps ---
    gap_data = assess_gaps(region, working_theory, pass_1_results)

    # --- Pass 2: Fill gaps (if needed) ---
    pass_2_results: list[dict] = []
    if gap_data.get("run_pass_2") and gap_data.get("follow_up_queries"):
        query_type = gap_data.get("follow_up_query_type", "cyber")
        pass_2_results = run_search_pass(region, gap_data["follow_up_queries"], query_type, window)

    all_results = pass_1_results + pass_2_results

    # --- Firecrawl deep extraction ---
    from tools.firecrawl_scraper import scrape_urls as _firecrawl_scrape

    # Build URL pool: junk-filtered, deduplicated, sorted by Tavily score
    _score_lookup: dict[str, float] = {r["url"]: r.get("score", 0.0) for r in all_results if r.get("url")}
    _seen_fc: set[str] = set()
    _candidate_urls: list[str] = []
    for r in all_results:
        u = r.get("url", "")
        if u and u not in _seen_fc and not _is_junk_url(u):
            _seen_fc.add(u)
            _candidate_urls.append(u)

    top5_urls = sorted(_candidate_urls, key=lambda u: _score_lookup.get(u, 0.0), reverse=True)[:5]
    _snippet_lookup: dict[str, str] = {r["url"]: r.get("summary", "") for r in all_results if r.get("url")}

    scraped_items = _firecrawl_scrape(top5_urls, _snippet_lookup, _score_lookup, region)

    # Adapt ScrapedItems for synthesize_signals: inject source_type tag into summary
    synthesis_inputs = [
        {
            "title": s["title"],
            "url": s["url"],
            "summary": f"[{s['source_type']}] {s['content']}",
            "published_date": "",
        }
        for s in scraped_items
    ]

    # Track stats for scratchpad
    _fc_succeeded = sum(1 for s in scraped_items if s["source_type"] == "fulltext")
    _fc_stats = {
        "attempted": len(scraped_items),
        "succeeded": _fc_succeeded,
        "fell_back": len(scraped_items) - _fc_succeeded,
    }

    # --- LLM Call 3: Synthesize (Sonnet) ---
    geo_signals, cyber_signals, conclusion = synthesize_signals(
        region,
        working_theory,
        synthesis_inputs,
        source_note=(
            "Items labeled [fulltext] are main-content extracts up to ~3k tokens. "
            "Items labeled [snippet] are 200-char previews. "
            "Weight fulltext primary sources more heavily when both are available."
        ),
    )

    # --- Collect source URLs from raw Tavily results (junk-filtered) ---
    source_urls = list(dict.fromkeys(
        r["url"] for r in all_results if r.get("url") and not _is_junk_url(r["url"])
    ))

    # --- Enrich with metadata ---
    collected_at = datetime.now(timezone.utc).isoformat()

    # --- Enrich lead_indicators with signal_ids and pillar ---
    geo_indicators = _enrich_indicators_with_ids(
        geo_signals.get("lead_indicators", []), region, "geo", geo_signals.get("sources", [])
    )
    cyber_indicators = _enrich_indicators_with_ids(
        cyber_signals.get("lead_indicators", []), region, "cyber", cyber_signals.get("sources", [])
    )

    # --- Merge into unified osint_signals.json ---
    # Combine sources from both pillars, deduplicated by URL
    all_sources = []
    seen_source_urls = set()
    for src in geo_signals.get("sources", []) + cyber_signals.get("sources", []):
        url = src.get("url", "")
        if url and url not in seen_source_urls:
            seen_source_urls.add(url)
            all_sources.append(src)

    # Determine dominant pillar from conclusion
    dominant_pillar = conclusion.get("dominant_pillar", "Cyber")

    # Merge matched_topics
    matched_topics = list(dict.fromkeys(
        geo_signals.get("matched_topics", []) + cyber_signals.get("matched_topics", [])
    ))

    osint_signals = {
        "region": region,
        "collected_at": collected_at,
        "collection_window": {
            "days": int(window.rstrip("d")) if window and window != "all" else 0,
            "since": "",  # filled by caller if needed
        },
        "dominant_pillar": dominant_pillar,
        "summary": geo_signals.get("summary", "") + " " + cyber_signals.get("summary", ""),
        "lead_indicators": geo_indicators + cyber_indicators,
        "sources": all_sources,
        "matched_topics": matched_topics,
        "source_provenance": "osint:tavily",
    }

    # --- Write unified output ---
    _write_json(out_dir / "osint_signals.json", osint_signals)

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
            "firecrawl_stats": _fc_stats,
        },
        "conclusion": conclusion,
    }
    _write_json(out_dir / "osint_scratchpad.json", scratchpad)

    # --- Collection quality gate ---
    check_collection_quality(region)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: osint_collector.py <REGION> [--mock] [--window 7d]", file=sys.stderr)
        sys.exit(1)

    region = sys.argv[1].upper()
    if region not in VALID_REGIONS:
        print(f"Invalid region: {region}. Valid: {VALID_REGIONS}", file=sys.stderr)
        sys.exit(1)

    mock = "--mock" in sys.argv

    window = None
    for i, arg in enumerate(sys.argv):
        if arg == "--window" and i + 1 < len(sys.argv):
            window = sys.argv[i + 1]
            break

    if mock:
        run_mock_mode(region, window)
    else:
        run_live_mode(region, window)


if __name__ == "__main__":
    main()
