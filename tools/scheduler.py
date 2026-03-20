#!/usr/bin/env python3
"""Lightweight scheduler for RSM pipeline jobs.

Usage:
    scheduler.py --once          # Run all due jobs once, then exit
    scheduler.py --loop          # Run continuously, check every 5 minutes
    scheduler.py --list          # List jobs and their last-run times

Reads:  data/schedule_config.json
State:  output/.scheduler_state.json  (last-run timestamps per job ID)
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, ".")

CONFIG_PATH = Path("data/schedule_config.json")
STATE_PATH = Path("output/.scheduler_state.json")
CHECK_INTERVAL_SEC = 300  # 5 minutes


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _cron_due(cron: str, last_run_iso: str | None, now: datetime) -> bool:
    """Simplified cron evaluation — checks if job is due based on cron expression.
    Supports: minute hour dom month dow patterns.
    For simplicity, evaluates based on current hour/minute vs cron pattern.
    """
    if last_run_iso is None:
        return True  # Never run → always due

    last_run = datetime.fromisoformat(last_run_iso.replace("Z", "+00:00"))
    elapsed_sec = (now - last_run).total_seconds()

    parts = cron.strip().split()
    if len(parts) != 5:
        return False

    minute_part, hour_part, _, _, dow_part = parts

    # Every N hours: "0 */6 * * *"
    if hour_part.startswith("*/") and minute_part == "0":
        interval_hours = int(hour_part[2:])
        return elapsed_sec >= interval_hours * 3600

    # Specific time on specific day: "0 5 * * 1" (Monday 05:00)
    if hour_part.isdigit() and minute_part.isdigit() and dow_part.isdigit():
        target_hour = int(hour_part)
        target_minute = int(minute_part)
        target_dow = int(dow_part)  # 0=Sun, 1=Mon, ..., 6=Sat
        if now.weekday() + 1 == target_dow and now.hour == target_hour and now.minute <= target_minute:
            return elapsed_sec >= 3600 * 24 * 6  # Don't re-run within same week
        return False

    # Half-hour offset: "30 */6 * * *"
    if hour_part.startswith("*/") and minute_part.isdigit():
        interval_hours = int(hour_part[2:])
        return elapsed_sec >= interval_hours * 3600

    return False


def _run_job(job: dict) -> None:
    regions = job.get("regions") or [None]
    for region in regions:
        cmd = job["command"]
        if region:
            cmd = cmd.replace("{region}", region)
        print(f"[scheduler] running: {cmd}", file=sys.stderr)
        try:
            subprocess.run(cmd, shell=True, check=False, timeout=300)
        except subprocess.TimeoutExpired:
            print(f"[scheduler] timeout: {cmd}", file=sys.stderr)


def run_once() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    state = _load_state()
    now = datetime.now(timezone.utc)

    for job in config.get("jobs", []):
        job_id = job["id"]
        last_run = state.get(job_id)
        if _cron_due(job["cron"], last_run, now):
            print(f"[scheduler] job due: {job_id} — {job['description']}", file=sys.stderr)
            _run_job(job)
            state[job_id] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            print(f"[scheduler] job not due: {job_id}", file=sys.stderr)

    _save_state(state)


def list_jobs() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    state = _load_state()
    print(f"{'JOB':<30} {'CRON':<20} {'LAST RUN'}")
    for job in config.get("jobs", []):
        last = state.get(job["id"], "never")
        print(f"{job['id']:<30} {job['cron']:<20} {last}")


def main():
    args = sys.argv[1:]
    if "--list" in args:
        list_jobs()
    elif "--loop" in args:
        print("[scheduler] starting loop, checking every 5 minutes", file=sys.stderr)
        while True:
            run_once()
            time.sleep(CHECK_INTERVAL_SEC)
    else:
        run_once()


if __name__ == "__main__":
    main()
