"""Archives the current pipeline run into output/runs/{timestamp}/ and updates output/latest/."""
import os
import sys
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.config import MANIFEST_PATH

# Files and directories to archive from output/
ARCHIVE_FILES = [
    "pipeline/run_manifest.json",
    "pipeline/global_report.json",
    "pipeline/global_report.md",
    "pipeline/dashboard.html",
    "pipeline/trend_brief.json",
    "pipeline/trend_analysis.json",
    "pipeline/threat_landscape.json",
    "pipeline/vacr_research.json",
    "deliverables/board_report.pdf",
    "deliverables/board_report.pptx",
    "deliverables/ciso_brief.docx",
    "logs/system_trace.log",
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
            dst = f"{run_dir}/{fname}"
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
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
