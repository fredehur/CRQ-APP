from datetime import date


def board_example() -> dict:
    return {
        "cover": {
            "title": "AeroGrid · Board Report · Q2 2026",
            "classification": "INTERNAL — BOARD DISTRIBUTION",
            "prepared_by": "M. Okonkwo",
            "reviewed_by": "R. Salazar",
            "issued_at": date(2026, 4, 17),
            "version": "v1.0 — final",
            "quarter": "Q2 2026",
            "quarter_short": "Q2·26",
            "board_meeting": "21 April 2026 · London HQ",
            "distribution_note": "AeroGrid Wind Solutions · Board of Directors",
        },
        "state_of_risk_line": "Q2 2026 saw elevated North African unrest...",
        "cover_thesis_title": "Two items warrant board action.",
        "cover_thesis_subtitle": "Six remain within management authority.",
        "posture": {
            "overall_posture": "HIGH", "posture_shift": "↑ from MEDIUM · Q1",
            "admiralty": "B2", "admiralty_shift": "held · Q1 was B2",
            "scenarios_on_watch": 8, "scenarios_split": "2 board-action · 6 mgmt",
            "next_review": "Q3 board · October 2026",
        },
        "board_takeaways": [
            {"n": 1, "severity": "high",
             "body_markdown": "**Cape Wind (crown-jewel, MA)** remains on raised watch...",
             "anchor": "S-07 · MED"},
        ],
        "delta_bar": [
            {"region": "MED", "direction": "up", "label": "Raised",
             "cause": "MA election, IT port strike · posture raised through May."},
            {"region": "NCE", "direction": "high", "label": "Held · cyber ↑",
             "cause": "Physical quiet. Sector-targeting cyber active."},
            {"region": "APAC", "direction": "down", "label": "Quieted",
             "cause": "Transit corridor stability improved."},
            {"region": "LATAM", "direction": "flat", "label": "Baseline",
             "cause": "No new triggers. Watchlist cold."},
            {"region": "AME", "direction": "flat", "label": "Baseline",
             "cause": "No new triggers. Third-party vendor watch retained."},
        ],
        "key_developments": [],
        "also_tracking": [],
        "watch_next": [],
        "matrix": {
            "headline": "Concentration in MED political and NCE cyber.",
            "bottom_line": "Two scenarios in the upper-right warrant board-level action.",
            "dots": [], "register_tail": [],
        },
        "scenarios": [],
        "methodology": {
            "sources": {}, "rating_system": {}, "reading_rules": [],
            "against_last_quarter_prose": "", "against_last_quarter_kv": {},
        },
        "end_matter": {
            "distribution": {}, "provenance": {},
            "handling_paragraphs": [], "linked_products": {},
        },
    }


