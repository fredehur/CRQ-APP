"""
suggest_tags.py — LLM-assisted search tag generation for register scenarios.

Usage:
    uv run python tools/suggest_tags.py --name "Wind Farm OT Ransomware" \
        --description "Ransomware targeting SCADA systems..."
Outputs: JSON array of tags to stdout.
"""

import argparse
import json
import sys

import anthropic


def suggest_tags(name: str, description: str) -> list[str]:
    client = anthropic.Anthropic()
    prompt = (
        f"You are helping build search tags for a cyber risk scenario so a pipeline can find "
        f"quantitative sources (dollar figures and probability percentages) about it.\n\n"
        f"Scenario name: {name}\n"
        f"Description: {description}\n\n"
        f"Return ONLY a JSON array of 4-8 lowercase snake_case search tags. "
        f"Tags should capture: industry sector, attack type, asset type, and threat actor context. "
        f"Example: [\"ot_systems\", \"energy_operator\", \"ransomware\", \"scada\"]\n\n"
        f"JSON array only — no explanation, no markdown."
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", required=True)
    args = parser.parse_args()
    tags = suggest_tags(args.name, args.description)
    print(json.dumps(tags))


if __name__ == "__main__":
    main()
