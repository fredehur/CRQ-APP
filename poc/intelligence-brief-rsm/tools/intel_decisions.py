#!/usr/bin/env python3
"""tools/intel_decisions.py — per-run transparency log.

Reads the run folder's existing artifacts (seerist_signals.json,
osint_physical_signals.json, osint_dropped.json, claims.json) and writes
`intel_decisions.md` next to them. Pure derivation — no LLM calls — so the
file can be regenerated any time without re-running the pipeline.

What it records:
  - Seerist intake (counts per signal class + which signal_ids the analyst cited)
  - OSINT agent-enrichment outcome (kept vs dropped, with reason per drop)
  - Which kept OSINT signals were cited in claims vs left uncited
  - Final brief composition (claims by pillar / type, distinct signal_ids cited)

Usage:
    uv run python tools/intel_decisions.py <day_dir>

The poc_runner wires this into the --render phase so each run gets a
fresh decisions log alongside email.html.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _read_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _seerist_signal_ids(seerist: dict | None) -> set[str]:
    """Collect every Seerist signal_id the analyst was offered."""
    ids: set[str] = set()
    if not seerist:
        return ids
    situational = seerist.get("situational", {}) or {}
    analytical = seerist.get("analytical", {}) or {}
    for key in ("events", "verified_events", "breaking_news", "news"):
        for e in situational.get(key, []) or []:
            if isinstance(e, dict) and e.get("signal_id"):
                ids.add(e["signal_id"])
    for key in ("hotspots", "scribe"):
        for e in analytical.get(key, []) or []:
            if isinstance(e, dict) and e.get("signal_id"):
                ids.add(e["signal_id"])
    for e in seerist.get("poi_alerts", []) or []:
        if isinstance(e, dict) and e.get("signal_id"):
            ids.add(e["signal_id"])
    for e in seerist.get("cyber_signals", []) or []:
        if isinstance(e, dict) and e.get("signal_id"):
            ids.add(e["signal_id"])
    return ids


def _seerist_counts(seerist: dict | None) -> dict:
    if not seerist:
        return {}
    situational = seerist.get("situational", {}) or {}
    analytical = seerist.get("analytical", {}) or {}
    return {
        "events": len(situational.get("events", []) or []),
        "verified": len(situational.get("verified_events", []) or []),
        "breaking": len(situational.get("breaking_news", []) or []),
        "news": len(situational.get("news", []) or []),
        "hotspots": len(analytical.get("hotspots", []) or []),
        "scribe": len(analytical.get("scribe", []) or []),
        "poi_alerts": len(seerist.get("poi_alerts", []) or []),
        "cyber_signals": len(seerist.get("cyber_signals", []) or []),
        "threat_actors": len(analytical.get("threat_actor_context", []) or []),
    }


def _claims_summary(claims: dict | None) -> dict:
    by_pillar = {"physical": 0, "cyber": 0, "early_warning": 0}
    by_type = {"fact": 0, "assessment": 0, "estimate": 0}
    cited: set[str] = set()
    if not claims:
        return {"total": 0, "by_pillar": by_pillar, "by_type": by_type, "cited": cited}
    for c in claims.get("claims", []) or []:
        pillar = c.get("pillar", "")
        if pillar in by_pillar:
            by_pillar[pillar] += 1
        else:
            by_pillar[pillar] = 1
        ct = c.get("claim_type", "")
        if ct in by_type:
            by_type[ct] += 1
        else:
            by_type[ct] = 1
        for sid in c.get("signal_ids", []) or []:
            cited.add(sid)
    return {
        "total": len(claims.get("claims", []) or []),
        "by_pillar": by_pillar,
        "by_type": by_type,
        "cited": cited,
    }


def render(day_dir: Path) -> str:
    region = day_dir.name.upper()
    date = day_dir.parent.name

    seerist = _read_json(day_dir / "seerist_signals.json")
    osint = _read_json(day_dir / "osint_physical_signals.json")
    dropped_doc = _read_json(day_dir / "osint_dropped.json")
    claims = _read_json(day_dir / "claims.json")

    seerist_counts = _seerist_counts(seerist)
    seerist_ids = _seerist_signal_ids(seerist)

    osint_kept_signals = (osint or {}).get("signals", []) or []
    osint_ids = {s.get("signal_id") for s in osint_kept_signals if isinstance(s, dict) and s.get("signal_id")}
    dropped_rows = (dropped_doc or {}).get("dropped", []) or []

    cs = _claims_summary(claims)
    cited = cs["cited"]

    seerist_cited = seerist_ids & cited
    seerist_uncited = seerist_ids - cited
    osint_cited = osint_ids & cited
    osint_uncited = osint_ids - cited

    lines: list[str] = []
    lines.append(f"# {region} {date} — Intel decisions log")
    lines.append("")
    lines.append(
        "Audit trail for this run. Records what intel was pulled, what the analyst "
        "used, and what was dropped (with reasons). Derived from the run folder's "
        "artifacts — re-run `tools/intel_decisions.py` to regenerate."
    )
    lines.append("")

    # ── Seerist
    lines.append("## Seerist (top-tier)")
    lines.append("")
    if seerist is None:
        lines.append("_`seerist_signals.json` not found — no Seerist data this run._")
    else:
        c = seerist_counts

        def _p(n: int, singular: str, plural: str | None = None) -> str:
            return f"{n} {singular if n == 1 else (plural or singular + 's')}"

        lines.append(
            "Pulled: "
            f"{_p(c['events'], 'event')} · "
            f"{_p(c['verified'], 'verified')} · "
            f"{_p(c['breaking'], 'breaking')} · "
            f"{_p(c['news'], 'news', 'news')} · "
            f"{_p(c['hotspots'], 'hotspot')} · "
            f"{_p(c['scribe'], 'scribe note')} · "
            f"{_p(c['poi_alerts'], 'POI alert')} · "
            f"{_p(c['cyber_signals'], 'cyber signal')} · "
            f"{_p(c['threat_actors'], 'actor')} in watchlist"
        )
        lines.append("")
        lines.append(
            f"**Cited in claims:** {len(seerist_cited)} of {len(seerist_ids)} discrete Seerist signal_ids."
        )
        if seerist_uncited:
            lines.append("")
            lines.append("**Uncited (offered but not picked up by the analyst):**")
            for sid in sorted(seerist_uncited):
                lines.append(f"- `{sid}`")
    lines.append("")

    # ── OSINT
    lines.append("## OSINT physical-pillar (Tavily + Firecrawl)")
    lines.append("")
    if osint is None:
        lines.append("_`osint_physical_signals.json` not found — OSINT was disabled or skipped this run._")
    else:
        kept = len(osint_kept_signals)
        dropped = len(dropped_rows)
        total = kept + dropped
        lines.append(
            f"**Agent enrichment outcome:** {kept} kept · {dropped} dropped (of {total} raw signals)"
        )
        lines.append("")
        lines.append(
            f"**Cited in claims:** {len(osint_cited)} of {len(osint_ids)} kept OSINT signals."
        )
        if osint_uncited:
            lines.append("")
            lines.append("**Uncited kept signals (passed enrichment but no claim cited them):**")
            for sid in sorted(osint_uncited):
                lines.append(f"- `{sid}`")
        if dropped_rows:
            lines.append("")
            lines.append("### Drops (with reasons)")
            lines.append("")
            lines.append("| # | Title | URL | Reason |")
            lines.append("|---|---|---|---|")
            for i, row in enumerate(dropped_rows, 1):
                title = ((row.get("title") or "")[:80]).replace("|", "\\|").replace("\n", " ")
                url = (row.get("url") or "").replace("|", "\\|")
                reason = (row.get("relevance_reason") or "").replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {i} | {title} | {url} | {reason} |")
        lines.append("")
        lines.append(
            "> Collector-layer drops (Tavily score floor, broken titles, exclude-domains, scrape failures) "
            "happen before signals reach this file. A separate `osint_collector_stats.json` would capture those — "
            "currently deferred as a follow-up."
        )
    lines.append("")

    # ── Final brief composition
    lines.append("## Final brief composition")
    lines.append("")
    if claims is None:
        lines.append("_`claims.json` not found — brief not yet authored or claim authoring failed._")
    else:
        bp = cs["by_pillar"]
        bt = cs["by_type"]
        lines.append(
            f"{cs['total']} claims total: "
            f"{bp.get('physical', 0)} physical · "
            f"{bp.get('cyber', 0)} cyber · "
            f"{bp.get('early_warning', 0)} early-warning"
        )
        lines.append("")
        lines.append(
            f"By claim type: {bt.get('fact', 0)} fact · "
            f"{bt.get('assessment', 0)} assessment · "
            f"{bt.get('estimate', 0)} estimate"
        )
        lines.append("")
        lines.append(f"Distinct signal_ids cited: {len(cited)}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "**How to read this:** the brief is the polished output. This file is the audit "
        "trail — every kept and dropped signal is explainable. If a drop looks wrong, the "
        "reason text is the enrichment-pass verdict; tune the enrichment prompt and re-run."
    )
    lines.append("")

    return "\n".join(lines)


def write(day_dir: Path) -> Path:
    out = day_dir / "intel_decisions.md"
    out.write_text(render(day_dir), encoding="utf-8")
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: intel_decisions.py <day_dir>", file=sys.stderr)
        return 1
    day_dir = Path(sys.argv[1]).resolve()
    if not day_dir.exists():
        print(f"[intel_decisions] day_dir does not exist: {day_dir}", file=sys.stderr)
        return 1
    out = write(day_dir)
    print(f"[intel_decisions] wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
