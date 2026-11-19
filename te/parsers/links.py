"""Generic extractor for ordinary HTML calendars.

Instead of per-site CSS selectors it works from the one thing every calendar has - a link to each event's page:

  1. find every <a> whose href matches the venue's `link_pattern`;
  2. climb from the link to the smallest surrounding "card" that contains a date but only ONE distinct event link;
  3. read title / date / time / place out of that card;
  4. if the card shows no date, try (a) a date in the URL, (b) the nearest date heading above it ("Friday, Nov 20"),
     (c) opening the event page itself (`follow_detail`).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup, Tag

from ..models import RawEvent
from ..places import extract_address
from ..textparse import best_date, clean, date_range, extract_times, find_dates, parse_iso
from . import jsonld

API_KIND = False
MAX_DETAIL = 40
NOTES: List[str] = []   # short diagnostics; te.pipeline copies them onto the venue and clears the list

GENERIC_TITLE = re.compile(
    r"^(buy |get |purchase )?(tickets?|info|more( info(rmation)?)?|read more|learn more|details|view( details| event)?|"
    r"see more|register( now)?|rsvp|sold out|add to calendar|google calendar|ical|\+ ?calendar|free|download|apply|"
    r"find out more|event details?)\W*$", re.I)
CHROME_CLASS = re.compile(r"(^|[-_ ])(nav|navbar|navigation|menu|footer|breadcrumbs?)([-_ ]|$)", re.I)
URL_DATE = re.compile(r"/(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:/|$|\?)")
HEADING = re.compile(r"^h[1-6]$")
# <time> / text that is a *post's* date (byline, "updated", blog date) rather than the event's date
PUBLISH_CLS = re.compile(r"(^|[-_ ])(posted-on|entry-date|post-date|blog-date|byline|entry-meta|post-meta|published|updated|author)([-_ ]|$)", re.I)
GENERIC_LINK_NAME = re.compile(r"^(map|directions|get directions|view map|google maps?|apple maps?|more|details)\W*$", re.I)


def _event_time_tag(scope: Tag):
    for t in scope.find_all("time", attrs={"datetime": True}):
        chain = [t] + list(t.parents)[:3]
        cls = " ".join(" ".join(c.get("class") or []) for c in chain if isinstance(c, Tag))
        if not PUBLISH_CLS.search(cls):
            return t
    return None


def _strip_datetime(text: str, ref: date) -> str:
    t = text
    for h in reversed(find_dates(t, ref)):
        t = t[:h.start] + " " + t[h.end:]
    t = re.sub(r"\b\d{1,2}(:\d{2})?\s*(a\.?m\.?|p\.?m\.?)\b", " ", t, flags=re.I)
    t = re.sub(r"\b(mon|tues?|wed(nes)?|thu(rs?)?|fri|sat(ur)?|sun)(day)?\b\.?", " ", t, flags=re.I)
    t = re.sub(r"\b(to|doors?|show|at|from|and|all|day|noon)\b", " ", t, flags=re.I)
    return clean(re.sub(r"[\W_]+", " ", t))


def is_datetime_only(text: str, ref: date) -> bool:
    return len(_strip_datetime(text, ref)) <= 2


def _in_chrome(tag: Tag) -> bool:
    for p in [tag] + list(tag.parents):
        if not isinstance(p, Tag) or p.name in ("body", "html", "[document]"):
            continue
        if p.name in ("nav", "footer"):
            return True
        cls = " ".join(p.get("class") or []) + " " + (p.get("id") or "")
        if CHROME_CLASS.search(cls) or p.get("role") == "navigation":
            return True
    return False


def _norm(base: str, href: str) -> str:
    if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return ""
    return urldefrag(urljoin(base, href.strip()))[0]


def _header_dates(soup: BeautifulSoup, ref: date) -> Dict[int, Optional[date]]:
    """id(<a>) -> date of the nearest preceding date-only heading (for 'day group' layouts)."""
    current: Optional[date] = None
    out: Dict[int, Optional[date]] = {}
    for el in soup.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name == "a" and el.get("href"):
            out[id(el)] = current
            continue
        cls = " ".join(el.get("class") or [])
        if HEADING.match(el.name) or el.name in ("time", "th", "dt", "caption", "legend") or re.search(r"date|day|dow", cls, re.I):
            txt = clean(el.get_text(" "))
            if 0 < len(txt) <= 60:
                hit = best_date(find_dates(txt, ref))
                if hit and is_datetime_only(txt, ref):
                    current = hit.date
    return out


def _pick_title(card: Tag, anchors: List[Tag], ref: date) -> str:
    def ok(t: str, maxlen: int = 160) -> bool:
        return 2 <= len(t) <= maxlen and not GENERIC_TITLE.match(t) and not is_datetime_only(t, ref) and not find_dates(t, ref)

    for a in anchors:
        t = clean(a.get_text(" "))
        if ok(t, 110):
            return t
    for h in card.find_all(HEADING):
        t = clean(h.get_text(" "))
        if ok(t, 200):
            return t
    for a in anchors:
        for cand in (a.get("title"), (a.find("img") or {}).get("alt") if a.find("img") else None, a.get("aria-label")):
            t = clean(cand or "")
            if ok(t):
                return t
    el = card.find(class_=re.compile(r"title|name|heading", re.I))
    if el:
        t = clean(el.get_text(" "))
        if ok(t, 200):
            return t
    for line in card.get_text("\n").split("\n"):
        t = clean(line)
        if ok(t, 120):
            return t
    return ""


def _pick_location(card: Tag, ref: date) -> str:
    el = card.find(class_=re.compile(r"venue|location|where|address|place\b", re.I))
    if el:
        t = clean(el.get_text(" "))
        if 2 <= len(t) <= 120 and not is_datetime_only(t, ref):
            return t
    return ""


def _when(card: Tag, url: str, ref: date, header_date: Optional[date]):
    """-> (start datetime, end datetime|None, has_time, doors, all_day) or None"""
    text = clean(card.get_text(" "))
    iso = None
    tt = _event_time_tag(card)
    if tt:
        iso = parse_iso(tt["datetime"])
    d1, d2, ranged = date_range(text, ref)
    day = (iso.date() if iso else None) or d1
    until = None
    if d1 and not ranged and not iso:  # "Through Jan 31, 2027": an exhibition that's already open
        h = best_date(find_dates(text, ref))
        if h and re.search(r"(through|until|thru|closes?|ends?|closing)\W*(on\W*)?$", text[max(0, h.start - 14):h.start], re.I):
            day, until, ranged, d2 = ref, h.date, True, h.date
    if not day:
        m = URL_DATE.search(url)
        if m:
            try:
                day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                day = None
    if not day:
        day = header_date
    if not day:
        return None

    scope = text
    hits = find_dates(text, ref)
    if len(hits) > 1:  # several dates in one card: read the time next to the one we chose
        h = best_date(hits)
        scope = text[max(0, h.start - 60): h.end + 160]
    ti = extract_times(scope)
    start_t = ti.start
    if iso and tt and "T" in tt["datetime"] and iso.time() != time(0, 0):
        start_t = iso.time()
    start = datetime.combine(day, start_t or time(0, 0))
    end = None
    if ranged and d2 and d2 > day:
        end = datetime.combine(d2, ti.end or time(23, 59))
    elif ti.end and start_t:
        end = datetime.combine(day, ti.end)
        if end <= start:
            end = None
    return start, end, bool(start_t), ti.doors, bool(ti.all_day and not start_t)


def extract_cards(html: str, venue, pat, ex, ref: date, reads: Optional[dict] = None,
                  stats: Optional[dict] = None) -> Tuple[List[RawEvent], Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "template"]):
        t.decompose()
    base = venue.url
    self_url = _norm(base, base).rstrip("/")

    href_of: Dict[int, str] = {}
    by_href: Dict[str, List[Tag]] = {}
    for a in soup.find_all("a", href=True):
        h = _norm(base, a["href"])
        if not h or h.rstrip("/") == self_url:
            continue
        if pat and not pat.search(h):
            continue
        if ex and ex.search(h):
            continue
        if stats is not None:
            stats["matched"] = stats.get("matched", 0) + 1
        if _in_chrome(a):
            if stats is not None:
                stats["chrome"] = stats.get("chrome", 0) + 1
            continue
        href_of[id(a)] = h
        by_href.setdefault(h, []).append(a)

    headers = _header_dates(soup, ref)

    def distinct_hrefs(node: Tag) -> set:
        return {href_of[id(a)] for a in node.find_all("a", href=True) if id(a) in href_of}

    events: List[RawEvent] = []
    pending: Dict[str, str] = {}
    seen = set()
    for a in [x for x in soup.find_all("a", href=True) if id(x) in href_of]:
        href = href_of[id(a)]
        node, card, dated = a, None, False
        for _ in range(8):
            parent = node.parent
            if not isinstance(parent, Tag) or parent.name in ("body", "html", "[document]"):
                break
            if len(distinct_hrefs(parent)) > 1:
                break
            node = parent
            card = node
            if find_dates(clean(node.get_text(" ")), ref) or node.find("time", attrs={"datetime": True}):
                dated = True
                break
        card = card or a
        in_card = [x for x in card.find_all("a", href=True) if href_of.get(id(x)) == href] or [a]
        title = _pick_title(card, in_card, ref)
        if not title:
            continue
        if venue.detail_only:
            pending.setdefault(href, title)
            if reads is not None and href not in reads:   # whole entry on the list page: backup if the event page can't be read
                big = a
                for _ in range(10):
                    up = big.parent
                    if not isinstance(up, Tag) or up.name in ("body", "html", "[document]") or len(distinct_hrefs(up)) > 1:
                        break
                    big = up
                reads[href] = big
            continue
        when = _when(card, href, ref, headers.get(id(a)))
        if not when:
            pending.setdefault(href, title)
            continue
        start, end, has_time, doors, all_day = when
        key = (href, start)
        if key in seen:
            continue
        seen.add(key)
        events.append(RawEvent(
            title=title, start=start, end=end, has_time=has_time, doors=doors, all_day=all_day, url=href,
            location_name=_pick_location(card, ref), context=clean(card.get_text(" "))[:500], confidence="card"))
    done = {e.url for e in events}
    return events, {h: t for h, t in pending.items() if h not in done}


def _name_before(text: str, idx: int) -> str:
    seg = text[max(0, idx - 70): idx]
    m = re.search(r"(?:^|[|•·@\n]|\bat\b|\bVenue:|\bLocation:|\bWhere:)\s*([A-Z0-9][^|•·@\n,()]{2,40}?)\s*[,(]\s*$", seg)
    return clean(m.group(1)) if m else ""


def _venue_name(scope: Tag, addr: str) -> str:
    """Name of the place, taken from the link sitting beside the address (e.g. '<a>Off Broadway</a> ( 3509 Lemp Ave ... )')."""
    core = clean(addr.split(",")[0])
    if not core:
        return ""
    holders = [t for t in scope.find_all(True) if core in clean(t.get_text(" "))]
    if not holders:
        return ""
    holder = min(holders, key=lambda t: len(t.get_text(" ")))
    for a in holder.find_all("a"):
        name = clean(a.get_text(" "))
        if 3 <= len(name) <= 60 and not GENERIC_LINK_NAME.match(name):
            return name
    return ""


def _read_scope(scope: Tag, url: str, fallback_title: str, ref: date) -> Optional[RawEvent]:
    for t in scope.find_all(class_=PUBLISH_CLS):   # bylines / "updated" dates are not the event date
        t.decompose()
    text = clean(scope.get_text(" "))[:6000]
    hits = find_dates(text, ref)
    weekday_hit = next((h for h in hits if h.has_weekday), None)
    tt = _event_time_tag(scope)
    iso = parse_iso(tt["datetime"]) if tt else None
    if weekday_hit:          # "Saturday, December 12th, 2026" beats everything else on the page
        day, hit = weekday_hit.date, weekday_hit
    elif iso:
        day, hit = iso.date(), None
    elif hits:
        day, hit = hits[0].date, hits[0]
    else:
        return None
    scope_text = text[max(0, hit.start - 60): hit.end + 200] if hit else text[:400]
    ti = extract_times(scope_text)
    start_t = ti.start or (iso.time() if iso and iso.date() == day and iso.time() != time(0, 0) else None)
    addr = extract_address(text)
    name = _venue_name(scope, addr) if addr else ""
    if addr and not name:
        m = re.search(re.escape(addr[:12]), text)
        name = _name_before(text, m.start()) if m else ""
    title = fallback_title
    if not title:
        h1 = scope.find("h1")
        title = clean(h1.get_text(" ")) if h1 else ""
    if not title:
        return None
    end = datetime.combine(day, ti.end) if ti.end and start_t else None
    if end and end <= datetime.combine(day, start_t):
        end = None
    return RawEvent(title=title, start=datetime.combine(day, start_t or time(0, 0)), end=end, has_time=bool(start_t),
                    doors=ti.doors, url=url, location_name=name, address=addr, confidence="text",
                    context=text[:500])


def detail_event(html: str, url: str, fallback_title: str, ref: date) -> Optional[RawEvent]:
    """Read one event page: JSON-LD if present, otherwise the event's dated line in the page text."""
    ld = [e for e in jsonld.events_from_html(html, url) if e.start]
    if ld:
        e = ld[0]
        e.url = e.url or url
        e.title = e.title or fallback_title
        return e
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "template", "nav", "footer"]):
        t.decompose()   # NOT <header>: many themes put the event's date line inside the post's own <header>
    seen = set()
    for scope in (soup.find("article"), soup.find("main"), soup.body):
        if scope is None or id(scope) in seen:
            continue
        seen.add(id(scope))
        ev = _read_scope(scope, url, fallback_title, ref)
        if ev:
            return ev
    return None


