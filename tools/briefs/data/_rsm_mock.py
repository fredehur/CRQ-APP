"""Static mock for RSM MED Weekly INTSUM 2026-W17.

Transcribes `docs/design/handoff/RSM Weekly INTSUM MED.html` field-by-field into
Pydantic instances. Used by `build_pdf.py --brief rsm --mock` until the live
loader in `tools/briefs/data/rsm.py` ships in Phase 7.
"""
from __future__ import annotations
from datetime import date

from tools.briefs.models import (
    BaselineDelta,
    CountryPulse,
    CoverMeta,
    CyberCalloutComputed,
    CyberEvidence,
    CyberStripItem,
    JoinedEvent,
    MinorSiteRow,
    PhysicalEvidence,
    RankedEvent,
    RegionalCyberPage,
    RsmBriefData,
    SecondarySite,
    SiteBaseline,
    SiteBlock,
    SiteComputed,
    SiteContext,
    SiteNarrative,
    TocEntry,
)


def _cape_wind() -> SiteBlock:
    context = SiteContext(
        site_id="MED-CAPEWIND",
        name="Cape Wind",
        region="MED",
        country="Morocco",
        lat=33.58,
        lon=-7.62,
        poi_radius_km=50,
        type="wind_farm",
        subtype="onshore",
        shift_pattern="24/7",
        criticality="crown_jewel",
        personnel_count=142,
        expat_count=38,
        site_lead={"name": "S. Ouazzani", "phone": "+212-555-0101"},
        tier="crown_jewel",
        criticality_drivers=(
            "Single largest MED offtake node. 620 MW nameplate. "
            "Downstream: Moroccan national grid balancing."
        ),
        downstream_dependency="Moroccan national grid balancing",
        asset_type="wind_farm",
        status="active",
        seerist_country_code="MA",
        contractors_count=51,
        country_lead={
            "name": "S. Ouazzani",
            "email": "s.ouazzani@aerogrid.internal",
            "phone": "+212-555-0101",
        },
        host_country_risk_baseline="elevated",
        standing_notes=(
            "Watch cadence raised for election window through May 6. "
            "Country lead coordinating with local police liaison."
        ),
        relevant_seerist_categories=["civil_unrest", "sabotage", "elections"],
        threat_actors_of_interest=[701, 704],
        relevant_attack_types=[12, 18, 22],
        ot_stack=[{"vendor": "Vendor X", "product": "Turbine SCADA", "version": "4.2"}],
    )
    computed = SiteComputed(
        baseline=SiteBaseline(
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="↘",
            days_since_incident=67,
            admiralty="B2",
            host_baseline="Elevated · MA",
        ),
        proximity_hits=[
            JoinedEvent(
                signal_id="SIG-E1",
                headline="Casablanca unrest — protest escalation in commercial district",
                where="Casablanca, MA",
                when="2026-04-22",
                severity="medium",
                distance_km=18.0,
                ref="E1",
                join_reason="Within 50 km POI of Cape Wind",
            ),
            JoinedEvent(
                signal_id="SIG-E3",
                headline="Sabotage arrest — four detained near Agadir grid infrastructure",
                where="Agadir province, MA",
                when="2026-04-24",
                severity="high",
                distance_km=35.0,
                ref="E3",
                join_reason="Sibling-site proximity — Agadir Substation",
            ),
        ],
        pattern_hits=[
            JoinedEvent(
                signal_id="SIG-PAT-MA30",
                headline=(
                    "Two energy-sector sabotage arrests in MA past 30 days — "
                    "pattern consistent with elevated pre-election posture."
                ),
                where="MA · country-level",
                when="30D ROLLING",
                severity="high",
                distance_km=None,
                ref="E7,E8",
                join_reason="Relevant attack types · MA / 30d",
            ),
        ],
        actor_hits=[
            JoinedEvent(
                signal_id="SIG-E9",
                headline=(
                    "FAM-7 activity up — anti-infrastructure leaflets distributed in "
                    "Casablanca; call for \u201caction\u201d during election week."
                ),
                where="Casablanca, MA",
                when="2026-04-22",
                severity="medium",
                distance_km=None,
                ref="E9",
                join_reason="FAM-7 in threat_actors_of_interest",
            ),
        ],
        calendar_ahead=[],
        cyber_callout_computed=CyberCalloutComputed(
            cve_or_actor="APT28",
            match_kind="host-country scanning — MA energy sector",
        ),
    )
    narrative = SiteNarrative(
        standing_notes_synthesis=None,
        pattern_framing=None,
        cyber_callout_text=(
            "APT28 scanning MA energy sector; no Cape Wind telemetry anomalies "
            "observed to date."
        ),
    )
    # Calendar item for the Moroccan general election
    from tools.briefs.models import CalendarItem

    computed = SiteComputed(
        baseline=computed.baseline,
        proximity_hits=computed.proximity_hits,
        pattern_hits=computed.pattern_hits,
        actor_hits=computed.actor_hits,
        calendar_ahead=[
            CalendarItem(
                label=(
                    "Moroccan general election — national polls; post-result "
                    "demonstrations routine in Casablanca/Rabat axis."
                ),
                date_str="2026-04-30",
                horizon_days=10,
            ),
        ],
        cyber_callout_computed=computed.cyber_callout_computed,
    )
    return SiteBlock(context=context, computed=computed, narrative=narrative)


