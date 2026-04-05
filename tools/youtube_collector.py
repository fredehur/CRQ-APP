#!/usr/bin/env python3
"""YouTube OSINT Collector — transcripts from approved channels for tracked topics.

Usage:
    uv run python tools/youtube_collector.py APAC [--mock] [--window 7d]
    uv run python tools/youtube_collector.py AME  [--mock] [--window 30d]

Writes:
    output/regional/{region}/youtube_signals.json

Signal schema:
    {
      "summary": "...",
      "lead_indicators": ["..."],
      "dominant_pillar": "Geopolitical|Cyber",
      "matched_topics": ["topic-id"],
      "source_videos": [{"title", "channel", "channel_id", "url", "published_at"}]
    }

Sources:
    data/youtube_sources.json  — approved channel registry (managed via Config tab)
    data/osint_topics.json     — shared topic registry

Video listing:  yt-dlp (no key) OR YouTube Data API (YOUTUBE_API_KEY env var, faster)
Transcripts:    youtube-transcript-api (no key, public videos only)
Extraction:     Claude Haiku via tools/deep_research._extract_with_haiku
Mock mode:      reads data/mock_osint_fixtures/{REGION}_youtube.json
"""
import asyncio
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research import _extract_with_haiku

OUTPUT = Path(__file__).resolve().parent.parent / "output"
DATA = Path(__file__).resolve().parent.parent / "data"
MOCK_DIR = DATA / "mock_osint_fixtures"
VALID_REGIONS = {"APAC", "AME", "LATAM", "MED", "NCE"}

# Max videos per topic-channel combo and per run
MAX_VIDEOS_PER_RUN = 5
MAX_VIDEOS_PER_CHANNEL = 1

# Window string → timedelta
WINDOW_MAP = {
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}


def _parse_window(window_str: str) -> timedelta:
    return WINDOW_MAP.get(window_str, timedelta(days=7))


