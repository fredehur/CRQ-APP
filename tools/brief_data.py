"""Shared brief data — single source of truth for build_pdf.py and build_pptx.py."""

BRIEF_DATA = {
    "title":          "Global Threat Brief · Cycle 2026-W16",
    "doc_type":       "GLOBAL THREAT BRIEF",
    "cover_title":    "Cycle 2026-W16",
    "cover_subtitle": "11-17 April 2026",
    "published_date": "2026-04-17",
    "prepared_by":    "CRQ Analyst Team",
    "version":        "v2.0 · 2026-04-20",
    "cycle":          "2026-W16",
    "previous_cycle": "CYCLE 2026-W15",
    "refreshed":      "2026-04-17",
    "footer_left":    "GLOBAL CYCLE BRIEF · v2.0",

    "exec_top_line": (
        "Global posture held at HIGH. Two new CRITICAL-grade developments this cycle; "
        "three ongoing situations worth sustained attention."
    ),
    "confidence": "HIGH",
    "admiralty":  "B2",

    "key_developments": [
        {
            "severity": "CRITICAL", "is_new": True, "region": "MED",
            "headline": "Eastern Mediterranean shadow-fleet activity confirmed",
            "impact": (
                "Suez throughput degraded; 3 insurers withdrew Gulf-of-Iskenderun coverage "
                "within 72 hours. Reroute adds 8-14 days."
            ),
        },
        {
            "severity": "CRITICAL", "is_new": False, "region": "APAC",
            "headline": "Taiwan Strait - sustained chokepoint pressure",
            "impact": "APAC turbine shipments at 2-3x baseline transit costs; unchanged for 3 cycles.",
        },
        {
            "severity": "HIGH", "is_new": True, "region": "APAC",
            "headline": "JP/KR energy - OT phishing campaign confirmed",
            "impact": "Active sector targeting; elevated monitoring cadence for OT-connected sites.",
        },
        {
            "severity": "HIGH", "is_new": False, "region": "APAC",
            "headline": "Southeast Asia typhoon-driven crew shortages",
            "impact": "Regional shipping throughput down ~22%.",
        },
        {
            "severity": "MEDIUM", "is_new": False, "region": "NCE",
            "headline": "Baltic cable interference activity ongoing",
            "impact": None,
        },
    ],

    "also_tracking": [
        {"severity": "MONITOR", "region": "LATAM", "text": "Panama Canal drought-related logistics strain"},
        {"severity": "MONITOR", "region": "NCE",   "text": "Emerging EU subsea-infrastructure regulation"},
        {"severity": "MONITOR", "region": "AME",   "text": "US grid OT reconnaissance activity"},
    ],

    "watch_next": (
        "Typhoon season closure and Taiwan Strait stabilization are the two variables that would "
        "de-escalate APAC. Watch MED for further underwriter withdrawals - insurance-market "
        "response remains the leading indicator of escalation."
    ),

    "total_scenarios": 3,
    "scenarios": [
        {
            "number": "01", "region": "APAC",
            "headline": "Taiwan Strait disruption escalates into sustained chokepoint pressure",
            "drivers": [
                {"letter": "M", "label": "Maritime coercion intensifies",   "implication": "Strait transit costs sustained 2-3x baseline"},
                {"letter": "W", "label": "Typhoon season prolonged",        "implication": "Crew shortages persist into Q3"},
                {"letter": "C", "label": "OT-targeted intrusion campaign",  "implication": "Energy-sector ICS exposure widens"},
            ],
            "type": "BASELINE", "type_subtitle": "Forward projection of current trends",
            "bold_conclusion": "Concentration is structural, not cyclical.",
            "body": (
                "APAC's share of CRITICAL signal volume has held within +-3 points across the last three reporting "
                "cycles despite changes in collection coverage. The drivers - maritime activity in the Taiwan Strait, "
                "weather-driven crew shortages across Southeast Asian shipping lanes, and OT-targeted phishing in "
                "JP/KR energy - reinforce one another and are unlikely to resolve absent exogenous intervention."
            ),
            "likelihood_verdict": "Most likely if posture holds: continued elevation through Q2.",
            "implications": [
                {"label": "Operational", "text": "Strait-dependent shipping at sustained risk; reroute adds 8-14 days."},
                {"label": "Financial",   "text": "Energy/insurance margin pressure continues; reinsurance firming."},
                {"label": "Competitive", "text": "Diversified routing gains advantage; concentration punished."},
                {"label": "Legal",       "text": "Sanctions and emergency measures evolving rapidly."},
            ],
            "actions": [
                "Stress-test exposure to Strait shipping & energy disruption",
                "Harden resilience for energy, logistics, cyber-dependent ops",
                "Review sanctions, insurance, counterparty risk per jurisdiction",
                "Activate maritime route contingencies; validate alternate ports",
            ],
            "evidence": "Admiralty B2 · 12 sources · refreshed 2026-04-17 06:00 UTC",
        },
        {
            "number": "02", "region": "MED",
            "headline": "Eastern Mediterranean port disruption confirms shadow-fleet escalation pattern",
            "drivers": [
                {"letter": "M", "label": "Shadow-fleet activity confirmed", "implication": "Insurance withdrawal accelerating across multiple carriers"},
                {"letter": "G", "label": "Regional tensions propagating",   "implication": "Adjacent ports entering elevated-risk classifications"},
                {"letter": "C", "label": "Port-OT reconnaissance observed", "implication": "Pre-positioning signatures consistent with prior campaigns"},
            ],
            "type": "PLAUSIBLE", "type_subtitle": "Realistic alternative under evolving drivers",
            "bold_conclusion": "Ceasefire conditions are failing the stress test.",
            "body": (
                "Eastern Mediterranean port disruption has escalated from MONITOR to CRITICAL in a single cycle, "
                "driven by confirmed shadow-fleet activity and corroborating port-OT reconnaissance signatures. "
                "Insurance markets are responding faster than diplomatic channels: three underwriters withdrew "
                "Gulf-of-Iskenderun coverage within 72 hours of the latest incidents."
            ),
            "likelihood_verdict": "More likely if current trajectory holds; de-escalation windows narrowing.",
            "implications": [
                {"label": "Operational", "text": "Eastern Med transit at severe risk; Suez throughput degraded."},
                {"label": "Financial",   "text": "Cargo insurance spiking; energy shipments repriced weekly."},
                {"label": "Competitive", "text": "Flexibility premium grows for diversified shipping networks."},
                {"label": "Legal",       "text": "Fragmented sanctions; enforcement unpredictability rising."},
            ],
            "actions": [
                "Accelerate alternate routing (Cape, trans-Atlantic) contingencies",
                "Pre-position inventory in safer regional nodes",
                "Validate port-OT segmentation and backup communications",
                "Elevate executive decision cadence to weekly on MED exposure",
            ],
            "evidence": "Admiralty B2 · 9 sources · refreshed 2026-04-17 06:00 UTC",
        },
        {
            "number": "03", "region": "NCE",
            "headline": "Baltic cable interference activity persistent but contained; watch posture maintained",
            "drivers": [
                {"letter": "M", "label": "Subsea infrastructure signaling", "implication": "Pattern consistent with prior-cycle gray-zone activity"},
                {"letter": "G", "label": "State-adjacent signaling",        "implication": "No direct attribution; plausible deniability preserved"},
                {"letter": "C", "label": "Opportunistic intrusion attempts","implication": "Elevated baseline but no campaign-scale activity"},
            ],
            "type": "WILDCARD", "type_subtitle": "Low-probability, high-impact - maintain monitoring",
            "bold_conclusion": "Posture stable but not resolved - watch for escalation triggers.",
            "body": (
                "Baltic cable interference activity remains ongoing but contained to patterns consistent with prior "
                "cycles. No escalation triggers observed this cycle, but the tempo of subsea infrastructure signaling "
                "has not diminished. NCE posture is MEDIUM with MONITOR-grade elevation warranted on Baltic-specific assets."
            ),
            "likelihood_verdict": "Stable probability; watch for triggering events rather than gradual change.",
            "implications": [
                {"label": "Operational",  "text": "No immediate impact; contingency plans warm."},
                {"label": "Financial",    "text": "Limited cost impact; elevated monitoring resource draw."},
                {"label": "Legal",        "text": "Emerging EU frameworks on subsea infrastructure."},
                {"label": "Reputational", "text": "Low immediate reputational exposure."},
            ],
            "actions": [
                "Maintain elevated Baltic-specific monitoring cadence",
                "Validate subsea redundancy pathing quarterly",
                "Engage regulatory frameworks proactively",
                "Pre-brief comms team on possible triggering scenarios",
            ],
            "evidence": "Admiralty B3 · 6 sources · refreshed 2026-04-17 06:00 UTC",
        },
    ],

    "matrix": {
        "headline": "Two scenarios cluster in the high-likelihood, high-impact quadrant - both APAC and MED",
        "bottom_line": (
            "Top-right quadrant concentration suggests the cycle's risk profile is convergent rather than "
            "diversified. Two of eight monitored scenarios drive disproportionate exposure, and both are in "
            "the maritime-chokepoint category - suggesting a systemic pattern rather than isolated incidents."
        ),
        "reading": (
            "Each dot is one monitored scenario, plotted by current likelihood (x) and potential impact (y). "
            "Color encodes severity grade. The shaded zone marks the high-likelihood / high-impact quadrant."
        ),
        "dots": [
            {"label": "APAC · Taiwan Strait", "severity": "CRITICAL", "x": 78, "y": 82},
            {"label": "MED · Shadow-fleet",   "severity": "CRITICAL", "x": 68, "y": 76},
            {"label": "APAC · JP/KR OT",      "severity": "HIGH",     "x": 62, "y": 64},
            {"label": "APAC · SEA typhoon",   "severity": "HIGH",     "x": 54, "y": 52},
            {"label": "NCE · Baltic cable",   "severity": "MEDIUM",   "x": 38, "y": 58},
            {"label": "LATAM · Panama",       "severity": "MEDIUM",   "x": 46, "y": 34},
            {"label": "AME · US grid",        "severity": "MONITOR",  "x": 30, "y": 62},
            {"label": "NCE · EU reg",         "severity": "MONITOR",  "x": 22, "y": 40},
        ],
    },

    "methodology": {
        "meta": [
            ("PIPELINE VERSION",    "crq-app v0.9.3"),
            ("MODEL VERSION",       "Claude Sonnet 4.6 (analyst), Haiku 4.5 (gate)"),
            ("COLLECTION WINDOW",   "11-17 April 2026 (UTC)"),
            ("EVIDENCE CEILING",    "B2 (Usually reliable, probably true)"),
            ("REGIONS COVERED",     "APAC, AME, LATAM, MED, NCE"),
            ("SCENARIOS MONITORED", "8 active across 5 regions"),
        ],
        "sources": [
            ("A1", "Maritime AIS aggregator (commercial)"),
            ("B2", "Regional security service notifications"),
            ("B2", "OSINT - open vessel tracking + media"),
            ("B3", "Sectoral CERT advisories (JP, KR)"),
            ("C2", "Industry trade-body bulletins"),
            ("B2", "Recorded Future Insikt (cross-ref)"),
            ("B2", "Mandiant Advantage threat feed"),
        ],
        "changes": [
            ("^", "MED escalated MEDIUM -> CRITICAL"),
            ("^", "APAC scenario count 6 -> 8"),
            ("^", "Confidence MEDIUM -> HIGH"),
            ("->", "AME / LATAM / NCE unchanged"),
            ("+", "1 new scenario opened (NCE Baltic)"),
            ("X", "0 scenarios resolved"),
        ],
    },
}
