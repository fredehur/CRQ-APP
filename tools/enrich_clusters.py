"""Enrich signal_clusters.json with url and credibility_tier from signal files.

Reads osint_signals.json sources array, matches by name
(case-insensitive) against cluster source entries, and adds url + credibility_tier.

Usage: python tools/enrich_clusters.py <REGION>
"""
import json
import os
import sys

_TIER_A_DOMAINS = [
    ".gov", "enisa.europa.eu", "nist.gov", "cisa.gov",
    "eur-lex.europa.eu", "nato.int", "un.org", "interpol.int",
]
_TIER_C_DOMAINS = ["youtube.com", "twitter.com", "reddit.com", "facebook.com"]


def _infer_tier(url):
    if not url:
        return "B"
    url_lower = url.lower()
    for domain in _TIER_A_DOMAINS:
        if domain in url_lower:
            return "A"
    for domain in _TIER_C_DOMAINS:
        if domain in url_lower:
            return "C"
    return "B"


def _build_source_lookup(region_lower):
    """Build a case-insensitive name -> {name, url} lookup from signal files."""
    lookup = {}
    for signal_file in ["osint_signals.json"]:
        path = f"output/regional/{region_lower}/{signal_file}"
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for src in data.get("sources", []):
            name = src.get("name", "")
            url = src.get("url")
            if name:
                lookup[name.lower()] = {"name": name, "url": url}
    return lookup


def enrich(region):
    region_lower = region.lower()
    clusters_path = f"output/regional/{region_lower}/signal_clusters.json"

    if not os.path.exists(clusters_path):
        print(f"[SKIP] {clusters_path} does not exist", file=sys.stderr)
        return

    with open(clusters_path, encoding="utf-8") as f:
        clusters_data = json.load(f)

    lookup = _build_source_lookup(region_lower)
    resolved = 0
    unresolved = 0

    for cluster in clusters_data.get("clusters", []):
        enriched_sources = []
        for src in cluster.get("sources", []):
            # Handle both string entries and object entries
            if isinstance(src, str):
                src_name = src
                headline = None
            else:
                src_name = src.get("name", "")
                headline = src.get("headline")

            match = lookup.get(src_name.lower())
            if match:
                entry = {
                    "name": match["name"],
                    "url": match["url"],
                    "credibility_tier": _infer_tier(match["url"]),
                }
                resolved += 1
            else:
                print(f"[UNRESOLVED] {src_name}", file=sys.stderr)
                entry = {
                    "name": src_name,
                    "url": None,
                    "credibility_tier": "B",
                }
                unresolved += 1

            if headline:
                entry["headline"] = headline
            enriched_sources.append(entry)

        cluster["sources"] = enriched_sources

    with open(clusters_path, "w", encoding="utf-8") as f:
        json.dump(clusters_data, f, indent=2)

    print(f"Enriched {clusters_path} — {resolved} resolved, {unresolved} unresolved")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: enrich_clusters.py <REGION>", file=sys.stderr)
        sys.exit(1)
    enrich(sys.argv[1])
