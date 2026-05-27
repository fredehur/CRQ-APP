# tests/test_crq_run.py
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import crq_run  # noqa: E402


def _write_config(tmp_path: Path, data) -> Path:
    p = tmp_path / "crq.config.json"
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return p


def test_load_config_valid(tmp_path):
    p = _write_config(tmp_path, {"brand_label": "ACME", "org_context_default": True})
    cfg = crq_run.load_config(p)
    assert cfg["brand_label"] == "ACME"
    assert cfg["org_context_default"] is True


def test_load_config_missing_file(tmp_path):
    with pytest.raises(crq_run.CrqRunError, match="/setup"):
        crq_run.load_config(tmp_path / "nope.json")


def test_load_config_malformed_json(tmp_path):
    p = _write_config(tmp_path, "{not json")
    with pytest.raises(crq_run.CrqRunError, match="valid JSON"):
        crq_run.load_config(p)


def test_load_config_missing_fields(tmp_path):
    p = _write_config(tmp_path, {"brand_label": "ACME"})
    with pytest.raises(crq_run.CrqRunError, match="org_context_default"):
        crq_run.load_config(p)


def test_load_config_wrong_types(tmp_path):
    p = _write_config(tmp_path, {"brand_label": 1, "org_context_default": "yes"})
    with pytest.raises(crq_run.CrqRunError, match="brand_label"):
        crq_run.load_config(p)


# Task 2 — region expansion
def test_expand_regions_subset():
    assert crq_run.expand_regions(["MED", "nce"]) == ["MED", "NCE"]


def test_expand_regions_all():
    assert crq_run.expand_regions(["ALL"]) == ["APAC", "AME", "LATAM", "MED", "NCE"]


def test_expand_regions_dedupe_preserves_order():
    assert crq_run.expand_regions(["MED", "MED", "APAC"]) == ["MED", "APAC"]


def test_expand_regions_unknown():
    with pytest.raises(crq_run.CrqRunError, match="unknown region"):
        crq_run.expand_regions(["ATLANTIS"])


def test_expand_regions_empty():
    with pytest.raises(crq_run.CrqRunError, match="no regions"):
        crq_run.expand_regions([])


# Task 3 — org-context resolution + flag translation
def test_resolve_org_context_default_used_when_no_override():
    assert crq_run.resolve_org_context(override=None, config_default=True) is True
    assert crq_run.resolve_org_context(override=None, config_default=False) is False


def test_resolve_org_context_override_wins():
    assert crq_run.resolve_org_context(override=True, config_default=False) is True
    assert crq_run.resolve_org_context(override=False, config_default=True) is False


def test_build_collect_argv_org_grounded():
    argv = crq_run.build_collect_argv("MED", "2026-05-22", org_context=True, brand_label="ACME")
    assert argv[1] == crq_run.POC_RUNNER
    assert argv[2:5] == ["MED", "2026-05-22", "--collect"]
    assert "--require-live" in argv
    assert "--no-org-context" not in argv
    assert argv[-2:] == ["--brand", "ACME"]


def test_build_collect_argv_region_guided_adds_flag():
    argv = crq_run.build_collect_argv("NCE", "2026-05-22", org_context=False, brand_label="Neutral")
    assert "--no-org-context" in argv
    assert "--require-live" in argv
    assert argv[-2:] == ["--brand", "Neutral"]


def test_build_phase_argv():
    assert crq_run.build_phase_argv("MED", "2026-05-22", "--prep-format")[2:] == [
        "MED", "2026-05-22", "--prep-format",
    ]
    assert crq_run.build_phase_argv("MED", "2026-05-22", "--render")[2:] == [
        "MED", "2026-05-22", "--render",
    ]


def test_day_dir_shape_briefs_date_region():
    """Brief folders live at output/briefs/<date>/<REGION>/ (date-first grouping)."""
    p = crq_run._day_dir("MED", "2026-05-27")
    assert p.parts[-3:] == ("briefs", "2026-05-27", "MED")


def test_day_dir_region_uppercased():
    """Region is uppercased in the folder name (matches header in brief.md)."""
    assert crq_run._day_dir("med", "2026-05-27").name == "MED"
    assert crq_run._day_dir("apac", "2026-05-27").name == "APAC"


# Task 4 — date helper + run-state round-trip
def test_today_iso_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", crq_run.today_iso())


