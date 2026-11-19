"""Shows what the scraper sees for ONE venue, so a wrong or empty result can be traced.

    bash run.sh diagnose new-music-circle

Prints a short report (also saved to debug/diagnose-<venue>.txt). Paste it back if a calendar still comes up empty.
"""
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from te.fetch import Fetcher  # noqa: E402
from te.parsers import links  # noqa: E402
from te.places import extract_address  # noqa: E402
from te.textparse import clean, find_dates  # noqa: E402
from te.venues import BY_ID  # noqa: E402


def main(argv):
    if not argv or argv[0] not in BY_ID:
        print("usage: bash run.sh diagnose <venue-id>\nvenue ids: " + ", ".join(BY_ID))
        return 2
    v = BY_ID[argv[0]]
    today = date.today()
    out = []

    def say(*a):
        line = " ".join(str(x) for x in a)
        out.append(line)
        print(line)

    fx = Fetcher(debug_dir=ROOT / "debug", log=lambda *_: None)
    say(f"venue: {v.id}   page: {v.url}   today: {today}")
    html = fx.text(v.url)
    say(f"calendar page: {'downloaded, %d characters' % len(html) if html else 'NOT downloaded (' + str(fx.status.get(v.url)) + ')'}")
    if not html:
        return 1
    if v.link_pattern:
        stats, reads = {}, {}
        evs, pend = links.extract_cards(html, v, re.compile(v.link_pattern),
                                        re.compile(v.exclude_pattern) if v.exclude_pattern else None, today, reads, stats)
        say(f"links matching the event pattern: {stats.get('matched', 0)}  (inside menus/footers: {stats.get('chrome', 0)})")
        say(f"events read straight from the list page: {len(evs)};  pages that need opening: {len(pend)}")
        for href, title in list(pend.items())[:3]:
            say(f"\n--- {title}\n    {href}")
            card = reads.get(href)
            if card is not None:
                say("    list-page text:", clean(card.get_text(" "))[:260])
            body = fx.text(href)
            say("    event page:", f"downloaded, {len(body)} characters" if body else f"NOT downloaded ({fx.status.get(href)})")
            if body:
                text = clean(re.sub(r"<(script|style)[\s\S]*?</\1>", " ", body))
                text = clean(re.sub(r"<[^>]+>", " ", text))
                for h in find_dates(text, today)[:6]:
                    say(f"    date in text: {h.date}  weekday={h.has_weekday}  «{text[max(0, h.start - 25):h.end + 40]}»")
                say("    address in text:", extract_address(text) or "(none)")
                ev = links.detail_event(body, href, title, today)
                say("    -> read as:", f"{ev.title!r} on {ev.start} at {ev.location_name!r} {ev.address!r}" if ev else "NOTHING")
    else:
        say("(this venue has no link pattern; see debug/ for the fetched files)")
    Path(ROOT / "debug").mkdir(exist_ok=True)
    (ROOT / "debug" / f"diagnose-{v.id}.txt").write_text("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
