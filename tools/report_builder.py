# tools/report_builder.py
"""
Reads all pipeline output files and assembles a ReportData object.
No rendering logic — consumed by export_pdf.py and export_pptx.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = "output"
REGIONS = ["APAC", "AME", "LATAM", "MED", "NCE"]


class RegionStatus(StrEnum):
    ESCALATED = "escalated"
    MONITOR = "monitor"
    CLEAR = "clear"


@dataclass
class RegionEntry:
    name: str
    status: RegionStatus
    vacr: float | None
    admiralty: str | None
    velocity: str | None
    severity: str | None
    scenario_match: str | None
    why_text: str | None
    how_text: str | None
    so_what_text: str | None


@dataclass
class ReportData:
    run_id: str
    timestamp: str
    total_vacr: float
    exec_summary: str
    escalated_count: int
    monitor_count: int
    clear_count: int
    regions: list[RegionEntry]
    monitor_regions: list[str]
    trend_delta: str = "\u2014"


# ── Header sets for pillar parsing (prefix match) ─────────────────────────────
_PILLAR_HEADERS = [
    # Designed headers (Phase C+)
    ("## Why", "## How", "## So What"),
    # Legacy headers (pre-Phase C agent output)
    ("## Situation Overview", "## Risk Context", "## Board-Level"),
]


def _header_matches(line: str, prefix: str) -> bool:
    """True if line starts with prefix followed by space, em-dash, or EOL."""
    if not line.startswith(prefix):
        return False
    rest = line[len(prefix):]
    return rest == "" or rest.startswith((" ", "—", "\r", "\n"))


def _parse_pillars(text: str) -> tuple[str | None, str | None, str | None]:
    """Split report.md text into (why, how, so_what) by section header prefix.

    Tries designed headers first, then legacy headers.
    Falls back to (full_text, None, None) if no headers matched.
    """
    lines = text.splitlines(keepends=True)

    for h1, h2, h3 in _PILLAR_HEADERS:
        indices = {}
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if _header_matches(stripped, h1) and 1 not in indices:
                indices[1] = i
            elif _header_matches(stripped, h2) and 2 not in indices:
                indices[2] = i
            elif _header_matches(stripped, h3) and 3 not in indices:
                indices[3] = i

        if len(indices) == 3:
            i1, i2, i3 = indices[1], indices[2], indices[3]
            if not (i1 < i2 < i3):
                logger.warning("Pillar headers found out of order — skipping this header set")
                continue  # try next header set
            why     = "".join(lines[i1 + 1 : i2]).strip()
            how     = "".join(lines[i2 + 1 : i3]).strip()
            so_what = "".join(lines[i3 + 1 :]).strip()
            return why, how, so_what

    # No recognised headers — return full text as why, rest None
    return text.strip(), None, None


def _get_previous_total_vacr(output_dir: str) -> float | None:
    """Return total VaCR from the most recent archived run, or None."""
    runs_dir = Path(output_dir) / "runs"
    if not runs_dir.is_dir():
        return None
    try:
        subdirs = sorted(d.name for d in runs_dir.iterdir() if d.is_dir())
        if not subdirs:
            return None
        prev_manifest = runs_dir / subdirs[-1] / "run_manifest.json"
        if not prev_manifest.exists():
            return None
        manifest = json.loads(prev_manifest.read_text(encoding="utf-8"))
        return float(manifest.get("total_vacr_exposure_usd") or 0)
    except Exception:
        return None


def _format_delta(current: float, previous: float | None) -> str:
    """Format a VaCR delta as a direction arrow + dollar amount, or em-dash."""
    if previous is None:
        return "\u2014"
    diff = current - previous
    if diff == 0:
        return "\u2014"
    abs_m = abs(diff) / 1_000_000
    if abs_m >= 1:
        label = f"${abs_m:.1f}M"
    else:
        label = f"${abs(diff) / 1_000:,.0f}K"
    return f"\u25b2{label}" if diff > 0 else f"\u25bc{label}"


# ── Public API ─────────────────────────────────────────────────────────────────

def build(output_dir: str = OUTPUT_DIR) -> ReportData:
    """Assemble ReportData from pipeline output files.

    Args:
        output_dir: path to the output/ directory (override in tests).

    Raises:
        FileNotFoundError: if global_report.json or run_manifest.json are absent.
    """
    base = Path(output_dir)

    # --- run_manifest.json ---
    manifest = json.loads((base / "run_manifest.json").read_text(encoding="utf-8"))
    run_id    = manifest.get("pipeline_id", "unknown")
    timestamp = manifest.get("run_timestamp", "unknown")

    # --- global_report.json ---
    global_report = json.loads(
        (base / "global_report.json").read_text(encoding="utf-8")
    )
    total_vacr    = float(global_report.get("total_vacr_exposure") or 0)
    exec_summary  = global_report.get("executive_summary", "")
    monitor_regions = global_report.get("monitor_regions", [])

    # --- Regional entries ---
    regions: list[RegionEntry] = []
    for region_name in REGIONS:
        data_path = base / "regional" / region_name.lower() / "data.json"
        if not data_path.exists():
            logger.warning("Missing data.json for %s — skipping", region_name)
            continue

        d = json.loads(data_path.read_text(encoding="utf-8"))
        raw_status = d.get("status", "clear")
        try:
            status = RegionStatus(raw_status)
        except ValueError:
            logger.warning("Unknown status %r for %s — defaulting to clear", raw_status, region_name)
            status = RegionStatus.CLEAR

        why_text = how_text = so_what_text = None
        if status == RegionStatus.ESCALATED:
            report_path = base / "regional" / region_name.lower() / "report.md"
            if report_path.exists():
                why_text, how_text, so_what_text = _parse_pillars(
                    report_path.read_text(encoding="utf-8")
                )
            else:
                logger.warning(
                    "report.md missing for escalated region %s — body will be empty",
                    region_name,
                )

        regions.append(RegionEntry(
            name=region_name,
            status=status,
            vacr=float(d.get("vacr_exposure_usd", 0) or 0),
            admiralty=d.get("admiralty"),
            velocity=d.get("velocity"),
            severity=d.get("severity"),
            scenario_match=d.get("primary_scenario"),
            why_text=why_text,
            how_text=how_text,
            so_what_text=so_what_text,
        ))

    escalated = [r for r in regions if r.status == RegionStatus.ESCALATED]
    monitor   = [r for r in regions if r.status == RegionStatus.MONITOR]
    clear     = [r for r in regions if r.status == RegionStatus.CLEAR]

    prev_total = _get_previous_total_vacr(output_dir)
    trend_delta = _format_delta(total_vacr, prev_total)

    return ReportData(
        run_id=run_id,
        timestamp=timestamp,
        total_vacr=total_vacr,
        exec_summary=exec_summary,
        escalated_count=len(escalated),
        monitor_count=len(monitor),
        clear_count=len(clear),
        regions=regions,
        monitor_regions=monitor_regions,
        trend_delta=trend_delta,
    )
