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

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

GEO_KEYWORDS = ["trade", "sanction", "tariff", "geopolit", "diplomatic", "border",
                 "government", "policy", "regulation", "political", "alliance"]
CYBER_KEYWORDS = ["cyber", "hack", "attack", "malware", "ransomware", "breach",
                  "intrusion", "vulnerability", "exploit", "phishing"]
REGULATORY_KEYWORDS = ["regulat", "compliance", "legislat", "law", "directive",
                       "standard", "audit", "certif"]


def run_search(region, query, mock):
    cmd = [sys.executable, "tools/osint_search.py", region, query, "--type", "geo"]
    if mock:
        cmd.append("--mock")
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


def collect(region, mock):
    articles1 = run_search(region, f"{region} geopolitical risk wind energy", mock)
    articles2 = run_search(region, f"{region} trade tensions manufacturing", mock)
    # Deduplicate by title
    seen = set()
    articles = []
    for a in articles1 + articles2:
        key = a.get("title", "")
        if key not in seen:
            seen.add(key)
            articles.append(a)
    return normalize(articles), articles


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: geo_collector.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args

    if region not in VALID_REGIONS:
        print(f"[geo_collector] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    normalized, raw_articles = collect(region, mock)

    out_dir = f"output/regional/{region.lower()}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/geo_signals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    print(f"[geo_collector] wrote {out_path}", file=sys.stderr)

    from datetime import datetime, timezone

    geo_sources = [
        {
            "title": a.get("title", ""),
            "snippet": a.get("summary", a.get("snippet", "")),
            "source": a.get("source", ""),
            "published_date": a.get("date", a.get("published_date", "")),
            "url": a.get("url", None),
            "mock": mock,
        }
        for a in raw_articles
    ]

    intel_path = f"{out_dir}/intelligence_sources.json"
    intel_doc = {
        "region": region,
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "geo_sources": geo_sources,
    }
    with open(intel_path, "w", encoding="utf-8") as f:
        json.dump(intel_doc, f, indent=2, ensure_ascii=False)

    print(f"[geo_collector] wrote {intel_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
