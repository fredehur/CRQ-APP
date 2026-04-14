"""Pydantic data contract for source_librarian snapshots."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

PublisherTier = Literal["T1", "T2", "T3"]
ScrapeStatus = Literal["ok", "failed", "skipped"]
ScenarioStatus = Literal["ok", "no_authoritative_coverage", "engines_down"]
EngineStatusTavily = Literal["ok", "failed", "disabled"]
EngineStatusFirecrawl = Literal["ok", "failed"]


class SourceEntry(BaseModel):
    url: str
    title: str
    publisher: str
    publisher_tier: PublisherTier
    published_date: Optional[str]
    discovered_by: list[Literal["tavily", "firecrawl"]]
    score: float
    summary: Optional[str]
    figures: list[str] = Field(default_factory=list)
    scrape_status: ScrapeStatus


class ScenarioResult(BaseModel):
    scenario_id: str
    scenario_name: str
    status: ScenarioStatus
    sources: list[SourceEntry] = Field(default_factory=list)
    diagnostics: Optional[dict] = None


class Snapshot(BaseModel):
    register_id: str
    run_id: str
    intent_hash: str
    started_at: datetime
    completed_at: Optional[datetime]
    tavily_status: EngineStatusTavily
    firecrawl_status: EngineStatusFirecrawl
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    debug: Optional[dict] = None


def intent_hash(yaml_text: str) -> str:
    """Stable 8-char sha256 prefix of the intent yaml text."""
    return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()[:8]


def snapshot_filename(register_id: str, started_at: datetime, hash8: str) -> str:
    """Filename format: <register>_<YYYY-MM-DD-HHMM>_<hash8>.json"""
    stamp = started_at.strftime("%Y-%m-%d-%H%M")
    return f"{register_id}_{stamp}_{hash8}.json"


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "research"


def write_snapshot(snap: Snapshot, output_dir: Optional[Path] = None) -> Path:
    """Write a snapshot to output/research/<filename>. Returns the path."""
    target = output_dir or OUTPUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    name = snapshot_filename(snap.register_id, snap.started_at, snap.intent_hash)
    path = target / name
    path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    return path


def list_snapshot_paths(register_id: str, output_dir: Optional[Path] = None) -> list[Path]:
    """Return all snapshot paths for a register, newest filename first."""
    target = output_dir or OUTPUT_DIR
    if not target.exists():
        return []
    return sorted(target.glob(f"{register_id}_*.json"), reverse=True)


def read_snapshot(path: Path) -> Snapshot:
    return Snapshot.model_validate_json(path.read_text(encoding="utf-8"))
