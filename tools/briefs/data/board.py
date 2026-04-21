from datetime import date
from tools.briefs.models import (
    BoardBriefData, BoardCover, PosturePanel, BoardTakeaway, RegionDelta,
    KeyDevelopment, AlsoTrackingItem, WatchNextItem, MatrixDot, RegisterRow,
    RiskMatrix, ScenarioPosture, ScenarioNarrative, EvidenceRef, BoardScenario,
    ReadingRule, Methodology, EndMatter,
)


def load_board_data(quarter: str) -> BoardBriefData:
    """Static mock matching docs/design/handoff/Board Report Q2 2026.html.

    Future: replaced by a quarterly synthesizer reading aggregated regional output.
    """
    if quarter != "2026Q2":
        raise NotImplementedError(f"only 2026Q2 mock is available; got {quarter}")

    cover = BoardCover(
        title="AeroGrid · Board Report · Q2 2026",
        classification="INTERNAL — BOARD DISTRIBUTION",
        prepared_by="M. Okonkwo · Director, Threat Intelligence",
        reviewed_by="R. Salazar · VP Risk & Resilience",
        issued_at=date(2026, 4, 17),
        version="v1.0 — final",
        quarter="Q2 2026",
        quarter_short="Q2·26",
        board_meeting="21 April 2026 · London HQ",
        distribution_note="AeroGrid Wind Solutions · Board of Directors",
    )

    return BoardBriefData(
        cover=cover,
        state_of_risk_line=(
            "Q2 2026 saw elevated North African unrest, sustained EU renewables "
            "cyber pressure, and a material stabilisation of APAC transit corridors; "
            "the AeroGrid portfolio remains materially exposed to Moroccan political "
            "volatility and a widening EU ransomware campaign."
        ),
        cover_thesis_title="Two items warrant board action.",
        cover_thesis_subtitle="Six remain within management authority.",
        posture=PosturePanel(
            overall_posture="HIGH",
            posture_shift="↑ from MEDIUM · Q1",
            admiralty="B2",
            admiralty_shift="held · Q1 was B2",
            scenarios_on_watch=8,
            scenarios_split="2 board-action · 6 mgmt",
            next_review="Q3 board · October 2026",
        ),
        board_takeaways=[
            BoardTakeaway(
                n=1, severity="high",
                body_markdown=(
                    "<strong>Cape Wind (crown-jewel, MA) remains on raised watch through Q3</strong> "
                    "following the April general election. Short-term unrest risk on the Casablanca "
                    "corridor is the dominant portfolio exposure this quarter; reassess at the October board."
                ),
                anchor="S-07 · MED",
            ),
            BoardTakeaway(
                n=2, severity="high",
                body_markdown=(
                    "<strong>SolarGlare ransomware is no longer hypothetical for NCE.</strong> "
                    "The campaign has been confirmed at two German wind operators; AeroGrid NCE sites "
                    "should be treated as exposed. Recommend accelerating CVE-2026-1847 patching "
                    "and a third-party vendor access review."
                ),
                anchor="S-11 · NCE",
            ),
            BoardTakeaway(
                n=3, severity="medium",
                body_markdown=(
                    "<strong>APT28 scanning of Moroccan and Spanish energy ASNs tracks the election calendar.</strong> "
                    "No observed AeroGrid impact, but the cyber-physical coupling means Cape Wind carries "
                    "a joint intelligence signal, not two separate ones. SOC monitoring in place."
                ),
                anchor="S-07 · MED",
            ),
            BoardTakeaway(
                n=4, severity="monitor",
                body_markdown=(
                    "<strong>Supply chain exposure on turbine blades is stable but strategically watched.</strong> "
                    "Single-source Chinese supplier remains a 2027 delivery-timeline risk. "
                    "Second-source qualification targeted Q4 2026; no board action required this quarter."
                ),
                anchor="S-14 · APAC",
            ),
            BoardTakeaway(
                n=5, severity="monitor",
                body_markdown=(
                    "<strong>Regulatory surface is widening.</strong> EU Commission draft legislation "
                    "on OT/ICS resilience has a Q3 submission deadline; compliance cost estimate "
                    "pending for the October board. Flag, not action."
                ),
                anchor="REG · EU",
            ),
        ],
        delta_bar=[
            RegionDelta(
                region="MED", direction="up", label="Raised",
                cause="MA election, IT port strike · posture raised through May.",
            ),
            RegionDelta(
                region="NCE", direction="high", label="Held · cyber ↑",
                cause="Physical quiet. Sector-targeting cyber active.",
            ),
            RegionDelta(
                region="APAC", direction="down", label="Quieted",
                cause="Transit corridor stability improved. Supply watch retained.",
            ),
            RegionDelta(
                region="LATAM", direction="flat", label="Baseline",
                cause="No new triggers. Watchlist cold.",
            ),
            RegionDelta(
                region="AME", direction="flat", label="Baseline",
                cause="No new triggers. Third-party vendor watch retained.",
            ),
        ],
        key_developments=[
            KeyDevelopment(
                n=1, category="G",
                headline="Moroccan general election (April).",
                body="Outcome elevated short-term unrest risk on the Casablanca corridor; coalition formation ongoing.",
                meaning="Cape Wind (crown-jewel) remains on raised watch through Q3; reassess at October board.",
                severity="high", region="MED · MA", anchors=["E1", "E2", "E4"],
            ),
            KeyDevelopment(
                n=2, category="C",
                headline="SolarGlare ransomware confirmed at two German wind operators.",
                body="TTP pattern observed; 4 additional EU operators report probable targeting.",
                meaning="NCE sites move from hypothetical to exposed; CVE-2026-1847 patch deployment at 40% portfolio rollout.",
                severity="high", region="NCE · DE", anchors=["C1", "C2", "C3"],
            ),
            KeyDevelopment(
                n=3, category="W",
                headline="Taranto Offshore commissioning on track.",
                body="Grid-tie achieved on schedule; storm-season preparations complete ahead of October.",
                meaning="No governance ask; flagged positively for baseline continuity.",
                severity="monitor", region="MED · IT", anchors=["E5", "E6"],
            ),
            KeyDevelopment(
                n=4, category="C",
                headline="APT28 scanning against Moroccan and Spanish energy ASNs.",
                body="Cadence up 3× over March; coincident with MA election calendar.",
                meaning="No observed AeroGrid impact. Treat cyber activity + physical exposure as a joint signal.",
                severity="medium", region="MED · MA/ES", anchors=["C4", "C5"],
            ),
            KeyDevelopment(
                n=5, category="G",
                headline="EU Commission draft legislation on OT/ICS resilience.",
                body="Q3 submission deadline; compliance cost estimate pending for the October board.",
                meaning="Regulatory surface widens across the NCE footprint; flag for now, action next quarter.",
                severity="monitor", region="NCE · EU", anchors=["E8"],
            ),
        ],
        also_tracking=[
            AlsoTrackingItem(
                head="Greek local election · late May.",
                tail="3 minor AeroGrid sites in region; contained exposure, monitored through polling window.",
            ),
            AlsoTrackingItem(
                head="Turkish currency instability.",
                tail="Vendor payment exposure under review by Treasury; joint assessment with GRC expected by late May.",
            ),
            AlsoTrackingItem(
                head="US IRA tariff adjustments.",
                tail="Indirect supply-chain effect under assessment; no direct AeroGrid footprint impact identified.",
            ),
        ],
        watch_next=[
            WatchNextItem(
                horizon="6–12 weeks",
                head="Moroccan post-election coalition stability.",
                tail="Drives whether Cape Wind posture normalises or remains raised into Q4.",
            ),
            WatchNextItem(
                horizon="Q3 rollout",
                head="CVE-2026-1847 — turbine SCADA patching.",
                tail="Portfolio-wide deployment target; residual exposure modelled for October board.",
            ),
            WatchNextItem(
                horizon="Oct onward",
                head="Winter season onset · MED offshore.",
                tail="Taranto, Cape Wind weather-risk baseline reset; standard seasonal review.",
            ),
        ],
        matrix=RiskMatrix(
            headline="Two scenarios in the upper-right warrant board-level action this quarter.",
            bottom_line=(
                "S-07 (MED) and S-11 (NCE) are the board-action set. The remaining six are "
                "within management authority and are tracked through the RSM reporting line."
            ),
            dots=[
                MatrixDot(
                    scenario_id="S-07", region="MED", label="Unrest · Cape Wind (MED)",
                    likelihood=72, impact=72, severity="high", label_position="up",
                ),
                MatrixDot(
                    scenario_id="S-11", region="NCE", label="OT cyber · NCE",
                    likelihood=78, impact=82, severity="high", label_position="down",
                ),
                MatrixDot(
                    scenario_id="S-14", region="APAC", label="Blades supply · APAC",
                    likelihood=48, impact=50, severity="medium", label_position="down",
                ),
                MatrixDot(
                    scenario_id="S-09", region="AME", label="3P vendor · AME",
                    likelihood=44, impact=38, severity="medium", label_position="left",
                ),
                MatrixDot(
                    scenario_id="S-03", region="LATAM", label="Local unrest · LATAM",
                    likelihood=22, impact=30, severity="monitor", label_position="right",
                ),
                MatrixDot(
                    scenario_id="S-05", region="MED", label="GR local · MED",
                    likelihood=32, impact=20, severity="monitor", label_position="down",
                ),
                MatrixDot(
                    scenario_id="S-12", region="NCE", label="OT/ICS reg · NCE",
                    likelihood=58, impact=62, severity="medium", label_position="up",
                ),
                MatrixDot(
                    scenario_id="S-06", region="MED", label="TR vendor · MED",
                    likelihood=38, impact=14, severity="monitor", label_position="down",
                ),
            ],
            register_tail=[
                RegisterRow(id="S-03", region="LATAM", headline="Local unrest · minor sites", severity="monitor"),
                RegisterRow(id="S-05", region="MED",   headline="GR local election exposure", severity="monitor"),
                RegisterRow(id="S-06", region="MED",   headline="TR currency · vendor pay",    severity="monitor"),
                RegisterRow(id="S-07", region="MED",   headline="Unrest · Cape Wind",          severity="high"),
                RegisterRow(id="S-09", region="AME",   headline="3P vendor compromise",        severity="medium"),
                RegisterRow(id="S-11", region="NCE",   headline="Cyber · OT vendor",           severity="high"),
                RegisterRow(id="S-12", region="NCE",   headline="OT/ICS regulation",           severity="medium"),
                RegisterRow(id="S-14", region="APAC",  headline="Blades · supply chain",       severity="medium"),
            ],
        ),
        scenarios=[
            BoardScenario(
                id="S-07", region="MED · Morocco",
                title="Sustained civil unrest in the Casablanca corridor near Cape Wind.",
                type_tags=["Political-security", "Crown-jewel exposure", "Horizon: 0–12 weeks"],
                posture=ScenarioPosture(
                    pill_label="HIGH · MED likelihood", pill_severity="high",
                    severity="HIGH", likelihood="MED", admiralty="B2",
                    delta_vs_prior="↑ from MED",
                ),
                narrative=ScenarioNarrative(
                    lede=(
                        "The April general election closed without a clear coalition. "
                        "Youth unemployment and regional economic stress remain the structural drivers; "
                        "the post-election window is the acute one."
                    ),
                    paragraphs=[
                        (
                            "Protest activity clustered in urban centres through the polling period and has not fully "
                            "subsided. Security-force posture in the Casablanca corridor is elevated and is expected "
                            "to remain so until a governing coalition is named. The Cape Wind site itself has not been "
                            "the object of protest; the proximate risks are access-road disruption, expat movement, "
                            "and secondary effects on local vendor continuity."
                        ),
                        (
                            "In parallel, APT28 scanning against Moroccan energy ASNs has run coincident with the "
                            "election calendar. The SOC has observed no anomalies at Cape Wind, but the cyber-physical "
                            "coupling means the scenario is being assessed as a joint signal: state-actor cyber posture "
                            "is mirroring state-actor physical interest, and the monitoring posture reflects that."
                        ),
                        (
                            "Base case is normalisation over a 6–12 week horizon as coalition formation completes. "
                            "Tail risk is prolonged coalition friction combined with economic stress — that case "
                            "reaches the October board."
                        ),
                    ],
                ),
                implications=[
                    "Offtake continuity — local grid interface",
                    "Expat safety & movement (12 FTE on site)",
                    "Local reputation with host ministry",
                    "Insurance premium renewal (Q4 cycle)",
                ],
                baselines_moved=[
                    "Regional posture: <strong>MED → HIGH</strong>",
                    "Site watch: <strong>normal → raised</strong>",
                    "Expat travel: <strong>permitted → essential only</strong>",
                ],
                drivers=[
                    "Post-election coalition friction; no clear plurality winner.",
                    "Youth unemployment at structural highs; regional wage stagnation.",
                    "Broader regional economic stress (currency, remittances).",
                    "Historic pattern of post-poll protest activity in urban centres.",
                ],
                actions=[
                    "Continue raised site watch at Cape Wind through end Q3.",
                    "Reassess severity at the October board based on coalition outcome.",
                    "Maintain SOC joint-signal monitoring on Moroccan energy ASNs.",
                    "No board approval needed this quarter; noting for awareness.",
                ],
                evidence_anchors=[
                    EvidenceRef(ref="E1", headline="MA election result · Reuters", admiralty="B1"),
                    EvidenceRef(ref="E2", headline="Casablanca protest tracker · Le360", admiralty="B2"),
                    EvidenceRef(ref="E4", headline="Security posture advisory · Seerist", admiralty="A2"),
                    EvidenceRef(ref="C4", headline="ASN scanning · CERT-MA", admiralty="B2"),
                    EvidenceRef(ref="C5", headline="APT28 TTP · NCSC brief", admiralty="B1"),
                ],
            ),
            BoardScenario(
                id="S-11", region="NCE · EU wind operators",
                title="Cyber intrusion into AeroGrid OT via a shared SCADA vendor.",
                type_tags=["Cyber · campaign-driven", "Shared-vendor exposure", "Horizon: 0–8 weeks"],
                posture=ScenarioPosture(
                    pill_label="HIGH · MED-HIGH likelihood", pill_severity="high",
                    severity="HIGH", likelihood="MED-HIGH", admiralty="B1",
                    delta_vs_prior="↑ new evidence",
                ),
                narrative=ScenarioNarrative(
                    lede=(
                        "The SolarGlare ransomware campaign is now confirmed at two German wind operators. "
                        "Four additional EU operators report probable targeting. The campaign's TTPs match a "
                        "single actor set, and the shared-vendor vector is active."
                    ),
                    paragraphs=[
                        (
                            "AeroGrid NCE sites run the same Vendor X SCADA stack implicated in the confirmed intrusions. "
                            "Patch availability for CVE-2026-1847 is current; portfolio deployment stands at 40% as of the "
                            "issue date. CVE-2026-1722 (grid HMI) has a workaround only, with two sites affected. "
                            "Vendor X's access into AeroGrid environments has not been reviewed since Q3 2025."
                        ),
                        (
                            "The governance question is no longer whether NCE is exposed — it is whether the current patch "
                            "cadence and vendor-access posture are sufficient given the campaign's demonstrated velocity. "
                            "SOC monitoring has been raised; no intrusions observed to date."
                        ),
                        (
                            "If the campaign reaches an AeroGrid operator, regulatory reporting is triggered under the "
                            "pending EU OT/ICS framework and under existing national obligations. That is the downside "
                            "tail case."
                        ),
                    ],
                ),
                implications=[
                    "Generation availability across NCE fleet",
                    "OT data integrity (metering, control)",
                    "Regulatory reporting (national + draft EU)",
                    "Insurance cyber-rider — review trigger",
                ],
                baselines_moved=[
                    "NCE cyber: <strong>held → pressured</strong>",
                    "Vendor X risk: <strong>MED → HIGH</strong>",
                    "Patch SLA: <strong>30d → 14d for 1847</strong>",
                ],
                drivers=[
                    "SolarGlare campaign confirmed at 2 DE operators; 4 probable.",
                    "Shared SCADA vendor (Vendor X v4.2) across the NCE fleet.",
                    "CVE-2026-1847 patch at 40% rollout — residual exposure.",
                    "Third-party vendor access unreviewed since Q3 2025.",
                ],
                actions=[
                    "<strong>Board ask:</strong> endorse accelerated CVE-2026-1847 patching — 14-day SLA.",
                    "<strong>Board ask:</strong> approve a third-party vendor access review, scope Vendor X + two adjacent.",
                    "SOC maintains raised monitoring posture until campaign subsides.",
                    "Report back at October board with patch completion and review findings.",
                ],
                evidence_anchors=[
                    EvidenceRef(ref="C1", headline="SolarGlare campaign · CERT-EU", admiralty="A2"),
                    EvidenceRef(ref="C2", headline="DE operator disclosure · Der Spiegel", admiralty="B1"),
                    EvidenceRef(ref="C3", headline="CVE-2026-1847 · CISA advisory", admiralty="A1"),
                    EvidenceRef(ref="C6", headline="Vendor X advisory · vendor bulletin", admiralty="B2"),
                    EvidenceRef(ref="E8", headline="Draft EU OT/ICS framework · EC", admiralty="A1"),
                ],
            ),
            BoardScenario(
                id="S-14", region="APAC · blade supply",
                title="Supply-chain disruption on turbine blades via a single-source supplier.",
                type_tags=["Supply chain", "Project-delivery risk", "Horizon: 2027 delivery window"],
                posture=ScenarioPosture(
                    pill_label="MEDIUM · LOW-MED likelihood", pill_severity="medium",
                    severity="MED", likelihood="LOW-MED", admiralty="B2",
                    delta_vs_prior="↓ transit eased",
                ),
                narrative=ScenarioNarrative(
                    lede=(
                        "Blade supply for the 2027 project cohort currently relies on a single Chinese supplier. "
                        "Transit conditions in the APAC corridor improved this quarter, which eases the short-term "
                        "logistics risk but leaves the structural single-source exposure intact."
                    ),
                    paragraphs=[
                        (
                            "The governance concern is strategic, not tactical. Geopolitical export-restriction risk — "
                            "against the backdrop of ongoing US-China trade policy shifts — is the case that would bind. "
                            "A disruption at the supplier in late 2026 would propagate through the 2027 delivery timeline "
                            "and create an observable EBITDA impact in 2027–28."
                        ),
                        (
                            "Procurement has a qualified second-source programme in early stages. Target qualification is "
                            "Q4 2026; that date is the board-level milestone to track. No quarterly board action is requested; "
                            "inclusion here is for visibility and milestone anchoring."
                        ),
                    ],
                ),
                implications=[
                    "2027 project delivery timeline",
                    "EBITDA exposure 2027–28",
                    "Procurement programme cost",
                    "Customer commitments (2 offtake contracts)",
                ],
                baselines_moved=[
                    "APAC transit: <strong>watched → stable</strong>",
                    "Supplier concentration: <strong>held</strong>",
                    "2nd-source: <strong>on plan (Q4 2026)</strong>",
                ],
                drivers=[
                    "Single-source Chinese supplier for 2027 blade cohort.",
                    "Geopolitical export-restriction risk — trade policy shifts.",
                    "Transit corridor improved (short-term), structural exposure held.",
                    "Second-source qualification in early stages.",
                ],
                actions=[
                    "Procurement to complete second-source qualification by Q4 2026.",
                    "Treasury to model 2027–28 EBITDA under disruption case.",
                    "Reconfirm at October board; escalate to board-action if 2nd-source slips past Q1 2027.",
                    "No board approval required this quarter.",
                ],
                evidence_anchors=[
                    EvidenceRef(ref="E9", headline="APAC transit brief · Seerist", admiralty="B2"),
                    EvidenceRef(ref="E10", headline="Supplier concentration note · Internal", admiralty="C2"),
                    EvidenceRef(ref="E11", headline="US-China trade policy tracker · Nikkei", admiralty="B2"),
                    EvidenceRef(ref="E12", headline="Procurement 2nd-source plan · Internal", admiralty="A1"),
                ],
            ),
        ],
        methodology=Methodology(
            sources={
                "Commercial": "Seerist (Control Risks) — geopolitical feed, confidence-rated.",
                "OSINT":      "Firecrawl + Tavily discovery across accredited regional media.",
                "Cyber":      "CERT-EU, CISA, NCSC, vendor advisories.",
                "Internal":   "RSM weekly INTSUMs (MED, NCE, APAC, LATAM, AME).",
            },
            rating_system={
                "Severity":   "CRITICAL · HIGH · MEDIUM · MONITOR.",
                "Likelihood": "HIGH · MED-HIGH · MEDIUM · LOW-MED · LOW.",
                "Admiralty":  "A1 (near-certain) — F6 (unverifiable). Typical range: B1–C2.",
                "Confidence": "NATO framework: HIGH / MODERATE / LOW.",
            },
            reading_rules=[
                ReadingRule(
                    cond="B2 → A1",
                    then_markdown=(
                        "A scenario moving from <strong>B2 to A1</strong> on Admiralty should be treated as "
                        "near-certain. Governance response is warranted even if severity is unchanged."
                    ),
                ),
                ReadingRule(
                    cond="MED → HIGH",
                    then_markdown=(
                        "A severity change from <strong>MEDIUM to HIGH</strong> warrants a board conversation in the "
                        "next cycle — not necessarily an action, but not silent either."
                    ),
                ),
                ReadingRule(
                    cond="Quiet region",
                    then_markdown=(
                        "A region in <strong>baseline</strong> with no new triggers is a signal in itself. "
                        "The absence of escalation is an intelligence product — not an omission."
                    ),
                ),
                ReadingRule(
                    cond="Joint signal",
                    then_markdown=(
                        "Cyber and physical activity in the same country should be read as <strong>one signal</strong>, "
                        "not two. S-07 (MED) is the current example."
                    ),
                ),
                ReadingRule(
                    cond="Evidence chain",
                    then_markdown=(
                        "Every assertion traces to an <strong>E- or C-prefixed anchor</strong>. "
                        "If an anchor is missing, challenge the assertion."
                    ),
                ),
            ],
            against_last_quarter_prose=(
                "Q1 2026 flagged Moroccan election risk as emerging; this quarter escalates it to board-action. "
                "SolarGlare was a watch item last quarter; it is now confirmed. APAC transit was watched; "
                "it is now stable. The three other regions have held at baseline."
            ),
            against_last_quarter_kv={
                "Deltas":     "3 scenarios moved severity; 1 moved likelihood; 2 moved Admiralty.",
                "Continuity": "6 of 8 scenarios carried from Q1; 2 are new this quarter (S-11, S-12).",
                "Retired":    "S-08 (MED winter storms) retired post-season · archived in risk register.",
                "Next cycle": "October 2026. Issue date expected 10 October; board meeting 14 October.",
            },
        ),
        end_matter=EndMatter(
            distribution={
                "01–11":  "Board of Directors (11 copies, numbered).",
                "12":     "Chair, Audit & Risk Committee — read-deep copy.",
                "13":     "Chief Executive Officer.",
                "14":     "Chief Information Security Officer.",
                "15":     "General Counsel.",
                "16":     "VP Risk · author of record.",
                "Master": "Global Security & Intelligence, secure archive.",
            },
            provenance={
                "Prepared":    "M. Okonkwo · Director, Threat Intelligence.",
                "Contributed": "RSMs (MED / NCE / APAC / LATAM / AME); CISO office; Treasury.",
                "Reviewed":    "R. Salazar · VP Risk & Resilience.",
                "Approved":    "E. Wada · Chief Risk Officer.",
                "Version":     "v1.0 — final · supersedes v0.7 (pre-read draft).",
                "Issued":      "17 April 2026 · 06:00 UTC.",
            },
            handling_paragraphs=[
                (
                    "<strong>Internal — Board Distribution.</strong> Printed copies are numbered; digital copy resides in "
                    "the board portal with access confined to the distribution list above. Do not forward or reproduce."
                ),
                (
                    "Return printed copies to the Company Secretary at the close of the board meeting for "
                    "secure destruction."
                ),
                "Queries, challenges, or corrections: contact the preparer direct within 10 business days of issue.",
            ],
            linked_products={
                "Monthly": "CISO Brief — April 2026 (cyber-led, cross-regional).",
                "Weekly":  "RSM INTSUM series — MED, NCE, APAC, LATAM, AME.",
                "Ad hoc":  "Scenario memos on request from the Audit & Risk Committee.",
                "Next":    "Q3 Board Report · issue 10 Oct 2026 · board 14 Oct 2026.",
            },
        ),
    )
