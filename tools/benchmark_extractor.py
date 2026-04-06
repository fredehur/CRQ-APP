#!/usr/bin/env python3
"""Benchmark extractor — runs Haiku over cached source text to extract financial figures.

Usage:
    benchmark_extractor.py [--mock]
    benchmark_extractor.py --source SOURCE_ID [--mock]

Reads:  output/validation_cache/**/*.json  (files where benchmarks == [])
Writes: updates benchmarks[] in each cache file in-place
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

from tools.config import VALIDATION_CACHE_DIR
CACHE_ROOT = VALIDATION_CACHE_DIR
MODEL = "claude-haiku-4-5-20251001"

EXTRACTION_PROMPT = """\
You are extracting financial impact data from a cybersecurity industry report.

Extract all dollar-denominated financial impact figures for cyber incidents. For each figure found:
- scenario_tag: classify into one of: System intrusion, Ransomware, Accidental disclosure, Physical threat, Insider misuse, DoS attack, Scam or fraud, Defacement, System failure
- sector: the industry sector this applies to (e.g. "manufacturing", "energy", "all")
- cost_low_usd: lower bound in USD as integer (null if not stated)
- cost_median_usd: median or average in USD as integer (null if not stated)
- cost_high_usd: upper bound in USD as integer (null if not stated)
- note: brief description of what this figure represents
- raw_quote: the exact text excerpt this came from (max 200 chars)

Return ONLY a JSON array. If no financial figures found, return [].

Text to analyze:
{raw_text}"""


def _extract_with_haiku(raw_text: str) -> list[dict]:
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(raw_text=raw_text[:15_000]),
                }
            ],
        )
        content = response.content[0].text.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"[extractor] JSON parse error from Haiku: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[extractor] Haiku call failed: {e}", file=sys.stderr)
        return []


def extract_file(cache_path: Path, mock: bool) -> None:
    data = json.loads(cache_path.read_text(encoding="utf-8"))

    if data.get("benchmarks"):
        print(f"[extractor] {cache_path.name} already has benchmarks, skipping", file=sys.stderr)
        return

    if data.get("mock"):
        print(f"[extractor] {cache_path.name} is mock stub, skipping", file=sys.stderr)
        return

    raw_text = data.get("raw_text", "")
    if not raw_text:
        print(f"[extractor] {cache_path.name} has no raw_text, skipping", file=sys.stderr)
        return

    if mock:
        data["benchmarks"] = [{"mock": True}]
    else:
        print(f"[extractor] extracting benchmarks from {cache_path}", file=sys.stderr)
        benchmarks = _extract_with_haiku(raw_text)
        data["benchmarks"] = benchmarks
        print(f"[extractor] extracted {len(benchmarks)} benchmarks", file=sys.stderr)

    cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run(source_id: str | None = None, mock: bool = False) -> None:
    pattern = str(CACHE_ROOT / (source_id or "**") / "*.json")
    files = glob.glob(pattern, recursive=True)

    if not files:
        print(f"[extractor] no cache files found at {pattern}", file=sys.stderr)
        return

    for path_str in files:
        extract_file(Path(path_str), mock)

    print(f"[extractor] done — processed {len(files)} cache files", file=sys.stderr)


def main():
    args = sys.argv[1:]
    mock = "--mock" in args
    source_id = None
    if "--source" in args:
        idx = args.index("--source")
        if idx + 1 < len(args):
            source_id = args[idx + 1]
    run(source_id=source_id, mock=mock)


if __name__ == "__main__":
    main()