def ciso_example() -> dict:
    base_cover = {
        "title": "AeroGrid · CISO Brief · April 2026",
        "classification": "INTERNAL — CISO OFFICE",
        "prepared_by": "M. Okonkwo",
        "reviewed_by": "R. Salazar",
        "issued_at": date(2026, 4, 17),
        "version": "v1.0",
        "month": "April 2026",
        "month_short": "04·26",
        "audience": "Primary: CISO · Secondary: VP Security, GRC, Threat Intel",
    }
    return {
        "cover": base_cover,
        "cover_thesis_primary": "The month's dominant signal is EU ransomware pressure.",
        "cover_thesis_secondary": "Physical remains quiet outside MED.",
        "state_of_risk_line": "April 2026 is cyber-pressed with MED physical overlay.",
        "posture": {
            "posture": "HIGH",
            "posture_shift": "↑ from MODERATE",
            "admiralty": "B2",
            "admiralty_shift": "held",
            "regions_moved": 2,
            "regions_movement_summary": "MED up, NCE cyber-pressed.",
            "scenarios_watched": 8,
            "scenarios_delta_note": "2 new this month.",
        },
        "ciso_takeaways": [
            {
                "n": 1, "severity": "cyber",
                "body_markdown": "**SolarGlare** confirmed at two DE operators.",
                "anchor": "S-11 · NCE",
            },
        ],
        "regions_grid": [
            {
                "region": "MED", "classification": "moved", "direction": "up",
                "status_label": "Raised", "admiralty": "B2", "admiralty_shift": "held",
                "note": "Cape Wind raised watch.",
                "why_clear_label": "Why raised:", "why_clear_body": "MA election window.",
            },
            {
                "region": "NCE", "classification": "cyber-pressed", "direction": "cyber",
                "status_label": "Cyber-pressed", "admiralty": "B3", "admiralty_shift": "↑ from B2",
                "note": "SolarGlare confirmed.",
                "why_clear_label": "Why cyber:", "why_clear_body": "Sector campaign active.",
            },
            {
                "region": "APAC", "classification": "quieted", "direction": "down",
                "status_label": "Quieted", "admiralty": "B2", "admiralty_shift": "held",
                "note": "Transit stable.",
                "why_clear_label": "Why clear:", "why_clear_body": "No new triggers.",
            },
            {
                "region": "LATAM", "classification": "baseline", "direction": "flat",
                "status_label": "Baseline", "admiralty": "B3", "admiralty_shift": "held",
                "note": "Watchlist cold.",
                "why_clear_label": "Why clear:", "why_clear_body": "No triggers.",
            },
            {
                "region": "AME", "classification": "baseline", "direction": "flat",
                "status_label": "Baseline", "admiralty": "B2", "admiralty_shift": "held",
                "note": "Vendor watch retained.",
                "why_clear_label": "Why clear:", "why_clear_body": "No new triggers.",
            },
        ],
        "cross_regional_items": [],
        "coupling_strip": {
            "region": "MED",
            "label": "Morocco joint signal",
            "physical_track": "Casablanca protest activity post-election.",
            "cyber_track": "APT28 scanning against MA energy ASNs.",
            "summary": "Read: one signal, not two.",
        },
        "cyber_surface": {
            "sector_campaigns": [],
            "actor_activity": [],
            "vulnerability_signal": [],
        },
        "cyber_physical_join": {
            "region": "MED",
            "title_markdown": "Morocco is the month's <span class='cyber-accent'>joint signal</span>.",
            "lede": "Two tracks, one signal.",
            "physical": {
                "title": "Physical",
                "narrative_paragraphs": ["Protest activity clustered."],
                "facts": {"sites": "Cape Wind"},
            },
            "cyber": {
                "title": "Cyber",
                "narrative_paragraphs": ["APT28 scanning."],
                "facts": {"actor": "APT28"},
            },
            "timeline": {
                "range_label": "Apr 1 – Apr 30",
                "ticks": [],
                "physical_events": [],
                "cyber_events": [],
                "join_marks": [],
            },
            "read_summary": "CISO read: joint signal, single scenario.",
        },
        "scenarios": [],
        "evidence_physical": [],
        "evidence_cyber": [],
    }


def rsm_example() -> dict:
    cover = {
        "title": "AeroGrid · RSM Weekly INTSUM · MED · W17",
        "classification": "INTERNAL — RSM",
        "prepared_by": "MED RSM",
        "reviewed_by": "R. Salazar",
        "issued_at": date(2026, 4, 20),
        "version": "v1.0",
    }
    return {
        "cover": cover,
        "admiralty_physical": "B2",
        "admiralty_cyber": "B3",
        "headline": "MED: Cape Wind on raised watch; Taranto commissioning on track.",
        "baseline_strip": [],
        "top_events": [],
        "cyber_strip": [],
        "baselines_moved": [],
        "reading_guide": [],
        "sites": [],
        "regional_cyber": {
            "admiralty": "B3",
            "actors_count": 3,
            "cves_on_watch": 2,
            "active_campaigns": 1,
            "standing_notes": "",
            "sector_signal": [],
            "actor_activity": [],
            "geography_overlay": [],
            "vulnerability_signal": [],
        },
        "secondary_sites": [],
        "minor_sites": [],
        "evidence_physical": [],
        "evidence_cyber": [],
    }
