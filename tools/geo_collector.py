#!/usr/bin/env python3
"""Geo signal collector — calls osint_search.py, normalizes to geo_signals.json.

Usage:
    geo_collector.py REGION [--mock]

Writes: output/regional/{region}/geo_signals.json
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, ".")

from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

GEO_KEYWORDS = ["trade", "sanction", "tariff", "geopolit", "diplomatic", "border",
                 "government", "policy", "regulation", "political", "alliance"]
CYBER_KEYWORDS = ["cyber", "hack", "attack", "malware", "ransomware", "breach",
                  "intrusion", "vulnerability", "exploit", "phishing"]
REGULATORY_KEYWORDS = ["regulat", "compliance", "legislat", "law", "directive",
                       "standard", "audit", "certif"]


def _load_topics_for_region(region: str) -> list:
    """Return active topics from data/osint_topics.json scoped to this region."""
    path = Path("data/osint_topics.json")
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            all_topics = json.load(f)
        return [t for t in all_topics if t.get("active") and region in t.get("regions", [])]
    except (json.JSONDecodeError, KeyError):
        return []


def run_search(region, query, mock, window=None):
    cmd = [sys.executable, "tools/osint_search.py", region, query, "--type", "geo"]
    if mock:
        cmd.append("--mock")
    if window:
        cmd += ["--window", window]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def infer_dominant_pillar(articles):
    text = " ".join(
        (a.get("title", "") + " " + a.get("summary", "")).lower()
        for a in articles
    )
    scores = {
        "Geopolitical": sum(1 for kw in GEO_KEYWORDS if kw in text),
        "Cyber": sum(1 for kw in CYBER_KEYWORDS if kw in text),
        "Regulatory": sum(1 for kw in REGULATORY_KEYWORDS if kw in text),
    }
    return max(scores, key=scores.get)


def normalize(articles):
    if not articles:
        return {
            "summary": "No active geopolitical signals detected in current period.",
            "lead_indicators": ["No significant geopolitical developments identified"],
            "dominant_pillar": "Geopolitical",
        }

    top = articles[:2]
    summary = " ".join(
        a.get("summary", a.get("title", ""))[:250] for a in top
    ).strip()

    lead_indicators = [a.get("title", "")[:120] for a in articles[:3] if a.get("title")]
    if not lead_indicators:
        lead_indicators = ["No specific indicators identified"]

    dominant_pillar = infer_dominant_pillar(articles)

    return {
        "summary": summary,
        "lead_indicators": lead_indicators,
        "dominant_pillar": dominant_pillar,
    }


def collect(region, mock, window=None):
    articles1 = run_search(region, f"{region} geopolitical risk wind energy", mock, window)
    articles2 = run_search(region, f"{region} trade tensions manufacturing", mock, window)

    # Topic-focused pass: one search per active topic scoped to this region.
    # Baseline catches unexpected events; topic queries deepen focus on known ones.
    topics = _load_topics_for_region(region)
    topic_articles = []
    for topic in topics:
        query = " ".join(topic["keywords"][:4])  # max 4 keywords per query
        results = run_search(region, query, mock, window)
        topic_articles.extend(results)

    # Deduplicate across baseline + topic results by title
    seen = set()
    articles = []
    for a in articles1 + articles2 + topic_articles:
        key = a.get("title", "")
        if key not in seen:
            seen.add(key)
            articles.append(a)

    base = normalize(articles)
    # Record which topic IDs were searched for traceability
    base["matched_topics"] = [t["id"] for t in topics]

    # Seerist enrichment (only when SEERIST_API_KEY is set)
    if not mock and os.environ.get("SEERIST_API_KEY"):
        try:
            from tools.seerist_client import get_full_intelligence
            seerist_data = get_full_intelligence(region)
            seerist_payload = {k: v for k, v in seerist_data.items() if v is not None}
            if seerist_payload:
                base["seerist"] = seerist_payload
                events = seerist_data.get("events") or []
                if events:
                    seerist_indicators = [
                        f"[{e.get('category', 'Event')}] {e.get('title', '')}"
                        for e in events[:3] if e.get("title")
                    ]
                    base["lead_indicators"] = seerist_indicators + base["lead_indicators"]
                if seerist_data.get("scribe"):
                    base["seerist_assessment"] = seerist_data["scribe"]
                if seerist_data.get("hotspots"):
                    base["anomaly_detected"] = True
        except Exception as e:
            print(f"[geo_collector] Seerist enrichment failed: {e}", file=sys.stderr)

    return base


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: geo_collector.py REGION [--mock] [--window 1d|7d|30d|90d]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args

    window = None
    if "--window" in args:
        idx = args.index("--window")
        if idx + 1 < len(args):
            window = args[idx + 1]

    if region not in VALID_REGIONS:
        print(f"[geo_collector] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    result = collect(region, mock, window)

    out_dir = f"output/regional/{region.lower()}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/geo_signals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[geo_collector] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