def _keyword_score(text: str, keywords: list[str]) -> int:
    """Count how many topic keywords appear in text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def _load_sources(region: str) -> list[dict]:
    """Load approved channels filtered to this region."""
    path = DATA / "youtube_sources.json"
    if not path.exists():
        return []
    try:
        sources = json.loads(path.read_text(encoding="utf-8"))
        return [s for s in sources if region in s.get("region_focus", [])]
    except Exception:
        return []


def _load_topics(region: str) -> list[dict]:
    """Load active topics for this region."""
    path = DATA / "osint_topics.json"
    if not path.exists():
        return []
    try:
        topics = json.loads(path.read_text(encoding="utf-8"))
        return [t for t in topics if t.get("active", True) and region in t.get("regions", [])]
    except Exception:
        return []


def _list_channel_videos_ytdlp(channel_id: str, window: timedelta) -> list[dict]:
    """List recent videos from a channel using yt-dlp. Returns [{id, title, description, published_at, url}]."""
    try:
        import yt_dlp

        cutoff = datetime.now(timezone.utc) - window
        # Build channel URL from handle or channel ID
        if channel_id.startswith("@"):
            url = f"https://www.youtube.com/{channel_id}/videos"
        elif channel_id.startswith("UC"):
            url = f"https://www.youtube.com/channel/{channel_id}/videos"
        else:
            url = f"https://www.youtube.com/@{channel_id}/videos"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": 20,  # limit to last 20 videos
        }

        videos = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info or "entries" not in info:
                return []

            for entry in info.get("entries", []) or []:
                if not entry:
                    continue
                vid_id = entry.get("id", "")
                title = entry.get("title", "")
                description = entry.get("description", "") or ""
                upload_date = entry.get("upload_date", "")  # YYYYMMDD

                # Parse date
                published_at = None
                if upload_date and len(upload_date) == 8:
                    try:
                        published_at = datetime(
                            int(upload_date[:4]),
                            int(upload_date[4:6]),
                            int(upload_date[6:8]),
                            tzinfo=timezone.utc,
                        )
                    except ValueError:
                        pass

                if published_at and published_at < cutoff:
                    continue  # outside window

                videos.append({
                    "id": vid_id,
                    "title": title,
                    "description": description,
                    "published_at": published_at.isoformat()[:10] if published_at else "",
                    "url": f"https://youtube.com/watch?v={vid_id}",
                })

        return videos
    except Exception as e:
        print(f"[youtube_collector] yt-dlp error for {channel_id}: {e}", file=sys.stderr)
        return []


def _list_channel_videos_api(channel_id: str, window: timedelta, api_key: str) -> list[dict]:
    """List recent videos using YouTube Data API v3."""
    try:
        import urllib.request
        import urllib.parse

        cutoff = datetime.now(timezone.utc) - window
        published_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Resolve handle to channel ID if needed
        resolved_id = channel_id
        if channel_id.startswith("@"):
            handle = channel_id[1:]
            params = urllib.parse.urlencode({
                "part": "id",
                "forHandle": handle,
                "key": api_key,
            })
            with urllib.request.urlopen(
                f"https://www.googleapis.com/youtube/v3/channels?{params}", timeout=10
            ) as r:
                data = json.loads(r.read())
                items = data.get("items", [])
                if items:
                    resolved_id = items[0]["id"]

        params = urllib.parse.urlencode({
            "part": "snippet",
            "channelId": resolved_id,
            "order": "date",
            "type": "video",
            "publishedAfter": published_after,
            "maxResults": 20,
            "key": api_key,
        })
        with urllib.request.urlopen(
            f"https://www.googleapis.com/youtube/v3/search?{params}", timeout=10
        ) as r:
            data = json.loads(r.read())

        videos = []
        for item in data.get("items", []):
            vid_id = item.get("id", {}).get("videoId", "")
            snippet = item.get("snippet", {})
            videos.append({
                "id": vid_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "published_at": snippet.get("publishedAt", "")[:10],
                "url": f"https://youtube.com/watch?v={vid_id}",
            })
        return videos
    except Exception as e:
        print(f"[youtube_collector] YouTube API error for {channel_id}: {e}", file=sys.stderr)
        return []


def _fetch_transcript(video_id: str) -> str | None:
    """Fetch transcript text for a YouTube video ID. Returns None if unavailable."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        text = " ".join(entry["text"] for entry in transcript_list)
        # Normalise whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text if text else None
    except Exception:
        return None


