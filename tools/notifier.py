#!/usr/bin/env python3
"""Notifier — delivers formatted RSM briefs via configured channel.

Usage:
    notifier.py ROUTING_DECISIONS_PATH [--mock]

Mock mode: writes brief to output/mock_delivery/ instead of sending email.
Live mode: sends via SMTP (SMTP_HOST, SMTP_USER, SMTP_PASS in .env).

Appends to: output/delivery_log.jsonl
"""
import json
import shutil
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, ".")
from dotenv import load_dotenv
import os

load_dotenv()

OUTPUT_ROOT = Path("output")
DELIVERY_LOG_PATH = Path("output/delivery_log.jsonl")
MOCK_DELIVERY_DIR = Path("output/mock_delivery")
AUDIENCE_CONFIG_PATH = Path("data/audience_config.json")


def _log_delivery(entry: dict) -> None:
    DELIVERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DELIVERY_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _send_email(recipients: list[str], subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "localhost")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user or "noreply@aerowind.com"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(host, port) as server:
        if user and password:
            server.starttls()
            server.login(user, password)
        server.sendmail(msg["From"], recipients, msg.as_string())


def _mock_deliver(decision: dict, brief_content: str, mock_dir: Path | None = None) -> None:
    """Write brief to mock_delivery/ for testing. Accepts optional mock_dir for test isolation."""
    import tools.notifier as _self  # module-level reference so monkeypatch works
    dest_dir = mock_dir if mock_dir is not None else _self.MOCK_DELIVERY_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    brief_path = Path(decision["brief_path"])
    dest = dest_dir / brief_path.name
    dest.write_text(brief_content, encoding="utf-8")
    print(f"[notifier] mock delivery → {dest}", file=sys.stderr)


def notify(routing_path: Path, mock: bool = True) -> None:
    if not routing_path.exists():
        print(f"[notifier] routing file not found: {routing_path}", file=sys.stderr)
        return

    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    audience_config = {}
    if AUDIENCE_CONFIG_PATH.exists():
        audience_config = json.loads(AUDIENCE_CONFIG_PATH.read_text(encoding="utf-8"))

    for decision in routing.get("decisions", []):
        if not decision.get("triggered"):
            continue

        audience_key = decision.get("audience", "")
        region = decision.get("region", "")
        product = decision.get("product", "")
        brief_path = Path(decision.get("brief_path", ""))

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log_entry = {
            "timestamp": timestamp,
            "audience": audience_key,
            "region": region,
            "product": product,
            "channel": "email",
            "recipient": ", ".join(audience_config.get(audience_key, {}).get("delivery", {}).get("recipients", [])),
            "brief_path": str(brief_path),
            "status": "failed",
            "error": None,
        }

        try:
            if not brief_path.exists():
                raise FileNotFoundError(f"Brief not found: {brief_path}")

            brief_content = brief_path.read_text(encoding="utf-8")
            subject_prefix = "⚡ FLASH ALERT" if product == "flash" else "INTSUM"
            subject = f"[AEROWIND] {subject_prefix} // {region} // {timestamp[:10]}"

            if mock:
                import tools.notifier as _self
                _mock_deliver(decision, brief_content, mock_dir=_self.MOCK_DELIVERY_DIR)
            else:
                recipients = audience_config.get(audience_key, {}).get("delivery", {}).get("recipients", [])
                if recipients:
                    _send_email(recipients, subject, brief_content)

            log_entry["status"] = "delivered"
        except Exception as e:
            log_entry["error"] = str(e)
            print(f"[notifier] delivery failed for {audience_key}/{product}: {e}", file=sys.stderr)

        _log_delivery(log_entry)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: notifier.py ROUTING_DECISIONS_PATH [--mock]", file=sys.stderr)
        sys.exit(1)

    routing_path = Path(args[0])
    mock = "--mock" in args
    notify(routing_path, mock=mock)


if __name__ == "__main__":
    main()
