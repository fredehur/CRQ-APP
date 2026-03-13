"""
Writes output/regional/{region}/gatekeeper_decision.json.
Accepts JSON on stdin.

Usage:
  echo '<json>' | uv run python tools/write_gatekeeper_decision.py <REGION>
"""
import sys
import json
import os


def main():
    if len(sys.argv) != 2:
        print("Usage: write_gatekeeper_decision.py <REGION>")
        sys.exit(1)

    region = sys.argv[1].lower()
    out_dir = f"output/regional/{region}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/gatekeeper_decision.json"

    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON on stdin — {e}", file=sys.stderr)
        sys.exit(1)

    required = {"decision", "admiralty", "dominant_pillar"}
    missing = required - payload.keys()
    if missing:
        print(f"ERROR: Missing required fields: {missing}", file=sys.stderr)
        sys.exit(1)

    if payload.get("admiralty") is None:
        print("ERROR: admiralty must not be null", file=sys.stderr)
        sys.exit(1)
    if not isinstance(payload["admiralty"], dict):
        print("ERROR: admiralty must be a dict", file=sys.stderr)
        sys.exit(1)
    adm_rating = payload["admiralty"].get("rating")
    if not adm_rating or not isinstance(adm_rating, str):
        print("ERROR: admiralty.rating must be a non-empty string", file=sys.stderr)
        sys.exit(1)

    if not payload.get("dominant_pillar") or not isinstance(payload["dominant_pillar"], str):
        print("ERROR: dominant_pillar must be a non-empty string", file=sys.stderr)
        sys.exit(1)

    valid_decisions = {"ESCALATE", "MONITOR", "CLEAR"}
    if payload.get("decision") not in valid_decisions:
        print(f"ERROR: decision must be one of {valid_decisions}", file=sys.stderr)
        sys.exit(1)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    rating = payload.get("admiralty", {}).get("rating", "?")
    print(f"Wrote {out_path} — decision: {payload['decision']}, admiralty: {rating}")


if __name__ == "__main__":
    main()
