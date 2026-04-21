from tools.briefs.models import (
    CoverMeta, BriefData,
    BoardBriefData, BoardTakeaway, MatrixDot,
    CisoBriefData,
    RsmBriefData, SiteContext,
)
import pytest
from datetime import date

def test_cover_meta_requires_issued_at_and_classification():
    cover = CoverMeta(
        title="AeroGrid · Board Report · Q2 2026",
        classification="INTERNAL — BOARD DISTRIBUTION",
        prepared_by="M. Okonkwo",
        reviewed_by="R. Salazar",
        issued_at=date(2026, 4, 17),
        version="v1.0 — final",
    )
    assert cover.classification.startswith("INTERNAL")
    assert cover.version == "v1.0 — final"

def test_brief_data_rejects_extra_fields():
    with pytest.raises(Exception):
        BriefData(unknown_field="x")


def test_board_takeaway_severity_enum():
    tk = BoardTakeaway(n=1, severity="high", body_markdown="**x** y", anchor="S-07 · MED")
    assert tk.severity == "high"
    with pytest.raises(Exception):
        BoardTakeaway(n=1, severity="extreme", body_markdown="x", anchor="y")


def test_matrix_dot_coords_clamped():
    d = MatrixDot(
        scenario_id="S-07", region="MED", label="Unrest · Cape Wind",
        likelihood=72, impact=72, severity="high", label_position="up",
    )
    assert 0 <= d.likelihood <= 100
    with pytest.raises(Exception):
        MatrixDot(
            scenario_id="S-99", region="MED", label="x",
            likelihood=150, impact=50, severity="high", label_position="up",
        )


def test_board_brief_data_full_example_parses():
    from tests.briefs.fixtures_data import board_example
    bbd = BoardBriefData.model_validate(board_example())
    assert bbd.cover.title.startswith("AeroGrid")
    assert len(bbd.delta_bar) == 5


def test_ciso_example_parses():
    from tests.briefs.fixtures_data import ciso_example
    cbd = CisoBriefData.model_validate(ciso_example())
    assert cbd.cover.month == "April 2026"
    assert len(cbd.regions_grid) == 5


def test_rsm_example_parses():
    from tests.briefs.fixtures_data import rsm_example
    rbd = RsmBriefData.model_validate(rsm_example())
    assert rbd.admiralty_physical == "B2"
    assert rbd.regional_cyber.actors_count == 3


def test_site_context_computed_properties():
    raw = {
        "site_id": "t1",
        "name": "Test",
        "region": "MED",
        "country": "MA",
        "type": "ops_center",
        "lat": 33.58,
        "lon": -7.62,
        "poi_radius_km": 50,
        "personnel_count": 100,
        "expat_count": 20,
        "criticality": "major",
        "site_lead": {"name": "X", "phone": "+1"},
        "previous_incidents": [
            {"date": "2024-01-10", "type": "labour", "summary": "a", "outcome": "ok"},
            {"date": "2025-06-01", "type": "protest", "summary": "b", "outcome": "ok"},
        ],
    }
    sc = SiteContext.model_validate(raw)
    assert sc.coordinates.lat == 33.58
    assert sc.seerist_poi_radius_km == 50
    assert sc.personnel.total == 100
    assert sc.personnel.expat == 20
    assert sc.resolved_tier == "primary"
    assert sc.last_incident["date"] == "2025-06-01"
    assert sc.resolved_country_lead["name"] == "X"