def parse(venue, fx, pages, window, today) -> Optional[List[RawEvent]]:
    if not venue.link_pattern:
        return None
    pat = re.compile(venue.link_pattern)
    ex = re.compile(venue.exclude_pattern) if venue.exclude_pattern else None
    out: List[RawEvent] = []
    pending: Dict[str, str] = {}
    reads: dict = {}
    stats: dict = {}
    for html in pages:
        evs, pend = extract_cards(html, venue, pat, ex, today, reads, stats)
        out.extend(evs)
        pending.update(pend)
    if not stats.get("matched"):
        NOTES.append("no link on the calendar page matched this venue's event-link pattern")
    elif stats.get("chrome") == stats.get("matched"):
        NOTES.append(f"all {stats['matched']} matching links sit inside menus/footers, so none were used")
    if venue.follow_detail or venue.detail_only:
        todo = list(pending.items())[:MAX_DETAIL]
        got_page = from_page = from_list = 0
        bad = []
        for href, title in todo:
            body = fx.text(href)
            ev = None
            if body:
                got_page += 1
                fx.dump(f"{venue.id}-detail-{len(out)}.html", body[:300000])
                ev = detail_event(body, href, title, today)
                if ev:
                    from_page += 1
            else:
                bad.append(getattr(fx, "status", {}).get(href, "no answer"))
            if ev is None and venue.detail_only and href in reads:
                ev = _read_scope(reads[href], href, title, today)
                if ev:
                    from_list += 1
            if ev:
                out.append(ev)
        if todo:
            msg = f"{len(todo)} event pages: {got_page} downloaded, dates read from {from_page} of them"
            if from_list:
                msg += f" and for {from_list} more from the calendar list"
            if bad:
                msg += f"; could not download {len(bad)} (e.g. {bad[0]})"
            NOTES.append(msg)
    seen, dedup = set(), []
    for e in out:
        key = (e.url, e.start)
        if key not in seen:
            seen.add(key)
            dedup.append(e)
    return dedup or None


