"""
Grounding validator — deterministic check of claims.json integrity.
Runs as stop hook after regional-analyst-agent exits.

Guard: reads output/regional/*/gatekeeper_decision.json to find the region.
If decision != "ESCALATE", exit 0 immediately (no brief was written).

Checks:
0. claims.json.mtime < report.md.mtime — if report.md was written first,
   the two-step order was violated (fail with explicit message).
   If claims.json does not exist at all -> FAIL (for ESCALATED regions).
1. claims.json exists and is valid JSON.
2. Every fact claim has non-empty signal_ids.
3. Every signal_id in claims exists in geo/cyber_signals.json lead_indicators.
   SKIP this check when research_scratchpad.json is ABSENT (mock mode).
   Use research_scratchpad.json PRESENCE as the live/mock signal — NOT os.environ.
4. At least one claim per paragraph type (why, how, sowhat).
   estimate claims count as valid (they explicitly signal absence).
5. If ALL claims are estimate AND gatekeeper decision == ESCALATE -> FAIL.
   This means the analyst has no grounded analysis for an escalated region.

Emits to output/logs/system_trace.log:
- Claim type distribution {fact: N, assessment: N, estimate: N}
- fact_claims / total_claims ratio (grounding score)
- Orphaned signal_ids (collected but not cited in claims)

Retry pattern: output/.retries/grounding-validator.retries
Max 3 retries then force-approve with warning logged to system_trace.log.
Exit codes: 0 = pass/skip, 1 = fail (triggers agent retry).
"""

import sys
import json
import glob
import os
import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Retry machinery
# ---------------------------------------------------------------------------
RETRY_FILE = Path("output/.retries/grounding-validator.retries")
MAX_RETRIES = 3


def get_retry_count() -> int:
    if RETRY_FILE.exists():
        try:
            return int(RETRY_FILE.read_text().strip())
        except Exception:
            return 0
    return 0


def increment_retry() -> int:
    count = get_retry_count() + 1
    RETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    RETRY_FILE.write_text(str(count))
    return count


