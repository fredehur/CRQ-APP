"""Merge a per-scenario rerun result into the latest register snapshot."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .snapshot import (
    OUTPUT_DIR, ScenarioResult, Snapshot,
    list_snapshot_paths, read_snapshot, write_snapshot,
)


def merge_scenario_result(
    register_id: str,
    new_result: ScenarioResult,
    *,
    output_dir: Optional[Path] = None,
) -> Snapshot:
    """Load the latest snapshot, replace one scenario's result, write a new file.

    Raises FileNotFoundError if no base snapshot exists.
    Raises KeyError if scenario_id not in base snapshot.
    intent_hash is preserved from the base — the yaml did not change.
    """
    target = output_dir or OUTPUT_DIR
    paths = list_snapshot_paths(register_id, output_dir=target)
    if not paths:
        raise FileNotFoundError(
            f"No base snapshot found for register '{register_id}'"
        )

    base = read_snapshot(paths[0])
    scenario_ids = [s.scenario_id for s in base.scenarios]
    if new_result.scenario_id not in scenario_ids:
        raise KeyError(
            f"Scenario '{new_result.scenario_id}' not found in base snapshot "
            f"(known: {scenario_ids})"
        )

    merged_scenarios = [
        new_result if s.scenario_id == new_result.scenario_id else s
        for s in base.scenarios
    ]

    merged = Snapshot(
        register_id=base.register_id,
        run_id=base.run_id,
        intent_hash=base.intent_hash,   # preserved — yaml unchanged
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        tavily_status=base.tavily_status,
        firecrawl_status=base.firecrawl_status,
        scenarios=merged_scenarios,
        debug=base.debug,
    )
    write_snapshot(merged, output_dir=target)
    return merged
