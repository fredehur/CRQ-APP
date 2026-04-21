from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_ROOT = Path("output/deliverables/archive")
RETENTION = int(os.getenv("BRIEFS_RETENTION", "5"))


@dataclass(frozen=True)
class VersionRecord:
    audience_id: str
    version_ts: str                # ISO 8601 UTC, e.g. "2026-04-21T04:12:00Z"
    pipeline_run_id: str | None
    narrated: bool
    generated_by: str              # "cli" | "api" | "manual"
    metadata: dict
    pdf_path: Path
    thumbnail_path: Path


def utc_now_iso() -> str:
    now = datetime.now(timezone.utc)
    millis = now.microsecond // 1000
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{millis:03d}Z"


def iso_to_compact(iso: str) -> str:
    # "2026-04-21T04:12:00.123Z" → "20260421T041200.123Z"
    # "2026-04-21T04:12:00Z"     → "20260421T041200Z" (back-compat)
    return iso.replace("-", "").replace(":", "")


def compact_to_iso(compact: str) -> str:
    # "20260421T041200.123Z" → "2026-04-21T04:12:00.123Z"
    # "20260421T041200Z"     → "2026-04-21T04:12:00Z"
    date = f"{compact[0:4]}-{compact[4:6]}-{compact[6:8]}"
    tail = compact[8:]  # starts with "T", ends with "Z", seconds maybe have ".fff"
    return f"{date}T{tail[1:3]}:{tail[3:5]}:{tail[5:]}"


def _audience_dir(audience_id: str) -> Path:
    d = ARCHIVE_ROOT / audience_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_sidecar(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def record_version(
    audience_id: str,
    pdf_tmp_path: Path,
    thumbnail_tmp_path: Path,
    pipeline_run_id: str | None,
    narrated: bool,
    generated_by: str,
    metadata: dict,
) -> VersionRecord:
    if not pdf_tmp_path.exists() or pdf_tmp_path.stat().st_size == 0:
        raise ValueError(f"pdf tmp file missing or empty: {pdf_tmp_path}")
    if not thumbnail_tmp_path.exists() or thumbnail_tmp_path.stat().st_size == 0:
        raise ValueError(f"thumbnail tmp file missing or empty: {thumbnail_tmp_path}")

    sweep_orphans(audience_id)

    version_ts = utc_now_iso()
    basename = iso_to_compact(version_ts)
    dest_dir = _audience_dir(audience_id)
    pdf_dest = dest_dir / f"{basename}.pdf"
    png_dest = dest_dir / f"{basename}.png"
    sidecar_dest = dest_dir / f"{basename}.json"

    os.replace(pdf_tmp_path, pdf_dest)
    try:
        os.replace(thumbnail_tmp_path, png_dest)
    except Exception:
        pdf_dest.unlink(missing_ok=True)
        raise

    payload = {
        "audience_id": audience_id,
        "version_ts": version_ts,
        "pipeline_run_id": pipeline_run_id,
        "narrated": narrated,
        "generated_by": generated_by,
        "metadata": metadata,
    }
    try:
        _write_sidecar(sidecar_dest, payload)
    except Exception:
        pdf_dest.unlink(missing_ok=True)
        png_dest.unlink(missing_ok=True)
        raise

    prune(audience_id)

    return VersionRecord(
        audience_id=audience_id,
        version_ts=version_ts,
        pipeline_run_id=pipeline_run_id,
        narrated=narrated,
        generated_by=generated_by,
        metadata=metadata,
        pdf_path=pdf_dest,
        thumbnail_path=png_dest,
    )


def sweep_orphans(audience_id: str) -> int:
    """Remove pdf/png files without matching sidecar. Returns count removed."""
    d = ARCHIVE_ROOT / audience_id
    if not d.exists():
        return 0
    removed = 0
    for artifact in list(d.glob("*.pdf")) + list(d.glob("*.png")):
        sidecar = artifact.with_suffix(".json")
        if not sidecar.exists():
            artifact.unlink(missing_ok=True)
            removed += 1
    return removed


def list_versions(audience_id: str) -> list[VersionRecord]:
    d = ARCHIVE_ROOT / audience_id
    if not d.exists():
        return []
    records: list[VersionRecord] = []
    for sidecar in d.glob("*.json"):
        basename = sidecar.stem
        pdf = d / f"{basename}.pdf"
        png = d / f"{basename}.png"
        if not (pdf.exists() and png.exists()):
            continue
        try:
            payload = json.loads(sidecar.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        records.append(VersionRecord(
            audience_id=payload["audience_id"],
            version_ts=payload["version_ts"],
            pipeline_run_id=payload.get("pipeline_run_id"),
            narrated=bool(payload.get("narrated", False)),
            generated_by=payload.get("generated_by", "unknown"),
            metadata=payload.get("metadata", {}),
            pdf_path=pdf,
            thumbnail_path=png,
        ))
    records.sort(key=lambda r: r.version_ts, reverse=True)
    return records


def get_latest(audience_id: str) -> VersionRecord | None:
    versions = list_versions(audience_id)
    return versions[0] if versions else None


def get_specific(audience_id: str, version_ts: str) -> VersionRecord | None:
    for rec in list_versions(audience_id):
        if rec.version_ts == version_ts:
            return rec
    return None


def prune(audience_id: str) -> int:
    """Keep newest N versions per BRIEFS_RETENTION. Returns count removed."""
    if RETENTION <= 0:
        return 0
    versions = list_versions(audience_id)
    removed = 0
    for rec in versions[RETENTION:]:
        basename = iso_to_compact(rec.version_ts)
        d = ARCHIVE_ROOT / audience_id
        (d / f"{basename}.pdf").unlink(missing_ok=True)
        (d / f"{basename}.png").unlink(missing_ok=True)
        (d / f"{basename}.json").unlink(missing_ok=True)
        removed += 1
    return removed
