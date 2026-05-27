"""Region-guided (no-org-context) mode — builder, collector, validator, renderer.

Covers the switch that makes REGION the only scoping input: no sites, personnel,
footprint, audience, or site-proximity reach the pipeline.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.rsm_input_builder import build_rsm_inputs, manifest_summary  # noqa: E402


def _seed_required_inputs(output_dir: Path, region: str = "med") -> None:
    """build_rsm_inputs requires osint_signals.json + data.json to exist."""
    regional = output_dir / "regional" / region
    regional.mkdir(parents=True, exist_ok=True)
    (regional / "osint_signals.json").write_text("{}", encoding="utf-8")
    (regional / "data.json").write_text("{}", encoding="utf-8")


# ── 1. Builder, mode off ──────────────────────────────────────────────────────
def test_builder_no_org_context_strips_org_grounding(tmp_path):
    _seed_required_inputs(tmp_path)
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path), include_org_context=False)

    assert m["org_context_included"] is False
    assert m["site_registry"] == []
    assert m["notable_dates"] == []
    assert m["previous_incidents"] == []
    assert m["poi_proximity"] is None
    assert m["brand_label"]  # populated with the neutral default
    for org_key in ("aerowind_sites", "audience_config", "poi_proximity"):
        assert m["fallback_flags"][org_key] is True


# ── 2. Builder regression: default path unchanged ─────────────────────────────
def test_builder_default_keeps_org_context(tmp_path):
    _seed_required_inputs(tmp_path)
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path))

    assert m["org_context_included"] is True
    assert m["brand_label"] == "AEROWIND"
    # The real MED registry ships 3 sites; default mode must still load them.
    assert len(m["site_registry"]) >= 1
    assert all(s["region"] == "MED" for s in m["site_registry"])


# ── 3. manifest_summary banner + no allowlist ─────────────────────────────────
def test_manifest_summary_region_guided_banner(tmp_path):
    _seed_required_inputs(tmp_path)
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path), include_org_context=False)
    summary = manifest_summary(m)

    assert "REGION-GUIDED MODE" in summary
    assert "Allowed site names" not in summary


def test_manifest_summary_default_has_allowlist(tmp_path):
    _seed_required_inputs(tmp_path)
    m = build_rsm_inputs("MED", "daily", output_dir=str(tmp_path))
    summary = manifest_summary(m)

    assert "REGION-GUIDED MODE" not in summary
    assert "Allowed site names" in summary  # registry present → allowlist printed


# ── 4. Collector strip (the key leak test) ────────────────────────────────────
def test_collector_no_org_context_strips_poi_alerts(tmp_path, monkeypatch):
    import tools.seerist_collector as sc

    monkeypatch.setattr(sc, "OUTPUT_ROOT", tmp_path / "output")
    result = sc.collect("MED", mock=True, window_days=7, no_org_context=True)

    assert result["poi_alerts"] == []
    # The MED fixture ships a baked-in facility name — it must not survive.
    assert "Casablanca Wind Farm Operations" not in json.dumps(result)


def test_collector_default_keeps_poi_alerts(tmp_path, monkeypatch):
    import tools.seerist_collector as sc

    monkeypatch.setattr(sc, "OUTPUT_ROOT", tmp_path / "output")
    result = sc.collect("MED", mock=True, window_days=7)

    # Default mock path preserves the fixture's facility-keyed alerts.
    assert "Casablanca Wind Farm Operations" in json.dumps(result)


# ── 5 & 6. Validator + renderer against a region-guided brief ─────────────────
_REGION_BRIEF = """REGIONAL RISK INTELLIGENCE // MED DAILY // 2026-05-17Z
PULSE: 6.2 | ADM: B2 | NEW: 1 EVT · 0 HOT · 1 CYB

█ SITUATION
Elevated unrest risk across the central Mediterranean this period.

█ REGIONAL EXPOSURE
Italy and Morocco show the most elevated regional risk this window; Spain
remains stable. Region-level read only — no site-specific exposure.

█ PHYSICAL & GEOPOLITICAL — LAST 24H
No new events.

█ CYBER — ACTIVE EXPOSURE
THREATS ACTIVE: MEDUSA · Sandworm + 3 others (full list watched)

- [OT/ICS] [MED · sev 3 · Probable] MEDUSA campaign targeting regional energy sector. [1]

█ EARLY WARNING — NEW
No new anomalies.

█ WATCH — NEXT 72H
- No new physical or operational watch items for the next 72 hours.

█ APPENDIX — SOURCES
[1] MEDUSA campaign targeting regional energy sector. — seerist:cyber:med-001 (Seerist analysis)
"""

_NO_ORG_MANIFEST = {
    "region": "MED",
    "cadence": "daily",
    "org_context_included": False,
    "brand_label": "REGIONAL RISK INTELLIGENCE",
    "site_registry": [],
}


def _write_pair(tmp_path: Path, brief_text: str, manifest: dict) -> tuple[Path, Path]:
    brief = tmp_path / "brief.md"
    brief.write_text(brief_text, encoding="utf-8")
    mf = tmp_path / "manifest.json"
    mf.write_text(json.dumps(manifest), encoding="utf-8")
    return brief, mf


def _run_validate(brief: Path, manifest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tools/validate_brief.py", str(brief), str(manifest)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def test_validator_accepts_regional_exposure_in_region_guided_mode(tmp_path):
    brief, manifest = _write_pair(tmp_path, _REGION_BRIEF, _NO_ORG_MANIFEST)
    r = _run_validate(brief, manifest)
    assert r.returncode == 0, r.stderr


def test_validator_rejects_aerowind_exposure_in_region_guided_mode(tmp_path):
    wrong = _REGION_BRIEF.replace("█ REGIONAL EXPOSURE", "█ AEROWIND EXPOSURE")
    brief, manifest = _write_pair(tmp_path, wrong, _NO_ORG_MANIFEST)
    r = _run_validate(brief, manifest)
    assert r.returncode != 0
    assert "REGIONAL EXPOSURE" in r.stderr


def test_renderer_uses_neutral_brand_no_aerowind(tmp_path):
    from tools.render_brief_html import render

    brief, manifest = _write_pair(tmp_path, _REGION_BRIEF, _NO_ORG_MANIFEST)
    html = render(brief, manifest, subject="REGIONAL RISK INTELLIGENCE // MED Daily")

    assert "REGIONAL RISK INTELLIGENCE" in html
    assert "AEROWIND" not in html
    assert "PoC v1" not in html
