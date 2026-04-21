from tools.briefs.data.board import load_board_data
from tools.briefs.models import BoardBriefData


def test_load_board_data_returns_valid_model():
    data = load_board_data("2026Q2")
    assert isinstance(data, BoardBriefData)
    assert data.cover.quarter == "Q2 2026"
    assert len(data.delta_bar) == 5
    assert len(data.board_takeaways) >= 3
    assert len(data.key_developments) >= 4
    assert len(data.scenarios) >= 2
