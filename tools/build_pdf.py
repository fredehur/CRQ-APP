from __future__ import annotations
import argparse
import asyncio
from pathlib import Path
from tools.briefs.renderer import render_pdf


BRIEFS = ("board", "ciso", "rsm")


def _load_data(brief: str, args: argparse.Namespace):
    if brief == "board":
        from tools.briefs.data.board import load_board_data
        return load_board_data(args.quarter)
    if brief == "ciso":
        from tools.briefs.data.ciso import load_ciso_data
        return load_ciso_data(args.month)
    if brief == "rsm":
        if args.mock:
            from tools.briefs.data._rsm_mock import rsm_med_w17_mock
            return rsm_med_w17_mock()
        from tools.briefs.data.rsm import load_rsm_data
        return load_rsm_data(args.region, args.week_of)
    raise SystemExit(f"unknown brief: {brief}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_pdf")
    p.add_argument("--brief", required=True, choices=BRIEFS)
    p.add_argument("--out", type=Path, required=True)
    # per-brief flags
    p.add_argument("--region", help="RSM: region code (APAC, AME, LATAM, MED, NCE)")
    p.add_argument("--week-of", dest="week_of", help="RSM: ISO week, e.g. 2026-W17")
    p.add_argument("--quarter", help="Board: e.g. 2026Q2")
    p.add_argument("--month", help="CISO: YYYY-MM")
    p.add_argument("--mock", action="store_true", help="RSM: use static mock data")
    args = p.parse_args(argv)
    data = _load_data(args.brief, args)
    asyncio.run(render_pdf(args.brief, data, args.out))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