def reset_retries():
    if RETRY_FILE.exists():
        RETRY_FILE.unlink()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log_trace(msg: str):
    ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    line = f"[{ts}] [GROUNDING] {msg}"
    try:
        with open("output/logs/system_trace.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


# ---------------------------------------------------------------------------
# Region discovery
# ---------------------------------------------------------------------------
def find_latest_region() -> str | None:
    """Find the region whose claims.json was most recently written."""
    pattern = "output/regional/*/claims.json"
    files = glob.glob(pattern)
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    return Path(latest).parent.name.upper()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(region: str) -> tuple[bool, list[str]]:
    """Returns (passed, list_of_failures)."""
    region_lower = region.lower()
    base = Path(f"output/regional/{region_lower}")

    claims_path = base / "claims.json"
    report_path = base / "report.md"
    geo_path = base / "geo_signals.json"
    cyber_path = base / "cyber_signals.json"
    scratchpad_path = base / "research_scratchpad.json"
    gatekeeper_path = base / "gatekeeper_decision.json"

    failures = []

    # Guard: only validate ESCALATED regions
    try:
        gd = json.loads(gatekeeper_path.read_text(encoding="utf-8"))
        if gd.get("decision") != "ESCALATE":
            return True, []  # Not escalated — skip
    except Exception:
        return True, []  # No gatekeeper file — skip

    # Check 0: claims.json must exist and be written before report.md
    if not claims_path.exists():
        failures.append("CHECK 0 FAIL: claims.json does not exist for ESCALATED region")
        return False, failures

    if report_path.exists():
        if claims_path.stat().st_mtime > report_path.stat().st_mtime:
            failures.append("CHECK 0 FAIL: report.md written before claims.json — two-step order violated")

    # Check 1: valid JSON
    try:
        data = json.loads(claims_path.read_text(encoding="utf-8"))
        claims = data.get("claims", [])
    except json.JSONDecodeError as e:
        failures.append(f"CHECK 1 FAIL: claims.json is not valid JSON: {e}")
        return False, failures

    if not claims:
        failures.append("CHECK 1 FAIL: claims.json has no claims")
        return False, failures

    # Check 2: every fact claim has non-empty signal_ids
    for c in claims:
        if c.get("claim_type") == "fact" and not c.get("signal_ids"):
            failures.append(f"CHECK 2 FAIL: fact claim '{c.get('claim_id')}' has empty signal_ids")

    # Check 3: every signal_id resolves (live mode only)
    live_mode = scratchpad_path.exists()
    if live_mode:
        known_ids = set()
        for sig_path in [geo_path, cyber_path]:
            try:
                sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
                for ind in sig_data.get("lead_indicators", []):
                    if isinstance(ind, dict) and ind.get("signal_id"):
                        known_ids.add(ind["signal_id"])
            except Exception:
                pass

        for c in claims:
            for sid in c.get("signal_ids", []):
                if sid and sid not in known_ids:
                    failures.append(f"CHECK 3 FAIL: signal_id '{sid}' in claim '{c.get('claim_id')}' not found in signal files")

    # Check 4: at least one claim per paragraph type
    paragraphs = {c.get("paragraph") for c in claims}
    for required in ["why", "how", "sowhat"]:
        if required not in paragraphs:
            failures.append(f"CHECK 4 FAIL: no claim with paragraph='{required}'")

    # Check 5: all-estimate + ESCALATED = fail
    types = [c.get("claim_type") for c in claims]
    if all(t == "estimate" for t in types):
        failures.append("CHECK 5 FAIL: all claims are estimate for ESCALATED region — no grounded analysis")

    return len(failures) == 0, failures


def emit_grounding_score(region: str, claims: list):
    """Emit grounding score and orphaned signal_ids to system_trace.log."""
    region_lower = region.lower()

    type_counts = {"fact": 0, "assessment": 0, "estimate": 0}
    cited_ids = set()
    for c in claims:
        ct = c.get("claim_type", "estimate")
        type_counts[ct] = type_counts.get(ct, 0) + 1
        cited_ids.update(c.get("signal_ids", []))

    total = len(claims)
    grounding_score = round(type_counts["fact"] / total, 2) if total else 0.0

    log_trace(f"{region} claim distribution: {type_counts} | grounding_score={grounding_score}")

    # Orphaned signal_ids
    known_ids = set()
    for pillar in ["geo", "cyber"]:
        sig_path = Path(f"output/regional/{region_lower}/{pillar}_signals.json")
        try:
            sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
            for ind in sig_data.get("lead_indicators", []):
                if isinstance(ind, dict) and ind.get("signal_id"):
                    known_ids.add(ind["signal_id"])
        except Exception:
            pass

    orphaned = known_ids - cited_ids
    if orphaned:
        log_trace(f"{region} orphaned signal_ids (collected but uncited): {sorted(orphaned)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    region = find_latest_region()
    if not region:
        # No claims.json found — might be a non-escalated run
        sys.exit(0)

    region_lower = region.lower()

    # Check retry count
    retry_count = get_retry_count()
    if retry_count >= MAX_RETRIES:
        log_trace(f"{region} grounding validator force-approved after {MAX_RETRIES} retries")
        reset_retries()
        sys.exit(0)

    passed, failures = validate(region)

    # Load claims for scoring (even on failure, for logging)
    try:
        data = json.loads(Path(f"output/regional/{region_lower}/claims.json").read_text(encoding="utf-8"))
        claims = data.get("claims", [])
        emit_grounding_score(region, claims)
    except Exception:
        pass

    if passed:
        reset_retries()
        log_trace(f"{region} grounding validation PASSED")
        sys.exit(0)
    else:
        count = increment_retry()
        for f in failures:
            log_trace(f"{region} {f}")
        log_trace(f"{region} grounding validation FAILED (retry {count}/{MAX_RETRIES})")
        print("\n".join(failures))
        sys.exit(1)