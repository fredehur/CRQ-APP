"""source_librarian — per-run reading list builder for risk-register scenarios.

Public API:
    run_snapshot(register_id, ...)  -> Snapshot
    get_latest_snapshot(register_id) -> Snapshot | None
    list_snapshots(register_id)      -> list[Path]
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from dotenv import load_dotenv
load_dotenv()

from .discovery import EngineStatus, discover_for_scenario, seed_candidates
from .intents import Intent, load_intent, load_publishers
from .queries import build_queries
from .ranker import rank_and_select
from .scraper import ScrapeCache
from .snapshot import (
    OUTPUT_DIR,
    ScenarioResult,
    Snapshot,
    SourceEntry,
    intent_hash,
    list_snapshot_paths,
    read_snapshot,
    write_snapshot,
)
from .summarizer import summarize_pair

logger = logging.getLogger(__name__)


def _build_clients() -> tuple[Optional[Any], Optional[Any], Optional[Any], EngineStatus]:
    """Construct real Tavily / Firecrawl / Anthropic clients from env, if keys present."""
    status = EngineStatus()
    tavily_client = None
    firecrawl_client = None
    haiku_client = None

    if os.environ.get("TAVILY_API_KEY"):
        try:
            from tavily import TavilyClient
            tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        except Exception as exc:
            logger.warning("[source_librarian] tavily init failed: %s", exc)
            status.tavily = "failed"
    else:
        status.tavily = "disabled"

    if os.environ.get("FIRECRAWL_API_KEY"):
        try:
            from firecrawl import FirecrawlApp
            firecrawl_client = FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])
        except Exception as exc:
            logger.warning("[source_librarian] firecrawl init failed: %s", exc)
            status.firecrawl = "failed"
    else:
        status.firecrawl = "failed"

    try:
        import anthropic
        haiku_client = anthropic.Anthropic()
    except Exception as exc:
        logger.warning("[source_librarian] anthropic init failed: %s", exc)
        haiku_client = None

    return tavily_client, firecrawl_client, haiku_client, status


def _query_terms_for(intent: Intent, sid: str) -> list[str]:
    sc = intent.scenarios[sid]
    return [
        sc.threat_terms[0].lower(),
        sc.asset_terms[0].lower().split()[0],
        sc.industry_terms[0].lower().split()[0],
    ]


def run_snapshot(
    register_id: str,
    *,
    on_progress: Optional[Callable[[dict], None]] = None,
    scenario_id: Optional[str] = None,
    debug: bool = False,
    tavily_client: Optional[Any] = None,
    firecrawl_client: Optional[Any] = None,
    haiku_client: Optional[Any] = None,
    today: Optional[date] = None,
) -> Snapshot:
    """Build a reading-list snapshot for one register. External clients are
    injected for testability; if all are None, real clients are constructed from env."""
    intent = load_intent(register_id)
    publishers = load_publishers()
    today = today or date.today()
    started_at = datetime.now(timezone.utc)

    if tavily_client is None and firecrawl_client is None and haiku_client is None:
        tavily_client, firecrawl_client, haiku_client, status = _build_clients()
    else:
        status = EngineStatus()
        if tavily_client is None:
            status.tavily = "disabled"
        if firecrawl_client is None:
            status.firecrawl = "failed"

    query_plan = build_queries(intent, today=today)

    # Filter to one scenario when scenario_id is set
    if scenario_id is not None:
        if scenario_id not in query_plan:
            raise KeyError(f"scenario_id '{scenario_id}' not in intent for '{register_id}'")
        query_plan = {scenario_id: query_plan[scenario_id]}

    scenario_ids = list(query_plan.keys())
    total = len(scenario_ids)

    def _emit(stage: str, sid: str, done_count: int) -> None:
        if on_progress is None:
            return
        on_progress({
            "stage": stage,
            "scenario_id": sid,
            "status": "done",
            "counts": {stage: {"done": done_count, "total": total}},
        })

    # Discovery per scenario (mutates `status` on failure)
    discovered: dict[str, list[dict]] = {}
    for i, (sid, queries) in enumerate(query_plan.items(), 1):
        discovered[sid] = discover_for_scenario(
            news_queries=queries["news_set"],
            doc_queries=queries["doc_set"],
            tavily_client=tavily_client,
            firecrawl_client=firecrawl_client,
            status=status,
        )
        _emit("discovery", sid, i)

    both_failed = (
        status.tavily in ("failed", "disabled")
        and status.firecrawl == "failed"
    )

    # Pre-seeded T1/T2 candidates always injected — seeds act as fallback when engines fail
    seeds = seed_candidates(publishers)

    scenarios_out: list[ScenarioResult] = []

    if both_failed and not seeds:
        for sid in scenario_ids:
            sc = intent.scenarios[sid]
            scenarios_out.append(
                ScenarioResult(
                    scenario_id=sid,
                    scenario_name=sc.name,
                    status="engines_down",
                    sources=[],
                    diagnostics={"reason": "both engines failed"},
                )
            )
    else:
        # Merge seeds into each scenario's candidate pool

        # Rank per scenario
        selections = {
            sid: rank_and_select(
                discovered[sid] + seeds,
                publishers=publishers,
                query_terms=_query_terms_for(intent, sid),
                top_n=10,
                today=today,
            )
            for sid in scenario_ids
        }

        # Scrape top N sources per scenario (not all) to stay within credit limits
        _SCRAPE_TOP_N = 3
        scrape_cache = ScrapeCache(firecrawl_client) if firecrawl_client is not None else None
        unique_urls = {src.url for sel in selections.values() for src in sel.sources[:_SCRAPE_TOP_N]}
        if scrape_cache is not None:
            for url in unique_urls:
                scrape_cache.get(url)

        # Summarize per (scenario × source) — only top _SCRAPE_TOP_N get scraped
        for i, (sid, sel) in enumerate(selections.items(), 1):
            for j, src in enumerate(sel.sources):
                if scrape_cache is None or j >= _SCRAPE_TOP_N:
                    src.scrape_status = "skipped"
                    continue
                scrape = scrape_cache.get(src.url)
                if scrape.status != "ok":
                    src.scrape_status = "failed"
                    continue
                src.scrape_status = "ok"
                if haiku_client is not None:
                    sc = intent.scenarios[sid]
                    summary, figures = summarize_pair(
                        client=haiku_client,
                        scenario_name=sc.name,
                        scenario_notes=sc.notes,
                        markdown=scrape.markdown,
                    )
                    src.summary = summary
                    src.figures = figures
            scenarios_out.append(
                ScenarioResult(
                    scenario_id=sid,
                    scenario_name=intent.scenarios[sid].name,
                    status=sel.status,
                    sources=sel.sources,
                    diagnostics=sel.diagnostics,
                )
            )
            _emit("summarizing", sid, i)

    snap = Snapshot(
        register_id=register_id,
        run_id=str(uuid.uuid4()),
        intent_hash=intent_hash(intent.raw_yaml),
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        tavily_status=status.tavily,  # type: ignore[arg-type]
        firecrawl_status=status.firecrawl,  # type: ignore[arg-type]
        scenarios=scenarios_out,
        debug=None,
    )
    # Skip disk write for per-scenario reruns — caller owns merge + write
    if scenario_id is None:
        write_snapshot(snap)

    return snap


def get_latest_snapshot(register_id: str) -> Optional[Snapshot]:
    paths = list_snapshot_paths(register_id)
    if not paths:
        return None
    return read_snapshot(paths[0])


def list_snapshots(register_id: str) -> list[Path]:
    return list_snapshot_paths(register_id)


__all__ = [
    "run_snapshot",
    "get_latest_snapshot",
    "list_snapshots",
    "Snapshot",
    "ScenarioResult",
    "SourceEntry",
]