def test_state_round_trip(tmp_path):
    p = tmp_path / "crq_run_state.json"
    state = {
        "date": "2026-05-22",
        "regions": ["MED", "NCE"],
        "org_context": False,
        "region_org_context": {"MED": False, "NCE": False},
        "brand_label": "X",
    }
    crq_run.write_state(state, p)
    assert crq_run.read_state(p) == state


def test_read_state_missing(tmp_path):
    with pytest.raises(crq_run.CrqRunError, match="collect"):
        crq_run.read_state(tmp_path / "nope.json")


# Task 5 — subcommands with mocked subprocess
def _patch_run(monkeypatch):
    """Capture argvs instead of running subprocess."""
    calls = []
    monkeypatch.setattr(crq_run, "_run", lambda argv: calls.append(argv))
    return calls


def _write_sites(tmp_path: Path, regions_with_sites) -> Path:
    """Write an aerowind_sites.json containing 1 site per listed region."""
    p = tmp_path / "aerowind_sites.json"
    p.write_text(json.dumps({"sites": [
        {"site_id": f"{r.lower()}-test-001", "name": f"{r} test site", "region": r}
        for r in regions_with_sites
    ]}), encoding="utf-8")
    return p


def test_cmd_collect_loops_regions_and_writes_state(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    state = tmp_path / "state.json"
    sites = _write_sites(tmp_path, ["MED", "NCE"])
    calls = _patch_run(monkeypatch)

    crq_run.cmd_collect(
        regions=["MED", "NCE"], org_grounded_override=None, date="2026-05-22",
        config_path=cfg, state_path=state, sites_path=sites,
    )

    # one collect call per region, org-grounded (no --no-org-context), brand passed, require-live on
    assert len(calls) == 2
    assert calls[0][2:5] == ["MED", "2026-05-22", "--collect"]
    assert "--require-live" in calls[0] and "--no-org-context" not in calls[0]
    assert calls[0][-2:] == ["--brand", "ACME"]
    assert calls[1][2] == "NCE"
    # state persisted
    saved = json.loads(state.read_text())
    assert saved == {
        "date": "2026-05-22",
        "regions": ["MED", "NCE"],
        "org_context": True,
        "region_org_context": {"MED": True, "NCE": True},
        "brand_label": "ACME",
    }
    # no-osint collect prints the "analyze" next-step guidance (not analyst_request)
    out = capsys.readouterr().out
    assert "uv run python tools/crq_run.py analyze" in out


def test_cmd_collect_region_guided_override(tmp_path, monkeypatch):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    state = tmp_path / "state.json"
    sites = _write_sites(tmp_path, ["MED"])
    calls = _patch_run(monkeypatch)

    crq_run.cmd_collect(
        regions=["MED"], org_grounded_override=False, date="2026-05-22",
        config_path=cfg, state_path=state, sites_path=sites,
    )
    assert "--no-org-context" in calls[0]
    assert json.loads(state.read_text())["org_context"] is False


# Task 7 — auto-fallback to region-guided when a region has no sites
def test_region_has_sites_true_when_present(tmp_path):
    sites = _write_sites(tmp_path, ["MED"])
    assert crq_run._region_has_sites("MED", sites) is True


def test_region_has_sites_false_when_absent(tmp_path):
    sites = _write_sites(tmp_path, ["MED"])
    assert crq_run._region_has_sites("NCE", sites) is False


def test_region_has_sites_false_when_file_missing(tmp_path):
    assert crq_run._region_has_sites("MED", tmp_path / "nope.json") is False


def test_region_has_sites_false_when_file_malformed(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert crq_run._region_has_sites("MED", p) is False


def test_cmd_collect_auto_falls_back_when_region_has_no_sites(tmp_path, monkeypatch, capsys):
    """User asks org-grounded for MED+NCE; only MED has sites. NCE auto-falls-back."""
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    state = tmp_path / "state.json"
    sites = _write_sites(tmp_path, ["MED"])  # MED has sites, NCE does not
    calls = _patch_run(monkeypatch)

    crq_run.cmd_collect(
        regions=["MED", "NCE"], org_grounded_override=True, date="2026-05-22",
        config_path=cfg, state_path=state, sites_path=sites,
    )

    # MED: org-grounded honored (no --no-org-context)
    assert "--no-org-context" not in calls[0]
    # NCE: auto-fell-back (has --no-org-context)
    assert "--no-org-context" in calls[1]
    # state captures the per-region effective context
    saved = json.loads(state.read_text())
    assert saved["org_context"] is True  # what the user requested
    assert saved["region_org_context"] == {"MED": True, "NCE": False}
    # operator notice printed for the fallback
    err = capsys.readouterr().err
    assert "NCE" in err and "no sites" in err and "region-guided" in err


def test_cmd_analyze_passes_per_region_org_context_and_brand(tmp_path, monkeypatch):
    """cmd_analyze must propagate per-region org_context + brand to poc_runner."""
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "date": "2026-05-22",
        "regions": ["MED", "NCE"],
        "org_context": True,
        "region_org_context": {"MED": True, "NCE": False},
        "brand_label": "ACME",
    }), encoding="utf-8")
    calls = _patch_run(monkeypatch)

    crq_run.cmd_analyze(state_path=state)

    assert len(calls) == 2
    # MED: org-grounded, brand passed
    med = calls[0]
    assert med[2] == "MED" and "--analyze" in med
    assert "--no-org-context" not in med
    assert med[-2:] == ["--brand", "ACME"]
    # NCE: region-guided, brand passed
    nce = calls[1]
    assert nce[2] == "NCE" and "--analyze" in nce
    assert "--no-org-context" in nce
    assert nce[-2:] == ["--brand", "ACME"]


