"""Live RSM data loader: joins sites with physical/cyber signals, returns RsmBriefData."""
from __future__ import annotations
import re
from datetime import date
from pathlib import Path

from tools.briefs.loaders import (
    load_sites_for_region,
    load_physical_signals,
    load_cyber_indicators,
    load_calendar,
)
from tools.briefs.joins import proximity_hits, pattern_hits, actor_hits, calendar_ahead
from tools.briefs.models import (
    SiteContext,
    SiteComputed,
    SiteNarrative,
    SiteBlock,
    SiteBaseline,
    CyberCalloutComputed,
    RsmBriefData,
    CoverMeta,
    CountryPulse,
    RankedEvent,
    CyberStripItem,
    TocEntry,
    RegionalCyberPage,
    SecondarySite,
    MinorSiteRow,
    PhysicalEvidence,
    CyberEvidence,
    JoinedEvent,
    CyberIndicator,
    SiteForNarration,
    WeeklySynthesisInput,
    WeeklySynthesisOutput,
)

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "monitor": 3}
_BASELINE_SEVERITY = {"low": "green", "elevated": "amber", "high": "red"}
_BASELINE_LABEL = {"low": "Stable", "elevated": "Watch", "high": "Raised"}


def load_rsm_data(region: str, week_of: str | None = None, narrate: bool = False) -> RsmBriefData:
    reg = region.upper()
    sites = load_sites_for_region(reg)
    phys = load_physical_signals(reg)
    cyb = load_cyber_indicators(reg)
    calendar = load_calendar(reg)

    primary_sites = [s for s in sites if s.resolved_tier in ("crown_jewel", "primary")]
    site_blocks: list[SiteBlock] = []
    for ctx in primary_sites:
        computed = SiteComputed(
            baseline=_baseline_for(ctx),
            proximity_hits=proximity_hits(ctx, phys),
            pattern_hits=pattern_hits(ctx, phys),
            actor_hits=actor_hits(ctx, phys),
            calendar_ahead=calendar_ahead(ctx, calendar),
            cyber_callout_computed=_match_cyber(ctx, cyb),
        )
        narrative = SiteNarrative(
            standing_notes_synthesis=None,
            pattern_framing=None,
            cyber_callout_text=None,
        )
        site_blocks.append(SiteBlock(context=ctx, computed=computed, narrative=narrative))

    brief = RsmBriefData(
        cover=_build_cover(reg, week_of),
        admiralty_physical="B3",
        admiralty_cyber="B3",
        headline=_placeholder_headline(reg),
        baseline_strip=_build_baseline_strip(sites),
        top_events=_rank_region_events(site_blocks),
        cyber_strip=_build_cyber_strip(cyb),
        baselines_moved=[],
        reading_guide=_build_reading_guide(site_blocks, sites),
        sites=site_blocks,
        regional_cyber=_build_regional_cyber(cyb),
        secondary_sites=_build_secondary(sites, phys),
        minor_sites=_build_minor(sites, phys),
        evidence_physical=_build_evidence_phys(phys, site_blocks),
        evidence_cyber=_build_evidence_cyb(cyb),
    )
    if narrate:
        from datetime import date as _date
        iso = _date.today().isocalendar()
        resolved_week = week_of or f"{iso[0]}-W{iso[1]:02d}"
        brief = _narrate(brief, reg, resolved_week)
    return brief


def _build_cover(region: str, week_of: str | None) -> CoverMeta:
    today = date.today()
    iso = today.isocalendar()
    week_label = week_of or f"{iso[0]}-W{iso[1]:02d}"
    return CoverMeta(
        title=f"AeroGrid · RSM Weekly INTSUM · {region} · {week_label}",
        classification="RESTRICTED — RSM DISTRIBUTION",
        prepared_by="Intelligence Cell",
        reviewed_by="Regional Director",
        issued_at=today,
        version="v1.0",
    )


def _baseline_for(ctx: SiteContext) -> SiteBaseline:
    days = 999
    if ctx.last_incident:
        try:
            inc_date = date.fromisoformat(ctx.last_incident["date"])
            days = (date.today() - inc_date).days
        except (KeyError, ValueError):
            pass
    return SiteBaseline(
        pulse_label=_BASELINE_LABEL.get(ctx.host_country_risk_baseline, "Watch"),
        pulse_severity=_BASELINE_SEVERITY.get(ctx.host_country_risk_baseline, "amber"),
        forecast_arrow="→",
        days_since_incident=days,
        admiralty="B3",
        host_baseline=ctx.host_country_risk_baseline,
    )


