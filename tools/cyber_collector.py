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

sys.path.insert(0, ".")

from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

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
    cmd = [sys.executable, "tools/osint_search.py", region, query, "--type", "cyber"]
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


def collect(region, mock, window=None):
    articles1 = run_search(region, f"{region} cyber threat industrial control systems", mock, window)
    articles2 = run_search(region, f"{region} OT security wind energy", mock, window)

    # Topic-focused pass: one search per active topic scoped to this region
    topics = _load_topics_for_region(region)
    topic_articles = []
    for topic in topics:
        query = " ".join(topic["keywords"][:4])
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
    base["matched_topics"] = [t["id"] for t in topics]

    # Seerist +Cyber enrichment (requires SEERIST_API_KEY + SEERIST_CYBER_ADDON=true)
    if not mock and os.environ.get("SEERIST_API_KEY") and os.environ.get("SEERIST_CYBER_ADDON", "").lower() == "true":
        try:
            from tools.seerist_client import get_cyber_risk
            cyber_data = get_cyber_risk(region)
            if cyber_data:
                base["seerist_cyber"] = cyber_data
        except Exception as e:
            print(f"[cyber_collector] Seerist +Cyber enrichment failed: {e}", file=sys.stderr)

    return base


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: cyber_collector.py REGION [--mock] [--window 1d|7d|30d|90d]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    mock = "--mock" in args

    window = None
    if "--window" in args:
        idx = args.index("--window")
        if idx + 1 < len(args):
            window = args[idx + 1]

    if region not in VALID_REGIONS:
        print(f"[cyber_collector] invalid region '{region}'", file=sys.stderr)
        sys.exit(1)

    result = collect(region, mock, window)

    out_dir = f"output/regional/{region.lower()}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/cyber_signals.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[cyber_collector] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