def _taranto_offshore() -> SiteBlock:
    context = SiteContext(
        site_id="MED-TARANTO",
        name="Taranto Offshore",
        region="MED",
        country="Italy",
        lat=40.47,
        lon=17.24,
        poi_radius_km=50,
        type="wind_farm",
        subtype="floating_offshore",
        shift_pattern="24/7",
        criticality="crown_jewel",
        personnel_count=89,
        expat_count=11,
        site_lead={"name": "L. Ferrari", "phone": "+39-555-0202"},
        tier="crown_jewel",
        criticality_drivers=(
            "Italian south grid stability; first commercial floating offshore in "
            "AeroGrid portfolio."
        ),
        downstream_dependency="Italian south grid stability",
        asset_type="wind_farm",
        status="active",
        seerist_country_code="IT",
        contractors_count=34,
        country_lead={
            "name": "L. Ferrari",
            "email": "l.ferrari@aerogrid.internal",
            "phone": "+39-555-0202",
        },
        host_country_risk_baseline="low",
        standing_notes=(
            "Quiet week. Routine maintenance on WTG-14 completes 2026-04-25."
        ),
        relevant_seerist_categories=["labor_action", "weather"],
        threat_actors_of_interest=[704],
        relevant_attack_types=[18, 22],
        ot_stack=[{"vendor": "Vendor X", "product": "Turbine SCADA", "version": "4.2"}],
    )
    from tools.briefs.models import CalendarItem

    computed = SiteComputed(
        baseline=SiteBaseline(
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            days_since_incident=214,
            admiralty="B2",
            host_baseline="Low · IT",
        ),
        proximity_hits=[
            JoinedEvent(
                signal_id="SIG-E2",
                headline=(
                    "Taranto port labour strike — USB 48h action; gate access delays "
                    "likely Wed–Thu."
                ),
                where="Port of Taranto, IT · on-site",
                when="2026-04-23",
                severity="medium",
                distance_km=0.0,
                ref="E2",
                join_reason="On-site impact",
            ),
        ],
        pattern_hits=[],
        actor_hits=[],
        calendar_ahead=[
            CalendarItem(
                label=(
                    "Storm system — Ionian low-pressure front forecast landfall "
                    "Sun–Mon; crew-transfer vessel windows tight."
                ),
                date_str="2026-04-26",
                horizon_days=5,
            ),
        ],
        cyber_callout_computed=None,
    )
    narrative = SiteNarrative(
        standing_notes_synthesis=None,
        pattern_framing=None,
        cyber_callout_text=None,
    )
    return SiteBlock(context=context, computed=computed, narrative=narrative)


