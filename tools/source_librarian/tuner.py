"""Auto-tune loop: self-healing discovery for no_authoritative_coverage scenarios."""
from __future__ import annotations

import copy
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .intents import load_intent
from .snapshot import Snapshot
from .tuning_log import append_event


@dataclass
class AutoTuneResult:
    outcome: str   # "found" | "exhausted" | "cancelled"
    iterations_used: int
    cost_usd: float
    winning_diff: Optional[dict] = None
    winning_sources: list[dict] = field(default_factory=list)
    log_entries: list[dict] = field(default_factory=list)


def _apply_diff(scenario_intent: dict, diff: dict) -> dict:
    """Return a NEW dict with diff applied. Original is never mutated."""
    result = copy.deepcopy(scenario_intent)
    for key in ("threat_terms", "asset_terms", "industry_terms"):
        current = list(result.get(key, []))
        adds = diff.get(f"add_{key}", [])
        removes = set(diff.get(f"remove_{key}", []))
        result[key] = [t for t in current if t not in removes] + adds
    return result


def _call_tuner_agent(
    scenario_intent: dict,
    rejected_candidates: list[dict],
    scenario_desc: str,
    prior_attempts: list[dict],
) -> dict:
    """Call Haiku to propose a diff. In tests, this function is patched."""
    import anthropic
    client = anthropic.Anthropic()
    prompt = (
        f"Scenario: {scenario_desc}\n\n"
        f"Current intent scenario:\n{json.dumps(scenario_intent, indent=2)}\n\n"
        f"Rejected candidates:\n{json.dumps(rejected_candidates, indent=2)}\n\n"
        f"Prior diffs tried:\n{json.dumps(prior_attempts, indent=2)}\n\n"
        f"Propose a diff with keys: add_threat_terms, remove_threat_terms, "
        f"add_asset_terms, remove_asset_terms, add_industry_terms, remove_industry_terms, reasoning. "
        f"Respond with ONLY valid JSON."
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _call_validator_agent(
    diff: dict,
    rejected_candidates: list[dict],
    scenario_desc: str,
) -> dict:
    """Call Haiku to validate the diff. In tests, this function is patched."""
    import anthropic
    client = anthropic.Anthropic()
    prompt = (
        f"Scenario: {scenario_desc}\n\n"
        f"Proposed diff:\n{json.dumps(diff, indent=2)}\n\n"
        f"Rejected candidates:\n{json.dumps(rejected_candidates, indent=2)}\n\n"
        f"Approve if terms are on-topic, not hallucinated, and not more narrow. "
        f"Respond with ONLY: {{\"verdict\": \"approved\"|\"rejected\", \"reason\": \"...\"}}"
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _run_discovery_for_scenario(
    register_id: str,
    scenario_id: str,
    modified_intent_sc: dict,
) -> Snapshot:
    """Run discovery+rank for one scenario with an in-memory modified intent.

    The yaml on disk is never read after the initial load.
    In tests, this function is patched.
    """
    from .intents import load_intent, ScenarioIntent
    from . import run_snapshot
    import tools.source_librarian.intents as _intents_mod

    base_intent = load_intent(register_id)
    modified_sc = ScenarioIntent(
        name=modified_intent_sc.get("name", ""),
        threat_terms=modified_intent_sc.get("threat_terms", []),
        asset_terms=modified_intent_sc.get("asset_terms", []),
        industry_terms=modified_intent_sc.get("industry_terms", []),
        time_focus_years=modified_intent_sc.get("time_focus_years", 3),
        notes=modified_intent_sc.get("notes", ""),
    )
    patched_scenarios = {**base_intent.scenarios, scenario_id: modified_sc}
    patched_intent = base_intent.model_copy(update={"scenarios": patched_scenarios})

    original_load = _intents_mod.load_intent

    def _patched_load(reg_id: str):
        return patched_intent if reg_id == register_id else original_load(reg_id)

    _intents_mod.load_intent = _patched_load
    try:
        return run_snapshot(register_id, scenario_id=scenario_id)
    finally:
        _intents_mod.load_intent = original_load


def run_autotune(
    register_id: str,
    scenario_id: str,
    *,
    base_snapshot: Snapshot,
    max_iterations: int = 5,
    max_cost_usd: float = 0.50,
    cancel_event: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> AutoTuneResult:
    """Self-healing discovery loop. Returns on success, budget exhaustion, or cancellation.

    The intent yaml on disk is NEVER mutated.
    """
    run_id = f"autotune-{uuid.uuid4().hex[:8]}"
    intent = load_intent(register_id)
    sc_intent = intent.scenarios.get(scenario_id)
    if sc_intent is None:
        raise KeyError(f"Scenario '{scenario_id}' not in intent for '{register_id}'")

    base_sc = next((s for s in base_snapshot.scenarios if s.scenario_id == scenario_id), None)
    if base_sc is None:
        raise KeyError(f"Scenario '{scenario_id}' not in base_snapshot")

    scenario_desc = sc_intent.name + (f" — {sc_intent.notes}" if sc_intent.notes else "")
    current_sc_dict = sc_intent.model_dump()
    rejected_candidates = (base_sc.diagnostics or {}).get("top_rejected", [])
    prior_attempts: list[dict] = []
    total_cost = 0.0
    log_entries: list[dict] = []
    last_iteration = 0

    for iteration in range(1, max_iterations + 1):
        last_iteration = iteration

        if cancel_event and cancel_event.is_set():
            return AutoTuneResult(
                outcome="cancelled", iterations_used=iteration - 1,
                cost_usd=total_cost, log_entries=log_entries,
            )

        if on_progress:
            on_progress({"event": "iteration_start", "iteration": iteration, "max": max_iterations})

        diff = _call_tuner_agent(current_sc_dict, rejected_candidates, scenario_desc, prior_attempts)
        verdict_resp = _call_validator_agent(diff, rejected_candidates, scenario_desc)
        verdict = verdict_resp.get("verdict", "rejected")

        log_entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "register_id": register_id, "scenario_id": scenario_id,
            "run_id": run_id, "iteration": iteration,
            "event": "proposed", "diff": diff,
            "reasoning": diff.get("reasoning", ""),
            "validator_verdict": verdict, "cost_usd": 0.01,
        }
        append_event(register_id, log_entry)
        log_entries.append(log_entry)
        total_cost += 0.01

        if on_progress:
            on_progress({"event": "diff_proposed", "iteration": iteration,
                         "reasoning": diff.get("reasoning", ""), "verdict": verdict})

        if verdict != "approved":
            prior_attempts.append(diff)
            continue

        modified_sc_dict = _apply_diff(current_sc_dict, diff)
        rerun_snap = _run_discovery_for_scenario(register_id, scenario_id, modified_sc_dict)

        rerun_sc = next((s for s in rerun_snap.scenarios if s.scenario_id == scenario_id), None)
        t1t2_count = len([s for s in (rerun_sc.sources if rerun_sc else [])
                          if s.publisher_tier in ("T1", "T2")])
        new_rejected = (rerun_sc.diagnostics or {}).get("top_rejected", []) if rerun_sc else []

        rerun_entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "register_id": register_id, "scenario_id": scenario_id,
            "run_id": run_id, "iteration": iteration, "event": "rerun_result",
            "candidates_discovered": (rerun_sc.diagnostics or {}).get("candidates_discovered", 0) if rerun_sc else 0,
            "t1_t2_count": t1t2_count,
            "best_rejection": new_rejected[0] if new_rejected else None,
            "cost_usd": 0.04,
        }
        append_event(register_id, rerun_entry)
        log_entries.append(rerun_entry)
        total_cost += 0.04

        if on_progress:
            on_progress({"event": "rerun_result", "iteration": iteration,
                         "t1_t2_count": t1t2_count,
                         "best_rejection": new_rejected[0] if new_rejected else None})

        success = t1t2_count > 0 or (rerun_sc is not None and rerun_sc.status == "ok")
        if success:
            won: dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "register_id": register_id, "scenario_id": scenario_id,
                "run_id": run_id, "iteration": iteration, "event": "succeeded",
                "winning_diff": diff,
                "sources_found": [s.model_dump(mode="json") for s in (rerun_sc.sources if rerun_sc else [])],
                "total_cost_usd": total_cost,
            }
            append_event(register_id, won)
            log_entries.append(won)
            return AutoTuneResult(
                outcome="found", iterations_used=iteration, cost_usd=total_cost,
                winning_diff=diff,
                winning_sources=[s.model_dump(mode="json") for s in (rerun_sc.sources if rerun_sc else [])],
                log_entries=log_entries,
            )

        rejected_candidates = new_rejected
        prior_attempts.append(diff)

        if total_cost >= max_cost_usd:
            break

    return AutoTuneResult(
        outcome="exhausted", iterations_used=last_iteration,
        cost_usd=total_cost, log_entries=log_entries,
    )
