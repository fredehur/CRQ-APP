import sys
import os
from datetime import datetime, timezone

LOG_PATH = "output/system_trace.log"

def log_event(event_type, message):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"[{timestamp}] [{event_type}] {message}\n"
    with open(LOG_PATH, "a") as f:
        f.write(entry)
    print(entry.strip())

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: audit_logger.py <EVENT_TYPE> <MESSAGE>")
        sys.exit(1)
    log_event(sys.argv[1], " ".join(sys.argv[2:]))
