"""Tests for vacr_researcher.py — Tavily Research API integration."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CONTENT = (
    "Ransomware attacks on energy sector operators averaged $4.1M in 2024 according to IBM X-Force. "
    "Verizon DBIR 2024 found median recovery cost of $3.8M for OT/ICS-impacted incidents. "
    "Probability of ransomware targeting energy operators in a given year: ~12% (Dragos ICS/OT 2024)."
)


def _make_client(status="completed", content=None, empty_content=False):
    """Build a mock TavilyClient that returns research content."""
    mock = MagicMock()
    mock.research.return_value = {"request_id": "req-test-123"}
    payload = {"status": status}
    if status == "completed":
        payload["content"] = "" if empty_content else (content or SAMPLE_CONTENT)
        payload["sources"] = []
    mock.get_research.return_value = payload
    return mock


# ---------------------------------------------------------------------------
# _research_tavily tests
# ---------------------------------------------------------------------------

def test_research_tavily_returns_content():
    """_research_tavily() returns the synthesised content string."""
    from tools.vacr_researcher import _research_tavily

    mock_client = _make_client()

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client):
        result = _research_tavily("Ransomware", "energy")

    assert isinstance(result, str)
    assert len(result) > 0
    mock_client.research.assert_called_once()
    call_kwargs = mock_client.research.call_args
    assert "Ransomware" in call_kwargs.kwargs.get("input", call_kwargs.args[0] if call_kwargs.args else "")


def test_research_tavily_raises_on_timeout():
    """_research_tavily() raises TimeoutError when research never completes."""
    from tools.vacr_researcher import _research_tavily, _RESEARCH_TIMEOUT_S

    mock_client = _make_client(status="running")  # never completes

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client):
        with patch("time.sleep"):
            with patch("time.monotonic", side_effect=[0, _RESEARCH_TIMEOUT_S + 1]):
                with pytest.raises(TimeoutError):
                    _research_tavily("Ransomware", "energy")


def test_research_tavily_raises_on_empty_content():
    """_research_tavily() raises ValueError when content is empty."""
    from tools.vacr_researcher import _research_tavily

    mock_client = _make_client(empty_content=True)

    with patch("tools.vacr_researcher.TavilyClient", return_value=mock_client):
        with pytest.raises(ValueError, match="empty content"):
            _research_tavily("Ransomware", "energy")


# ---------------------------------------------------------------------------
# research_scenario integration test
# ---------------------------------------------------------------------------

def test_research_scenario_uses_tavily_content():
    """research_scenario() passes Tavily content string into Sonnet reasoning."""
    from tools.vacr_researcher import research_scenario

    mock_client = _make_client()

    fake_reasoning = {
        "findings": [{"source": "IBM X-Force", "quote": "averaged $4.1M", "figure_usd": 4_100_000, "direction": "↑", "assessment": "Supports higher VaCR."}],
        "overall_direction": "↑",
        "agent_summary": "Evidence supports a higher VaCR estimate.",
    }

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
