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


# Task 4 — date helper + run-state round-trip
def test_today_iso_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", crq_run.today_iso())


def test_state_round_trip(tmp_path):
    p = tmp_path / "crq_run_state.json"
    state = {"date": "2026-05-22", "regions": ["MED", "NCE"], "org_context": False, "brand_label": "X"}
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


def test_cmd_collect_loops_regions_and_writes_state(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    state = tmp_path / "state.json"
    calls = _patch_run(monkeypatch)

    crq_run.cmd_collect(
        regions=["MED", "NCE"], org_grounded_override=None, date="2026-05-22",
        config_path=cfg, state_path=state,
    )

    # one collect call per region, org-grounded (no --no-org-context), brand passed, require-live on
    assert len(calls) == 2
    assert calls[0][2:5] == ["MED", "2026-05-22", "--collect"]
    assert "--require-live" in calls[0] and "--no-org-context" not in calls[0]
    assert calls[0][-2:] == ["--brand", "ACME"]
    assert calls[1][2] == "NCE"
    # state persisted
    saved = json.loads(state.read_text())
    assert saved == {"date": "2026-05-22", "regions": ["MED", "NCE"], "org_context": True, "brand_label": "ACME"}
    # prints the analyst_request path + agent-step marker
    out = capsys.readouterr().out
    assert "analyst_request.md" in out
    assert "AGENT STEP REQUIRED" in out


def test_cmd_collect_region_guided_override(tmp_path, monkeypatch):
    cfg = tmp_path / "crq.config.json"
    cfg.write_text(json.dumps({"brand_label": "ACME", "org_context_default": True}), encoding="utf-8")
    state = tmp_path / "state.json"
    calls = _patch_run(monkeypatch)

    crq_run.cmd_collect(
        regions=["MED"], org_grounded_override=False, date="2026-05-22",
        config_path=cfg, state_path=state,
    )
    assert "--no-org-context" in calls[0]
    assert json.loads(state.read_text())["org_context"] is False


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
