"""Last resort for calendars whose events are plain text under date headings, with no per-event links.

    Thu, Nov 19, 2026          <- date heading
    The Apartment (35MM)       <- title
    7:00 PM                    <- optional time line

Only enabled for venues that list it in `parsers`, because on the wrong page it can mistake menu text for titles.
The event's link falls back to the calendar page itself.
"""
from __future__ import annotations

import re
from datetime import datetime, time
from typing import List, Optional

from bs4 import BeautifulSoup

from ..models import RawEvent
from ..textparse import best_date, clean, extract_times, find_dates
from .links import GENERIC_TITLE, is_datetime_only

API_KIND = False

STOP = re.compile(r"©|all rights reserved|privacy policy|subscribe|newsletter|follow us|sign up for", re.I)
MENU = re.compile(r"^(home|about( us)?|contact( us)?|menu|showtimes?|calendar|events?|donate|visit|gift cards?|"
                  r"membership|rentals?|faq|search|log ?in|cart|press|jobs|merch|shop|now playing|coming soon|"
                  r"today|next|prev(ious)?|month|week|day|list|grid|filters?|all|more)\W*$", re.I)


def parse(venue, fx, pages, window, today) -> Optional[List[RawEvent]]:
    out: List[RawEvent] = []
    seen = set()
    for html in pages:
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style", "noscript", "template", "nav", "header", "footer", "svg", "button", "select"]):
            t.decompose()
        lines = [clean(x) for x in soup.get_text("\n").split("\n")]
        lines = [x for x in lines if x]
        day = None
        last: Optional[RawEvent] = None
        for line in lines:
            if STOP.search(line) and day:
                break
            hits = find_dates(line, today)
            if hits and is_datetime_only(line, today):
                day = best_date(hits).date
                last = None
                continue
            if day is None:
                continue
            ti = extract_times(line)
            if ti.start and is_datetime_only(line, today):
                if last is not None and not last.has_time:
                    last.start = datetime.combine(last.start.date(), ti.start)
                    last.has_time = True
                continue
            if not (3 <= len(line) <= 100) or GENERIC_TITLE.match(line) or MENU.match(line) or hits:
                continue
            key = (line.lower(), day)
            if key in seen:
                continue
            seen.add(key)
            last = RawEvent(title=line, start=datetime.combine(day, time(0, 0)), has_time=False,
                            url=venue.url, confidence="text")
            out.append(last)
    return out or None
