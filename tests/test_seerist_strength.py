"""Tests for seerist_strength.py — shared Seerist signal scoring utility."""
import pytest


def _make_seerist(events=None, verified=None, hotspots=None, avg_delta=0.0):
    return {
        "situational": {
            "events": events or [],
            "verified_events": verified or [],
            "breaking_news": [],
            "news": [],
        },
        "analytical": {
            "hotspots": hotspots or [],
            "pulse": {"region_summary": {"avg_delta": avg_delta}},
        },
    }


def test_high_on_hotspot_anomaly():
    from tools.seerist_strength import score_seerist_strength
    seerist = _make_seerist(
        hotspots=[{"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True}]
    )
    assert score_seerist_strength(seerist) == "high"


def test_hotspot_without_anomaly_is_not_high():
    from tools.seerist_strength import score_seerist_strength
    seerist = _make_seerist(
        hotspots=[{"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": False}]
    )
    assert score_seerist_strength(seerist) == "none"


def test_high_on_verified_event():
    from tools.seerist_strength import score_seerist_strength
    seerist = _make_seerist(
        verified=[{"signal_id": "seerist:event:apac-v001", "title": "Confirmed incident"}]
    )
    assert score_seerist_strength(seerist) == "high"


def test_high_on_pulse_delta_at_threshold():
    from tools.seerist_strength import score_seerist_strength, PULSE_DELTA_THRESHOLD
    seerist = _make_seerist(avg_delta=PULSE_DELTA_THRESHOLD)
    assert score_seerist_strength(seerist) == "high"


def test_high_on_pulse_delta_below_threshold():
    from tools.seerist_strength import score_seerist_strength, PULSE_DELTA_THRESHOLD
    seerist = _make_seerist(avg_delta=PULSE_DELTA_THRESHOLD - 0.1)
    assert score_seerist_strength(seerist) == "high"


def test_low_on_unverified_events_only():
    from tools.seerist_strength import score_seerist_strength
    seerist = _make_seerist(
        events=[{"signal_id": "seerist:event:apac-001", "verified": False, "title": "Protest"}]
    )
    assert score_seerist_strength(seerist) == "low"


def test_low_on_negative_delta_above_threshold():
    from tools.seerist_strength import score_seerist_strength, PULSE_DELTA_THRESHOLD
    seerist = _make_seerist(avg_delta=PULSE_DELTA_THRESHOLD + 0.1)
    assert score_seerist_strength(seerist) == "low"


def test_none_on_empty_dict():
    from tools.seerist_strength import score_seerist_strength
    assert score_seerist_strength({}) == "none"


def test_none_on_all_empty_arrays():
    from tools.seerist_strength import score_seerist_strength
    seerist = _make_seerist()
    assert score_seerist_strength(seerist) == "none"


def test_get_substantive_signal_ids_includes_anomaly_hotspot():
    from tools.seerist_strength import get_substantive_signal_ids
    seerist = _make_seerist(
        hotspots=[
            {"signal_id": "seerist:hotspot:apac-001", "anomaly_flag": True},
            {"signal_id": "seerist:hotspot:apac-002", "anomaly_flag": False},
        ]
    )
    ids = get_substantive_signal_ids(seerist)
    assert "seerist:hotspot:apac-001" in ids
    assert "seerist:hotspot:apac-002" not in ids


def test_get_substantive_signal_ids_includes_verified_event():
    from tools.seerist_strength import get_substantive_signal_ids
    seerist = _make_seerist(
        verified=[{"signal_id": "seerist:event:apac-v001", "title": "Confirmed"}],
        events=[{"signal_id": "seerist:event:apac-001", "verified": False}],
    )
    ids = get_substantive_signal_ids(seerist)
    assert "seerist:event:apac-v001" in ids
    assert "seerist:event:apac-001" not in ids


def test_get_substantive_signal_ids_empty_on_no_substantive():
    from tools.seerist_strength import get_substantive_signal_ids
    assert get_substantive_signal_ids({}) == []
    assert get_substantive_signal_ids(_make_seerist()) == []
