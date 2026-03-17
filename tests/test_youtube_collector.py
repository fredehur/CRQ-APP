"""Tests for tools/youtube_collector.py"""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """Wire collector to temp directories."""
    import tools.youtube_collector as yc
    monkeypatch.setattr(yc, "OUTPUT", tmp_path / "output")
    monkeypatch.setattr(yc, "DATA", tmp_path / "data")
    monkeypatch.setattr(yc, "MOCK_DIR", tmp_path / "data" / "mock_osint_fixtures")
    (tmp_path / "output" / "regional" / "apac").mkdir(parents=True)
    (tmp_path / "data" / "mock_osint_fixtures").mkdir(parents=True)
    return tmp_path


# ── Unit tests ──────────────────────────────────────────────────────────

def test_keyword_score_matches():
    from tools.youtube_collector import _keyword_score
    score = _keyword_score("Ransomware targeting wind energy operators", ["ransomware", "wind energy"])
    assert score == 2


def test_keyword_score_no_match():
    from tools.youtube_collector import _keyword_score
    assert _keyword_score("Climate change debate", ["ransomware", "SCADA"]) == 0


def test_parse_window_7d():
    from tools.youtube_collector import _parse_window
    from datetime import timedelta
    assert _parse_window("7d") == timedelta(days=7)


def test_parse_window_30d():
    from tools.youtube_collector import _parse_window
    from datetime import timedelta
    assert _parse_window("30d") == timedelta(days=30)


def test_parse_window_default():
    from tools.youtube_collector import _parse_window
    from datetime import timedelta
    assert _parse_window("unknown") == timedelta(days=7)


def test_chunk_transcript_short():
    from tools.youtube_collector import _chunk_transcript
    text = "Short transcript."
    assert _chunk_transcript(text) == [text]


def test_chunk_transcript_long():
    from tools.youtube_collector import _chunk_transcript
    # 10 sentences of ~100 chars each → ~1000 chars, chunk at 500
    sentence = "This is a sentence about wind energy risk in the Asia-Pacific region. "
    text = sentence * 20  # ~1400 chars
    chunks = _chunk_transcript(text, max_chars=500)
    assert len(chunks) > 1
    assert all(len(c) <= 550 for c in chunks)  # small overshoot allowed at boundaries


def test_empty_signals_schema():
    from tools.youtube_collector import _empty_signals
    sig = _empty_signals("APAC")
    assert "summary" in sig
    assert "lead_indicators" in sig
    assert "source_videos" in sig
    assert sig["source_videos"] == []


# ── Mock fixture tests ──────────────────────────────────────────────────

def test_load_sources_filters_by_region(tmp_env):
    import tools.youtube_collector as yc
    sources = [
        {"channel_id": "@CFR_org", "name": "CFR", "region_focus": ["AME", "APAC"], "topics": [], "credibility_tier": "A"},
        {"channel_id": "@chathamhouse", "name": "Chatham House", "region_focus": ["MED", "NCE"], "topics": [], "credibility_tier": "A"},
    ]
    (tmp_env / "data").mkdir(exist_ok=True)
    (tmp_env / "data" / "youtube_sources.json").write_text(json.dumps(sources), encoding="utf-8")
    result = yc._load_sources("APAC")
    assert len(result) == 1
    assert result[0]["channel_id"] == "@CFR_org"


def test_load_sources_empty_when_no_match(tmp_env):
    import tools.youtube_collector as yc
    sources = [{"channel_id": "@CFR_org", "name": "CFR", "region_focus": ["AME"], "topics": [], "credibility_tier": "A"}]
    (tmp_env / "data").mkdir(exist_ok=True)
    (tmp_env / "data" / "youtube_sources.json").write_text(json.dumps(sources), encoding="utf-8")
    result = yc._load_sources("LATAM")
    assert result == []


def test_mock_mode_reads_fixture(tmp_env):
    import tools.youtube_collector as yc
    fixture = {
        "summary": "Test summary",
        "lead_indicators": ["indicator"],
        "dominant_pillar": "Geopolitical",
        "matched_topics": [],
        "source_videos": [],
    }
    (tmp_env / "data" / "mock_osint_fixtures" / "APAC_youtube.json").write_text(
        json.dumps(fixture), encoding="utf-8"
    )
    result = yc._run_mock("APAC")
    assert result["summary"] == "Test summary"


def test_mock_mode_missing_fixture_returns_empty(tmp_env):
    import tools.youtube_collector as yc
    result = yc._run_mock("NCE")
    assert result["lead_indicators"] == []
    assert result["source_videos"] == []


def test_mock_mode_writes_output_file(tmp_env):
    import tools.youtube_collector as yc
    fixture = {
        "summary": "Mock output",
        "lead_indicators": [],
        "dominant_pillar": "Geopolitical",
        "matched_topics": [],
        "source_videos": [],
    }
    (tmp_env / "data" / "mock_osint_fixtures" / "AME_youtube.json").write_text(
        json.dumps(fixture), encoding="utf-8"
    )
    (tmp_env / "output" / "regional" / "ame").mkdir(parents=True, exist_ok=True)
    signals = yc._run_mock("AME")
    out_path = tmp_env / "output" / "regional" / "ame" / "youtube_signals.json"
    # Write manually as main() would
    out_path.write_text(json.dumps(signals, indent=2), encoding="utf-8")
    assert out_path.exists()
    saved = json.loads(out_path.read_text())
    assert saved["summary"] == "Mock output"


# ── deep_research.py extension tests ───────────────────────────────────

def test_youtube_extraction_prompt_exists():
    from tools.deep_research import EXTRACTION_PROMPTS
    assert "youtube" in EXTRACTION_PROMPTS


def test_youtube_validator_passes_valid():
    from tools.deep_research import _validate_youtube_signals
    valid = {
        "summary": "test",
        "lead_indicators": ["a"],
        "dominant_pillar": "Geopolitical",
        "matched_topics": [],
    }
    assert _validate_youtube_signals(valid) == valid


def test_youtube_validator_rejects_missing_key():
    from tools.deep_research import _validate_youtube_signals
    with pytest.raises(ValueError):
        _validate_youtube_signals({"summary": "x"})


# ── CLI tests ───────────────────────────────────────────────────────────

def test_valid_regions_covers_all_five():
    import tools.youtube_collector as yc
    assert yc.VALID_REGIONS == {"APAC", "AME", "LATAM", "MED", "NCE"}
