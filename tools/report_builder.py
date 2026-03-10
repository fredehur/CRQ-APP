# tools/report_builder.py
"""
Reads all pipeline output files and assembles a ReportData object.
No rendering logic — consumed by export_pdf.py and export_pptx.py.
"""
from __future__ import annotations

import json
import logging
import os
import warnings
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
