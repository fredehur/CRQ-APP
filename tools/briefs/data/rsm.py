"""Live RSM data loader: joins sites with physical/cyber signals, returns RsmBriefData."""
from __future__ import annotations
from datetime import date

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
)

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "monitor": 3}
_BASELINE_SEVERITY = {"low": "green", "elevated": "amber", "high": "red"}
_BASELINE_LABEL = {"low": "Stable", "elevated": "Watch", "high": "Raised"}


def load_rsm_data(region: str, week_of: str | None = None) -> RsmBriefData:
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

    return RsmBriefData(
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
