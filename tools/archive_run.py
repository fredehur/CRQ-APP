"""Archives the current pipeline run into output/runs/{timestamp}/ and updates output/latest/."""
import os
import sys
import json
import shutil
from datetime import datetime, timezone
from tools.config import MANIFEST_PATH

# Files and directories to archive from output/
ARCHIVE_FILES = [
    "run_manifest.json",
    "global_report.json",
    "global_report.md",
    "dashboard.html",
    "board_report.pdf",
    "board_report.pptx",
    "system_trace.log",
]
ARCHIVE_DIRS = [
    "regional",
]


def archive():
    # Derive timestamp from run_manifest if available, else use current time
    manifest_path = str(MANIFEST_PATH)
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        ts_raw = manifest.get("run_timestamp", "")
        # Convert 2026-03-09T12:46:39Z → 2026-03-09_124639Z
        ts_slug = ts_raw.replace(":", "").replace("-", "-").replace("T", "_")
        if not ts_slug:
            ts_slug = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")
    else:
        ts_slug = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%SZ")

    run_dir = f"output/runs/{ts_slug}"
    os.makedirs(run_dir, exist_ok=True)

    copied = 0
    for fname in ARCHIVE_FILES:
        src = f"output/{fname}"
        if os.path.exists(src):
            shutil.copy2(src, f"{run_dir}/{fname}")
            copied += 1

    for dirname in ARCHIVE_DIRS:
        src = f"output/{dirname}"
        dst = f"{run_dir}/{dirname}"
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            copied += 1

    # Update output/latest/ as a full copy (symlinks unreliable on Windows)
    latest_dir = "output/latest"
    if os.path.exists(latest_dir):
        shutil.rmtree(latest_dir)
    shutil.copytree(run_dir, latest_dir)

    print(f"Archived run to {run_dir} ({copied} items)")
    print(f"Updated output/latest/")
    return run_dir


if __name__ == "__main__":
    archive()
