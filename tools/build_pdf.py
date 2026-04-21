from __future__ import annotations
import argparse
import asyncio
import shutil
import tempfile
from pathlib import Path

from tools.briefs import storage
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
            return rsm_med_w17_mock(), None
        from tools.briefs.data.rsm import load_rsm_data
        return load_rsm_data(args.region, args.week_of, narrate=args.narrate)
    raise SystemExit(f"unknown brief: {brief}")


def _audience_id(brief: str, region: str | None) -> str:
    if brief == "rsm":
        return f"rsm-{region.lower()}"
    return brief


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build_pdf")
    p.add_argument("--brief", required=True, choices=BRIEFS)
    p.add_argument("--out", type=Path, help="Optional output path (for ad-hoc renders)")
    p.add_argument("--no-archive", action="store_true",
                   help="Skip archive; requires --out")
    p.add_argument("--region", help="RSM: region code (APAC, AME, LATAM, MED, NCE)")
    p.add_argument("--week-of", dest="week_of", help="RSM: ISO week, e.g. 2026-W17")
    p.add_argument("--quarter", help="Board: e.g. 2026Q2")
    p.add_argument("--month", help="CISO: YYYY-MM")
    p.add_argument("--mock", action="store_true", help="RSM: use static mock data")
    p.add_argument("--narrate", action="store_true",
                   help="RSM: call synthesizer agent via Anthropic API")
    args = p.parse_args(argv)

    if args.no_archive and not args.out:
        raise SystemExit("--no-archive requires --out")

    data, pipeline_run_id = _load_data(args.brief, args)

    with tempfile.TemporaryDirectory() as td:
        tmp_pdf = Path(td) / "out.pdf"
        tmp_png = Path(td) / "out.png"
        asyncio.run(render_pdf(args.brief, data, tmp_pdf, thumbnail_path=tmp_png))

        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(tmp_pdf, args.out)

        if not args.no_archive:
            audience_id = _audience_id(args.brief, args.region)
            narrated = bool(getattr(args, "narrate", False))
            metadata: dict = {}
            if args.brief == "rsm":
                metadata["region"] = args.region
                metadata["week_of"] = args.week_of
            elif args.brief == "ciso":
                metadata["month"] = args.month
            elif args.brief == "board":
                metadata["quarter"] = args.quarter
            storage.record_version(
                audience_id=audience_id,
                pdf_tmp_path=tmp_pdf,
                thumbnail_tmp_path=tmp_png,
                pipeline_run_id=pipeline_run_id,
                narrated=narrated,
                generated_by="cli",
                metadata=metadata,
            )
            print(f"archived {audience_id}")

    if args.out:
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
