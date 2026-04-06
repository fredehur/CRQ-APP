#!/usr/bin/env python3
"""Phase 0 environment validator.

Checks required env vars are present before the pipeline starts.
Exits 1 with a clear error message if anything is missing.

Usage:
    uv run python tools/validate_env.py [--live]

    --live   Validate live OSINT mode requirements (ANTHROPIC_API_KEY mandatory,
             TAVILY_API_KEY optional — warns if absent, falls back to DuckDuckGo)
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def check(name: str, required: bool = True, hint: str = "") -> bool:
    val = os.environ.get(name, "").strip()
    if val:
        print(f"  [OK]   {name}")
        return True
    if required:
        print(f"  [FAIL] {name} — missing. {hint}")
        return False
    else:
        print(f"  [WARN] {name} — not set. {hint}")
        return True  # warnings don't block


def main() -> None:
    live = "--live" in sys.argv
    mode = "LIVE" if live else "MOCK"
    print(f"[validate_env] mode={mode}")

    failures = []

    # Always required — check via client init (Claude Code injects key via proxy)
    try:
        import anthropic
        anthropic.Anthropic()
        print("  [OK]   ANTHROPIC_API_KEY (client initialised)")
    except Exception as e:
        print(f"  [FAIL] Anthropic client failed: {e}")
        failures.append("ANTHROPIC_API_KEY")

    if live:
        # Tavily is optional — DDG fallback available
        check("TAVILY_API_KEY", required=False,
              hint="Optional — Tavily gives higher quality results. "
                   "Falling back to DuckDuckGo (free, no key).")

    if failures:
        print(f"\n[validate_env] FAILED — {len(failures)} missing variable(s): "
              f"{', '.join(failures)}")
        print("  Set these in .env and re-run.")
        sys.exit(1)

    print(f"[validate_env] OK — environment valid for {mode} mode")


if __name__ == "__main__":
    main()
