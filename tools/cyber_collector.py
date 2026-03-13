#!/usr/bin/env python3
"""Cyber signal collector — calls osint_search.py, normalizes to cyber_signals.json.

Usage:
    cyber_collector.py REGION [--mock]

Writes: output/regional/{region}/cyber_signals.json
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

THREAT_VECTOR_PATTERNS = [
    ("ransomware", "Ransomware deployment via phishing and credential theft"),
    ("supply chain", "Supply chain compromise through third-party software updates"),
    ("phishing", "Spear-phishing campaigns targeting engineering and operations staff"),
    ("intrusion", "Network intrusion via exposed remote access infrastructure"),
    ("insider", "Insider threat through privileged account misuse"),
    ("OT", "Operational technology exploitation via IT/OT network segmentation gaps"),
    ("segmentation", "Operational technology exploitation via IT/OT network segmentation gaps"),
    ("credential", "Credential harvesting targeting privileged access accounts"),
]

ASSET_KEYWORDS = {
    "turbine": "Wind turbine control systems",
    "wind": "Wind turbine operational platforms",
    "blade": "Blade production line systems",
    "manufacturing": "Manufacturing execution systems",
    "SCADA": "SCADA and supervisory control infrastructure",
    "OT": "Operational technology networks",
    "IP": "Proprietary design and engineering IP repositories",
    "design": "Turbine design and engineering data repositories",
    "maintenance": "Predictive maintenance platforms",
    "telemetry": "Turbine telemetry and monitoring systems",
}


def run_search(region, query, mock):
    cmd = [sys.executable, "tools/osint_search.py", region, query, "--type", "cyber"]
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


def extract_threat_vector(articles):
    text = " ".join(
        (a.get("title", "") + " " + a.get("summary", "")).lower()
        for a in articles
    )
    for keyword, vector in THREAT_VECTOR_PATTERNS:
        if keyword.lower() in text:
            return vector
    return "Advanced persistent threat targeting critical infrastructure"


def extract_target_assets(articles):
    text = " ".join(
        (a.get("title", "") + " " + a.get("summary", ""))
        for a in articles
    )
    found = []
    for keyword, asset in ASSET_KEYWORDS.items():
        if keyword in text and asset not in found:
            found.append(asset)
    return found[:3]


def normalize(articles):
    if not articles:
        return {
            "summary": "No active cyber threat signals detected in current period.",
            "threat_vector": "No active threat vector identified",
            "target_assets": ["Operational technology systems"],
        }

    top = articles[:2]
    summary = " ".join(
        a.get("summary", a.get("title", ""))[:250] for a in top
    ).strip()

    threat_vector = extract_threat_vector(articles)
    target_assets = extract_target_assets(articles)
    if not target_assets:
        target_assets = ["Operational technology systems"]

    return {
        "summary": summary,
        "threat_vector": threat_vector,
        "target_assets": target_assets,
    }


def collect(region, mock):
    articles1 = run_search(region, f"{region} cyber threat industrial control systems", mock)
    articles2 = run_search(region, f"{region} OT security wind energy", mock)
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
        print("Usage: cyber_collector.py REGION [--mock]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args

    if region not in VALID_REGIONS:
        print(f"[cyber_collector] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    normalized, raw_articles = collect(region, mock)

    out_dir = f"output/regional/{region.lower()}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/cyber_signals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    print(f"[cyber_collector] wrote {out_path}", file=sys.stderr)

    cyber_sources = [
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
    intel_doc = {}
    if os.path.exists(intel_path):
        try:
            with open(intel_path, encoding="utf-8") as f:
                intel_doc = json.load(f)
            if "geo_sources" not in intel_doc:
                print(
                    f"[cyber_collector] WARNING: {intel_path} missing geo_sources key — "
                    "writing cyber_sources only. Run geo_collector first.",
                    file=sys.stderr,
                )
        except (json.JSONDecodeError, OSError):
            intel_doc = {}

    intel_doc["region"] = region
    intel_doc["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    intel_doc["cyber_sources"] = cyber_sources

    with open(intel_path, "w", encoding="utf-8") as f:
        json.dump(intel_doc, f, indent=2, ensure_ascii=False)

    print(f"[cyber_collector] wrote {intel_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