# ----------------------------------------------------------------------------- listings that only supply page URLs

def hrefs_matching(html: str, venue) -> set:
    """Event-page URLs linked from one listing page (used to tell when a '?page=N' page brings nothing new)."""
    if not venue.link_pattern:
        return set()
    pat = re.compile(venue.link_pattern)
    ex = re.compile(venue.exclude_pattern) if venue.exclude_pattern else None
    out = set()
    for m in re.finditer(r"""href=["']([^"']+)["']""", html or "", re.I):
        h = _norm(venue.url, m.group(1).replace("&amp;", "&"))
        if h and pat.search(h) and not (ex and ex.search(h)) and h.rstrip("/") != venue.url.rstrip("/"):
            out.add(h)
    return out


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]


def listing_links(pages: List[str], venue) -> List[Tuple[str, str]]:
    """[(link text, url)] for every event-page link on the listing pages."""
    pat = re.compile(venue.link_pattern)
    ex = re.compile(venue.exclude_pattern) if venue.exclude_pattern else None
    out: List[Tuple[str, str]] = []
    for html in pages:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            h = _norm(venue.url, a["href"])
            if not h or not pat.search(h) or (ex and ex.search(h)) or h.rstrip("/") == venue.url.rstrip("/") or _in_chrome(a):
                continue
            text = clean(a.get_text(" ")) or clean(a.get("title") or a.get("aria-label") or "")
            out.append((text, h))
    return out


def match_url(title: str, day: date, cands: List[Tuple[str, str]]) -> str:
    """Find the listing link for an event known only by title + date: by the link's text, else by the URL's slug."""
    tw = _words(title)
    if not tw:
        return ""
    t = " ".join(tw)
    hits = [h for text, h in cands if t in " ".join(_words(text))]
    if not hits:
        tset = set(tw)
        for text, h in cands:
            slug = [w for w in _words(urldefrag(h)[0].rstrip("/").rsplit("/", 1)[-1]) if not w.isdigit()]
            if len(set(slug)) >= 2 and set(slug) <= tset and len(set(slug)) / len(tset) >= 0.6:
                hits.append(h)
    hits = list(dict.fromkeys(hits))
    if len(hits) > 1:   # same title on several dates: take the link whose text carries this date ("8 December")
        mon = _MONTHS[day.month - 1]
        for text, h in cands:
            if h in hits and re.search(rf"\b{day.day}\s+{mon[:3]}|\b{mon[:3]}\w*\.?\s+{day.day}\b", text.lower()):
                return h
    return hits[0] if hits else ""
