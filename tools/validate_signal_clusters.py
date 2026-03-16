#!/usr/bin/env python3
"""Validates signal_clusters.json schema. Exits 0 on pass, 1 on fail."""
import json
import sys

VALID_PILLARS = {"Geo", "Cyber"}


def validate(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    errors = []

    for key in ("region", "timestamp", "window_used", "total_signals", "sources_queried", "clusters"):
        if key not in data:
            errors.append(f"Missing top-level key: {key}")

    if not isinstance(data.get("clusters"), list):
        errors.append("'clusters' must be a list")
    else:
        for i, c in enumerate(data["clusters"]):
            for ckey in ("name", "pillar", "convergence", "sources"):
                if ckey not in c:
                    errors.append(f"clusters[{i}] missing key: {ckey}")
            if c.get("pillar") not in VALID_PILLARS:
                errors.append(f"clusters[{i}].pillar must be 'Geo' or 'Cyber', got: {c.get('pillar')}")
            if not isinstance(c.get("convergence"), int):
                errors.append(f"clusters[{i}].convergence must be int")
            if not isinstance(c.get("sources"), list):
                errors.append(f"clusters[{i}].sources must be list")
            else:
                for j, s in enumerate(c["sources"]):
                    if "name" not in s or "headline" not in s:
                        errors.append(f"clusters[{i}].sources[{j}] missing name or headline")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"PASS: {path} — {len(data['clusters'])} clusters, {data['total_signals']} signals")
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: validate_signal_clusters.py <path>")
        sys.exit(1)
    validate(sys.argv[1])
