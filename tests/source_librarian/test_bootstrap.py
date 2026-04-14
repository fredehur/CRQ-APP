"""Tests for tools/source_librarian/bootstrap.py."""
import json
from unittest.mock import MagicMock, patch


def _haiku_yaml_response():
    text = """
register_id: wind_power_plant
register_name: Wind Power Plant
industry: renewable_energy
sub_industry: wind_power_generation
geography:
  primary: [europe, north_america]
  secondary: [apac]
scenarios:
  WP-001:
    name: "System intrusion"
    threat_terms: [system intrusion, OT compromise]
    asset_terms: [wind turbine, SCADA]
    industry_terms: [wind farm, renewable energy]
    time_focus_years: 3
    notes: "Focus on documented OT intrusions in renewables."
query_modifiers:
  news_set:
    - "{threat} {asset} attack {year}"
  doc_set:
    - "{threat} {asset} report pdf"
"""
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_bootstrap_writes_yaml_and_returns_path(tmp_path, monkeypatch):
    reg_dir = tmp_path / "registers"
    reg_dir.mkdir()
    (reg_dir / "wind_power_plant.json").write_text(json.dumps({
        "register_id": "wind_power_plant",
        "display_name": "Wind Power Plant",
        "scenarios": [
            {"scenario_id": "WP-001", "scenario_name": "System intrusion",
             "description": "OT/SCADA breach", "search_tags": ["ot_systems", "scada"]},
        ],
    }), encoding="utf-8")

    out_dir = tmp_path / "research_intents"
    out_dir.mkdir()
    monkeypatch.setattr("tools.source_librarian.bootstrap.REGISTERS_DIR", reg_dir)
    monkeypatch.setattr("tools.source_librarian.bootstrap.INTENTS_DIR", out_dir)

    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.return_value.messages.create.return_value = _haiku_yaml_response()
    with patch("tools.source_librarian.bootstrap.anthropic", fake_anthropic):
        from tools.source_librarian.bootstrap import bootstrap_intent_yaml
        path = bootstrap_intent_yaml("wind_power_plant")

    assert path == out_dir / "wind_power_plant.yaml"
    text = path.read_text(encoding="utf-8")
    assert "register_id: wind_power_plant" in text
    assert "WP-001" in text


def test_bootstrap_strips_markdown_fences(tmp_path, monkeypatch):
    reg_dir = tmp_path / "registers"
    reg_dir.mkdir()
    (reg_dir / "wp.json").write_text(json.dumps({
        "register_id": "wp",
        "display_name": "WP",
        "scenarios": [{"scenario_id": "X-001", "scenario_name": "x", "description": "y", "search_tags": []}],
    }), encoding="utf-8")
    out_dir = tmp_path / "ri"
    out_dir.mkdir()
    monkeypatch.setattr("tools.source_librarian.bootstrap.REGISTERS_DIR", reg_dir)
    monkeypatch.setattr("tools.source_librarian.bootstrap.INTENTS_DIR", out_dir)

    fenced_text = (
        "```yaml\n"
        "register_id: wp\n"
        "register_name: WP\n"
        "industry: x\n"
        "sub_industry: y\n"
        "geography:\n  primary: []\n  secondary: []\n"
        "scenarios:\n"
        "  X-001:\n    name: x\n    threat_terms: [a]\n    asset_terms: [b]\n    industry_terms: [c]\n    time_focus_years: 1\n    notes: ''\n"
        "query_modifiers:\n  news_set: ['{threat}']\n  doc_set: ['{threat}']\n"
        "```\n"
    )
    fenced = MagicMock()
    fenced.content = [MagicMock(text=fenced_text)]

    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.return_value.messages.create.return_value = fenced
    with patch("tools.source_librarian.bootstrap.anthropic", fake_anthropic):
        from tools.source_librarian.bootstrap import bootstrap_intent_yaml
        path = bootstrap_intent_yaml("wp")

    text = path.read_text(encoding="utf-8")
    assert "```" not in text
    assert text.startswith("register_id:")