def _agadir_substation() -> SiteBlock:
    context = SiteContext(
        site_id="MED-AGADIR",
        name="Agadir Substation",
        region="MED",
        country="Morocco",
        lat=30.43,
        lon=-9.60,
        poi_radius_km=40,
        type="substation",
        subtype="grid_node",
        shift_pattern="24/7",
        criticality="major",
        personnel_count=24,
        expat_count=3,
        site_lead={"name": "S. Ouazzani", "phone": "+212-555-0101"},
        tier="primary",
        criticality_drivers=(
            "Critical grid node for southern MA offtake from Cape Wind."
        ),
        downstream_dependency="Southern MA offtake from Cape Wind",
        asset_type="substation",
        status="active",
        seerist_country_code="MA",
        contractors_count=12,
        country_lead={
            "name": "S. Ouazzani",
            "email": "s.ouazzani@aerogrid.internal",
            "phone": "+212-555-0101",
        },
        host_country_risk_baseline="elevated",
        standing_notes="",
        relevant_seerist_categories=["civil_unrest", "sabotage"],
        threat_actors_of_interest=[701, 704],
        relevant_attack_types=[12, 18],
        ot_stack=[{"vendor": "Vendor Y", "product": "Grid HMI", "version": "3.1"}],
    )
    computed = SiteComputed(
        baseline=SiteBaseline(
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="↘",
            days_since_incident=120,
            admiralty="B2",
            host_baseline="Elevated · MA",
        ),
        proximity_hits=[
            JoinedEvent(
                signal_id="SIG-E3",
                headline="Sabotage arrest — four detained near Agadir grid infrastructure.",
                where="Agadir province, MA",
                when="2026-04-24",
                severity="high",
                distance_km=35.0,
                ref="E3",
                join_reason="Within 50 km POI of Agadir Substation",
            ),
        ],
        pattern_hits=[
            JoinedEvent(
                signal_id="SIG-PAT-MA30",
                headline=(
                    "Two MA energy-sector sabotage arrests past 30 days — "
                    "country-level pattern."
                ),
                where="MA · country-level",
                when="30D ROLLING",
                severity="high",
                distance_km=None,
                ref="E7,E8",
                join_reason="Relevant attack types · MA / 30d",
            ),
        ],
        actor_hits=[],
        calendar_ahead=[],
        cyber_callout_computed=CyberCalloutComputed(
            cve_or_actor="APT28",
            match_kind="credential-harvesting watch — SCADA gateways",
        ),
    )
    narrative = SiteNarrative(
        standing_notes_synthesis=None,
        pattern_framing=None,
        cyber_callout_text=(
            "APT28 scanning MA energy sector. Watch for credential-harvesting "
            "attempts against remote SCADA gateways."
        ),
    )
    return SiteBlock(context=context, computed=computed, narrative=narrative)


def _baseline_strip() -> list[CountryPulse]:
    return [
        CountryPulse(
            country="Morocco · MA",
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="↘",
            note="Forecast declining",
        ),
        CountryPulse(
            country="Italy · IT",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            note="Steady",
        ),
        CountryPulse(
            country="Egypt · EG",
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="↗",
            note="Elevated",
        ),
        CountryPulse(
            country="Spain · ES",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            note="Stable",
        ),
        CountryPulse(
            country="Greece · GR",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            note="Stable",
        ),
        CountryPulse(
            country="Region · MED",
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="↘",
            note="Mixed · trending down",
        ),
    ]


def _top_events() -> list[RankedEvent]:
    return [
        RankedEvent(
            what=(
                "Protest escalation — anti-government demonstration turned violent in "
                "Casablanca commercial district"
            ),
            where="Casablanca, MA",
            when="2026-04-22",
            severity_short="Medium",
            severity="medium",
            distance_km=18.0,
            nearest_site="Cape Wind · 18 km",
            ref="E1",
        ),
        RankedEvent(
            what=(
                "Port labour strike — USB dockworkers 48-hour action over collective "
                "agreement"
            ),
            where="Taranto, IT",
            when="2026-04-23",
            severity_short="Medium",
            severity="medium",
            distance_km=0.0,
            nearest_site="Taranto Offshore · on-site",
            ref="E2",
        ),
        RankedEvent(
            what=(
                "Sabotage arrest — four detained near Agadir grid infrastructure; "
                "DGST announcement pending"
            ),
            where="Agadir province, MA",
            when="2026-04-24",
            severity_short="High",
            severity="high",
            distance_km=35.0,
            nearest_site="Agadir Substation · 35 km",
            ref="E3",
        ),
        RankedEvent(
            what=(
                "Storm system — eastern Med low-pressure front, 5-day forecast "
                "landfall Ionian coast"
            ),
            where="Ionian Sea",
            when="2026-04-26+",
            severity_short="Medium",
            severity="medium",
            distance_km=None,
            nearest_site="Taranto Offshore · approach 5d",
            ref="E4",
        ),
        RankedEvent(
            what=(
                "Moroccan general election — polls 10 days out; campaigning enters "
                "national-intensity phase"
            ),
            where="National · MA",
            when="2026-04-30",
            severity_short="Monitor",
            severity="monitor",
            distance_km=None,
            nearest_site="All MA sites · national",
            ref="E5",
        ),
        RankedEvent(
            what=(
                "Routine industrial action — CCOO port workers 24-hour stoppage at "
                "Algeciras container terminal"
            ),
            where="Algeciras, ES",
            when="2026-04-22",
            severity_short="Monitor",
            severity="monitor",
            distance_km=None,
            nearest_site="No site proximity",
            ref="E6",
        ),
    ]


