#!/usr/bin/env python3
"""CRQ Comparator — diffs VaCR figures against extracted benchmarks.

Usage:
    crq_comparator.py

Reads:  data/mock_crq_database.json
        data/master_scenarios.json
        data/validation_sources.json
        output/validation_cache/**/*.json
Writes: output/validation_flags.json
        output/validation_flags.md
"""
import glob
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv

load_dotenv()

from tools.config import VALIDATION_CACHE_DIR, VALIDATION_FLAGS_JSON, VALIDATION_FLAGS_MD

CRQ_DB_PATH = Path("data/mock_crq_database.json")
MASTER_SCENARIOS_PATH = Path("data/master_scenarios.json")
SOURCES_PATH = Path("data/validation_sources.json")
CACHE_ROOT = VALIDATION_CACHE_DIR
FLAGS_PATH = VALIDATION_FLAGS_JSON
FLAGS_MD_PATH = VALIDATION_FLAGS_MD

STALE_MONTHS = 18
CHALLENGE_THRESHOLD = 0.50  # 50% deviation triggers "challenged"
REVIEW_THRESHOLD = 2.00     # 200% deviation always flagged for review

# CRQ scenario name → master scenario type keyword mapping
SCENARIO_KEYWORDS = {
    "Ransomware": ["ransomware"],
    "System intrusion": ["scada", "intrusion", "system intrusion", "ip & scada", "ip theft", "telemetry", "disruption", "operational"],
    "Accidental disclosure": ["disclosure", "accidental", "offshore"],
    "Insider misuse": ["insider", "misuse"],
    "DoS attack": ["dos attack", " dos "],
    "Scam or fraud": ["fraud", "scam", "social"],
    "Physical threat": ["physical"],
    "Defacement": ["defacement"],
    "System failure": ["system failure", "failure"],
}


def _map_crq_to_scenario(scenario_name: str) -> str | None:
    name_lower = scenario_name.lower()
    for master, keywords in SCENARIO_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return master
    return None


def _db_hash(path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:8]


def _is_stale(fetched_date_str: str) -> bool:
    try:
        fetched = date.fromisoformat(fetched_date_str)
        months_old = (date.today() - fetched).days / 30
        return months_old > STALE_MONTHS
    except Exception:
        return False


def _load_vacr_by_scenario() -> dict[str, float]:
    """Flatten CRQ database → {master_scenario_type: vacr_usd}."""
    crq = json.loads(CRQ_DB_PATH.read_text(encoding="utf-8"))
    result = {}
    for region_scenarios in crq.values():
        for entry in region_scenarios:
            scenario_name = entry.get("scenario_name", "")
            vacr = float(entry.get("value_at_cyber_risk_usd", 0) or 0)
            master = _map_crq_to_scenario(scenario_name)
            if master and vacr > 0:
                # Keep highest VaCR if multiple regions have same scenario type
                result[master] = max(result.get(master, 0), vacr)
    return result


def _load_benchmarks_by_scenario(sources_by_id: dict) -> dict[str, list[dict]]:
    """Load all cache files → {master_scenario_type: [benchmark_entries]}."""
    result: dict[str, list[dict]] = {}
    files = glob.glob(str(CACHE_ROOT / "**" / "*.json"), recursive=True)

    for path_str in files:
        path = Path(path_str)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        source_id = data.get("source_id", "")
        source_meta = sources_by_id.get(source_id, {})
        admiralty_reliability = source_meta.get("admiralty_reliability", data.get("admiralty", {}).get("reliability", "C"))
        fetched_date = data.get("fetched_date", "")
        admiralty_rating = data.get("admiralty", {}).get("rating", f"{admiralty_reliability}2")

        # Only use A or B reliability sources
        if admiralty_reliability not in ("A", "B"):
            continue

        for bm in data.get("benchmarks", []):
            if bm.get("mock"):
                continue
            scenario_tag = bm.get("scenario_tag", "")
            if scenario_tag not in SCENARIO_KEYWORDS:
                continue
            enriched = {**bm, "source_id": source_id, "fetched_date": fetched_date, "admiralty": admiralty_rating}
            result.setdefault(scenario_tag, []).append(enriched)

    return result


