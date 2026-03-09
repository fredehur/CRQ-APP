# Phase 5: Observability Layer

> Build this AFTER Phases 1–4 are fully working. This is a purely additive layer — nothing in the existing architecture changes.

---

## What This Adds

| Feature | Current (Phases 1–4) | Phase 5 |
|---|---|---|
| Agent identity | None | Unique `agent_id` + `session_id` per run |
| State visibility | Retry counter files only | Full event log in SQLite |
| Mid-run debugging | Read retry files manually | Live dashboard via WebSocket |
| Audit trail | Pass/fail on final output | Every tool call, hook event, and retry captured |
| Failure diagnosis | Guess from output | See exactly which hook failed and why |

---

## Architecture

```
Claude Agents
    │
    ├── PreToolUse hook  ──┐
    ├── PostToolUse hook ──┤
    ├── Stop hook ─────────┤──→ send_event.py ──→ HTTP POST ──→ Bun/Python server
    ├── SubagentStart ──────┤                                         │
    └── SubagentStop ───────┘                                         ▼
                                                                   SQLite (WAL)
                                                                      │
                                                                   WebSocket
                                                                      │
                                                                   Dashboard (HTML/JS)
```

---

## Session & Agent Identity

Every agent invocation gets two identifiers injected via environment or hook context:

- **`session_id`** — unique per `/run-crq` invocation (one per full pipeline run)
- **`agent_id`** — unique per subagent (one per regional-analyst, one for global-analyst, etc.)

These are written into every event payload so you can:
- Filter the dashboard by region or agent type
- Correlate which regional draft came from which agent invocation
- Replay a failed run by querying all events for a `session_id`

### Identity Generation

```python
# tools/identity.py
import uuid, os, time

def get_session_id():
    # Persists for the full pipeline run — set once by run-crq orchestrator
    sid = os.environ.get("CRQ_SESSION_ID")
    if not sid:
        sid = f"session_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        os.environ["CRQ_SESSION_ID"] = sid
    return sid

def get_agent_id(label: str):
    # Unique per agent invocation — label = "gatekeeper-APAC", "regional-MED", etc.
    return f"{label}_{uuid.uuid4().hex[:8]}"
```

---

## Structured State (Event Sourcing)

Every hook fires an event. Events are immutable — never updated, only appended. This gives you a full audit trail of every run.

### Event Schema

```json
{
    "event_id": "uuid",
    "session_id": "session_1741478400_a3f9c1",
    "agent_id": "regional-APAC_b72e4f1a",
    "event_type": "Stop",
    "hook": "jargon-auditor",
    "status": "PASSED",
    "region": "APAC",
    "retry_count": 1,
    "payload": {
        "file": "output/regional_draft_current.md",
        "label": "current"
    },
    "timestamp": "2026-03-09T14:23:01Z"
}
```

### Event Types to Capture

| Event | When | Key payload |
|---|---|---|
| `SessionStart` | `/run-crq` begins | `session_id`, regions to process |
| `GatekeeperResult` | After gatekeeper returns | `region`, `result` (YES/NO) |
| `RegionalAnalystStart` | Before regional agent runs | `region`, `agent_id`, `score` |
| `AuditResult` | After jargon-auditor fires | `status`, `retry_count`, `fail_reason` |
| `RegionalAnalystDone` | After archive step | `region`, `draft_path`, `vacr` |
| `GlobalAnalystDone` | After global report written | `total_exposure`, `regions_included` |
| `ExportDone` | After PDF/PPTX export | `pdf_path`, `pptx_path` |
| `SessionEnd` | Pipeline complete | `session_id`, `duration_seconds` |

---

## Build Steps

### Step 1: Event Sender

Write `tools/send_event.py` — called by every hook to POST the event:

```python
import requests, json, os, sys
from datetime import datetime, timezone

SERVER_URL = os.environ.get("CRQ_OBS_URL", "http://localhost:8765/event")

def send(event_type, agent_id, region=None, status=None, payload=None):
    event = {
        "event_id": __import__("uuid").uuid4().hex,
        "session_id": os.environ.get("CRQ_SESSION_ID", "unknown"),
        "agent_id": agent_id,
        "event_type": event_type,
        "region": region,
        "status": status,
        "payload": payload or {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        requests.post(SERVER_URL, json=event, timeout=2)
    except Exception:
        pass  # Observability must never block the pipeline

if __name__ == "__main__":
    import json as j
    data = j.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    send(**data)
```

### Step 2: Event Server

Write `tools/obs_server.py` — lightweight Python server (no Bun required):

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import sqlite3, json, threading, time

DB = "output/obs.db"

def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, session_id TEXT, agent_id TEXT,
            event_type TEXT, region TEXT, status TEXT,
            payload TEXT, timestamp TEXT
        )
    """)
    con.commit()
    con.close()

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        con = sqlite3.connect(DB)
        con.execute(
            "INSERT INTO events VALUES (NULL,?,?,?,?,?,?,?,?)",
            (body.get("event_id"), body.get("session_id"), body.get("agent_id"),
             body.get("event_type"), body.get("region"), body.get("status"),
             json.dumps(body.get("payload", {})), body.get("timestamp"))
        )
        con.commit()
        con.close()
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args): pass  # suppress request logs

if __name__ == "__main__":
    init_db()
    print("Observability server running on http://localhost:8765")
    HTTPServer(("localhost", 8765), Handler).serve_forever()
```

### Step 3: Update jargon-auditor.py

Add a `send_event.py` call at the end of `audit_report()` — after the pass/fail decision — before `sys.exit()`. This is the only change to existing files.

### Step 4: Update run-crq.md

Add to Phase 0:
- Set `CRQ_SESSION_ID` environment variable before any agents run
- Start `obs_server.py` in background: `uv run python tools/obs_server.py &`

### Step 5: Query Dashboard

After a run, query the SQLite database directly:

```bash
# See all events for the last session
sqlite3 output/obs.db "SELECT event_type, region, status, timestamp FROM events WHERE session_id = (SELECT session_id FROM events ORDER BY id DESC LIMIT 1) ORDER BY id"

# See all audit failures
sqlite3 output/obs.db "SELECT agent_id, region, payload FROM events WHERE event_type = 'AuditResult' AND status = 'FAILED'"

# Count retries per region
sqlite3 output/obs.db "SELECT region, COUNT(*) as retries FROM events WHERE event_type = 'AuditResult' AND status = 'FAILED' GROUP BY region"
```

Or add a simple HTML dashboard at `output/obs_dashboard.html` that reads from the SQLite DB via a `/events` GET endpoint on `obs_server.py`.

---

## Integration Checklist

- [ ] `tools/identity.py` written
- [ ] `tools/send_event.py` written
- [ ] `tools/obs_server.py` written
- [ ] `jargon-auditor.py` updated to call `send_event.py`
- [ ] `run-crq.md` updated to set `CRQ_SESSION_ID` and start server
- [ ] `output/obs.db` created on first server start
- [ ] Test: run `/run-crq`, then query SQLite for full event trail

---

## Why This Order

Building observability after the pipeline works means:
1. You know what events are actually worth capturing (from real runs)
2. The pipeline is never blocked waiting for the obs server
3. `send_event.py` silently swallows errors — the obs layer can be down without breaking anything
4. You can replay any past run by querying `obs.db` with its `session_id`
