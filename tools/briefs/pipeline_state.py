from __future__ import annotations
import json
from pathlib import Path

PIPELINE_LOG = Path("output/pipeline/last_run_log.json")
REGIONAL_ROOT = Path("output/regional")
_KNOWN_REGIONS = {"apac", "ame", "latam", "med", "nce"}


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def global_run_id() -> str | None:
    data = _read_json(PIPELINE_LOG)
    return data.get("run_id") if data else None


def region_run_id(region: str) -> str | None:
    data = _read_json(REGIONAL_ROOT / region.lower() / "meta.json")
    return data.get("run_id") if data else None


def current_run_id(audience_id: str) -> str | None:
    if audience_id in ("ciso", "board"):
        return global_run_id()
    if audience_id.startswith("rsm-"):
        region = audience_id.removeprefix("rsm-")
        if region not in _KNOWN_REGIONS:
            raise ValueError(f"unknown RSM region: {region}")
        return region_run_id(region)
    raise ValueError(f"unknown audience_id: {audience_id}")


def write_region_meta(region: str, run_id: str) -> None:
    d = REGIONAL_ROOT / region.lower()
    d.mkdir(parents=True, exist_ok=True)
    meta_path = d / "meta.json"
    existing = _read_json(meta_path) or {}
    existing["run_id"] = run_id
    meta_path.write_text(json.dumps(existing, indent=2, sort_keys=True))