def _cyber_strip() -> list[CyberStripItem]:
    return [
        CyberStripItem(
            kind="ACTOR",
            text=(
                "APT28 observed scanning MA energy-sector ASNs; reconnaissance "
                "consistent with prior campaigns against North African renewables."
            ),
            ref="C1",
        ),
        CyberStripItem(
            kind="SECTOR",
            text=(
                "SolarGlare ransomware campaign active against EU renewables — "
                "2 confirmed German wind-operator intrusions last week."
            ),
            ref="C2",
        ),
        CyberStripItem(
            kind="CVE",
            text=(
                "CVE-2026-1847 — turbine SCADA (Vendor X, v4.2); patch available "
                "via vendor portal since 2026-04-18."
            ),
            ref="C3",
        ),
    ]


def _baselines_moved() -> list[BaselineDelta]:
    return [
        BaselineDelta(
            country_or_label="MA",
            note="Amber → → Amber ↘ · forecast declining; election window driver.",
        ),
        BaselineDelta(
            country_or_label="EG",
            note="Amber → → Amber ↗ · background unrest uptick [E12].",
        ),
        BaselineDelta(
            country_or_label="IT · ES · GR",
            note="Unchanged. Steady / stable.",
        ),
        BaselineDelta(
            country_or_label="REGION",
            note="Physical admiralty unchanged (B2). Cyber admiralty unchanged (B3).",
        ),
    ]


def _reading_guide() -> list[TocEntry]:
    return [
        TocEntry(group="Crown-jewel & primary", title="Cape Wind · MA", page_ref="p 3"),
        TocEntry(
            group="Crown-jewel & primary",
            title="Taranto Offshore · IT",
            page_ref="p 4",
        ),
        TocEntry(
            group="Crown-jewel & primary",
            title="Agadir Substation · MA",
            page_ref="p 5",
        ),
        TocEntry(group="Regional", title="Cyber — MED", page_ref="p 6"),
        TocEntry(
            group="Secondary & minor",
            title="Murcia Solar · ES · Kavala Wind · GR",
            page_ref="p 7",
        ),
        TocEntry(
            group="Secondary & minor",
            title="Minor sites table · 6 rows",
            page_ref="p 8",
        ),
        TocEntry(
            group="Appendix",
            title="Evidence — physical E1–E12 · cyber C1–C5",
            page_ref="p 9",
        ),
    ]


