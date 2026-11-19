from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import List, Optional


@dataclass
class Window:
    start: date
    end: date  # inclusive

    def overlaps(self, first: date, last: date) -> bool:
        return first <= self.end and last >= self.start


@dataclass
class Venue:
    id: str
    name: str
    url: str
    address: str = ""            # where events happen unless the event says otherwise
    approx: bool = False         # True when that default is only a stand-in (multi-venue organisations)
    multi_site: bool = False     # events happen at several places: look for known place names in each listing
    parsers: tuple = ("jsonld", "links")
    render: str = "auto"         # "static" | "browser" | "auto" (static first, browser if that finds nothing)
    link_pattern: str = ""       # regex: which hrefs are event pages
    exclude_pattern: str = ""
    follow_detail: bool = False  # fetch each event page when the listing doesn't show a date
    detail_only: bool = False    # never trust dates on the listing (e.g. blog posts): always read the event page
    tribe_base: str = ""         # origin of a WordPress "The Events Calendar" install, if not the calendar's own
    paginate: bool = False       # calendar is a month grid: also click "next month" when the window crosses months
    priority: int = 1            # lower wins when two sources list the same event
    note: str = ""
    short: str = ""              # short label for the map's organization filter
    ics_url: str = ""            # the calendar's own .ics feed, when the listing page doesn't link to it
    list_pages: int = 1          # listing is paged with ?page=N ("Load more"): read up to this many pages
    page_param: str = "page"
    match_links: bool = False    # feed events have no page URLs: take them from the listing page, matched by title


@dataclass
class RawEvent:
    title: str
    start: datetime               # naive, St. Louis local time
    end: Optional[datetime] = None
    all_day: bool = False
    has_time: bool = True
    doors: Optional[time] = None
    url: str = ""
    location_name: str = ""
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    context: str = ""             # nearby page text, used to recognise known place names
    confidence: str = "structured"  # structured | card | text

    @property
    def first_day(self) -> date:
        return self.start.date()

    @property
    def last_day(self) -> date:
        if not self.end or self.end <= self.start:
            return self.start.date()
        end = self.end - timedelta(minutes=1) if self.end.time() == time(0, 0) else self.end
        return max(end.date(), self.start.date())