def compare() -> dict:
    vacr_by_scenario = _load_vacr_by_scenario()
    master_scenarios = json.loads(MASTER_SCENARIOS_PATH.read_text(encoding="utf-8"))
    sources_data = json.loads(SOURCES_PATH.read_text(encoding="utf-8")) if SOURCES_PATH.exists() else {}
    sources_by_id = {s["id"]: s for s in sources_data.get("sources", [])}
    benchmarks_by_scenario = _load_benchmarks_by_scenario(sources_by_id)

    today = date.today().isoformat()
    results = []
    summary = {"total_scenarios": 0, "supported": 0, "challenged": 0, "no_data": 0, "stale": 0, "flagged_for_review": 0, "sources_used": 0}

    for scenario_entry in master_scenarios.get("scenarios", []):
        scenario = scenario_entry["incident_type"]
        summary["total_scenarios"] += 1

        our_vacr = vacr_by_scenario.get(scenario)
        benchmarks = benchmarks_by_scenario.get(scenario, [])

        flag = {
            "scenario": scenario,
            "our_vacr_usd": our_vacr,
            "verdict": "no_data",
            "benchmark_range_usd": None,
            "benchmark_median_usd": None,
            "deviation_pct": None,
            "flagged_for_review": False,
            "review_reason": None,
            "supporting_sources": [],
            "last_validated": today,
        }

        if not benchmarks:
            summary["no_data"] += 1
            results.append(flag)
            continue

        # Check staleness — all sources stale?
        fresh = [b for b in benchmarks if not _is_stale(b.get("fetched_date", ""))]
        if not fresh:
            flag["verdict"] = "stale"
            summary["stale"] += 1
            results.append(flag)
            continue

        medians = [b["cost_median_usd"] for b in fresh if b.get("cost_median_usd")]
        lows = [b["cost_low_usd"] for b in fresh if b.get("cost_low_usd")]
        highs = [b["cost_high_usd"] for b in fresh if b.get("cost_high_usd")]

        if not medians:
            summary["no_data"] += 1
            results.append(flag)
            continue

        benchmark_median = sum(medians) / len(medians)
        benchmark_low = min(lows) if lows else None
        benchmark_high = max(highs) if highs else None
        flag["benchmark_median_usd"] = int(benchmark_median)
        flag["benchmark_range_usd"] = [
            int(benchmark_low) if benchmark_low else None,
            int(benchmark_high) if benchmark_high else None,
        ]
        flag["supporting_sources"] = [
            {"source_id": b["source_id"], "fetched_date": b["fetched_date"], "admiralty": b["admiralty"], "note": b.get("note", "")}
            for b in fresh[:3]
        ]

        if our_vacr is None:
            flag["verdict"] = "no_crq_entry"
            results.append(flag)
            continue

        deviation = abs(our_vacr - benchmark_median) / benchmark_median if benchmark_median else 0
        flag["deviation_pct"] = round(deviation * 100, 1)

        if deviation > CHALLENGE_THRESHOLD:
            flag["verdict"] = "challenged"
            summary["challenged"] += 1
        else:
            flag["verdict"] = "supported"
            summary["supported"] += 1

        if deviation > REVIEW_THRESHOLD:
            flag["flagged_for_review"] = True
            summary["flagged_for_review"] += 1
            pct = round(deviation * 100)
            direction = "above" if our_vacr > benchmark_median else "below"
            flag["review_reason"] = (
                f"VaCR is {pct}% {direction} benchmark median — warrants analyst review"
            )

        results.append(flag)

    contributing_ids = {b["source_id"] for bms in benchmarks_by_scenario.values() for b in bms}
    summary["sources_used"] = len(contributing_ids)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "crq_db_hash": _db_hash(CRQ_DB_PATH),
        "scenarios": results,
        "summary": summary,
    }


def _write_markdown(flags: dict) -> None:
    lines = [
        "# CRQ Validation Report",
        f"Generated: {flags['generated_at'][:10]}",
        "",
        "| Scenario | Our VaCR | Verdict | Deviation | Sources |",
        "|---|---|---|---|---|",
    ]
    for s in flags["scenarios"]:
        vacr = f"${s['our_vacr_usd']:,.0f}" if s["our_vacr_usd"] else "—"
        verdict_map = {
            "supported": "✓ SUPPORTED",
            "challenged": "⚠ CHALLENGED",
            "no_data": "— NO DATA",
            "stale": "⏱ STALE",
            "no_crq_entry": "— NO CRQ",
        }
        verdict = verdict_map.get(s["verdict"], s["verdict"])
        dev = f"+{s['deviation_pct']:.0f}%" if s.get("deviation_pct") else "—"
        top_source = ""
        if s["supporting_sources"]:
            src = s["supporting_sources"][0]
            top_source = f"{src['source_id']} {src['admiralty']}"
        lines.append(f"| {s['scenario']} | {vacr} | {verdict} | {dev} | {top_source} |")

    sm = flags["summary"]
    lines += [
        "",
        f"**Summary:** {sm['supported']} supported · {sm['challenged']} challenged · "
        f"{sm['no_data']} no data · {sm['stale']} stale · {sm['flagged_for_review']} flagged · "
        f"{sm['sources_used']} sources",
    ]
    FLAGS_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def run() -> None:
    FLAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    flags = compare()
    FLAGS_PATH.write_text(json.dumps(flags, indent=2), encoding="utf-8")
    _write_markdown(flags)
    sm = flags["summary"]
    print(
        f"[comparator] done — {sm['supported']} supported, {sm['challenged']} challenged, "
        f"{sm['no_data']} no data, {sm['flagged_for_review']} flagged",
        file=sys.stderr,
    )
    print(f"[comparator] flags → {FLAGS_PATH}", file=sys.stderr)


if __name__ == "__main__":
    run()