def _regional_cyber() -> RegionalCyberPage:
    return RegionalCyberPage(
        admiralty="B3",
        actors_count=7,
        cves_on_watch=4,
        active_campaigns=2,
        standing_notes=(
            "EU renewables under sustained ransomware pressure since Q1 2026. "
            "Hacktivist surface-probing and state-aligned reconnaissance both "
            "elevated. No confirmed operator-side intrusions on AeroGrid estate "
            "this cycle."
        ),
        sector_signal=[
            JoinedEvent(
                signal_id="SIG-C2",
                headline=(
                    "SolarGlare ransomware confirmed at 2 German wind operators last "
                    "week; affiliate-operator TTPs consistent with Q1 intrusions."
                ),
                where="DE",
                when="2026-04-14–19",
                severity="high",
                distance_km=None,
                ref="C2",
                join_reason="Energy / wind / utilities · last 7d",
            ),
        ],
        actor_activity=[
            JoinedEvent(
                signal_id="SIG-C1",
                headline=(
                    "APT28 — scanning MA energy ASNs; reconnaissance against "
                    "public-facing OT management interfaces."
                ),
                where="MA",
                when="2026-04-19–21",
                severity="high",
                distance_km=None,
                ref="C1",
                join_reason="Global + regional watchlist",
            ),
            JoinedEvent(
                signal_id="SIG-C4",
                headline=(
                    "Ghosts-of-Barca (hacktivist) — claimed DDoS against Italian "
                    "utility customer-portal; outage ~22 min."
                ),
                where="IT",
                when="2026-04-20",
                severity="medium",
                distance_km=None,
                ref="C4",
                join_reason="Global + regional watchlist",
            ),
        ],
        geography_overlay=[
            JoinedEvent(
                signal_id="SIG-GEO-MA",
                headline=(
                    "Morocco — state-actor cyber activity elevated; origin assessed "
                    "as suspected regional rival (low confidence on attribution)."
                ),
                where="MA",
                when="ONGOING",
                severity="high",
                distance_km=None,
                ref="C1",
                join_reason="Host-country cyber activity",
            ),
            JoinedEvent(
                signal_id="SIG-GEO-IT",
                headline=(
                    "Italy — low; no sector-aligned intrusions against renewables "
                    "operators observed this cycle."
                ),
                where="IT",
                when="BASELINE",
                severity="monitor",
                distance_km=None,
                ref="-",
                join_reason="Host-country cyber activity",
            ),
        ],
        vulnerability_signal=[
            JoinedEvent(
                signal_id="SIG-C3",
                headline=(
                    "CVE-2026-1847 — turbine SCADA (Vendor X, v4.2). Patch "
                    "available. Applicable: Cape Wind, Taranto Offshore, Kavala."
                ),
                where="CVSS 8.8",
                when="PATCH",
                severity="high",
                distance_km=None,
                ref="C3",
                join_reason="Touches ot_stack · cve_watch_categories",
            ),
            JoinedEvent(
                signal_id="SIG-C5",
                headline=(
                    "CVE-2026-1722 — grid HMI (Vendor Y). Workaround only; "
                    "segmentation + MFA advised."
                ),
                where="CVSS 7.2",
                when="WORKAROUND",
                severity="medium",
                distance_km=None,
                ref="C5",
                join_reason="Touches ot_stack · cve_watch_categories",
            ),
        ],
    )


def _secondary_sites() -> list[SecondarySite]:
    return [
        SecondarySite(
            name="Murcia Solar",
            country="Spain · ES",
            country_lead="R. Navarro",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            events=[
                JoinedEvent(
                    signal_id="SIG-E10",
                    headline=(
                        "Minor industrial action — CCOO port workers at Almería "
                        "container terminal; 90 km from site, no operational touch."
                    ),
                    where="Almería, ES",
                    when="2026-04-22",
                    severity="monitor",
                    distance_km=90.0,
                    ref="E10",
                    join_reason="Regional context",
                ),
            ],
        ),
        SecondarySite(
            name="Kavala Wind",
            country="Greece · GR",
            country_lead="A. Dimitriou",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            events=[
                JoinedEvent(
                    signal_id="SIG-E11",
                    headline=(
                        "Local election 3 weeks out — Kavala municipality; no "
                        "security implication at current posture."
                    ),
                    where="Kavala, GR",
                    when="2026-05-11",
                    severity="monitor",
                    distance_km=None,
                    ref="E11",
                    join_reason="Calendar watchpoint",
                ),
            ],
        ),
    ]


def _minor_sites() -> list[MinorSiteRow]:
    return [
        MinorSiteRow(
            name="Nador Office",
            country_code="MA",
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="→",
            delta_count=2,
            note="Monitoring Casablanca unrest spillover — no proximity hits yet.",
        ),
        MinorSiteRow(
            name="Barcelona HQ",
            country_code="ES",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            delta_count=0,
            note="Quiet.",
        ),
        MinorSiteRow(
            name="Naples Ops",
            country_code="IT",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            delta_count=1,
            note="Taranto port strike spillover — inventory staging delayed < 24 h. [E2]",
        ),
        MinorSiteRow(
            name="Tunis Warehouse",
            country_code="TN",
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="→",
            delta_count=0,
            note="Quiet.",
        ),
        MinorSiteRow(
            name="Limassol Port",
            country_code="CY",
            pulse_label="GREEN",
            pulse_severity="green",
            forecast_arrow="→",
            delta_count=0,
            note="Quiet.",
        ),
        MinorSiteRow(
            name="Alexandria Office",
            country_code="EG",
            pulse_label="AMBER",
            pulse_severity="amber",
            forecast_arrow="↗",
            delta_count=1,
            note="Background unrest uptick — cost-of-living protests weekly cadence. [E12]",
        ),
    ]


