"""
update_source_registry.py — CRQ Source Registry Builder

Ingests sources from all regional signal files (geo, cyber, youtube, seerist)
into a persistent SQLite database at data/sources.db.

Usage:
    uv run python tools/update_source_registry.py
"""

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "data" / "sources.db"
RUN_MANIFEST_PATH = REPO_ROOT / "output" / "run_manifest.json"
YOUTUBE_SOURCES_PATH = REPO_ROOT / "data" / "youtube_sources.json"
OUTPUT_REGIONAL = REPO_ROOT / "output" / "regional"

REGIONS = ["apac", "ame", "med", "nce", "latam"]

# ---------------------------------------------------------------------------
# Credibility tier classification
# ---------------------------------------------------------------------------

TIER_A_DOMAINS = {
    "cisa.gov", "nsa.gov", "asd.gov.au", "enisa.europa.eu", "ncsc.gov.uk",
    "mandiant.com", "unit42.paloaltonetworks.com", "dragos.com",
    "reuters.com", "bbc.com", "ft.com", "wsj.com",
    "chathamhouse.org", "cfr.org", "iiss.org", "csis.org",
}
TIER_C_DOMAINS = {"linkedin.com", "medium.com", "facebook.com", "twitter.com"}

# ---------------------------------------------------------------------------
# Source type classification
# ---------------------------------------------------------------------------

