from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt

from tools.briefs.models import CalendarItem, Coordinates, JoinedEvent, SiteContext


_EARTH_RADIUS_KM = 6371.0


def _severity_from_int(score: int) -> str:
    if score >= 8:
        return "critical"
    if score >= 6:
        return "high"
    if score >= 4:
        return "medium"
    return "monitor"


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "monitor": 3}


def _signal_date(sig) -> date:
    pub = sig.published_at
    if isinstance(pub, datetime):
        return pub.date()
    return pub


def _signal_location_name(sig) -> str:
    loc = getattr(sig, "location", None)
    if loc is None:
        return "unknown"
    name = getattr(loc, "name", None)
    return name or "unknown"


def haversine_km(a: Coordinates, b: Coordinates) -> float:
    lat1, lon1 = radians(a.lat), radians(a.lon)
    lat2, lon2 = radians(b.lat), radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(h))


def proximity_hits(site: SiteContext, signals: list) -> list[JoinedEvent]:
    site_coords = site.coordinates
    radius = site.seerist_poi_radius_km
    hits: list[tuple[float, JoinedEvent]] = []

    for sig in signals:
        loc = getattr(sig, "location", None)
        if loc is None:
            continue
        lat = getattr(loc, "lat", None)
        lon = getattr(loc, "lon", None)
        if lat is None or lon is None:
            continue

        distance = haversine_km(site_coords, Coordinates(lat=lat, lon=lon))
        if distance > radius:
            continue

        severity_str = _severity_from_int(sig.severity)
        event = JoinedEvent(
            signal_id=sig.signal_id,
            headline=sig.title,
            where=getattr(loc, "name", None) or "unknown",
            when=_signal_date(sig).isoformat(),
            severity=severity_str,
            distance_km=round(distance, 2),
            ref=sig.signal_id,
            join_reason="proximity",
        )
        hits.append((distance, event))

    hits.sort(key=lambda pair: (_SEVERITY_RANK[pair[1].severity], pair[0]))
    return [event for _, event in hits]


def pattern_hits(
    site: SiteContext,
    signals: list,
    since_days: int = 30,
) -> list[JoinedEvent]:
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=since_days)

    attack_types = set(site.relevant_attack_types)
    categories = set(site.relevant_seerist_categories)

    hits: list[JoinedEvent] = []
    for sig in signals:
        if getattr(sig, "country", None) != site.country:
            continue

        sig_date = _signal_date(sig)
        if sig_date < cutoff or sig_date > today:
            continue

        attack_type = getattr(sig, "attack_type", None)
        category = getattr(sig, "category", None)

        matches_attack = attack_type is not None and attack_type in attack_types
        matches_category = category is not None and category in categories
        if not (matches_attack or matches_category):
            continue

        severity_str = _severity_from_int(sig.severity)
        hits.append(
            JoinedEvent(
                signal_id=sig.signal_id,
                headline=sig.title,
                where=_signal_location_name(sig),
                when=sig_date.isoformat(),
                severity=severity_str,
                distance_km=None,
                ref=sig.signal_id,
                join_reason="pattern",
            )
        )

    hits.sort(key=lambda ev: _SEVERITY_RANK[ev.severity])
    return hits


def actor_hits(site: SiteContext, signals: list) -> list[JoinedEvent]:
    actors = set(site.threat_actors_of_interest)

    hits: list[JoinedEvent] = []
    for sig in signals:
        perp = getattr(sig, "perpetrator", None)
        if perp is None or perp not in actors:
            continue

        severity_str = _severity_from_int(sig.severity)
        hits.append(
            JoinedEvent(
                signal_id=sig.signal_id,
                headline=sig.title,
                where=_signal_location_name(sig),
                when=_signal_date(sig).isoformat(),
                severity=severity_str,
                distance_km=None,
                ref=sig.signal_id,
                join_reason="actor",
            )
        )

    hits.sort(key=lambda ev: _SEVERITY_RANK[ev.severity])
    return hits


def calendar_ahead(
    site: SiteContext,
    calendar: list,
    horizon_days: int = 14,
    reference_date: date | None = None,
) -> list[CalendarItem]:
    ref = reference_date or date.today()
    out: list[CalendarItem] = []

    for item in calendar:
        if getattr(item, "country", None) != site.country:
            continue

        try:
            event_date = date.fromisoformat(item.date_str)
        except (ValueError, TypeError):
            continue

        days_until = (event_date - ref).days
        if days_until < 0 or days_until > horizon_days:
            continue

        out.append(
            CalendarItem(
                label=item.label,
                date_str=item.date_str,
                horizon_days=days_until,
            )
        )

    out.sort(key=lambda c: c.horizon_days)
    return out
