"""Each rsm_{region} entry must have a daily product after this task."""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PATH = REPO_ROOT / "data" / "audience_config.json"
RSM_KEYS = ["rsm_apac", "rsm_ame", "rsm_latam", "rsm_med", "rsm_nce"]


def _load():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_every_rsm_has_daily_product():
    cfg = _load()
    for k in RSM_KEYS:
        assert "daily" in cfg[k]["products"], f"{k} missing daily"


def test_daily_has_required_keys():
    cfg = _load()
    for k in RSM_KEYS:
        d = cfg[k]["products"]["daily"]
        assert d["cadence"] == "daily"
        assert "time_local" in d
        assert "timezone" in d
        assert d.get("always_emit") is True


def test_weekly_intsum_still_present():
    cfg = _load()
    for k in RSM_KEYS:
        assert "weekly_intsum" in cfg[k]["products"]
