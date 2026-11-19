"""Wix Events: Wix inlines the events widget's data as JSON inside <script> tags. Best-effort - returns None if absent."""
from __future__ import annotations

import html as htmllib
import json
import re
from datetime import datetime
from typing import Any, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import RawEvent
from ..places import in_region
from ..textparse import clean, parse_iso

API_KIND = False


def _walk(node: Any) -> Iterable[dict]:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def parse(venue, fx, pages, window, today) -> Optional[List[RawEvent]]:
    out: List[RawEvent] = []
    seen = set()
    origin = "{0.scheme}://{0.netloc}".format(urlparse(venue.url))
    detail_prefix = ""
    if venue.link_pattern:
        m = re.match(r"^(/[\w\-/]*?)/?(?=[\[\(\\.*+?]|$)", venue.link_pattern.replace("\\/", "/"))
        detail_prefix = m.group(1) if m else ""
    for html in pages:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script"):
            raw = tag.string or ""
            if "scheduling" not in raw or not raw.lstrip().startswith(("{", "[")):
                continue
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            for d in _walk(data):
                sched = d.get("scheduling")
                if not (isinstance(sched, dict) and d.get("title") and d.get("slug")):
                    continue
                cfg = sched.get("config") or {}
                start = parse_iso(str(cfg.get("startDate") or ""))
                if not start:
                    continue
                key = (d["slug"], start)
                if key in seen:
                    continue
                seen.add(key)
                end = parse_iso(str(cfg.get("endDate") or ""))
                loc = d.get("location") or {}
                addr = ""
                if isinstance(loc.get("address"), dict):
                    addr = clean(loc["address"].get("formatted") or loc["address"].get("formattedAddress") or "")
                lat = lng = None
                coords = (loc.get("address") or {}).get("geocode") if isinstance(loc.get("address"), dict) else None
                if isinstance(coords, dict):
                    try:
                        la, ln = float(coords.get("latitude")), float(coords.get("longitude"))
                        if in_region(la, ln):
                            lat, lng = la, ln
                    except (TypeError, ValueError):
                        pass
                out.append(RawEvent(
                    title=clean(htmllib.unescape(str(d["title"]))), start=start, end=end,
                    url=urljoin(origin, f"{detail_prefix}/{d['slug']}") if detail_prefix else venue.url,
                    location_name=clean(str(loc.get("name") or "")), address=addr, lat=lat, lng=lng,
                    confidence="structured"))
    return out or None
