import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.config import TRACE_LOG_PATH

LOG_PATH = str(TRACE_LOG_PATH)

def log_event(event_type, message):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"[{timestamp}] [{event_type}] {message}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip())

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: audit_logger.py <EVENT_TYPE> <MESSAGE>")
        sys.exit(1)
    log_event(sys.argv[1], " ".join(sys.argv[2:]))
