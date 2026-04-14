#!/usr/bin/env python3
"""
Stop hook for source_librarian agent.

Validates that the most recent output/research/<register>_*.json:
  1. Exists (a snapshot was written this run)
  2. Validates against the Snapshot pydantic model
  3. completed_at is not null
  4. intent_hash matches the current intents yaml hash
  5. Every scenario in the intent yaml appears in snapshot.scenarios
  6. Every status="ok" scenario has >= 1 source with url + title + publisher_tier
  7. Every status="no_authoritative_coverage" has diagnostics.candidates_discovered > 0
  8. tavily_status in {ok, failed, disabled}
  9. firecrawl_status in {ok, failed}
  10. If both engines failed: every scenario.status == "engines_down"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "output" / "research"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    register_id = os.environ.get("SOURCE_LIBRARIAN_REGISTER")
    if not register_id:
        if not OUTPUT_DIR.exists():
            fail("output/research/ does not exist — no snapshot written")
        candidates = sorted(OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            fail("no snapshots found in output/research/")
        snap_path = candidates[0]
        # filename: {register_id}_{YYYY-MM-DD-HHMM}_{hash8}.json — strip last 2 segments
        register_id = "_".join(snap_path.stem.split("_")[:-2])
    else:
        candidates = sorted(
            OUTPUT_DIR.glob(f"{register_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            fail(f"no snapshot for register {register_id}")
        snap_path = candidates[0]

    try:
        from tools.source_librarian.snapshot import Snapshot, intent_hash
        from tools.source_librarian.intents import load_intent
    except Exception as exc:
        fail(f"cannot import source_librarian: {exc}")

    try:
        snap = Snapshot.model_validate_json(snap_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"snapshot {snap_path.name} fails pydantic validation: {exc}")

    if snap.completed_at is None:
        fail("completed_at is null — run did not finish")

    intent = load_intent(register_id)
    expected_hash = intent_hash(intent.raw_yaml)
    if snap.intent_hash != expected_hash:
        fail(f"intent_hash mismatch: snapshot={snap.intent_hash} current={expected_hash}")

    snap_sids = {s.scenario_id for s in snap.scenarios}
    intent_sids = set(intent.scenarios.keys())
    missing = intent_sids - snap_sids
    if missing:
        fail(f"missing scenarios in snapshot: {sorted(missing)}")

    if snap.tavily_status not in {"ok", "failed", "disabled"}:
        fail(f"tavily_status invalid: {snap.tavily_status}")
    if snap.firecrawl_status not in {"ok", "failed"}:
        fail(f"firecrawl_status invalid: {snap.firecrawl_status}")

    both_failed = (
        snap.tavily_status in ("failed", "disabled")
        and snap.firecrawl_status == "failed"
    )

    for sc in snap.scenarios:
        if both_failed and sc.status != "engines_down":
            fail(f"both engines failed but scenario {sc.scenario_id} status={sc.status}")
        if sc.status == "ok":
            if not sc.sources:
                fail(f"scenario {sc.scenario_id} status=ok but has 0 sources")
            for src in sc.sources:
                if not src.url or not src.title or not src.publisher_tier:
                    fail(f"scenario {sc.scenario_id} has source missing url/title/tier")
        if sc.status == "no_authoritative_coverage":
            if not sc.diagnostics or sc.diagnostics.get("candidates_discovered", 0) <= 0:
                fail(f"scenario {sc.scenario_id} no_authoritative_coverage missing diagnostics")

    print(f"OK — {snap_path.name} valid ({len(snap.scenarios)} scenarios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())