def _match_cyber(ctx: SiteContext, cyb: list[CyberIndicator]) -> CyberCalloutComputed | None:
    if not ctx.site_cyber_actors_of_interest:
        return None
    for ind in cyb:
        low = ind.text.lower()
        if any(kw in low for kw in ("ot", "scada", "volt", "sandworm", "apt")):
            return CyberCalloutComputed(
                cve_or_actor="OT/ICS actor activity in region",
                match_kind="actor",
            )
    return None


def _build_baseline_strip(sites: list[SiteContext]) -> list[CountryPulse]:
    seen: set[str] = set()
    result = []
    for site in sites:
        code = site.seerist_country_code or site.country
        if code not in seen:
            seen.add(code)
            result.append(CountryPulse(
                country=code,
                pulse_label=_BASELINE_LABEL.get(site.host_country_risk_baseline, "Watch"),
                pulse_severity=_BASELINE_SEVERITY.get(site.host_country_risk_baseline, "amber"),
                forecast_arrow="→",
                note=site.standing_notes[:80] if site.standing_notes else "",
            ))
    return result


def _rank_region_events(site_blocks: list[SiteBlock]) -> list[RankedEvent]:
    seen_ids: set[str] = set()
    events = []
    for block in site_blocks:
        for hit in block.computed.proximity_hits:
            if hit.signal_id not in seen_ids:
                seen_ids.add(hit.signal_id)
                events.append(RankedEvent(
                    what=hit.headline,
                    where=hit.where,
                    when=hit.when,
                    severity_short=hit.severity[:3].upper(),
                    severity=hit.severity,
                    distance_km=hit.distance_km,
                    nearest_site=block.context.name,
                    ref=hit.ref,
                ))
    events.sort(key=lambda e: (_SEVERITY_RANK.get(e.severity, 3), e.distance_km or 999))
    return events[:8]


def _build_cyber_strip(cyb: list[CyberIndicator]) -> list[CyberStripItem]:
    result = []
    for ind in cyb[:5]:
        low = ind.text.lower()
        if any(kw in low for kw in ("volt typhoon", "sandworm", "apt")):
            kind: str = "ACTOR"
        elif any(kw in low for kw in ("cve-", "vulnerability", "patch")):
            kind = "CVE"
        else:
            kind = "SECTOR"
        result.append(CyberStripItem(
            kind=kind,
            text=ind.text[:120],
            ref=ind.signal_id,
        ))
    return result


def _build_reading_guide(
    site_blocks: list[SiteBlock], all_sites: list[SiteContext]
) -> list[TocEntry]:
    entries = []
    for block in site_blocks:
        entries.append(TocEntry(
            group=block.context.resolved_tier.replace("_", " ").title(),
            title=block.context.name,
            page_ref="—",
        ))
    secondary = [s for s in all_sites if s.resolved_tier == "secondary"]
    if secondary:
        entries.append(TocEntry(group="Secondary", title=f"{len(secondary)} sites", page_ref="—"))
    minor = [s for s in all_sites if s.resolved_tier == "minor"]
    if minor:
        entries.append(TocEntry(group="Minor", title=f"{len(minor)} sites", page_ref="—"))
    return entries


def _build_regional_cyber(cyb: list[CyberIndicator]) -> RegionalCyberPage:
    actor_signals: list[JoinedEvent] = []
    sector_signals: list[JoinedEvent] = []
    today_str = date.today().isoformat()
    for ind in cyb[:4]:
        je = JoinedEvent(
            signal_id=ind.signal_id,
            headline=ind.text[:120],
            where="Regional",
            when=today_str,
            severity="medium",
            distance_km=None,
            ref=ind.signal_id,
            join_reason="cyber",
        )
        low = ind.text.lower()
        if any(kw in low for kw in ("volt", "sandworm", "apt", "nation-state")):
            actor_signals.append(je)
        else:
            sector_signals.append(je)
    return RegionalCyberPage(
        admiralty="B3",
        actors_count=len(actor_signals),
        cves_on_watch=0,
        active_campaigns=len(actor_signals),
        standing_notes="",
        sector_signal=sector_signals,
        actor_activity=actor_signals,
        geography_overlay=[],
        vulnerability_signal=[],
    )


