"""Tests for tools/source_librarian/summarizer.py — Haiku per (scenario × source)."""
from unittest.mock import MagicMock, patch


def _haiku_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_extract_figures_finds_dollar_amounts_and_percentages():
    from tools.source_librarian.summarizer import extract_figures
    text = "Wind operators saw 68% YoY increase; mean cost was $4.1M and recovery 14 days."
    figs = extract_figures(text)
    assert "68%" in figs
    assert "$4.1M" in figs
    assert "14 days" not in figs


def test_extract_figures_handles_dollar_billion_and_thousand_separators():
    from tools.source_librarian.summarizer import extract_figures
    text = "Total losses reached $4.45 billion in 2023, with averages around $9,800,000."
    figs = extract_figures(text)
    assert any("4.45 billion" in f for f in figs)
    assert any("9,800,000" in f for f in figs)


def test_summarize_pair_calls_haiku_and_returns_summary_and_figures():
    from tools.source_librarian.summarizer import summarize_pair
    client = MagicMock()
    client.messages.create.return_value = _haiku_response(
        "Wind operators saw a 68% YoY rise in OT incidents. Mean recovery cost reached $4.1M."
    )
    summary, figures = summarize_pair(
        client=client,
        scenario_name="Ransomware on OT/SCADA",
        scenario_notes="Vestas 2021 canonical.",
        markdown="long body...",
    )
    assert "68%" in summary
    assert "$4.1M" in figures
    assert "68%" in figures


def test_summarize_pair_two_sentence_cap():
    from tools.source_librarian.summarizer import summarize_pair
    client = MagicMock()
    client.messages.create.return_value = _haiku_response(
        "First sentence here. Second sentence here. Third sentence overflow. Fourth too."
    )
    summary, _ = summarize_pair(
        client=client, scenario_name="x", scenario_notes="", markdown="...",
    )
    assert summary.count(".") <= 2
    assert "Third sentence" not in summary


def test_summarize_pair_haiku_failure_returns_none_and_empty_figures():
    from tools.source_librarian.summarizer import summarize_pair
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    summary, figures = summarize_pair(
        client=client, scenario_name="x", scenario_notes="", markdown="...",
    )
    assert summary is None
    assert figures == []


def test_summarize_pair_retries_on_rate_limit_then_succeeds():
    from tools.source_librarian.summarizer import summarize_pair
    client = MagicMock()
    rate_limit = RuntimeError("rate_limit_error")
    client.messages.create.side_effect = [
        rate_limit, rate_limit, _haiku_response("Success. After retries."),
    ]
    with patch("tools.source_librarian.summarizer.time.sleep"):
        summary, _ = summarize_pair(
            client=client, scenario_name="x", scenario_notes="", markdown="...",
        )
    assert summary is not None
    assert "Success" in summary
    assert client.messages.create.call_count == 3
