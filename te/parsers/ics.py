"""iCalendar (.ics) feeds. Many calendar plugins publish one (Tribe: ?ical=1, Squarespace: ?format=ical)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import List, Optional
from urllib.parse import urljoin

from ..models import RawEvent
from ..places import extract_address
from ..textparse import LOCAL_TZ, clean, to_local

API_KIND = True


def _unfold(text: str) -> List[str]:
    lines: List[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(v: str) -> str:
    return v.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _dt(params: str, value: str):
    """-> (naive local datetime, is_date_only)"""
    value = value.strip()
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", value):
        return datetime.combine(datetime.strptime(value[:8], "%Y%m%d").date(), time(0, 0)), True
    fmt = "%Y%m%dT%H%M%S"
    dt = datetime.strptime(value.rstrip("Z"), fmt)
    if value.endswith("Z"):
        from datetime import timezone
        return to_local(dt.replace(tzinfo=timezone.utc)), False
    m = re.search(r"TZID=([^;:]+)", params)
    if m and LOCAL_TZ is not None:
        try:
            from zoneinfo import ZoneInfo
            return to_local(dt.replace(tzinfo=ZoneInfo(m.group(1)))), False
        except Exception:
            pass
    return dt, False


def parse_ics(text: str) -> List[RawEvent]:
    events: List[RawEvent] = []
    cur: Optional[dict] = None
    for line in _unfold(text):
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.startswith("END:VEVENT") and cur is not None:
            try:
                if "DTSTART" in cur:
                    start, date_only = _dt(*cur["DTSTART"])
                    end = None
                    if "DTEND" in cur:
                        end, _ = _dt(*cur["DTEND"])
                        if date_only:  # DTEND for all-day is exclusive: the last day is the day before it
                            last = (end - timedelta(days=1)).date()
                            end = datetime.combine(last, time(23, 59)) if last > start.date() else None
                    loc = clean(_unescape(cur.get("LOCATION", ("", ""))[1]))
                    events.append(RawEvent(
                        title=clean(_unescape(cur.get("SUMMARY", ("", ""))[1])), start=start, end=end,
                        all_day=date_only, has_time=not date_only, url=cur.get("URL", ("", ""))[1].strip(),
                        location_name=loc if not extract_address(loc) else loc.split(",")[0],
                        address=extract_address(loc), confidence="structured"))
            except (ValueError, KeyError):
                pass
            cur = None
        elif cur is not None and ":" in line:
            head, _, value = line.partition(":")
            name, _, params = head.partition(";")
            cur[name.upper()] = (params, value)
    return [e for e in events if e.title]


def _candidate_urls(venue, pages) -> List[str]:
    urls: List[str] = [venue.ics_url] if venue.ics_url else []
    base = venue.url
    sep = "&" if "?" in base else "?"
    urls.append(f"{base}{sep}ical=1")                       # Tribe
    urls.append(f"{base}{sep}format=ical")                  # Squarespace (single items) - harmless otherwise
    for html in pages:
        for m in re.finditer(r"""href=["']([^"']*(?:\.ics|ical=1|format=ical|webcal:)[^"']*)["']""", html, re.I):
            urls.append(urljoin(base, m.group(1).replace("webcal:", "https:")))
    return list(dict.fromkeys(urls))


def parse(venue, fx, pages, window, today) -> Optional[List[RawEvent]]:
    for url in _candidate_urls(venue, pages):
        body = fx.text(url, accept="text/calendar,*/*")
        if body and "BEGIN:VCALENDAR" in body:
            fx.dump(f"{venue.id}.ics", body[:400000])
            events = parse_ics(body)
            if events:
                return events
    return None