def _build_secondary(sites, phys) -> list[SecondarySite]:
    result = []
    for ctx in [s for s in sites if s.resolved_tier == "secondary"]:
        hits = proximity_hits(ctx, phys)[:2]
        result.append(SecondarySite(
            name=ctx.name,
            country=ctx.country,
            country_lead=ctx.resolved_country_lead.get("name", ctx.name),
            pulse_label=_BASELINE_LABEL.get(ctx.host_country_risk_baseline, "Watch"),
            pulse_severity=_BASELINE_SEVERITY.get(ctx.host_country_risk_baseline, "amber"),
            forecast_arrow="→",
            events=hits,
        ))
    return result


def _build_minor(sites, phys) -> list[MinorSiteRow]:
    result = []
    for ctx in [s for s in sites if s.resolved_tier == "minor"]:
        hits = proximity_hits(ctx, phys)
        result.append(MinorSiteRow(
            name=ctx.name,
            country_code=ctx.country,
            pulse_label=_BASELINE_LABEL.get(ctx.host_country_risk_baseline, "Watch"),
            pulse_severity=_BASELINE_SEVERITY.get(ctx.host_country_risk_baseline, "amber"),
            forecast_arrow="→",
            delta_count=len(hits),
            note=ctx.standing_notes[:80] if ctx.standing_notes else "No events this week.",
        ))
    return result


def _build_evidence_phys(phys, site_blocks) -> list[PhysicalEvidence]:
    seen_ids: set[str] = set()
    result = []
    sig_index = {s.signal_id: s for s in phys}
    for block in site_blocks:
        all_hits = block.computed.proximity_hits + block.computed.pattern_hits
        for hit in all_hits:
            if hit.signal_id not in seen_ids:
                seen_ids.add(hit.signal_id)
                sig = sig_index.get(hit.signal_id)
                result.append(PhysicalEvidence(
                    ref=hit.ref,
                    headline=hit.headline,
                    source=sig.outlet if sig and sig.outlet else "unknown",
                    admiralty="B3",
                    timestamp=hit.when,
                    why="",
                ))
    return result[:10]


def _build_evidence_cyb(cyb: list[CyberIndicator]) -> list[CyberEvidence]:
    result = []
    today_str = date.today().isoformat()
    for ind in cyb[:5]:
        result.append(CyberEvidence(
            ref=ind.signal_id,
            headline=ind.text[:120],
            source=ind.source_name or "unknown",
            admiralty="B3",
            timestamp=today_str,
            why="",
        ))
    return result


def _placeholder_headline(region: str) -> str:
    return f"{region} — regional intelligence summary for w/e {date.today().isoformat()}."


# ---- Phase 8.3: agent narration ----

_AGENT_PROMPT: str | None = None
_AGENT_MD = Path(__file__).resolve().parents[3] / ".claude" / "agents" / "rsm-weekly-synthesizer.md"


def _get_agent_prompt() -> str:
    global _AGENT_PROMPT
    if _AGENT_PROMPT is not None:
        return _AGENT_PROMPT
    raw = _AGENT_MD.read_text(encoding="utf-8")
    if raw.startswith("---"):
        end = raw.index("---", 3)
        raw = raw[end + 3:].strip()
    _AGENT_PROMPT = raw
    return _AGENT_PROMPT