GOV_TLDS = {".gov", ".mil"}
GOV_DOMAINS = {"asd.gov.au", "enisa.europa.eu", "ncsc.gov.uk", "ec.europa.eu"}
INTEL_DOMAINS = {
    "mandiant.com", "unit42.paloaltonetworks.com", "dragos.com",
    "recorded-future.com", "crowdstrike.com", "cisco.com",
    "group-ib.com", "kaspersky.com",
}
ACADEMIC_DOMAINS = {"chathamhouse.org", "cfr.org", "iiss.org", "csis.org", "brookings.edu"}
ACADEMIC_TLDS = {".edu"}
INDUSTRY_DOMAINS = {"windeurope.org", "energymonitor.ai", "pv-tech.org"}
SOCIAL_DOMAINS = {"linkedin.com", "facebook.com", "twitter.com", "youtube.com"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_id(url: str = "", name: str = "") -> str:
    """Generate a 12-char sha256-based id from url (preferred) or name."""
    key = url.strip() if url.strip() else name.strip()
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def extract_domain(url: str) -> str:
    """Return the registered domain (netloc without www. prefix)."""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.removeprefix("www.")
    except Exception:
        return ""


def assign_credibility_tier(domain: str, source_type: str = "") -> str:
    if domain in TIER_A_DOMAINS:
        return "A"
    # Government and intelligence sources are tier A even if not in the explicit allowlist
    if source_type in ("government", "intelligence"):
        return "A"
    if domain in TIER_C_DOMAINS:
        return "C"
    if source_type == "social":
        return "C"
    return "B"


def classify_source_type(domain: str) -> str:
    """Classify in order: government → intelligence → academic → industry → social → news."""
    # Government: explicit domain list or gov/mil TLD
    if domain in GOV_DOMAINS:
        return "government"
    parsed_tld = "." + domain.split(".")[-1] if "." in domain else ""
    if parsed_tld in GOV_TLDS:
        return "government"
    if domain in INTEL_DOMAINS:
        return "intelligence"
    if domain in ACADEMIC_DOMAINS or parsed_tld in ACADEMIC_TLDS:
        return "academic"
    if domain in INDUSTRY_DOMAINS:
        return "industry"
    if domain in SOCIAL_DOMAINS:
        return "social"
    return "news"


def derive_name_from_url(url: str) -> str:
    """Best-effort human-readable name from a URL when no name is provided."""
    domain = extract_domain(url)
    if not domain:
        return url
    # Strip common TLDs and capitalize
    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[-2].capitalize()
    return domain


def load_json(path: Path):
    """Load JSON from path; return None on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS sources_registry (
    id               TEXT PRIMARY KEY,
    url              TEXT UNIQUE,
    name             TEXT NOT NULL,
    domain           TEXT,
    source_type      TEXT,
    credibility_tier TEXT DEFAULT 'B',
    junk             INTEGER DEFAULT 0,
    blocked          INTEGER DEFAULT 0,
    collection_type  TEXT DEFAULT 'osint',
    published_at     TEXT,
    first_seen       TEXT,
    last_seen        TEXT,
    appearance_count INTEGER DEFAULT 1,
    cited_count      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS source_appearances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT REFERENCES sources_registry(id),
    run_id       TEXT,
    region       TEXT,
    pillar       TEXT,
    headline     TEXT,
    cited        INTEGER DEFAULT 0,
    collected_at TEXT
);

CREATE TABLE IF NOT EXISTS seerist_events (
    event_id        TEXT PRIMARY KEY,
    source          TEXT,
    region          TEXT,
    countries       TEXT,
    category        TEXT,
    severity        INTEGER,
    title           TEXT,
    description     TEXT,
    verified        INTEGER DEFAULT 0,
    lat             REAL,
    lon             REAL,
    event_timestamp TEXT,
    run_id          TEXT,
    ingested_at     TEXT
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


# ---------------------------------------------------------------------------
# Upsert logic
# ---------------------------------------------------------------------------

def upsert_source(
    conn: sqlite3.Connection,
    *,
    url: str = "",
    name: str,
    domain: str = "",
    source_type: str = "news",
    credibility_tier: str = "B",
    collection_type: str = "osint",
    published_at: str | None = None,
    timestamp: str,
) -> str:
    """
    Upsert a source into sources_registry.
    Returns the source id.
    Preserves junk=1 rows — does not overwrite credibility_tier on those.
    """
    sid = source_id(url=url, name=name)

    existing = conn.execute(
        "SELECT id, junk, appearance_count FROM sources_registry WHERE id = ?",
        (sid,),
    ).fetchone()

    if existing is None:
        conn.execute(
            """
            INSERT INTO sources_registry
                (id, url, name, domain, source_type, credibility_tier, collection_type, junk,
                 published_at, first_seen, last_seen, appearance_count, cited_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 1, 0)
            """,
            (sid, url or None, name, domain, source_type, credibility_tier, collection_type,
             published_at, timestamp, timestamp),
        )
    else:
        # On conflict: update last_seen + appearance_count; keep credibility_tier if junk=1
        if existing[1] == 1:
            # Junk row — only bump counters, don't touch tier
            conn.execute(
                """
                UPDATE sources_registry
                   SET last_seen = ?, appearance_count = appearance_count + 1
                 WHERE id = ?
                """,
                (timestamp, sid),
            )
        else:
            conn.execute(
                """
                UPDATE sources_registry
                   SET last_seen = ?, appearance_count = appearance_count + 1
                 WHERE id = ?
                """,
                (timestamp, sid),
            )

    return sid


def insert_appearance(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    run_id: str,
    region: str,
    pillar: str,
    headline: str = "",
    collected_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO source_appearances
            (source_id, run_id, region, pillar, headline, cited, collected_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (source_id, run_id, region.upper(), pillar, headline, collected_at),
    )


# ---------------------------------------------------------------------------
# Per-region ingest
# ---------------------------------------------------------------------------

def ingest_osint_signals(
    conn: sqlite3.Connection,
    region: str,
    run_id: str,
    signal_path: Path,
    pillar: str,
    timestamp: str,
) -> int:
    """
    Ingest geo or cyber signal file. Returns count of sources upserted.
    Prefers `sources` field [{name, url}] written by research_collector.py synthesis.
    Falls back to `source_urls` flat list for mock/legacy signal files.
    """
    data = load_json(signal_path)
    if data is None:
        return 0

    # Prefer `sources` field [{name, url}] written by research_collector.py synthesis.
    # Fall back to `source_urls` (flat list of strings) for older or mock signal files.
    named_sources = data.get("sources", [])
    flat_urls = data.get("source_urls", [])

    # Build a unified list of (name, url, published_at) tuples
    entries: list[tuple[str, str, str | None]] = []
    seen_urls: set[str] = set()
    for src in named_sources:
        if isinstance(src, dict):
            url = (src.get("url") or "").strip()
            name = (src.get("name") or "").strip()
            pub = src.get("published_date") or None
            if url and url not in seen_urls:
                entries.append((name or derive_name_from_url(url), url, pub))
                seen_urls.add(url)
    for url in flat_urls:
        if isinstance(url, str) and url.strip() and url.strip() not in seen_urls:
            entries.append((derive_name_from_url(url.strip()), url.strip(), None))
            seen_urls.add(url.strip())

    if not entries:
        return 0

    count = 0
    for name, url, published_at in entries:
        domain = extract_domain(url)
        stype = classify_source_type(domain)
        tier = assign_credibility_tier(domain, source_type=stype)

        sid = upsert_source(
            conn,
            url=url,
            name=name,
            domain=domain,
            source_type=stype,
            credibility_tier=tier,
            published_at=published_at,
            timestamp=timestamp,
        )
        insert_appearance(
            conn,
            source_id=sid,
            run_id=run_id,
            region=region,
            pillar=pillar,
            collected_at=timestamp,
        )
        count += 1

    return count


def ingest_youtube_signals(
    conn: sqlite3.Connection,
    region: str,
    run_id: str,
    signal_path: Path,
    yt_tier_lookup: dict,
    timestamp: str,
) -> int:
    """
    Ingest youtube_signals.json. Returns count of sources upserted.
    YouTube signals may be an object with 'source_videos' list,
    or a bare list. Each item may have channel/channel_name/channel_id fields.
    """
    data = load_json(signal_path)
    if data is None:
        return 0

    # Handle both list and dict formats
    if isinstance(data, list):
        videos = data
    elif isinstance(data, dict):
        videos = data.get("source_videos", [])
    else:
        return 0

    if not isinstance(videos, list) or len(videos) == 0:
        return 0

    count = 0
    for item in videos:
        if not isinstance(item, dict):
            continue

        channel_id = item.get("channel_id", "").strip()
        name = (
            item.get("channel_name")
            or item.get("channel")
            or channel_id
            or "Unknown YouTube Channel"
        )
        name = name.strip()

        # Build URL from channel_id if available
        if channel_id:
            url = f"https://youtube.com/@{channel_id}"
        else:
            url = item.get("url", "").strip()

        domain = "youtube.com"
        # Look up tier from youtube_sources.json by channel_id
        tier = yt_tier_lookup.get(channel_id, "B")

        sid = upsert_source(
            conn,
            url=url,
            name=name,
            domain=domain,
            source_type="social",
            credibility_tier=tier,
            timestamp=timestamp,
        )
        insert_appearance(
            conn,
            source_id=sid,
            run_id=run_id,
            region=region,
            pillar="youtube",
            headline=item.get("title", "").strip(),
            collected_at=timestamp,
        )
        count += 1

    return count


def ingest_seerist_events(
    conn: sqlite3.Connection,
    region: str,
    run_id: str,
    signal_path: Path,
    timestamp: str,
) -> int:
    """
    Ingest seerist_events.json (or seerist_signals.json).
    Returns count of events inserted.
    """
    data = load_json(signal_path)
    if data is None:
        return 0

    # File may be an object with 'events' list, or a bare list
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        events = data.get("events", [])
    else:
        return 0

    if not isinstance(events, list):
        return 0

    count = 0
    for event in events:
        if not isinstance(event, dict):
            continue

        event_id = event.get("event_id", "").strip()
        if not event_id:
            continue

        # Skip if already present (idempotent)
        existing = conn.execute(
            "SELECT 1 FROM seerist_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing:
            continue

        location = event.get("location", {}) or {}
        countries_raw = event.get("countries", location.get("country_code", ""))
        countries = (
            json.dumps(countries_raw)
            if isinstance(countries_raw, list)
            else str(countries_raw)
        )

        conn.execute(
            """
            INSERT INTO seerist_events
                (event_id, source, region, countries, category, severity, title,
                 description, verified, lat, lon, event_timestamp, run_id, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.get("source", ""),
                region.upper(),
                countries,
                event.get("category", ""),
                event.get("severity"),
                event.get("title", ""),
                event.get("description", ""),
                1 if event.get("verified") else 0,
                location.get("lat"),
                location.get("lon"),
                event.get("timestamp", event.get("event_timestamp", "")),
                run_id,
                timestamp,
            ),
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Citation detection
# ---------------------------------------------------------------------------

def detect_citations(
    conn: sqlite3.Connection,
    region: str,
    run_id: str,
    report_path: Path,
) -> int:
    """
    Read report.md and check which source names appear in the text.
    Sets cited=1 on matching source_appearances rows and increments cited_count.
    Returns number of citations found.
    """
    try:
        report_text = report_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0

    # Fetch all appearances for this region+run_id that are not yet cited
    rows = conn.execute(
        """
        SELECT sa.id, sa.source_id, sr.name
          FROM source_appearances sa
          JOIN sources_registry sr ON sr.id = sa.source_id
         WHERE sa.region = ? AND sa.run_id = ? AND sa.cited = 0
        """,
        (region.upper(), run_id),
    ).fetchall()

    cited = 0
    for row_id, src_id, name in rows:
        if name and name.lower() in report_text.lower():
            conn.execute(
                "UPDATE source_appearances SET cited = 1 WHERE id = ?", (row_id,)
            )
            conn.execute(
                "UPDATE sources_registry SET cited_count = cited_count + 1 WHERE id = ?",
                (src_id,),
            )
            cited += 1

    return cited


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    timestamp = now_iso()

    # 1. Read run_id
    manifest = load_json(RUN_MANIFEST_PATH)
    run_id = manifest.get("pipeline_id", "unknown") if isinstance(manifest, dict) else "unknown"

    # 2. Load YouTube tier lookup: channel_id → credibility_tier
    yt_sources = load_json(YOUTUBE_SOURCES_PATH) or []
    yt_tier_lookup: dict[str, str] = {}
    if isinstance(yt_sources, list):
        for item in yt_sources:
            if isinstance(item, dict):
                cid = item.get("channel_id", "").strip().lstrip("@")
                tier = item.get("credibility_tier", "B")
                if cid:
                    yt_tier_lookup[cid] = tier
                    # Also index with @ prefix for flexible matching
                    yt_tier_lookup[f"@{cid}"] = tier

    # 3. Open DB and init schema
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    init_db(conn)

    # Migration: add blocked column if missing
    try:
        conn.execute("ALTER TABLE sources_registry ADD COLUMN blocked INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # column already exists

    # Migration: add collection_type column if missing
    try:
        conn.execute("ALTER TABLE sources_registry ADD COLUMN collection_type TEXT DEFAULT 'osint'")
        conn.commit()
    except Exception:
        pass  # column already exists

    # Migration: add published_at column if missing
    try:
        conn.execute("ALTER TABLE sources_registry ADD COLUMN published_at TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists

    total_upserted = 0
    total_new_before = conn.execute(
        "SELECT COUNT(*) FROM sources_registry"
    ).fetchone()[0]

    # 4. Per-region ingest
    for region in REGIONS:
        region_dir = OUTPUT_REGIONAL / region
        region_upserted = 0
        region_cited = 0

        # Geo signals
        geo_path = region_dir / "geo_signals.json"
        region_upserted += ingest_osint_signals(
            conn, region, run_id, geo_path, "geo", timestamp
        )

        # Cyber signals
        cyber_path = region_dir / "cyber_signals.json"
        region_upserted += ingest_osint_signals(
            conn, region, run_id, cyber_path, "cyber", timestamp
        )

        # YouTube signals
        yt_path = region_dir / "youtube_signals.json"
        region_upserted += ingest_youtube_signals(
            conn, region, run_id, yt_path, yt_tier_lookup, timestamp
        )

        # Seerist events — try both naming conventions
        for seerist_name in ("seerist_events.json", "seerist_signals.json"):
            seerist_path = region_dir / seerist_name
            ingest_seerist_events(conn, region, run_id, seerist_path, timestamp)

        # Citation detection
        report_path = region_dir / "report.md"
        region_cited = detect_citations(conn, region, run_id, report_path)

        conn.commit()

        print(
            f"[{region.upper():5}] {region_upserted} sources upserted, "
            f"{region_cited} cited"
        )
        total_upserted += region_upserted

    # 5. Summary
    total_after = conn.execute(
        "SELECT COUNT(*) FROM sources_registry"
    ).fetchone()[0]
    new_this_run = total_after - total_new_before

    conn.close()

    blocked_count = sync_blocked_urls()
    print(f"[registry] Synced {blocked_count} blocked URLs to data/blocked_urls.txt")

    print(
        f"\nSource registry updated: {total_after} total sources, "
        f"{new_this_run} new this run"
    )
    return 0


def sync_blocked_urls(db_path: str = DB_PATH, output_path: str = "data/blocked_urls.txt") -> int:
    """Write all blocked URLs to a flat file for use by research_collector.py."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute("SELECT url FROM sources_registry WHERE blocked = 1 AND url IS NOT NULL").fetchall()
        urls = [r[0] for r in rows if r[0]]
        Path(output_path).write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
        return len(urls)
    except Exception as e:
        print(f"[sync_blocked_urls] Error: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[ERROR] Unrecoverable: {exc}", file=sys.stderr)
        sys.exit(1)


# ── Code-owned enrichment gate ────────────────────────────────────────────────
# These functions run AFTER update_source_registry populates source_appearances.
# Agents own reasoning. Code owns counting, URL matching, and arithmetic.

def _compute_source_quality(conn, region: str, run_id: str) -> dict:
    """Query source_appearances for this region+run, count by credibility_tier."""
    cur = conn.execute("""
        SELECT sr.credibility_tier, COUNT(DISTINCT sa.source_id)
        FROM source_appearances sa
        JOIN sources_registry sr ON sa.source_id = sr.id
        WHERE sa.region = ? AND sa.run_id = ?
        GROUP BY sr.credibility_tier
    """, (region.upper(), run_id))
    counts = {row[0]: row[1] for row in cur.fetchall()}
    return {
        "tier_a": counts.get("A", 0),
        "tier_b": counts.get("B", 0),
        "tier_c": counts.get("C", 0),
        "total": sum(counts.values()),
    }


def _enrich_cluster_sources(conn, region: str) -> int:
    """
    For each source in signal_clusters.json, look up url + credibility_tier
    from sources_registry and add them to the source object.
    Returns count of resolved sources.
    """
    clusters_path = Path("output") / "regional" / region.lower() / "signal_clusters.json"
    if not clusters_path.exists():
        return 0

    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    resolved = 0

    for cluster in data.get("clusters", []):
        for source in cluster.get("sources", []):
            name = source.get("name", "").strip()
            if not name:
                continue
            cur = conn.execute(
                "SELECT url, credibility_tier FROM sources_registry WHERE LOWER(name) = LOWER(?)",
                (name,)
            )
            row = cur.fetchone()
            if row:
                source["url"] = row[0]
                source["credibility_tier"] = row[1]
                resolved += 1
            else:
                source.setdefault("url", None)
                source.setdefault("credibility_tier", None)

    clusters_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return resolved


def _set_cited_flags(conn, region: str, run_id: str) -> int:
    """
    For each source in enriched signal_clusters.json that has a url,
    set cited=1 in source_appearances.
    Returns count of updated rows.
    """
    clusters_path = Path("output") / "regional" / region.lower() / "signal_clusters.json"
    if not clusters_path.exists():
        return 0

    data = json.loads(clusters_path.read_text(encoding="utf-8"))
    updated = 0

    for cluster in data.get("clusters", []):
        for source in cluster.get("sources", []):
            url = source.get("url")
            if not url:
                continue
            cur = conn.execute(
                "SELECT id FROM sources_registry WHERE url = ?", (url,)
            )
            row = cur.fetchone()
            if row:
                conn.execute(
                    "UPDATE source_appearances SET cited=1 WHERE source_id=? AND run_id=? AND region=?",
                    (row[0], run_id, region)
                )
                updated += 1

    conn.commit()
    return updated


def _validate_source_quality(data: dict) -> None:
    """Fail hard if source_quality is missing or arithmetic is wrong."""
    sq = data.get("source_quality")
    assert sq is not None, "source_quality missing from data.json"
    assert all(isinstance(sq.get(k), int) for k in ["tier_a", "tier_b", "tier_c", "total"]), \
        f"source_quality fields must be ints: {sq}"
    assert sq["total"] == sq["tier_a"] + sq["tier_b"] + sq["tier_c"], \
        f"source_quality total mismatch: {sq}"


def enrich_region_data(region: str, run_id: str, db_path: str = "data/sources.db") -> dict:
    """
    Code-owned enrichment gate. Runs after update_source_registry exits.
    1. Computes source_quality from DB and writes to data.json
    2. Enriches signal_clusters.json sources with url + credibility_tier
    3. Sets cited=1 in source_appearances for matched cluster sources

    Raises AssertionError if source_quality validation fails.
    Returns source_quality dict.
    """
    db = Path(db_path)
    if not db.exists():
        print(f"[enrich_region_data] WARNING: {db_path} not found — skipping enrichment")
        return {}

    conn = sqlite3.connect(str(db))
    try:
        sq = _compute_source_quality(conn, region, run_id)
        resolved = _enrich_cluster_sources(conn, region)
        cited = _set_cited_flags(conn, region, run_id)
    finally:
        conn.close()

    data_path = Path("output") / "regional" / region.lower() / "data.json"
    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["source_quality"] = sq
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    _validate_source_quality(json.loads(data_path.read_text(encoding="utf-8")))

    print(f"[enrich_region_data] {region}: source_quality={sq} resolved={resolved} cited={cited}")
    return sq
