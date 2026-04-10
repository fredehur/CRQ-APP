"""Tests for Phase G-0 — Shared OSINT Topic Registry.

Covers:
- data/osint_topics.json schema validation
- matched_topics field in osint_signals.json (written by osint_collector.py)
"""
import json
import os
import subprocess
import sys

PYTHON = sys.executable
CWD = "c:/Users/frede/crq-agent-workspace"
TOPICS_PATH = os.path.join(CWD, "data/osint_topics.json")

REQUIRED_KEYS = {"id", "label", "type", "keywords", "regions", "active"}
VALID_TYPES = {"event", "trend"}
VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}


# ── Topic registry schema ────────────────────────────────────────────────────

def test_topics_file_exists():
    assert os.path.exists(TOPICS_PATH), f"data/osint_topics.json not found at {TOPICS_PATH}"


def test_topics_is_valid_json():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "Expected a JSON array of topics"


def test_topics_required_keys():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        missing = REQUIRED_KEYS - t.keys()
        assert not missing, f"Topic '{t.get('id', '?')}' missing keys: {missing}"


def test_topics_valid_types():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert t["type"] in VALID_TYPES, \
            f"Topic '{t['id']}' has invalid type '{t['type']}' — must be 'event' or 'trend'"


def test_topics_keywords_are_nonempty_lists():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert isinstance(t["keywords"], list) and len(t["keywords"]) >= 1, \
            f"Topic '{t['id']}' keywords must be a non-empty list"


def test_topics_regions_valid_values():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert isinstance(t["regions"], list) and len(t["regions"]) >= 1, \
            f"Topic '{t['id']}' regions must be a non-empty list"
        for r in t["regions"]:
            assert r in VALID_REGIONS, \
                f"Topic '{t['id']}' has invalid region '{r}'"


def test_topics_ids_unique():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    ids = [t["id"] for t in topics]
    duplicates = {x for x in ids if ids.count(x) > 1}
    assert not duplicates, f"Duplicate topic IDs found: {duplicates}"


def test_at_least_one_active_topic():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    active = [t for t in topics if t.get("active")]
    assert len(active) >= 1, "At least one topic must be active"


def test_active_field_is_boolean():
    with open(TOPICS_PATH, encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        assert isinstance(t["active"], bool), \
            f"Topic '{t['id']}' active field must be a boolean, got {type(t['active'])}"


# ── Collector matched_topics integration tests ───────────────────────────────

def _run(region, extra_args=None):
    cmd = [PYTHON, "tools/osint_collector.py", region, "--mock"] + (extra_args or [])
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", cwd=CWD,
    )


def _osint_path(region):
    return os.path.join(CWD, f"output/regional/{region.lower()}/osint_signals.json")


def test_osint_collector_outputs_matched_topics_for_ame():
    """osint_collector AME must write matched_topics list — AME has active topics."""
    result = _run("AME")
    assert result.returncode == 0, f"osint_collector AME failed: {result.stderr}"
    with open(_osint_path("AME"), encoding="utf-8") as f:
        data = json.load(f)
    assert "matched_topics" in data, "osint_signals.json missing 'matched_topics'"
    assert isinstance(data["matched_topics"], list)
    assert len(data["matched_topics"]) > 0, "AME should have at least one matched topic"


def test_osint_collector_matched_topics_are_valid_ids():
    """All matched_topics entries must be valid IDs from the registry."""
    result = _run("AME")
    assert result.returncode == 0, f"osint_collector AME failed: {result.stderr}"
    with open(TOPICS_PATH, encoding="utf-8") as f:
        known_ids = {t["id"] for t in json.load(f)}
    with open(_osint_path("AME"), encoding="utf-8") as f:
        data = json.load(f)
    for tid in data["matched_topics"]:
        assert tid in known_ids, f"matched_topics contains unrecognised ID '{tid}'"


def test_osint_collector_latam_matched_topics():
    """LATAM has supply-chain-wind-components in scope — matched_topics must include it."""
    result = _run("LATAM")
    assert result.returncode == 0, f"osint_collector LATAM failed: {result.stderr}"
    with open(_osint_path("LATAM"), encoding="utf-8") as f:
        data = json.load(f)
    assert "matched_topics" in data
    assert "supply-chain-wind-components" in data["matched_topics"]


def test_osint_collector_all_regions_produce_matched_topics():
    """All 5 regions must produce a matched_topics list."""
    for region in ["APAC", "AME", "LATAM", "MED", "NCE"]:
        result = _run(region)
        assert result.returncode == 0, f"osint_collector {region} failed: {result.stderr}"
        with open(_osint_path(region), encoding="utf-8") as f:
            data = json.load(f)
        assert "matched_topics" in data, f"{region} osint_signals.json missing 'matched_topics'"
        assert isinstance(data["matched_topics"], list), f"{region} matched_topics must be a list"
