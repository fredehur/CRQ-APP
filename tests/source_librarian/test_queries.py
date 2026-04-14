"""Tests for tools/source_librarian/queries.py — pure template fill."""
from datetime import date
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def test_year_window_two_years():
    from tools.source_librarian.queries import year_window
    assert year_window(2, today=date(2026, 4, 14)) == "2024 2025"


def test_year_window_three_years():
    from tools.source_librarian.queries import year_window
    assert year_window(3, today=date(2026, 4, 14)) == "2023 2024 2025"


def test_build_queries_per_scenario_uses_first_terms():
    from tools.source_librarian.intents import load_intent_file
    from tools.source_librarian.queries import build_queries
    intent = load_intent_file(FIX / "intent_wind_minimal.yaml")
    plan = build_queries(intent, today=date(2026, 4, 14))

    assert set(plan.keys()) == {"WP-001", "WP-002"}

    wp1 = plan["WP-001"]
    assert "system intrusion wind turbine SCADA attack 2023 2024 2025" in wp1["news_set"]
    assert "system intrusion wind turbine SCADA report pdf" in wp1["doc_set"]
    assert len(wp1["news_set"]) == 2
    assert len(wp1["doc_set"]) == 2


def test_build_queries_year_respects_per_scenario_window():
    from tools.source_librarian.intents import load_intent_file
    from tools.source_librarian.queries import build_queries
    intent = load_intent_file(FIX / "intent_wind_minimal.yaml")
    plan = build_queries(intent, today=date(2026, 4, 14))
    wp2_news = " ".join(plan["WP-002"]["news_set"])
    assert "2024 2025" in wp2_news
    assert "2023" not in wp2_news
