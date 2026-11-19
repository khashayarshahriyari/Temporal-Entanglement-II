"""Scrape every venue, place each event on the map, merge duplicates, write events.json / events.js."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .models import RawEvent, Venue, Window
from .parsers import API_PARSERS, PARSERS, links
from .places import Geocoder, extract_address, find_alias, in_region, looks_like_address
from .textparse import clean

ONGOING_DAYS = 4  # an item spanning this many days or more is an exhibition / run, not a one-off event


@dataclass
class VenueResult:
    venue: Venue
    raw: List[RawEvent] = field(default_factory=list)
    strategy: str = ""
    parsed: int = 0
    in_window: int = 0
    notes: List[str] = field(default_factory=list)
    error: str = ""


# ----------------------------------------------------------------------------- scraping

def scrape_venue(venue: Venue, fx, window: Window, today: date, log: Callable = print,
                 use_browser: bool = True) -> VenueResult:
    res = VenueResult(venue)
    modes = {"static": ["static"], "browser": ["browser"]}.get(venue.render, ["static", "browser"])
    if not use_browser:
        modes = [m for m in modes if m != "browser"] or ["static"]
    cache: Dict[str, List[str]] = {}

    def pages_for(mode: str) -> List[str]:
        if mode in cache:
            return cache[mode]
        pages: List[str] = []
        try:
            if mode == "static":
                body = fx.text(venue.url)
                pages = [body] if body else []
                if not body:
                    res.notes.append("calendar page did not load")
                elif venue.list_pages > 1 and venue.link_pattern:
                    seen_links = links.hrefs_matching(body, venue)
                    sep = "&" if "?" in venue.url else "?"
                    for i in range(1, venue.list_pages):
                        more = fx.text(f"{venue.url}{sep}{venue.page_param}={i}")
                        fresh = links.hrefs_matching(more, venue) - seen_links if more else set()
                        if not fresh:
                            break
                        pages.append(more)
                        seen_links |= fresh
            else:
                months = (window.end.year * 12 + window.end.month) - (window.start.year * 12 + window.start.month)
                clicks = months if venue.paginate else 0
                pages = fx.render(venue.url, next_clicks=clicks)
                if not pages:
                    res.notes.append("browser rendering unavailable or failed")
        except Exception as exc:  # network trouble must not stop the other venues
            res.error = f"{type(exc).__name__}: {exc}"
        for i, p in enumerate(pages):
            fx.dump(f"{venue.id}-{mode}-{i}.html", p)
        cache[mode] = pages
        return pages

    tried_notes: List[str] = []   # diagnostics from parsers that found nothing; shown only if no parser succeeded
    for mode in modes:
        for name in venue.parsers:
            parser = PARSERS[name]
            is_api = name in API_PARSERS
            if is_api and mode != "static":
                continue
            pages = cache.get("static", []) if is_api else pages_for(mode)
            if not is_api and not pages:
                continue
            parser_notes = getattr(parser, "NOTES", [])
            parser_notes.clear()
            try:
                got = parser.parse(venue, fx, pages, window, today)
            except Exception as exc:
                res.notes.append(f"{name} failed: {type(exc).__name__}: {exc}")
                continue
            mine = list(parser_notes)
            parser_notes.clear()
            if got is None:
                tried_notes.extend(mine)
                continue
            # [] means the source answered and has nothing upcoming (e.g. a Squarespace events page whose events are all
            # in the past). That is a final answer: other methods would only dig up old, year-less dates.
            if got and venue.match_links and venue.link_pattern:
                cands = links.listing_links(pages_for("static"), venue)
                near = [e for e in got if window.overlaps(e.first_day, e.last_day)]
                missing = [e for e in near if not e.url or e.url.rstrip("/") == venue.url.rstrip("/")]
                for e in missing:
                    e.url = links.match_url(e.title, e.first_day, cands) or e.url
                still = sum(1 for e in missing if not e.url)
                if still:
                    mine.append(f"{still} of {len(near)} events in range: no page link found on the listing (they link to the calendar)")
            res.raw, res.parsed, res.strategy = got, len(got), f"{name}/{mode}"
            res.notes.extend(mine)
            return res
    res.strategy = "none"
    res.notes.extend(dict.fromkeys(tried_notes))
    res.notes.append("no strategy produced events (see debug/ for the fetched pages)")
    return res


def _norm_title(t: str) -> str:
    t = re.sub(r"\(.*?\)", " ", t.lower())
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


def keep_in_window(res: VenueResult, window: Window) -> None:
    kept, seen, cancelled = [], set(), 0
    later = sorted(e.first_day for e in res.raw if e.first_day > window.end)
    for e in res.raw:
        if not e.title:
            continue
        if re.search(r"\bcancel+ed\b", e.title, re.I):
            cancelled += 1
            continue
        if not window.overlaps(e.first_day, e.last_day):
            continue
        key = (_norm_title(e.title), e.start)
        if key in seen:
            continue
        seen.add(key)
        kept.append(e)
    if cancelled:
        res.notes.append(f"{cancelled} cancelled event(s) skipped")
    if res.raw and not kept and later:
        res.notes.append(f"calendar read fine: {len(res.raw)} event(s) found, none in range; next is {later[0]:%b} {later[0].day}")
    res.raw, res.in_window = kept, len(kept)


# ----------------------------------------------------------------------------- places

def locate(ev: RawEvent, venue: Venue, geocoder: Geocoder):
    """-> (display name, address, lat, lng, approximate?)"""
    name, addr = clean(ev.location_name), clean(ev.address)
    lat, lng = (ev.lat, ev.lng) if in_region(ev.lat, ev.lng) else (None, None)
    approx, alias = False, None
    if not looks_like_address(addr):
        addr = extract_address(name)
    if lat is None and not addr:
        alias = find_alias(name)
        if alias is None and (venue.multi_site or not venue.address):
            alias = find_alias(ev.title) or find_alias(ev.context)
        if alias:
            addr = alias[1]
    if lat is None and not addr and venue.multi_site and ev.context:
        addr = extract_address(ev.context)
    if lat is None and not addr and venue.address:
        addr, approx = venue.address, venue.approx
    if lat is None and addr:
        hit = geocoder.lookup(addr)
        if hit:
            lat, lng = hit
        elif venue.address and addr != venue.address:
            hit = geocoder.lookup(venue.address)
            if hit:
                lat, lng, approx = hit[0], hit[1], True
    display = name or (alias[0] if alias else venue.name)
    if display == addr:
        display = alias[0] if alias else venue.name
    if looks_like_address(display) or re.match(r"\d", display):   # a bare street address makes a poor label
        known = find_alias(display) or find_alias(addr)                # ...use the known place at that address
        if known:
            display = known[0]
    return display, addr, lat, lng, approx


# ----------------------------------------------------------------------------- merging

def _same(a: dict, b: dict) -> bool:
    if a["start"][:10] != b["start"][:10]:
        return False
    ta, tb = _norm_title(a["title"]), _norm_title(b["title"])
    short, long_ = sorted((ta, tb), key=len)
    if len(short) < 5 or short not in long_:
        return False
    if a["has_time"] and b["has_time"]:
        da = datetime.fromisoformat(a["start"])
        db = datetime.fromisoformat(b["start"])
        if abs((da - db).total_seconds()) > 90 * 60:
            return False
    return True


def merge_duplicates(events: List[dict]) -> List[dict]:
    kept: List[dict] = []
    for e in sorted(events, key=lambda x: (x["_priority"], x["start"])):
        dup = next((k for k in kept if _same(k, e)), None)
        if not dup:
            kept.append(e)
            continue
        if e["venue_id"] != dup["venue_id"] and e["venue"] not in dup["also_on"]:
            dup["also_on"].append(e["venue"])
            dup["also_on_ids"].append(e["venue_id"])
        if dup["lat"] is None and e["lat"] is not None:
            dup.update(lat=e["lat"], lng=e["lng"], address=dup["address"] or e["address"], approx=e["approx"])
        if dup["approx"] and not e["approx"] and e["lat"] is not None:
            dup.update(lat=e["lat"], lng=e["lng"], address=e["address"], location=e["location"], approx=False)
        if not dup["has_time"] and e["has_time"]:
            dup.update(start=e["start"], has_time=True, doors=e["doors"], end=e["end"])
    return kept


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%dT%H:%M") if dt else None


def to_dict(ev: RawEvent, venue: Venue, place) -> dict:
    display, addr, lat, lng, approx = place
    last = ev.last_day
    return {
        "id": hashlib.sha1(f"{venue.id}|{ev.title}|{ev.start}".encode()).hexdigest()[:10],
        "title": ev.title, "venue_id": venue.id, "venue": venue.name,
        "location": display, "address": addr, "lat": lat, "lng": lng, "approx": approx,
        "start": _iso(ev.start), "end": _iso(ev.end) if ev.end and ev.end > ev.start else None,
        "has_time": bool(ev.has_time and not ev.all_day), "all_day": ev.all_day,
        "doors": ev.doors.strftime("%H:%M") if ev.doors else None,
        "url": ev.url or venue.url, "ongoing": (last - ev.first_day).days >= ONGOING_DAYS,
        "confidence": ev.confidence, "also_on": [], "also_on_ids": [], "_priority": venue.priority,
    }


# ----------------------------------------------------------------------------- orchestration

def build(venues: List[Venue], fx, window: Window, today: date, geocoder: Geocoder,
          log: Callable = print, use_browser: bool = True) -> dict:
    results: List[VenueResult] = []
    events: List[dict] = []
    for v in venues:
        log(f"- {v.name}")
        res = scrape_venue(v, fx, window, today, log, use_browser)
        keep_in_window(res, window)
        for e in res.raw:
            events.append(to_dict(e, v, locate(e, v, geocoder)))
        log(f"    {res.strategy or '-':<22} parsed {res.parsed:>3}  in window {res.in_window:>3}"
            + (f"   !! {res.error}" if res.error else "") + "".join(f"\n    note: {n}" for n in res.notes))
        results.append(res)

    merged = merge_duplicates(events)
    merged.sort(key=lambda e: (e["start"], e["title"].lower()))
    counts: Dict[str, int] = {}
    for e in merged:
        counts[e["venue_id"]] = counts.get(e["venue_id"], 0) + 1
        e.pop("_priority", None)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "venues": [{
            "id": r.venue.id, "name": r.venue.name, "short": r.venue.short or r.venue.name, "url": r.venue.url,
            "count": counts.get(r.venue.id, 0),
            "parsed": r.parsed, "strategy": r.strategy, "error": r.error,
            "note": "; ".join(([r.venue.note] if r.venue.note else []) + r.notes)[:400],
        } for r in results],
        "events": merged,
    }


def write(data: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=1, ensure_ascii=False)
    (out_dir / "events.json").write_text(payload, encoding="utf-8")
    # events.js lets index.html load the data even when opened straight from disk (no server)
    (out_dir / "events.js").write_text("window.TE_DATA = " + payload + ";\n", encoding="utf-8")
