"""Squarespace: append ?format=json to a collection URL.

Tower Grove Park, The Luminary and Untitled Fine Art are Squarespace sites. Event collections return real start/end
timestamps and a location block; blog/summary collections don't, so for those we fall back to dates written in the
excerpt/body text (flagged confidence="text" so the map can say the date was inferred).
"""
from __future__ import annotations

import html
import json
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import RawEvent
from ..places import extract_address, in_region
from ..textparse import best_date, clean, extract_times, find_dates, from_epoch_ms
from datetime import datetime

API_KIND = True


def _text(fragment: str) -> str:
    return clean(BeautifulSoup(fragment or "", "html.parser").get_text(" "))


def _item_to_event(item: dict, base: str, today) -> Optional[RawEvent]:
    title = clean(html.unescape(item.get("title") or ""))
    if not title:
        return None
    url = urljoin(base, item.get("fullUrl") or item.get("url") or "")
    loc = item.get("location") or {}
    name = clean(loc.get("addressTitle") or "")
    addr = ", ".join(x for x in [loc.get("addressLine1"), loc.get("addressLine2")] if x)
    lat = lng = None
    try:
        la, ln = float(loc.get("mapLat")), float(loc.get("mapLng"))
        if in_region(la, ln):  # Squarespace's placeholder map point is in New York; in_region() rejects it
            lat, lng = la, ln
    except (TypeError, ValueError):
        pass

    start = from_epoch_ms(item.get("startDate")) if item.get("startDate") else None
    if start:
        end = from_epoch_ms(item.get("endDate")) if item.get("endDate") else None
        return RawEvent(title=title, start=start, end=end, url=url, location_name=name, address=addr,
                        lat=lat, lng=lng, confidence="structured")

    # not an event item: look for a written date in the excerpt / body
    blob = " ".join([title, _text(item.get("excerpt", "")), _text(item.get("body", ""))[:3000]])
    hit = best_date(find_dates(blob, today))
    if not hit:
        return None
    t = extract_times(blob[max(0, hit.start - 80): hit.end + 120])
    start = datetime.combine(hit.date, t.start) if t.start else datetime.combine(hit.date, datetime.min.time())
    return RawEvent(title=title, start=start, has_time=bool(t.start), doors=t.doors, url=url,
                    location_name=name, address=addr or extract_address(blob), lat=lat, lng=lng,
                    confidence="text", context=blob[:400])


def parse(venue, fx, pages, window, today) -> Optional[List[RawEvent]]:
    url = venue.url
    sep = "&" if "?" in url else "?"
    out: List[RawEvent] = []
    recognised = from_upcoming = False
    next_url = f"{url}{sep}format=json"
    for _ in range(6):
        data = fx.json(next_url)
        if not isinstance(data, dict):
            break
        if "upcoming" in data:
            from_upcoming = True
            items = list(data.get("upcoming") or [])
        elif "items" in data:
            items = list(data.get("items") or [])
        else:
            break
        recognised = True
        fx.dump(f"{venue.id}-squarespace.json", json.dumps(data, indent=1)[:400000])
        for it in items:
            ev = _item_to_event(it, url, today)
            if ev:
                out.append(ev)
        nxt = (data.get("pagination") or {}).get("nextPageUrl")
        if not nxt:
            break
        next_url = urljoin(url, nxt) + ("&" if "?" in nxt else "?") + "format=json"
    if not recognised:
        return None
    if not out and not from_upcoming:
        return None   # a blog / summary collection with no dated entries is not an events feed: let the other methods try
    return out
