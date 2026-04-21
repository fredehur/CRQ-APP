from tools.briefs.data.ciso import load_ciso_data
from tools.briefs.models import CisoBriefData


def test_load_ciso_data_returns_valid_model():
    data = load_ciso_data("2026-04")
    assert isinstance(data, CisoBriefData)
    assert data.cover.month == "April 2026"
    assert len(data.regions_grid) == 5
    assert len(data.ciso_takeaways) == 3
    assert len(data.scenarios) >= 3
    assert len(data.evidence_physical) >= 8
    assert len(data.evidence_cyber) >= 5
    assert data.cyber_physical_join.region == "MED"