def test_build_analyze_argv_region_guided_adds_no_org_context():
    argv = crq_run.build_analyze_argv("NCE", "2026-05-22", org_context=False, brand_label="Neutral")
    assert "--no-org-context" in argv
    assert argv[-2:] == ["--brand", "Neutral"]


def test_build_analyze_argv_org_grounded_no_flag():
    argv = crq_run.build_analyze_argv("MED", "2026-05-22", org_context=True, brand_label="ACME")
    assert "--no-org-context" not in argv
    assert argv[-2:] == ["--brand", "ACME"]


def test_cmd_prep_uses_state_regions(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(
        {"date": "2026-05-22", "regions": ["MED", "NCE"], "org_context": True, "brand_label": "ACME"}
    ), encoding="utf-8")
    calls = _patch_run(monkeypatch)

    crq_run.cmd_prep(state_path=state)
    assert [c[2] for c in calls] == ["MED", "NCE"]
    assert all(c[-1] == "--prep-format" for c in calls)
    out = capsys.readouterr().out
    assert "formatter_request.md" in out and "AGENT STEP REQUIRED" in out


def test_cmd_render_uses_state_regions(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps(
        {"date": "2026-05-22", "regions": ["MED"], "org_context": True, "brand_label": "ACME"}
    ), encoding="utf-8")
    calls = _patch_run(monkeypatch)

    crq_run.cmd_render(state_path=state)
    assert calls[0][-1] == "--render"
    out = capsys.readouterr().out
    assert "email.html" in out