def _build_synthesis_input(
    brief: RsmBriefData, region: str, week_of: str
) -> WeeklySynthesisInput:
    sites_to_narrate = []
    for block in brief.sites:
        ctx = block.context
        comp = block.computed
        sites_to_narrate.append(SiteForNarration(
            id=ctx.site_id,
            name=ctx.name,
            tier=ctx.resolved_tier,
            country=ctx.country,
            country_lead=ctx.resolved_country_lead,
            criticality_drivers=ctx.criticality_drivers,
            standing_notes_static=ctx.standing_notes,
            pulse_label=comp.baseline.pulse_label,
            pulse_severity=comp.baseline.pulse_severity,
            forecast_arrow=comp.baseline.forecast_arrow,
            host_baseline=comp.baseline.host_baseline,
            days_since_incident=comp.baseline.days_since_incident,
            proximity_hits=list(comp.proximity_hits),
            pattern_hits=list(comp.pattern_hits),
            actor_hits=list(comp.actor_hits),
            calendar_ahead=list(comp.calendar_ahead),
            cyber_event_to_attach=comp.cyber_callout_computed,
        ))
    evidence_entries = [
        {"ref": e.ref, "headline": e.headline, "source": e.source,
         "admiralty": e.admiralty, "timestamp": e.timestamp}
        for e in list(brief.evidence_physical) + list(brief.evidence_cyber)
    ]
    return WeeklySynthesisInput(
        region=region,
        week_of=week_of,
        regional_admiralty_physical=brief.admiralty_physical,
        regional_admiralty_cyber=brief.admiralty_cyber,
        baseline_strip=list(brief.baseline_strip),
        top_events=list(brief.top_events),
        baselines_moved=list(brief.baselines_moved),
        sites_to_narrate=sites_to_narrate,
        regional_cyber_context=brief.regional_cyber,
        evidence_entries=evidence_entries,
    )


def _call_synthesizer(synth_input: WeeklySynthesisInput) -> WeeklySynthesisOutput:
    import anthropic as _anthropic

    client = _anthropic.Anthropic()
    data_json = synth_input.model_dump_json(indent=2)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=_get_agent_prompt(),
        messages=[{"role": "user", "content": f"<data>\n{data_json}\n</data>"}],
    )
    text = response.content[0].text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    return WeeklySynthesisOutput.model_validate_json(text)


def _apply_narration(brief: RsmBriefData, output: WeeklySynthesisOutput) -> RsmBriefData:
    site_narr = {sn.site_id: sn for sn in output.sites_narrative}

    new_sites = []
    for block in brief.sites:
        narr_out = site_narr.get(block.context.site_id)
        new_narr = SiteNarrative(
            standing_notes_synthesis=narr_out.standing_notes_synthesis if narr_out else None,
            pattern_framing=narr_out.pattern_framing if narr_out else None,
            cyber_callout_text=narr_out.cyber_callout_text if narr_out else None,
        )
        new_sites.append(SiteBlock(
            context=block.context,
            computed=block.computed,
            narrative=new_narr,
        ))

    why = output.evidence_why_lines
    new_phys = [
        PhysicalEvidence(
            ref=e.ref, headline=e.headline, source=e.source,
            admiralty=e.admiralty, timestamp=e.timestamp,
            why=why.get(e.ref, e.why),
        )
        for e in brief.evidence_physical
    ]
    new_cyb = [
        CyberEvidence(
            ref=e.ref, headline=e.headline, source=e.source,
            admiralty=e.admiralty, timestamp=e.timestamp,
            why=why.get(e.ref, e.why),
        )
        for e in brief.evidence_cyber
    ]

    regional_cyber = brief.regional_cyber
    if output.regional_cyber_standing_notes:
        regional_cyber = RegionalCyberPage(
            admiralty=regional_cyber.admiralty,
            actors_count=regional_cyber.actors_count,
            cves_on_watch=regional_cyber.cves_on_watch,
            active_campaigns=regional_cyber.active_campaigns,
            standing_notes=output.regional_cyber_standing_notes,
            sector_signal=list(regional_cyber.sector_signal),
            actor_activity=list(regional_cyber.actor_activity),
            geography_overlay=list(regional_cyber.geography_overlay),
            vulnerability_signal=list(regional_cyber.vulnerability_signal),
        )

    return RsmBriefData(
        cover=brief.cover,
        admiralty_physical=brief.admiralty_physical,
        admiralty_cyber=brief.admiralty_cyber,
        headline=output.headline,
        baseline_strip=list(brief.baseline_strip),
        top_events=list(brief.top_events),
        cyber_strip=list(brief.cyber_strip),
        baselines_moved=list(brief.baselines_moved),
        reading_guide=list(brief.reading_guide),
        sites=new_sites,
        regional_cyber=regional_cyber,
        secondary_sites=list(brief.secondary_sites),
        minor_sites=list(brief.minor_sites),
        evidence_physical=new_phys,
        evidence_cyber=new_cyb,
    )


def _narrate(brief: RsmBriefData, region: str, week_of: str) -> RsmBriefData:
    synth_input = _build_synthesis_input(brief, region, week_of)
    output = _call_synthesizer(synth_input)
    return _apply_narration(brief, output)
