"""intel_decisions — per-run transparency log renderer.

Asserts the rendered markdown has the expected section headers and that
the kept/dropped/cited accounting reflects the inputs faithfully.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import intel_decisions  # noqa: E402


def _write(day: Path, name: str, data) -> None:
    (day / name).write_text(json.dumps(data), encoding="utf-8")


def _fixture_dir(tmp_path: Path) -> Path:
    """Create a fixture day dir at tmp_path/briefs/2026-05-27/MED/."""
    day = tmp_path / "briefs" / "2026-05-27" / "MED"
    day.mkdir(parents=True, exist_ok=True)
    return day


def test_renders_headers_when_all_inputs_present(tmp_path):
    day = _fixture_dir(tmp_path)
    _write(day, "seerist_signals.json", {
        "situational": {"events": [{"signal_id": "seerist:event:med-001"}]},
        "analytical": {"hotspots": [], "scribe": [], "threat_actor_context": ["A", "B"]},
        "poi_alerts": [], "cyber_signals": [],
    })
    _write(day, "osint_physical_signals.json", {
        "signals": [{"signal_id": "osint:physical:med-001"}, {"signal_id": "osint:physical:med-002"}],
    })
    _write(day, "osint_dropped.json", {"dropped": [{"title": "X", "url": "u", "relevance_reason": "off-region"}]})
    _write(day, "claims.json", {"claims": [
        {"pillar": "physical", "claim_type": "fact", "signal_ids": ["seerist:event:med-001", "osint:physical:med-001"]},
        {"pillar": "cyber", "claim_type": "estimate", "signal_ids": []},
    ]})

    out = intel_decisions.render(day)
    assert "# MED 2026-05-27 — Intel decisions log" in out
    assert "## Seerist (top-tier)" in out
    assert "## OSINT physical-pillar (Tavily + Firecrawl)" in out
    assert "## Final brief composition" in out


def test_reports_kept_vs_dropped_counts(tmp_path):
    day = _fixture_dir(tmp_path)
    _write(day, "osint_physical_signals.json", {
        "signals": [{"signal_id": f"osint:physical:med-{i:03d}"} for i in range(1, 4)],
    })
    _write(day, "osint_dropped.json", {"dropped": [
        {"title": f"dropped {i}", "url": f"u{i}", "relevance_reason": "off-region"} for i in range(5)
    ]})
    out = intel_decisions.render(day)
    # 3 kept · 5 dropped · 8 raw
    assert "3 kept · 5 dropped (of 8 raw signals)" in out


def test_drops_table_lists_each_dropped_item(tmp_path):
    day = _fixture_dir(tmp_path)
    _write(day, "osint_physical_signals.json", {"signals": []})
    _write(day, "osint_dropped.json", {"dropped": [
        {"title": "Serbia protests", "url": "https://lemonde.fr/serbia", "relevance_reason": "off-region; Balkans"},
        {"title": "Cuba health crisis", "url": "https://lemonde.fr/cuba", "relevance_reason": "off-region; Caribbean"},
    ]})
    out = intel_decisions.render(day)
    assert "| 1 | Serbia protests | https://lemonde.fr/serbia | off-region; Balkans |" in out
    assert "| 2 | Cuba health crisis | https://lemonde.fr/cuba | off-region; Caribbean |" in out


def test_surfaces_seerist_uncited_signals(tmp_path):
    day = _fixture_dir(tmp_path)
    _write(day, "seerist_signals.json", {
        "situational": {"events": [
            {"signal_id": "seerist:event:med-001"},
            {"signal_id": "seerist:event:med-002"},
        ]},
    })
    # Only med-001 is cited; med-002 should appear under "Uncited"
    _write(day, "claims.json", {"claims": [
        {"pillar": "physical", "claim_type": "fact", "signal_ids": ["seerist:event:med-001"]},
    ]})
    out = intel_decisions.render(day)
    assert "Uncited" in out
    assert "`seerist:event:med-002`" in out
    assert "`seerist:event:med-001`" not in out.split("Uncited")[1]


def test_surfaces_osint_uncited_kept_signals(tmp_path):
    day = _fixture_dir(tmp_path)
    _write(day, "osint_physical_signals.json", {"signals": [
        {"signal_id": "osint:physical:med-001"},
        {"signal_id": "osint:physical:med-002"},
    ]})
    _write(day, "osint_dropped.json", {"dropped": []})
    _write(day, "claims.json", {"claims": [
        {"pillar": "physical", "claim_type": "fact", "signal_ids": ["osint:physical:med-001"]},
    ]})
    out = intel_decisions.render(day)
    assert "Uncited kept signals" in out
    assert "`osint:physical:med-002`" in out


def test_claims_by_pillar_counts(tmp_path):
    day = _fixture_dir(tmp_path)
    _write(day, "claims.json", {"claims": [
        {"pillar": "physical", "claim_type": "fact", "signal_ids": []},
        {"pillar": "physical", "claim_type": "assessment", "signal_ids": []},
        {"pillar": "cyber", "claim_type": "estimate", "signal_ids": []},
        {"pillar": "early_warning", "claim_type": "assessment", "signal_ids": []},
    ]})
    out = intel_decisions.render(day)
    assert "4 claims total: 2 physical · 1 cyber · 1 early-warning" in out
    assert "By claim type: 1 fact · 2 assessment · 1 estimate" in out


def test_graceful_when_no_data_files(tmp_path):
    day = _fixture_dir(tmp_path)
    out = intel_decisions.render(day)
    assert "no Seerist data this run" in out
    assert "OSINT was disabled or skipped" in out
    assert "brief not yet authored" in out


def test_write_creates_intel_decisions_md(tmp_path):
    day = _fixture_dir(tmp_path)
    _write(day, "claims.json", {"claims": []})
    out_path = intel_decisions.write(day)
    assert out_path == day / "intel_decisions.md"
    assert out_path.exists()
    assert "Intel decisions log" in out_path.read_text(encoding="utf-8")


def test_pipe_characters_in_titles_are_escaped(tmp_path):
    """A title containing | breaks markdown tables if not escaped."""
    day = _fixture_dir(tmp_path)
    _write(day, "osint_physical_signals.json", {"signals": []})
    _write(day, "osint_dropped.json", {"dropped": [
        {"title": "A | B | C", "url": "u", "relevance_reason": "rule | applied"},
    ]})
    out = intel_decisions.render(day)
    # Title and reason both escaped — no raw pipes inside the row cells
    assert "A \\| B \\| C" in out
    assert "rule \\| applied" in out