# Task 6 — CLI entry point
def test_main_collect_parses_regions_and_region_guided(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(crq_run, "cmd_collect",
        lambda regions, org_grounded_override, date, **kw: captured.update(
            regions=regions, override=org_grounded_override, date=date))
    crq_run.main(["collect", "--regions", "MED", "NCE", "--region-guided", "--date", "2026-05-22"])
    assert captured["regions"] == ["MED", "NCE"]
    assert captured["override"] is False
    assert captured["date"] == "2026-05-22"


def test_main_collect_org_grounded_override(monkeypatch):
    captured = {}
    monkeypatch.setattr(crq_run, "cmd_collect",
        lambda regions, org_grounded_override, date, **kw: captured.update(override=org_grounded_override))
    crq_run.main(["collect", "--regions", "MED", "--org-grounded"])
    assert captured["override"] is True


def test_main_collect_no_override_is_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(crq_run, "cmd_collect",
        lambda regions, org_grounded_override, date, **kw: captured.update(override=org_grounded_override))
    crq_run.main(["collect", "--regions", "MED"])
    assert captured["override"] is None


def test_main_error_exits_nonzero(monkeypatch, capsys):
    def boom(*a, **k):
        raise crq_run.CrqRunError("config not found. Run /setup first.")
    monkeypatch.setattr(crq_run, "cmd_prep", boom)
    rc = crq_run.main(["prep"])
    assert rc == 1
    assert "/setup" in capsys.readouterr().err


# OSINT physical-pillar mode
def test_load_config_osint_default_optional_defaults_false(tmp_path):
    p = _write_config(tmp_path, {"brand_label": "ACME", "org_context_default": True})
    assert crq_run.load_config(p)["osint_default"] is False


def test_load_config_osint_default_present_bool(tmp_path):
    p = _write_config(tmp_path, {"brand_label": "ACME", "org_context_default": True, "osint_default": True})
    assert crq_run.load_config(p)["osint_default"] is True


def test_load_config_osint_default_wrong_type(tmp_path):
    p = _write_config(tmp_path, {"brand_label": "A", "org_context_default": True, "osint_default": "yes"})
    with pytest.raises(crq_run.CrqRunError, match="osint_default"):
        crq_run.load_config(p)


def test_build_collect_argv_osint_on():
    argv = crq_run.build_collect_argv("MED", "2026-05-22", org_context=True, brand_label="X", osint=True)
    assert "--osint" in argv and "--require-live" in argv and argv[-2:] == ["--brand", "X"]


def test_build_collect_argv_osint_off_by_default():
    argv = crq_run.build_collect_argv("MED", "2026-05-22", org_context=True, brand_label="X")
    assert "--osint" not in argv


def test_cmd_collect_osint_override_on(tmp_path, monkeypatch):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    calls = _patch_run(monkeypatch)
    crq_run.cmd_collect(regions=["MED"], org_grounded_override=None, osint_override=True,
                        date="2026-05-22", config_path=cfg, state_path=tmp_path / "s.json")
    assert "--osint" in calls[0]


def test_cmd_collect_osint_default_from_config(tmp_path, monkeypatch):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True, "osint_default": True}), encoding="utf-8")
    calls = _patch_run(monkeypatch)
    crq_run.cmd_collect(regions=["MED"], org_grounded_override=None, osint_override=None,
                        date="2026-05-22", config_path=cfg, state_path=tmp_path / "s.json")
    assert "--osint" in calls[0]


def test_cmd_collect_osint_override_off_beats_config_default(tmp_path, monkeypatch):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True, "osint_default": True}), encoding="utf-8")
    calls = _patch_run(monkeypatch)
    crq_run.cmd_collect(regions=["MED"], org_grounded_override=None, osint_override=False,
                        date="2026-05-22", config_path=cfg, state_path=tmp_path / "s.json")
    assert "--osint" not in calls[0]


def test_main_collect_osint_flags(monkeypatch):
    captured = {}
    monkeypatch.setattr(crq_run, "cmd_collect",
        lambda regions, org_grounded_override, osint_override, date, **kw: captured.update(osint=osint_override))
    crq_run.main(["collect", "--regions", "MED", "--osint"])
    assert captured["osint"] is True
    crq_run.main(["collect", "--regions", "MED", "--no-osint"])
    assert captured["osint"] is False
    crq_run.main(["collect", "--regions", "MED"])
    assert captured["osint"] is None


def test_build_analyze_argv_defaults_org_grounded():
    argv = crq_run.build_analyze_argv("MED", "2026-05-22")
    assert argv[2:5] == ["MED", "2026-05-22", "--analyze"]
    assert "--no-org-context" not in argv


def test_cmd_analyze_uses_state_regions(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "date": "2026-05-22",
        "regions": ["MED", "NCE"],
        "org_context": True,
        "region_org_context": {"MED": True, "NCE": True},
        "brand_label": "ACME",
    }), encoding="utf-8")
    calls = _patch_run(monkeypatch)
    crq_run.cmd_analyze(state_path=state)
    assert [c[2] for c in calls] == ["MED", "NCE"]
    assert all("--analyze" in c for c in calls)
    assert "AGENT STEP REQUIRED" in capsys.readouterr().out


def test_main_analyze_routes(monkeypatch):
    called = {}
    monkeypatch.setattr(crq_run, "cmd_analyze", lambda **k: called.setdefault("ok", True))
    crq_run.main(["analyze"])
    assert called["ok"]


def test_cmd_collect_osint_prints_enrich_pause(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True, "osint_default": True}), encoding="utf-8")
    _patch_run(monkeypatch)
    crq_run.cmd_collect(regions=["MED"], org_grounded_override=None, osint_override=None,
                        date="2026-05-22", config_path=cfg, state_path=tmp_path / "s.json")
    out = capsys.readouterr().out
    assert "osint_enrich_request.md" in out and "crq_run.py analyze" in out
