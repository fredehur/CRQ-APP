from __future__ import annotations
from datetime import date

from tools.briefs.pipeline_state import global_run_id
from tools.briefs.models import (
    CisoBriefData,
    CisoCover,
    CisoPosturePanel,
    CisoTakeaway,
    RegionCell,
    CrossRegionalItem,
    CouplingStrip,
    CyberSurface,
    CyberEntry,
    CyberPhysicalJoin,
    JoinFacts,
    Timeline,
    TimelineTick,
    TimelineEvent,
    CisoScenario,
    ScenarioPosture,
    DeltaRibbon,
    EvidenceEntry,
)


def load_ciso_data(month: str) -> tuple[CisoBriefData, str | None]:
    if month != "2026-04":
        raise NotImplementedError(
            f"only 2026-04 mock is available; got {month}"
        )

    cover = CisoCover(
        title="AeroGrid · CISO Brief · April 2026",
        classification="INTERNAL — AEROGRID SECURITY LEADERSHIP",
        prepared_by="D. Huang · Director, Threat Intelligence",
        reviewed_by="A. Mendes (Head of Threat Intel)",
        issued_at=date(2026, 4, 20),
        version="v1.0 — final",
        month="April 2026",
        month_short="04·26",
        audience="Primary: CISO · Secondary: VP Security, GRC, Threat Intel",
    )

    cover_thesis_primary = (
        "The month's dominant signal is <span class=\"cyber-accent\">"
        "geopolitical–cyber coupling</span>."
    )
    cover_thesis_secondary = (
        "State-actor cyber scanning is tracking state-actor physical activity."
    )
    state_of_risk_line = (
        "April 2026 was shaped by North African political volatility, "
        "sustained EU renewables ransomware pressure, and a quieting APAC "
        "transit picture. Three of five regions sit in stable baseline — "
        "that silence is itself an intelligence product."
    )

    posture = CisoPosturePanel(
        posture="HIGH",
        posture_shift="held from March",
        admiralty="B2",
        admiralty_shift="↑ B3 → B2 (MED coverage)",
        regions_moved=2,
        regions_movement_summary="MED ↑ · APAC ↓",
        scenarios_watched=4,
        scenarios_delta_note="2 with delta this month",
    )

    ciso_takeaways = [
        CisoTakeaway(
            n=1,
            severity="cyber",
            body_markdown=(
                "<strong>The Moroccan election window is the month's "
                "dominant signal — read physical and cyber as one.</strong> "
                "Cape Wind is on raised watch; APT28 scanning of MA energy "
                "ASNs runs coincident with the election calendar. "
                "The coupling is the point."
            ),
            anchor="S-07 · MED",
        ),
        CisoTakeaway(
            n=2,
            severity="high",
            body_markdown=(
                "<strong>SolarGlare is confirmed at multiple EU wind "
                "operators; NCE is exposed, not hypothetical.</strong> "
                "Treat Vendor X access as the primary vector. Patch rollout "
                "at 40% is not enough; tighten the SLA to 14 days for "
                "CVE-2026-1847."
            ),
            anchor="S-11 · NCE",
        ),
        CisoTakeaway(
            n=3,
            severity="monitor",
            body_markdown=(
                "<strong>Three regions sit in stable baseline — and that is "
                "the report.</strong> LATAM, AME, and APAC physical are "
                "quiet. Silence is an intelligence product; the regions "
                "grid below carries the <em>why clear</em> for each."
            ),
            anchor="Cross-reg",
        ),
    ]

    regions_grid = [
        RegionCell(
            region="MED",
            classification="moved",
            direction="up",
            status_label="Raised",
            admiralty="Adm. B2",
            admiralty_shift="↑ from B3",
            note=(
                "Morocco election (Apr) + Italy port strike. APT28 scanning "
                "coincident. Raised posture through May."
            ),
            why_clear_label="Triggers",
            why_clear_body=(
                "MA election; IT port strike; APT28 ASN scanning; "
                "Cape Wind raised-watch."
            ),
        ),
        RegionCell(
            region="NCE",
            classification="cyber-pressed",
            direction="cyber",
            status_label="Held · cyber ↑",
            admiralty="Adm. B1",
            admiralty_shift="held",
            note=(
                "Physical quiet. Sector-targeting cyber active. "
                "SolarGlare confirmed at DE operators; probable at 4 more."
            ),
            why_clear_label="Physical triggers",
            why_clear_body=(
                "None this month. Cyber pressure via shared-vendor vector; "
                "see §5."
            ),
        ),
        RegionCell(
            region="APAC",
            classification="baseline",
            direction="down",
            status_label="Quieted",
            admiralty="Adm. B2",
            admiralty_shift="held",
            note=(
                "Transit-corridor stability improved. Short-term logistics "
                "risk eased; supply-chain watch retained."
            ),
            why_clear_label="Why quieter",
            why_clear_body=(
                "Corridor advisories cleared; carrier volumes normalised; "
                "no sector cyber campaign material to portfolio."
            ),
        ),
        RegionCell(
            region="LATAM",
            classification="baseline",
            direction="flat",
            status_label="Baseline",
            admiralty="Adm. C2",
            admiralty_shift="held",
            note="No regional escalation. Host-country baselines stable.",
            why_clear_label="Why clear",
            why_clear_body=(
                "Brazil, Chile, Peru stable. Watchlist actors quiet. "
                "No new CVE or sector campaign material to portfolio. "
                "Next review: mid-May."
            ),
        ),
        RegionCell(
            region="AME",
            classification="baseline",
            direction="flat",
            status_label="Baseline",
            admiralty="Adm. C2",
            admiralty_shift="held",
            note=(
                "No regional escalation. Third-party vendor watch retained "
                "(S-09)."
            ),
            why_clear_label="Why clear",
            why_clear_body=(
                "No new triggers. Watchlist actors quiet. S-09 open on "
                "continuity only; no new evidence this month."
            ),
        ),
    ]

    cross_regional_items = [
        CrossRegionalItem(
            tag="MED moved",
            tag_cyber=False,
            head=(
                "Morocco election + Italy port strike raised MED posture "
                "through May."
            ),
            body=(
                "Two independent events in the same region within the same "
                "fortnight. The Morocco signal is structural (election → "
                "coalition friction → protest activity); the Italy signal "
                "is labour-tactical and contained to port-access. Neither "
                "touches AeroGrid sites directly; both touch the operating "
                "rhythm."
            ),
            delta="up",
            delta_label="↑ RAISED",
            rail_note="posture",
            anchors=["E1", "E2", "E3"],
        ),
        CrossRegionalItem(
            tag="NCE held · cyber ↑",
            tag_cyber=True,
            head=(
                "Physical quiet, cyber pressure mounting via a shared SCADA "
                "vendor."
            ),
            body=(
                "A sector-level pattern: SolarGlare is not a single-operator "
                "intrusion. Shared Vendor X access across the NCE fleet "
                "makes the exposure portfolio-wide by construction. Three "
                "of the confirmed or probable targets are within the "
                "AeroGrid NCE peer group."
            ),
            delta="up",
            delta_label="↑ SECTOR",
            rail_note="cyber",
            anchors=["C1", "C2", "C3"],
        ),
        CrossRegionalItem(
            tag="APAC quieted",
            tag_cyber=False,
            head=(
                "Transit-corridor stability improved; structural supplier "
                "concentration unchanged."
            ),
            body=(
                "The month's improvement is tactical. The 2027 blade cohort "
                "still sits on a single-source Chinese supplier; "
                "second-source qualification remains a Q4 2026 milestone. "
                "Track the milestone, not the month."
            ),
            delta="down",
            delta_label="↓ EASED",
            rail_note="transit",
            anchors=["E9", "E11"],
        ),
        CrossRegionalItem(
            tag="LATAM + AME baseline",
            tag_cyber=False,
            head=(
                "No regional escalation. Watchlist actors quiet. No new "
                "sector-level cyber material to portfolio."
            ),
            body=(
                "Silence here is not absence. Baselines were actively "
                "validated (not just read from the prior cycle). Seerist "
                "coverage remained steady; Firecrawl/Tavily discovery "
                "returned no new admiralty-grade entries touching AeroGrid."
            ),
            delta="flat",
            delta_label="→ HELD",
            rail_note="baseline",
            anchors=["Admiralty C2"],
        ),
    ]

    coupling_strip = CouplingStrip(
        region="MED",
        label="§ Coupling signal · MED",
        physical_track=(
            "Moroccan general election (April) drives a <strong>0–12 week "
            "unrest window</strong> along the Casablanca corridor. Cape Wind "
            "(crown-jewel) is on raised watch. Security posture elevated; "
            "expat travel on essential-only."
        ),
        cyber_track=(
            "<strong>APT28 scanning of MA + ES energy ASNs</strong> runs "
            "coincident with the election calendar. Cadence up 3× over "
            "March. SOC observes no anomalies at Cape Wind; the signal is "
            "external posture, not intrusion."
        ),
        summary=(
            "State-actor cyber posture is <strong>mirroring state-actor "
            "physical interest</strong>. Treat Cape Wind as a joint "
            "intelligence signal — not two separate streams. See §5 for "
            "the full join."
        ),
    )

    cyber_surface = CyberSurface(
        sector_campaigns=[
            CyberEntry(
                k="SolarGlare",
                ctx="Ransomware · EU wind",
                body=(
                    "Confirmed at 2 German wind operators. TTP pattern "
                    "observed: initial access via Vendor X SCADA (v4.2), "
                    "lateral via domain-joined OT bastion, extortion on "
                    "grid-availability data. 4 additional EU operators "
                    "report probable targeting; 3 within AeroGrid NCE peer "
                    "group."
                ),
                impact=(
                    "AeroGrid NCE sites — no confirmed impact. Monitoring "
                    "raised; CVE-2026-1847 patching is the primary "
                    "mitigation."
                ),
                severity="high",
                region_or_scope="NCE · DE",
                admiralty="Adm. A2",
                anchors=["C1", "C2", "C3"],
            ),
            CyberEntry(
                k="EmberPass",
                ctx="Phishing · renewables exec",
                body=(
                    "Low-volume credential-harvest campaign targeting "
                    "renewables-sector executives across EU. 6 AeroGrid "
                    "accounts received messages; none engaged. Identity "
                    "provider policy caught 4 of 6 at gateway."
                ),
                impact=(
                    "Contained. Identity team to retrospectively tighten "
                    "external-domain display rules; no board-level concern."
                ),
                severity="monitor",
                region_or_scope="NCE · EU",
                admiralty="Adm. B2",
                anchors=["C6"],
            ),
        ],
        actor_activity=[
            CyberEntry(
                k="APT28",
                ctx="State-linked · scanning",
                body=(
                    "Scanning Moroccan and Spanish energy ASNs through "
                    "April. Observed cadence up 3× over March. Coincident "
                    "with the MA election calendar and with elevated "
                    "diplomatic reporting on the Western Mediterranean. "
                    "Cape Wind SOC — no anomalies observed."
                ),
                impact=(
                    "Treat as external posture signal; see §6 (coupling) "
                    "for the physical join."
                ),
                severity="medium",
                region_or_scope="MED · MA/ES",
                admiralty="Adm. B1",
                anchors=["C4", "C5"],
            ),
            CyberEntry(
                k="FIN12-adj",
                ctx="Criminal · ransom-op",
                body=(
                    "Tooling overlap with SolarGlare. Not attributed; "
                    "tracked as an adjacent cluster. No direct AeroGrid "
                    "touch; included because a confirmed link would move "
                    "SolarGlare to a named-actor campaign and change "
                    "disclosure calculus."
                ),
                impact="Track; do not act. Re-evaluate on attribution.",
                severity="monitor",
                region_or_scope="EU-wide",
                admiralty="Adm. C2",
                anchors=["C7"],
            ),
        ],
        vulnerability_signal=[
            CyberEntry(
                k="CVE-2026-1847",
                ctx="Turbine SCADA · Vendor X v4.2",
                body=(
                    "Patch available. Portfolio rollout at 40% as of "
                    "18 Apr. The SolarGlare exploitation path terminates "
                    "at this CVE in the confirmed DE intrusions. "
                    "Accelerated SLA (14 d) recommended; approval required "
                    "from CISO office."
                ),
                impact=(
                    "Primary recommended action of the month. See §7 · S-11."
                ),
                severity="high",
                region_or_scope="Portfolio",
                admiralty="Adm. A1",
                anchors=["C3"],
            ),
            CyberEntry(
                k="CVE-2026-1722",
                ctx="Grid HMI · vendor workaround only",
                body=(
                    "Vendor patch not yet issued; workaround in place. "
                    "2 sites affected. Not known to be actively exploited. "
                    "Compensating controls (network-segmentation audit) "
                    "verified this month."
                ),
                impact=(
                    "Maintain workaround. Re-check vendor bulletin cadence "
                    "at mid-May."
                ),
                severity="medium",
                region_or_scope="2 sites",
                admiralty="Adm. B2",
                anchors=["C8"],
            ),
            CyberEntry(
                k="Identity perimeter",
                ctx="IdP provider · conditional access",
                body=(
                    "Advisory issued on token-theft TTPs observed across "
                    "financial sector; not yet active against energy. "
                    "Conditional-access baseline reviewed; device-posture "
                    "signal added to critical-app policies this month."
                ),
                impact=(
                    "Pre-emptive. Report on rollout completeness at next "
                    "brief."
                ),
                severity="monitor",
                region_or_scope="Global",
                admiralty="Adm. B1",
                anchors=["C9"],
            ),
        ],
    )

    cyber_physical_join = CyberPhysicalJoin(
        region="MED",
        title_markdown=(
            "Morocco is the month's <span class='cyber-accent'>joint "
            "signal</span>."
        ),
        lede=(
            "The election and the scanning are not independent events that "
            "happen to share a geography. Coincidence of this kind, at "
            "this cadence, across these actors, is a coupled signal and "
            "should be briefed as one."
        ),
        physical=JoinFacts(
            title="Cape Wind raised-watch window.",
            narrative_paragraphs=[
                (
                    "The April general election closed without a clear "
                    "coalition. Protest activity clustered in urban centres "
                    "through the polling period and has not fully subsided. "
                    "Security-force posture in the Casablanca corridor is "
                    "elevated and expected to remain so until a governing "
                    "coalition is named."
                ),
                (
                    "Cape Wind itself has not been the object of protest. "
                    "Proximate risks are access-road disruption, expat "
                    "movement, and secondary vendor-continuity effects. "
                    "Base case is normalisation over a 6–12 week horizon."
                ),
            ],
            facts={
                "Site": "Cape Wind · crown-jewel · Casablanca corridor",
                "Posture": "Raised · expat travel essential-only",
                "Horizon": "0–12 weeks · reassess at October board",
                "Anchors": "E1 · E2 · E4",
            },
        ),
        cyber=JoinFacts(
            title="APT28 scanning coincident with the polling window.",
            narrative_paragraphs=[
                (
                    "APT28 scanning of Moroccan and Spanish energy ASNs is "
                    "up 3× over March and runs coincident with the election "
                    "calendar. The SOC has observed no anomalies at Cape "
                    "Wind; the signal is external posture, not intrusion."
                ),
                (
                    "The cadence, the target set, and the timing are the "
                    "information. Treat as pre-positioning, not operation. "
                    "Monitoring raised; no incident triggered."
                ),
            ],
            facts={
                "Actor": "APT28 · state-linked",
                "Target": "MA + ES energy ASNs",
                "Cadence": "3× March baseline · window runs through May",
                "Anchors": "C4 · C5",
            },
        ),
        timeline=Timeline(
            range_label=(
                "§ Timeline · physical + cyber co-occurrence · Mar–May 2026"
            ),
            ticks=[
                TimelineTick(pct_pos=0, label="1 Mar"),
                TimelineTick(pct_pos=23, label="15 Mar"),
                TimelineTick(pct_pos=43, label="1 Apr"),
                TimelineTick(pct_pos=58, label="15 Apr"),
                TimelineTick(pct_pos=78, label="1 May"),
                TimelineTick(pct_pos=100, label="15 May"),
            ],
            physical_events=[
                TimelineEvent(
                    start_pct=0,
                    width_pct=20,
                    label="Pre-election campaigning",
                    is_ghost=True,
                ),
                TimelineEvent(
                    start_pct=43,
                    width_pct=26,
                    label="Polling + protest window",
                    is_ghost=False,
                ),
                TimelineEvent(
                    start_pct=70,
                    width_pct=28,
                    label="Coalition formation",
                    is_ghost=True,
                ),
            ],
            cyber_events=[
                TimelineEvent(
                    start_pct=0,
                    width_pct=30,
                    label="APT28 baseline cadence",
                    is_ghost=True,
                ),
                TimelineEvent(
                    start_pct=40,
                    width_pct=35,
                    label="APT28 scanning · 3× cadence · MA + ES ASNs",
                    is_ghost=False,
                ),
                TimelineEvent(
                    start_pct=78,
                    width_pct=20,
                    label="Expected taper",
                    is_ghost=True,
                ),
            ],
            join_marks=[48.0, 62.0],
        ),
        read_summary=(
            "Cape Wind is <strong>one intelligence signal, two "
            "streams</strong>. Incident response planning for MA must "
            "include both the physical access-disruption scenario and the "
            "cyber pre-positioning hypothesis. Do not split them across "
            "two on-call rotations."
        ),
    )

    scenarios = [
        CisoScenario(
            id="S-07",
            region="MED · Morocco",
            title="Sustained civil unrest near Cape Wind.",
            posture=ScenarioPosture(
                pill_label="HIGH · MED likelihood",
                pill_severity="high",
                severity="HIGH",
                likelihood="MED",
                admiralty="Adm. B2",
                delta_vs_prior="Severity ↑ · Adm. held",
            ),
            delta_ribbon=DeltaRibbon(
                kind="moved-up",
                tag="↑ Severity · MED → HIGH",
                body_markdown=(
                    "Moved this month. Post-election coalition friction is "
                    "the driver. Cape Wind site watch stepped up to raised; "
                    "expat travel essential-only. <strong>Read with S-07 "
                    "cyber coupling (§6).</strong>"
                ),
            ),
            narrative=(
                "Post-election window in Morocco drives a 0–12 week unrest "
                "horizon on the Casablanca corridor. Cape Wind itself is "
                "not the protest object; proximate risks are access-road "
                "disruption, expat movement, and vendor continuity. Base "
                "case normalises over coalition formation; tail case "
                "extends into Q3 and reaches the October board."
            ),
            drivers_line=(
                "coalition friction · youth unemployment · regional "
                "economic stress"
            ),
            side={
                "Delta": "Severity ↑ · Adm. held",
                "Horizon": "0–12 weeks",
                "Posture": "Raised watch",
                "Next": "Reassess Oct board",
            },
            anchors=["E1", "E2", "E4", "C4", "C5"],
        ),
        CisoScenario(
            id="S-11",
            region="NCE · OT vendor",
            title="Cyber intrusion via OT vendor.",
            posture=ScenarioPosture(
                pill_label="HIGH · MED-HIGH likelihood",
                pill_severity="high",
                severity="HIGH",
                likelihood="MED-HIGH",
                admiralty="Adm. B1",
                delta_vs_prior="New evidence · DE",
            ),
            delta_ribbon=DeltaRibbon(
                kind="moved-new",
                tag="◆ New evidence · DE confirmation",
                body_markdown=(
                    "Moved this month. SolarGlare confirmed at 2 German "
                    "wind operators; 4 more probable. <strong>Exposure "
                    "reclassified from hypothetical to sector-level."
                    "</strong> Primary recommended action: accelerate "
                    "CVE-2026-1847 to 14-day SLA."
                ),
            ),
            narrative=(
                "Shared Vendor X SCADA across the NCE fleet makes exposure "
                "portfolio-wide by construction. Patch deployment at 40%. "
                "Vendor X access into AeroGrid environments has not been "
                "reviewed since Q3 2025. The governance question is whether "
                "current patch cadence and vendor-access posture are "
                "sufficient given the campaign's demonstrated velocity."
            ),
            drivers_line=(
                "SolarGlare · unpatched SCADA · third-party vendor access"
            ),
            side={
                "Delta": "New evidence · DE",
                "Horizon": "0–8 weeks",
                "Asks": "14-day SLA · access review",
                "Next": "Patch status at May brief",
            },
            anchors=["C1", "C2", "C3", "C6"],
        ),
        CisoScenario(
            id="S-09",
            region="AME · Third-party vendor",
            title="Third-party vendor compromise.",
            posture=ScenarioPosture(
                pill_label="MED · MED likelihood",
                pill_severity="medium",
                severity="MED",
                likelihood="MED",
                admiralty="Adm. B2",
                delta_vs_prior="None",
            ),
            delta_ribbon=DeltaRibbon(
                kind="no-delta",
                tag="— No delta · continuity",
                body_markdown=(
                    "Included for continuity. No new evidence this month; "
                    "watchlist actors quiet; monitoring held. <strong>"
                    "Re-check at May brief; retire if two more months "
                    "hold.</strong>"
                ),
            ),
            narrative=(
                "Vendor concentration in the AME region remains the "
                "structural exposure. No new indicators this month. The "
                "scenario carries forward because two consecutive quiet "
                "months does not yet justify a retirement — three does. "
                "The open question for the CISO office is whether to "
                "close out at May."
            ),
            drivers_line=(
                "vendor concentration · regional monitoring · no new "
                "indicators"
            ),
            side={
                "Delta": "None",
                "Horizon": "Rolling",
                "Status": "Continuity only",
                "Next": "Retire? · May review",
            },
            anchors=["E7"],
        ),
        CisoScenario(
            id="S-14",
            region="APAC · Blade supply",
            title="Supply chain disruption — turbine blades.",
            posture=ScenarioPosture(
                pill_label="MED · LOW-MED likelihood",
                pill_severity="medium",
                severity="MED",
                likelihood="LOW-MED",
                admiralty="Adm. B2",
                delta_vs_prior="Likelihood ↓",
            ),
            delta_ribbon=DeltaRibbon(
                kind="moved-down",
                tag="↓ Improved · transit stabilised",
                body_markdown=(
                    "Moved this month. Transit-corridor stability improved; "
                    "short-term logistics risk eased. <strong>Structural "
                    "single-source exposure unchanged;</strong> 2027 "
                    "delivery timeline still rides on Q4 2026 second-source "
                    "qualification."
                ),
            ),
            narrative=(
                "The month's improvement is tactical, not structural. "
                "Second-source qualification remains the milestone to "
                "track; if it slips past Q1 2027, the scenario escalates "
                "to board-action. CISO office view: no action required "
                "this month; watch the milestone, not the weekly."
            ),
            drivers_line=(
                "single-source supplier · export restriction risk · "
                "2027 delivery"
            ),
            side={
                "Delta": "Likelihood ↓",
                "Horizon": "2027 delivery",
                "Milestone": "2nd-source · Q4 2026",
                "Next": "Q3 board review",
            },
            anchors=["E9", "E11"],
        ),
    ]

    evidence_physical = [
        EvidenceEntry(
            ref="E1",
            headline=(
                "Moroccan general election — provisional results and "
                "coalition arithmetic."
            ),
            source="Reuters · 14 Apr 2026",
            admiralty="B1",
            timestamp="14 Apr · 18:40 UTC",
            why="Primary physical signal driving S-07 posture change.",
        ),
        EvidenceEntry(
            ref="E2",
            headline=(
                "Casablanca protest tracker — week-over-week incident counts."
            ),
            source="Le360 · 16 Apr 2026",
            admiralty="B2",
            timestamp="16 Apr · 09:10 UTC",
            why="Trendline for the 0–12 week unrest horizon.",
        ),
        EvidenceEntry(
            ref="E3",
            headline=(
                "Italian dockworkers — 48h rolling stoppage, Taranto and "
                "Gioia Tauro."
            ),
            source="Reuters · 09 Apr 2026",
            admiralty="B1",
            timestamp="09 Apr · 11:20 UTC",
            why=(
                "Second MED movement item; port access disruption near "
                "Taranto."
            ),
        ),
        EvidenceEntry(
            ref="E4",
            headline=(
                "Country security advisory — raised travel posture, "
                "Morocco urban centres."
            ),
            source="Seerist · 15 Apr 2026",
            admiralty="A2",
            timestamp="15 Apr · 06:00 UTC",
            why="Basis for raised-watch determination at Cape Wind.",
        ),
        EvidenceEntry(
            ref="E5",
            headline=(
                "Taranto Offshore — grid tie achieved, commissioning on "
                "schedule."
            ),
            source="Internal · Project Ops · 18 Apr 2026",
            admiralty="A1",
            timestamp="18 Apr · 14:05 UTC",
            why="Confirms positive baseline; no escalation signal.",
        ),
        EvidenceEntry(
            ref="E6",
            headline="MED storm-season preparation review — offshore assets.",
            source="Internal · Ops · 12 Apr 2026",
            admiralty="A1",
            timestamp="12 Apr · 09:00 UTC",
            why="Seasonal baseline re-anchored for October review.",
        ),
        EvidenceEntry(
            ref="E7",
            headline=(
                "AME regional monitoring — no new indicators across "
                "watchlist countries."
            ),
            source="Internal · RSM-AME · 15 Apr 2026",
            admiralty="C2",
            timestamp="15 Apr · 12:00 UTC",
            why="Anchors the LATAM + AME \"why clear\" treatment.",
        ),
        EvidenceEntry(
            ref="E8",
            headline=(
                "Draft EU OT/ICS resilience framework — Commission text."
            ),
            source="European Commission · 17 Apr 2026",
            admiralty="A1",
            timestamp="17 Apr · 10:00 UTC",
            why=(
                "Relevant to S-11 disclosure calculus if campaign reaches "
                "operator."
            ),
        ),
        EvidenceEntry(
            ref="E9",
            headline=(
                "APAC transit corridor — April carrier-volume and advisory "
                "roll-up."
            ),
            source="Seerist · 17 Apr 2026",
            admiralty="B2",
            timestamp="17 Apr · 08:30 UTC",
            why="Basis for APAC quieting + S-14 likelihood reduction.",
        ),
        EvidenceEntry(
            ref="E10",
            headline=(
                "Greek local election timing + AeroGrid regional footprint "
                "overlay."
            ),
            source="Internal · RSM-MED · 18 Apr 2026",
            admiralty="B2",
            timestamp="18 Apr · 11:00 UTC",
            why="Context for May-window watch on minor GR sites.",
        ),
    ]

    evidence_cyber = [
        EvidenceEntry(
            ref="C1",
            headline=(
                "SolarGlare campaign — TTPs, indicators, and observed "
                "targeting across EU wind sector."
            ),
            source="CERT-EU · 16 Apr 2026",
            admiralty="A2",
            timestamp="16 Apr · 07:15 UTC",
            why="Primary campaign anchor for S-11.",
        ),
        EvidenceEntry(
            ref="C2",
            headline=(
                "German wind operator discloses ransomware incident; "
                "Vendor X SCADA vector confirmed."
            ),
            source="Der Spiegel · 13 Apr 2026",
            admiralty="B1",
            timestamp="13 Apr · 16:00 UTC",
            why="Confirmation changes NCE exposure classification.",
        ),
        EvidenceEntry(
            ref="C3",
            headline=(
                "CVE-2026-1847 — CISA advisory and patch guidance; "
                "turbine SCADA, Vendor X v4.2."
            ),
            source="CISA · 08 Apr 2026",
            admiralty="A1",
            timestamp="08 Apr · 15:00 UTC",
            why=(
                "Exploitation path for SolarGlare; primary recommended "
                "action."
            ),
        ),
        EvidenceEntry(
            ref="C4",
            headline=(
                "APT28 ASN scanning observed against Moroccan and Spanish "
                "energy infrastructure."
            ),
            source="CERT-MA (partner share) · 11 Apr 2026",
            admiralty="B2",
            timestamp="11 Apr · 13:45 UTC",
            why="Physical track of the MED coupling signal.",
        ),
        EvidenceEntry(
            ref="C5",
            headline=(
                "APT28 TTP update — cadence change, new infrastructure "
                "hashes."
            ),
            source="NCSC · 14 Apr 2026",
            admiralty="B1",
            timestamp="14 Apr · 09:30 UTC",
            why=(
                "Supports the 3× cadence observation underpinning the join."
            ),
        ),
        EvidenceEntry(
            ref="C6",
            headline=(
                "EmberPass — executive-targeted phishing across EU "
                "renewables."
            ),
            source="Internal · IR · 10 Apr 2026",
            admiralty="B2",
            timestamp="10 Apr · 17:20 UTC",
            why="Contained; included for completeness of monthly surface.",
        ),
        EvidenceEntry(
            ref="C7",
            headline=(
                "FIN12-adjacent cluster — tooling overlap with SolarGlare, "
                "unattributed."
            ),
            source="Mandiant brief · 16 Apr 2026",
            admiralty="C2",
            timestamp="16 Apr · 20:00 UTC",
            why="Watch item; attribution change would move S-11.",
        ),
        EvidenceEntry(
            ref="C8",
            headline=(
                "CVE-2026-1722 — grid HMI, no vendor patch; workaround "
                "details."
            ),
            source="CISA · 02 Apr 2026",
            admiralty="B2",
            timestamp="02 Apr · 10:00 UTC",
            why="Anchors the 2-site workaround posture.",
        ),
        EvidenceEntry(
            ref="C9",
            headline=(
                "Identity token-theft TTPs — cross-sector advisory, "
                "financial to energy crossover watch."
            ),
            source="CISA + partner · 17 Apr 2026",
            admiralty="B1",
            timestamp="17 Apr · 11:30 UTC",
            why=(
                "Underpins pre-emptive conditional-access tightening this "
                "month."
            ),
        ),
    ]

    brief = CisoBriefData(
        cover=cover,
        cover_thesis_primary=cover_thesis_primary,
        cover_thesis_secondary=cover_thesis_secondary,
        state_of_risk_line=state_of_risk_line,
        posture=posture,
        ciso_takeaways=ciso_takeaways,
        regions_grid=regions_grid,
        cross_regional_items=cross_regional_items,
        coupling_strip=coupling_strip,
        cyber_surface=cyber_surface,
        cyber_physical_join=cyber_physical_join,
        scenarios=scenarios,
        evidence_physical=evidence_physical,
        evidence_cyber=evidence_cyber,
    )
    return brief, global_run_id()
