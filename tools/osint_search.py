#!/usr/bin/env python3
"""OSINT search primitive — returns raw search results as JSON array to stdout.

Usage:
    osint_search.py REGION QUERY --type geo|cyber [--mock]

In --mock mode: loads fixture from data/mock_osint_fixtures/{region}_{type}.json
In live mode (not implemented yet): would call Tavily/DDG API
"""
import json
import sys

VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}
VALID_TYPES = {"geo", "cyber"}


def parse_args(argv):
    if len(argv) < 2:
        print("Usage: osint_search.py REGION QUERY --type geo|cyber [--mock]", file=sys.stderr)
        sys.exit(1)

    region = argv[0].upper()
    query = argv[1]
    type_ = None
    mock = False

    i = 2
    while i < len(argv):
        if argv[i] == "--type" and i + 1 < len(argv):
            type_ = argv[i + 1]
            i += 2
        elif argv[i] == "--mock":
            mock = True
            i += 1
        else:
            i += 1

    if region not in VALID_REGIONS:
        print(f"[osint_search] invalid region '{region}'. Valid: {sorted(VALID_REGIONS)}", file=sys.stderr)
        sys.exit(1)

    if type_ is None:
        print("[osint_search] --type geo|cyber is required", file=sys.stderr)
        sys.exit(1)

    if type_ not in VALID_TYPES:
        print(f"[osint_search] invalid type '{type_}'. Valid: geo, cyber", file=sys.stderr)
        sys.exit(1)

    return region, query, type_, mock


def load_fixture(region, type_):
    path = f"data/mock_osint_fixtures/{region.lower()}_{type_}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    region, query, type_, mock = parse_args(sys.argv[1:])

    if mock:
        articles = load_fixture(region, type_)
    else:
        # Live mode: not yet implemented — return empty array
        articles = []

    print(json.dumps(articles, ensure_ascii=False))


if __name__ == "__main__":
    main()
