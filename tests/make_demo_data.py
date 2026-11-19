"""Build a demo events.js from the test fixtures (fake coordinates!) - only for checking the map UI in the sandbox.

    python3 -m tests.make_demo_data /tmp/ui/web/data
"""
import json
import sys
from datetime import date
from pathlib import Path

from te.models import Venue, Window
from te.pipeline import build, write
from tests.fakes import FakeFx, FakeGeocoder, read
from te.venues import BY_ID, SHORT
from tests.test_pipeline import make, _washu_fx

TODAY = date(2026, 11, 19)
WINDOW = Window(TODAY, date(2026, 12, 17))


def main(out: Path):
    venues, fx = make()
    venues += [
        Venue("golden-record", "The Golden Record", "https://thegoldenrecord.live/events/",
              address="2720 Cherokee St, St. Louis, MO 63118", parsers=("links",), link_pattern=r"/event/[^/]+",
              exclude_pattern=r"etix\.com"),
        Venue("new-music-circle", "New Music Circle", "https://newmusiccircle.org/category/upcoming-events/",
              multi_site=True, parsers=("links",), link_pattern=r"newmusiccircle\.org/20\d{2}/\d{2}/\d{2}/[^/]+",
              detail_only=True),
        Venue("luminary", "The Luminary", "https://theluminaryarts.com/public-programs",
              address="2701 Cherokee St, St. Louis, MO 63118", parsers=("squarespace",)),
    ]
    fx.texts.update({
        "https://thegoldenrecord.live/events/": read("golden_record.html"),
        "https://newmusiccircle.org/category/upcoming-events/": read("nmc_list.html"),
        "https://newmusiccircle.org/2026/07/05/pedestrian-deposit/": read("nmc_pedestrian.html"),
        "https://newmusiccircle.org/2026/10/01/winter-solstice-set/": read("nmc_solstice.html"),
    })
    venues += [BY_ID["washu-music"], BY_ID["counterpublic"]]
    fx.texts.update(_washu_fx().texts)
    fx.texts[BY_ID["counterpublic"].url] = read("counterpublic_events.html")
    fx.jsons["https://theluminaryarts.com/public-programs?format=json"] = json.loads(read("squarespace_blog.json"))
    for v in venues:
        v.short = v.short or SHORT.get(v.id, v.name)
    data = build(venues, fx, WINDOW, TODAY, FakeGeocoder(), log=print)
    write(data, out)
    print(len(data["events"]), "events ->", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