def _chunk_transcript(text: str, max_chars: int = 8000) -> list[str]:
    """Split long transcript into chunks at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        # Find last sentence boundary before max_chars
        cut = text.rfind(". ", 0, max_chars)
        if cut == -1:
            cut = max_chars
        else:
            cut += 1  # include the period
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return chunks


async def _run_live(region: str, window: timedelta) -> dict:
    """Live mode: fetch videos, transcripts, extract signals."""
    import os

    sources = _load_sources(region)
    topics = _load_topics(region)

    if not sources:
        print(f"[youtube_collector] {region} — no approved channels for this region", file=sys.stderr)
        return _empty_signals(region)

    if not topics:
        print(f"[youtube_collector] {region} — no active topics for this region", file=sys.stderr)
        return _empty_signals(region)

    youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
    all_keywords = [kw for t in topics for kw in t.get("keywords", [])]
    selected_videos = []

    for source in sources:
        channel_id = source["channel_id"]
        print(f"[youtube_collector] {region} — listing {channel_id}...", flush=True)

        if youtube_api_key:
            videos = _list_channel_videos_api(channel_id, window, youtube_api_key)
        else:
            videos = _list_channel_videos_ytdlp(channel_id, window)

        if not videos:
            print(f"[youtube_collector] {region} — {channel_id}: no videos in window", file=sys.stderr)
            continue

        # Score and pick top 1 per channel
        scored = sorted(
            videos,
            key=lambda v: _keyword_score(v["title"] + " " + v["description"], all_keywords),
            reverse=True,
        )
        best = scored[0]
        if _keyword_score(best["title"] + " " + best["description"], all_keywords) == 0:
            print(f"[youtube_collector] {region} — {channel_id}: no keyword match in window", file=sys.stderr)
            continue

        selected_videos.append({**best, "channel": source["name"], "channel_id": channel_id})

        if len(selected_videos) >= MAX_VIDEOS_PER_RUN:
            break

    if not selected_videos:
        print(f"[youtube_collector] {region} — no matching videos found", file=sys.stderr)
        return _empty_signals(region)

    # Fetch transcripts + extract signals
    all_signals = []
    source_videos = []

    for video in selected_videos:
        vid_id = video["id"]
        print(f"[youtube_collector] {region} — fetching transcript: {video['title'][:60]}", flush=True)
        transcript = _fetch_transcript(vid_id)

        if not transcript:
            print(f"[youtube_collector] {region} — no transcript for {vid_id}, skipping", file=sys.stderr)
            continue

        chunks = _chunk_transcript(transcript)
        # Use first chunk (most recent content in auto-captions is often early)
        extracted = await _extract_with_haiku(chunks[0], "youtube", region)
        all_signals.append(extracted)
        source_videos.append({
            "title": video["title"],
            "channel": video["channel"],
            "channel_id": video["channel_id"],
            "url": video["url"],
            "published_at": video["published_at"],
        })

    if not all_signals:
        return _empty_signals(region)

    # Merge: use first signal as base, extend lead_indicators from others
    merged = all_signals[0].copy()
    merged["source_videos"] = source_videos
    for sig in all_signals[1:]:
        merged["lead_indicators"].extend(sig.get("lead_indicators", []))
    merged["lead_indicators"] = merged["lead_indicators"][:5]  # cap at 5

    # Populate matched_topics
    matched = set()
    for t in topics:
        for indicator in merged["lead_indicators"]:
            ind_text = indicator.get("text", "") if isinstance(indicator, dict) else str(indicator)
            if any(kw.lower() in ind_text.lower() for kw in t.get("keywords", [])):
                matched.add(t["id"])
    merged["matched_topics"] = list(matched)

    return merged


def _empty_signals(region: str) -> dict:
    return {
        "summary": f"No YouTube signals identified for {region} in the current collection window. "
                   "No approved channels produced content matching tracked topics. "
                   "Signal absence is logged — this does not indicate a low-risk environment.",
        "lead_indicators": [],
        "dominant_pillar": "Geopolitical",
        "matched_topics": [],
        "source_videos": [],
    }


def _run_mock(region: str) -> dict:
    """Mock mode: read fixture file."""
    fixture = MOCK_DIR / f"{region}_youtube.json"
    if not fixture.exists():
        print(f"[youtube_collector] mock fixture not found: {fixture}", file=sys.stderr)
        return _empty_signals(region)
    return json.loads(fixture.read_text(encoding="utf-8"))


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: youtube_collector.py REGION [--mock] [--window 7d]", file=sys.stderr)
        sys.exit(1)

    region = args[0].upper()
    if region not in VALID_REGIONS:
        print(f"Unknown region: {region}. Valid: {', '.join(sorted(VALID_REGIONS))}", file=sys.stderr)
        sys.exit(1)

    mock = "--mock" in args
    window_str = "7d"
    for a in args:
        if a.startswith("--window"):
            window_str = a.split("=", 1)[1] if "=" in a else (args[args.index(a) + 1] if args.index(a) + 1 < len(args) else "7d")

    print(f"[youtube_collector] {region} mock={mock} window={window_str}", flush=True)

    if mock:
        signals = _run_mock(region)
    else:
        signals = asyncio.run(_run_live(region, _parse_window(window_str)))

    # Write output
    out_dir = OUTPUT / "regional" / region.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "youtube_signals.json"
    out_path.write_text(json.dumps(signals, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[youtube_collector] {region} — wrote {out_path}", flush=True)
    print(json.dumps(signals, indent=2))


if __name__ == "__main__":
    main()
