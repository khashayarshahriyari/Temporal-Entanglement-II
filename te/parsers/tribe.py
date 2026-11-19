"""WordPress 'The Events Calendar' (Tribe) REST API: /wp-json/tribe/events/v1/events.

Used by Grand Center, CAM and City Museum (their pages carry the `tec-api` meta tag). Gives clean titles, local start/end
times, and the venue's address - even for events held at other places.
"""
from __future__ import annotations

import html
from datetime import timedelta
from typing import List, Optional
from urllib.parse import urlparse

from ..models import RawEvent
from ..textparse import clean, parse_iso

API_KIND = True
LOOKBACK_DAYS = 150   # how far back to look for exhibitions / runs that are still open


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _venue_fields(v) -> dict:
    if isinstance(v, list):
        v = v[0] if v else {}
    if not isinstance(v, dict):
        return {}
    addr = ", ".join(x for x in [v.get("address"), v.get("city"), v.get("state") or v.get("province"), v.get("zip")] if x)
    try:
        lat, lng = float(v.get("geo_lat")), float(v.get("geo_lng"))
    except (TypeError, ValueError):
        lat = lng = None
    return {"name": clean(html.unescape(v.get("venue") or "")), "address": addr, "lat": lat, "lng": lng}


def parse(venue, fx, pages, window, today) -> Optional[List[RawEvent]]:
    base = (venue.tribe_base or _origin(venue.url)).rstrip("/")
    url = f"{base}/wp-json/tribe/events/v1/events"
    # No end_date: the API treats it as "must END before", which hides exhibitions and runs that continue past the window
    # (e.g. a holiday run that closes in January). Start a while back so those are included, stop paging once past the window.
    params = {"start_date": (window.start - timedelta(days=LOOKBACK_DAYS)).isoformat(),
              "per_page": 100, "status": "publish"}
    out: List[RawEvent] = []
    saw_valid = False
    for _ in range(12):
        data = fx.json(url, params=params)
        if not isinstance(data, dict) or "events" not in data:
            break
        saw_valid = True
        fx.dump(f"{venue.id}-tribe.json", __import__("json").dumps(data, indent=1)[:400000])
        page_starts = []
        for e in data["events"]:
            start, end = parse_iso(e.get("start_date", "")), parse_iso(e.get("end_date", ""))
            if not start:
                continue
            page_starts.append(start.date())
            if start.date() > window.end or (end or start).date() < window.start:
                continue
            v = _venue_fields(e.get("venue"))
            all_day = bool(e.get("all_day"))
            out.append(RawEvent(
                title=clean(html.unescape(e.get("title") or "")),
                start=start, end=end, all_day=all_day, has_time=not all_day,
                url=e.get("url") or "", location_name=v.get("name", ""), address=v.get("address", ""),
                lat=v.get("lat"), lng=v.get("lng"), confidence="structured"))
        nxt = data.get("next_rest_url")
        if not nxt or (page_starts and min(page_starts) > window.end):
            break
        url, params = nxt, None
    return out if saw_valid else None
