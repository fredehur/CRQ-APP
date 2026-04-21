from tools.briefs.data._rsm_mock import rsm_med_w17_mock
from tools.briefs.models import RsmBriefData


def test_rsm_mock_returns_valid_model():
    data = rsm_med_w17_mock()
    assert isinstance(data, RsmBriefData)


def test_rsm_mock_has_crown_jewel_sites():
    data = rsm_med_w17_mock()
    crown_jewels = [s for s in data.sites if s.context.resolved_tier == "crown_jewel"]
    assert len(crown_jewels) >= 1


def test_rsm_mock_has_top_events():
    data = rsm_med_w17_mock()
    assert len(data.top_events) >= 1
