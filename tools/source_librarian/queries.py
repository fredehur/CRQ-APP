"""Pure template fill for news_set / doc_set per scenario."""
from __future__ import annotations

from datetime import date
from typing import Optional

from .intents import Intent, ScenarioIntent


def year_window(years: int, today: Optional[date] = None) -> str:
    """Return the most recent `years` complete calendar years (excluding the
    current year), space-joined. e.g. years=3 in 2026 → '2023 2024 2025'."""
    today = today or date.today()
    end = today.year - 1
    start = end - years + 1
    return " ".join(str(y) for y in range(start, end + 1))


def _fill(template: str, scenario: ScenarioIntent, industry_term: str, year_str: str) -> str:
    return (
        template
        .replace("{threat}", scenario.threat_terms[0])
        .replace("{asset}", scenario.asset_terms[0])
        .replace("{industry}", industry_term)
        .replace("{year}", year_str)
    )


def build_queries(intent: Intent, today: Optional[date] = None) -> dict[str, dict[str, list[str]]]:
    """Return {scenario_id: {'news_set': [...], 'doc_set': [...]}}."""
    plan: dict[str, dict[str, list[str]]] = {}
    for sid, scenario in intent.scenarios.items():
        year_str = year_window(scenario.time_focus_years, today=today)
        industry_term = scenario.industry_terms[0]
        plan[sid] = {
            "news_set": [
                _fill(t, scenario, industry_term, year_str)
                for t in intent.query_modifiers.news_set
            ],
            "doc_set": [
                _fill(t, scenario, industry_term, year_str)
                for t in intent.query_modifiers.doc_set
            ],
        }
    return plan
