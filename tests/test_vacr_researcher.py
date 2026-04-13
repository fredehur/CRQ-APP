"""Tests for vacr_researcher.py — Tavily Research API integration."""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(status="completed", figures=None, structured_output="present"):
    """Build a mock TavilyClient that behaves like the real SDK."""
    mock = MagicMock()
    mock.research.return_value = {"request_id": "req-test-123"}
    payload = {"status": status}
    if status == "completed":
        payload["structured_output"] = (
            {"figures": figures or []} if structured_output == "present" else None
        )
    mock.get_research.return_value = payload
    return mock


# ---------------------------------------------------------------------------
# _research_tavily tests
# ---------------------------------------------------------------------------

def test_research_tavily_returns_figures():
    """_research_tavily() returns the figures list from structured_output."""
    from tools.vacr_researcher import _research_tavily

    figures = [
        {
            "dimension": "financial",
            "cost_median_usd": 1_500_000,
            "note": "Median ransomware cost",
            "raw_quote": "Average cost $1.5M",
            "source_name": "IBM X-Force 2024",
            "source_url": "https://example.com",
        }
    ]
    mock_client = _make_client(figures=figures)

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client):
        result = _research_tavily("Ransomware", "energy")

    assert result == figures
    mock_client.research.assert_called_once()
    call_kwargs = mock_client.research.call_args
    assert "Ransomware" in call_kwargs.kwargs.get("input", call_kwargs.args[0] if call_kwargs.args else "")


def test_research_tavily_raises_on_timeout():
    """_research_tavily() raises TimeoutError when research never completes."""
    from tools.vacr_researcher import _research_tavily, _RESEARCH_TIMEOUT_S, _RESEARCH_POLL_INTERVAL_S

    mock_client = _make_client(status="running")  # never completes

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client):
        with patch("time.sleep"):  # skip real sleeps
            with patch("time.monotonic", side_effect=[0, _RESEARCH_TIMEOUT_S + 1]):
                with pytest.raises(TimeoutError):
                    _research_tavily("Ransomware", "energy")


def test_research_tavily_raises_on_missing_structured_output():
    """_research_tavily() raises ValueError when structured_output is absent."""
    from tools.vacr_researcher import _research_tavily

    mock_client = _make_client(structured_output="absent")

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client):
        with pytest.raises(ValueError, match="structured_output"):
            _research_tavily("Ransomware", "energy")


# ---------------------------------------------------------------------------
# research_scenario integration test
# ---------------------------------------------------------------------------

def test_research_scenario_uses_tavily_figures():
    """research_scenario() passes Tavily figures into Sonnet reasoning."""
    from tools.vacr_researcher import research_scenario

    figures = [
        {
            "dimension": "financial",
            "cost_median_usd": 2_000_000,
            "note": "Median cost",
            "raw_quote": "Average $2M",
            "source_name": "Verizon DBIR 2024",
            "source_url": "https://example.com",
        }
    ]
    mock_client = _make_client(figures=figures)

    fake_reasoning = {
        "findings": [{"source": "Verizon DBIR 2024", "quote": "Average $2M", "figure_usd": 2_000_000, "direction": "↑", "assessment": "Supports higher VaCR."}],
        "overall_direction": "↑",
        "agent_summary": "Evidence supports a higher VaCR estimate.",
    }

    import anthropic

    mock_anthropic = MagicMock()
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text=__import__("json").dumps(fake_reasoning))]
    )

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client):
        with patch("anthropic.Anthropic", return_value=mock_anthropic):
            result = research_scenario("Ransomware", 1_000_000, sector="energy")

    assert result["direction"] == "↑"
    assert result["agent_summary"] == "Evidence supports a higher VaCR estimate."
    assert result["incident_type"] == "Ransomware"
    assert result["current_vacr_usd"] == 1_000_000