def _evidence_physical() -> list[PhysicalEvidence]:
    return [
        PhysicalEvidence(
            ref="E1",
            headline=(
                "Casablanca — anti-government protest turned violent in commercial "
                "district; two police vehicles damaged."
            ),
            source="Reuters · Le360 · Seerist Verified",
            admiralty="B2",
            timestamp="2026-04-22 14:10Z",
            why="Cape Wind proximity · 18 km · underwrites elevated-posture headline.",
        ),
        PhysicalEvidence(
            ref="E2",
            headline=(
                "Taranto — USB dockworkers announce 48-hour strike over "
                "collective-agreement dispute."
            ),
            source="Corriere della Sera · Ansa",
            admiralty="B1",
            timestamp="2026-04-21 08:45Z",
            why="Taranto Offshore on-site impact; Naples Ops spillover.",
        ),
        PhysicalEvidence(
            ref="E3",
            headline=(
                "Agadir province — DGST detains four suspected of planning attack "
                "on grid infrastructure."
            ),
            source="Le360 · Reuters · Seerist Verified",
            admiralty="B2",
            timestamp="2026-04-24 11:20Z",
            why="Agadir Substation proximity · 35 km · Cape Wind sibling-site risk.",
        ),
        PhysicalEvidence(
            ref="E4",
            headline=(
                "Ionian low — 5-day storm forecast; sustained winds 55–70 kn "
                "landfall Sun–Mon."
            ),
            source="ECMWF · Meteo.it",
            admiralty="A2",
            timestamp="2026-04-21 06:00Z",
            why="Taranto Offshore operations window impact.",
        ),
        PhysicalEvidence(
            ref="E5",
            headline=(
                "Morocco — general election campaigning enters national-intensity "
                "phase; polls 2026-04-30."
            ),
            source="Le Monde · Hespress",
            admiralty="A1",
            timestamp="2026-04-20 00:00Z",
            why=(
                "All MA sites · calendar watchpoint; underwrites Cape Wind / Agadir "
                "posture."
            ),
        ),
        PhysicalEvidence(
            ref="E6",
            headline=(
                "Algeciras — CCOO 24-hour stoppage at container terminal; no "
                "AeroGrid counterparty exposure."
            ),
            source="El País · Europa Press",
            admiralty="B2",
            timestamp="2026-04-22 07:30Z",
            why="Regional context only · no site proximity.",
        ),
        PhysicalEvidence(
            ref="E7",
            headline=(
                "Kenitra — two arrested for planning sabotage of fuel depot; "
                "disclosure 2026-04-04."
            ),
            source="Le360 · Seerist Verified",
            admiralty="B2",
            timestamp="2026-04-04 13:15Z",
            why="MA pattern · energy-sector sabotage arrests, 30-day rolling.",
        ),
        PhysicalEvidence(
            ref="E8",
            headline=(
                "Tangier — one detained after reconnaissance near port-adjacent "
                "substation; released pending charges."
            ),
            source="Hespress · AP",
            admiralty="C2",
            timestamp="2026-04-11 09:00Z",
            why="MA pattern · energy-sector sabotage arrests, 30-day rolling.",
        ),
        PhysicalEvidence(
            ref="E9",
            headline=(
                "Casablanca — FAM-7 leaflets distributed at three public squares; "
                "call for \"action during election week\"."
            ),
            source="Seerist Verified · OSINT — Telegram channel monitoring",
            admiralty="B3",
            timestamp="2026-04-22 18:50Z",
            why="Cape Wind actor hit · FAM-7 in threat_actors_of_interest.",
        ),
        PhysicalEvidence(
            ref="E10",
            headline=(
                "Almería — CCOO port workers hold 6-hour picket; terminal "
                "operations resume by afternoon."
            ),
            source="El País · La Voz de Almería",
            admiralty="B2",
            timestamp="2026-04-22 12:00Z",
            why="Murcia Solar · 90 km · no operational touch, note only.",
        ),
        PhysicalEvidence(
            ref="E11",
            headline=(
                "Kavala — municipal electoral commission confirms 2026-05-11 "
                "local election."
            ),
            source="Kathimerini",
            admiralty="A1",
            timestamp="2026-04-20 10:00Z",
            why="Kavala Wind · calendar watchpoint.",
        ),
        PhysicalEvidence(
            ref="E12",
            headline=(
                "Alexandria — cost-of-living demonstrations continue at weekly "
                "cadence; low turnout, no escalation."
            ),
            source="Ahram Online · Reuters",
            admiralty="B3",
            timestamp="2026-04-19 16:40Z",
            why="Alexandria Office · background unrest uptick underwriting pulse shift.",
        ),
    ]


