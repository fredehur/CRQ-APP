"""CLI entry point: `python -m tools.source_librarian --register <id>`."""
from __future__ import annotations

import argparse
import logging
import sys

from . import run_snapshot
from .snapshot import OUTPUT_DIR, snapshot_filename


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.source_librarian")
    parser.add_argument("--register", help="register_id (e.g. wind_power_plant)")
    parser.add_argument("--bootstrap", metavar="REGISTER", help="bootstrap an intent yaml from a register json")
    parser.add_argument("--debug", action="store_true", help="include rejected candidates in output")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(name)s] %(message)s",
    )

    if args.bootstrap:
        from .bootstrap import bootstrap_intent_yaml
        path = bootstrap_intent_yaml(args.bootstrap)
        print(f"Wrote {path}")
        return 0

    if not args.register:
        parser.error("--register is required (or use --bootstrap)")

    snap = run_snapshot(args.register, debug=args.debug)
    name = snapshot_filename(snap.register_id, snap.started_at, snap.intent_hash)
    print(f"Snapshot written: {OUTPUT_DIR / name}")
    print(f"  Tavily: {snap.tavily_status}  Firecrawl: {snap.firecrawl_status}")
    for sc in snap.scenarios:
        print(f"  {sc.scenario_id} [{sc.status}] {len(sc.sources)} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
