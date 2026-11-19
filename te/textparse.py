"""Pull dates and times out of free text (US conventions).

Every venue writes dates differently ("Fri, Nov 20, 2026", "Nov. 19 – Jan. 3",
"Saturday, December 12th, 2026 | 7pm Doors / 8pm Show", "5:00–8:00 pm" ...), so the
scrapers lean on these helpers instead of per-site regexes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

try:  # zoneinfo ships with Python 3.9+
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover
    LOCAL_TZ = None

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_MONTH = (r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
          r"Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
_WD = r"(?:\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?,?\s+)?"

_MDY = re.compile(_WD + r"\b" + _MONTH + r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:\s*,?\s*(\d{4})\b)?", re.I)
_DMY = re.compile(_WD + r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r"\b\.?(?:,?\s*(\d{4})\b)?", re.I)
_ISO = re.compile(r"(?<![\d-])(20\d{2})-(\d{2})-(\d{2})(?!\d)")
_NUM = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])")


@dataclass
class DateHit:
    date: date
    start: int
    end: int
    has_year: bool
    has_weekday: bool


def _resolve_year(month: int, day: int, ref: date, weekday: Optional[int]) -> Optional[date]:
    """Year-less date -> a concrete date near `ref` (a few weeks back .. ~11 months ahead)."""
    candidates = []
    for y in (ref.year - 1, ref.year, ref.year + 1):
        try:
            candidates.append(date(y, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    if weekday is not None:  # "Fri, Nov 20" pins the year
        match = [c for c in candidates if c.weekday() == weekday]
        if match:
            return min(match, key=lambda c: abs((c - ref).days))
    floor = ref - timedelta(days=45)
    for c in candidates:
        if c >= floor:
            return c
    return candidates[-1]


def find_dates(text: str, ref: Optional[date] = None) -> List[DateHit]:
    ref = ref or date.today()
    hits: List[DateHit] = []

    def add(d: Optional[date], m, has_year: bool, wd_token: Optional[str]):
        if d:
            hits.append(DateHit(d, m.start(), m.end(), has_year, bool(wd_token)))

    for m in _MDY.finditer(text):
        wd, mon, day, year = m.groups()
        mi, di = MONTHS[mon[:3].lower()], int(day)
        wdi = WEEKDAYS.get(wd[:3].lower()) if wd else None
        if year:
            try:
                add(date(int(year), mi, di), m, True, wd)
            except ValueError:
                pass
        else:
            add(_resolve_year(mi, di, ref, wdi), m, False, wd)
    if not hits:  # day-first ("20 Nov 2026"), only as a fallback
        for m in _DMY.finditer(text):
            wd, day, mon, year = m.groups()
            mi, di = MONTHS[mon[:3].lower()], int(day)
            wdi = WEEKDAYS.get(wd[:3].lower()) if wd else None
            if year:
                try:
                    add(date(int(year), mi, di), m, True, wd)
                except ValueError:
                    pass
            else:
                add(_resolve_year(mi, di, ref, wdi), m, False, wd)
    for m in _ISO.finditer(text):
        try:
            add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))), m, True, None)
        except ValueError:
            pass
    for m in _NUM.finditer(text):
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            add(date(y, mo, d), m, True, None)
        except ValueError:
            pass
    hits.sort(key=lambda h: h.start)
    return hits


def best_date(hits: List[DateHit]) -> Optional[DateHit]:
    """The date most likely to be 'the' event date: prefer one written with a weekday."""
    if not hits:
        return None
    for h in hits:
        if h.has_weekday:
            return h
    return hits[0]


def _with_year(d: date, year: int) -> date:
    try:
        return d.replace(year=year)
    except ValueError:  # Feb 29
        return d


def date_range(text: str, ref: Optional[date] = None):
    """-> (start_date, end_date_or_None, has_explicit_range) from text like 'Nov 19, 2026 to Jan 3, 2027'.

    A year written only once ('Sep 26 - Dec 12, 2026') applies to the whole run, and a run written with no year at all
    ('Sep 26 - Dec 12') is read as the one that is under way or next to start - not as next year's.
    """
    ref = ref or date.today()
    hits = find_dates(text, ref)
    first = best_date(hits)
    if not first:
        return None, None, False
    idx = hits.index(first)
    if idx + 1 < len(hits):
        nxt = hits[idx + 1]
        between = text[first.end:nxt.start].strip().lower()
        if re.fullmatch(r"(to|through|thru|until|till|-|–|—|-\s*|–\s*)", between):
            start, end = first.date, nxt.date
            if not first.has_year and not first.has_weekday:
                if nxt.has_year:
                    start = _with_year(start, end.year)
                    if start > end:
                        start = _with_year(start, end.year - 1)
                else:
                    for y in (ref.year - 1, ref.year, ref.year + 1):
                        s2 = _with_year(start, y)
                        e2 = _with_year(end, y if (end.month, end.day) >= (s2.month, s2.day) else y + 1)
                        if e2 >= ref:
                            start, end = s2, e2
                            break
                return start, end, True
            if not nxt.has_year and end < start:
                end = _with_year(end, end.year + 1)
            return start, end, True
    return first.date, None, False


# ----------------------------------------------------------------------------- times

_T = r"(\d{1,2})(?::(\d{2}))?"
_MER = r"(a\.?m\.?|p\.?m\.?)"
_RANGE = re.compile(rf"(?<![\d:/.-]){_T}\s*(?:{_MER})?\s*(?:-|–|—|to|until)\s*{_T}\s*{_MER}(?![A-Za-z])", re.I)
_SINGLE = re.compile(rf"(?<![\d:/.-]){_T}\s*{_MER}(?![A-Za-z])", re.I)
_H24 = re.compile(r"(?<![\d:/.-])(1[3-9]|2[0-3]):([0-5]\d)(?![\d:])(?!\s*[ap]\.?m)")
_NOON = re.compile(r"\bnoon\b", re.I)
_AFTER_MONTH = re.compile(_MONTH + r"\.?\s*$", re.I)


@dataclass
class TimeInfo:
    start: Optional[time] = None
    end: Optional[time] = None
    doors: Optional[time] = None
    all_day: bool = False


def _mk(hour: int, minute: Optional[str], mer: Optional[str]) -> Optional[time]:
    m = int(minute) if minute else 0
    if m > 59 or hour > 23:
        return None
    if mer:
        if not 1 <= hour <= 12:
            return None
        is_pm = mer.lower().startswith("p")
        hour = hour % 12 + (12 if is_pm else 0)
    return time(hour, m)


def extract_times(text: str) -> TimeInfo:
    toks = []  # (index, end_index, time, end_time)
    spans = []
    for m in _RANGE.finditer(text):
        h1, m1, mer1, h2, m2, mer2 = m.groups()
        if _AFTER_MONTH.search(text[max(0, m.start() - 12):m.start()]):
            continue
        t2 = _mk(int(h2), m2, mer2)
        if not t2:
            continue
        t1 = _mk(int(h1), m1, mer1 or mer2)
        if t1 and not mer1 and t1 > t2:  # "10-1 pm" -> 10 am, not 10 pm
            t1 = _mk(int(h1), m1, "am" if mer2.lower().startswith("p") else "pm")
        if t1:
            toks.append((m.start(), m.end(), t1, t2))
            spans.append((m.start(), m.end()))
    inside = lambda i: any(a <= i < b for a, b in spans)  # noqa: E731
    for m in _SINGLE.finditer(text):
        if inside(m.start()) or _AFTER_MONTH.search(text[max(0, m.start() - 12):m.start()]):
            continue
        t = _mk(int(m.group(1)), m.group(2), m.group(3))
        if t:
            toks.append((m.start(), m.end(), t, None))
    for m in _H24.finditer(text):
        if not inside(m.start()):
            toks.append((m.start(), m.end(), time(int(m.group(1)), int(m.group(2))), None))
    for m in _NOON.finditer(text):
        if not inside(m.start()):
            toks.append((m.start(), m.end(), time(12, 0), None))
    toks.sort(key=lambda t: t[0])

    info = TimeInfo()
    if not toks:
        info.all_day = bool(re.search(r"all[\s-]?day", text, re.I))
        return info

    def label(tok):
        """'Doors 7 pm / Show 8 pm' and '7pm Doors / 8pm Show' both work: a label written before the time wins,
        otherwise the word right after it (only whitespace between) is the label."""
        before = text[max(0, tok[0] - 14):tok[0]].lower()
        after = text[tok[1]:tok[1] + 12].lower().lstrip(" ")
        if re.search(r"doors?[\s:@-]*(open[\s:@-]*)?(at[\s:@-]*)?$", before):
            return True, False
        if re.search(r"(show|starts?|begins?|curtain|perform\w*)[\s:@-]*(at[\s:@-]*)?$", before):
            return False, True
        return after.startswith(("doors", "door ")), after.startswith(("show", "start", "curtain"))

    labelled = [(t, *label(t)) for t in toks]
    start_tok = next((t for t, d, s in labelled if s), None) \
        or next((t for t, d, s in labelled if not d), None) \
        or toks[0]
    info.start, info.end = start_tok[2], start_tok[3]
    door_tok = next((t for t, d, s in labelled if d and t is not start_tok), None)
    if door_tok:
        info.doors = door_tok[2]
    return info


# ----------------------------------------------------------------------------- ISO / tz

def to_local(dt: datetime) -> datetime:
    """tz-aware -> naive St. Louis local time; naive stays as is."""
    if dt.tzinfo is None or LOCAL_TZ is None:
        return dt.replace(tzinfo=None)
    return dt.astimezone(LOCAL_TZ).replace(tzinfo=None)


def parse_iso(value: str) -> Optional[datetime]:
    """Lenient ISO-8601 -> naive local datetime (date-only becomes midnight)."""
    if not value:
        return None
    s = value.strip()
    s = re.sub(r"Z$", "+00:00", s)
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    s = re.sub(r"\.(\d{1,5})(?=[+-]|$)", lambda m: "." + m.group(1).ljust(6, "0"), s)
    s = s.replace(" ", "T", 1) if re.match(r"\d{4}-\d{2}-\d{2} \d", s) else s
    try:
        return to_local(datetime.fromisoformat(s))
    except ValueError:
        return None


def from_epoch_ms(ms) -> Optional[datetime]:
    try:
        return to_local(datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc))
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()