def _evidence_cyber() -> list[CyberEvidence]:
    return [
        CyberEvidence(
            ref="C1",
            headline=(
                "APT28 reconnaissance against MA energy-sector ASNs; TCP/443 + "
                "TCP/502 scanning, OSINT fingerprinting of public-facing HMIs."
            ),
            source="Seerist Cyber · CERT-MA advisory · Mandiant Advantage",
            admiralty="B2",
            timestamp="2026-04-19 — 04-21",
            why="Cape Wind + Agadir cyber callouts; MA geography overlay.",
        ),
        CyberEvidence(
            ref="C2",
            headline=(
                "SolarGlare ransomware — 2 German wind-operator intrusions last "
                "week; initial access via unpatched VPN appliances."
            ),
            source="CISA advisory AA26-111 · BleepingComputer · Recorded Future Insikt",
            admiralty="A2",
            timestamp="2026-04-14 — 04-19",
            why="EU sector signal; underwrites MED sector posture HIGH.",
        ),
        CyberEvidence(
            ref="C3",
            headline=(
                "CVE-2026-1847 — turbine SCADA (Vendor X, v4.2). Remote auth "
                "bypass. CVSS 8.8. Patch available 2026-04-18."
            ),
            source="Vendor X PSIRT · NVD · CERT-EU",
            admiralty="A1",
            timestamp="2026-04-18 12:00Z",
            why="Applicable to Cape Wind · Taranto Offshore · Kavala Wind ot_stack.",
        ),
        CyberEvidence(
            ref="C4",
            headline=(
                "Ghosts-of-Barca — claimed DDoS against Italian utility "
                "customer-portal; ~22-min outage; Layer-7 HTTP flood."
            ),
            source="Seerist Cyber · Italian utility press release",
            admiralty="B3",
            timestamp="2026-04-20 15:12Z",
            why="IT geography overlay; hacktivist actor activity.",
        ),
        CyberEvidence(
            ref="C5",
            headline=(
                "CVE-2026-1722 — grid HMI (Vendor Y). Stack overflow in protocol "
                "handler. CVSS 7.2. Workaround only."
            ),
            source="Vendor Y PSIRT · CERT-EU · CISA ICS-CERT",
            admiralty="A2",
            timestamp="2026-04-17 09:00Z",
            why="Applicable to Agadir Substation · Murcia Solar ot_stack.",
        ),
    ]


def rsm_med_w17_mock() -> RsmBriefData:
    """Return the fully-static RSM MED Weekly INTSUM 2026-W17 brief data."""
    return RsmBriefData(
        cover=CoverMeta(
            title="AEROGRID // MED Weekly INTSUM",
            classification="INTERNAL — AEROGRID SECURITY",
            prepared_by="AeroGrid Intelligence",
            reviewed_by="M. Keller · RSM MED",
            issued_at=date(2026, 4, 21),
            version="v1.0",
        ),
        admiralty_physical="B2",
        admiralty_cyber="B3",
        headline=(
            "Elevated unrest across North African maritime corridor; Italy and "
            "Iberia quiet; Moroccan election 10 days out raises watch posture for "
            "southern sites."
        ),
        baseline_strip=_baseline_strip(),
        top_events=_top_events(),
        cyber_strip=_cyber_strip(),
        baselines_moved=_baselines_moved(),
        reading_guide=_reading_guide(),
        sites=[_cape_wind(), _taranto_offshore(), _agadir_substation()],
        regional_cyber=_regional_cyber(),
        secondary_sites=_secondary_sites(),
        minor_sites=_minor_sites(),
        evidence_physical=_evidence_physical(),
        evidence_cyber=_evidence_cyber(),
    )
