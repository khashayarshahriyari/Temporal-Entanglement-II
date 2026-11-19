"""schema.org Event objects in <script type="application/ld+json"> (used by many theatres, ticketing plugins and CMSes)."""
from __future__ import annotations

import html as htmllib
import json
import re
from typing import Any, Iterable, List, Optional

from bs4 import BeautifulSoup

from ..models import RawEvent
from ..places import extract_address, in_region
from ..textparse import clean, parse_iso

API_KIND = False


def _walk(node: Any) -> Iterable[dict]:
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item", "subEvent", "event"):
            if key in node:
                yield from _walk(node[key])


def _is_event(d: dict) -> bool:
    t = d.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.endswith("Event") for x in types)


def _location(loc: Any):
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    if isinstance(loc, str):
        return clean(loc), extract_address(loc), None, None
    if not isinstance(loc, dict):
        return "", "", None, None
    name = clean(htmllib.unescape(loc.get("name") or ""))
    addr = loc.get("address")
    if isinstance(addr, dict):
        addr_s = ", ".join(str(addr.get(k)) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode") if addr.get(k))
    else:
        addr_s = clean(str(addr or ""))
    lat = lng = None
    geo = loc.get("geo")
    if isinstance(geo, dict):
        try:
            la, ln = float(geo.get("latitude")), float(geo.get("longitude"))
            if in_region(la, ln):
                lat, lng = la, ln
        except (TypeError, ValueError):
            pass
    return name, addr_s, lat, lng


def events_from_html(html: str, base_url: str = "") -> List[RawEvent]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[RawEvent] = []
    for tag in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except ValueError:
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]+", " ", raw))
            except ValueError:
                continue
        for d in _walk(data):
            if not _is_event(d):
                continue
            start = parse_iso(str(d.get("startDate") or ""))
            if not start:
                continue
            end = parse_iso(str(d.get("endDate") or ""))
            date_only = len(str(d.get("startDate"))) <= 10
            name, addr, lat, lng = _location(d.get("location"))
            url = d.get("url") or ""
            if isinstance(url, list):
                url = url[0] if url else ""
            if url and base_url and url.startswith("/"):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            out.append(RawEvent(
                title=clean(htmllib.unescape(str(d.get("name") or ""))), start=start, end=end,
                has_time=not date_only, all_day=date_only, url=str(url), location_name=name, address=addr,
                lat=lat, lng=lng, confidence="structured"))
    return [e for e in out if e.title]


def parse(venue, fx, pages, window, today) -> Optional[List[RawEvent]]:
    out: List[RawEvent] = []
    for html in pages:
        out.extend(events_from_html(html, venue.url))
    return out or None
