"""Parser tests run on small fixtures shaped like each platform's real output (the sandbox this was built in cannot
reach the venue sites, so these are modelled on pages read through another route - not saved copies of them)."""
import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

from te.models import Venue, Window
from te.parsers import ics, jsonld, links, squarespace, textblocks, tribe, wix

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 19)
WINDOW = Window(TODAY, date(2026, 12, 3))


def read(name):
    return (FIX / name).read_text()


class FakeFx:
    def __init__(self, texts=None, jsons=None):
        self.texts, self.jsons = texts or {}, jsons or {}

    def text(self, url, **kw):
        return self.texts.get(url)

    def json(self, url, params=None):
        return self.jsons.get(url)

    def dump(self, *a, **k):
        pass


def titles(evs):
    return sorted(e.title for e in evs)


# ----------------------------------------------------------------------------- links (generic HTML)

def test_golden_record_cards_are_deduped_and_times_read():
    v = Venue("gr", "The Golden Record", "https://thegoldenrecord.live/events/", link_pattern=r"/event/[^/]+",
              exclude_pattern=r"etix\.com")
    evs = links.parse(v, FakeFx(), [read("golden_record.html")], WINDOW, TODAY)
    assert len(evs) == 3                                   # grid + list views collapse to 3
    don = next(e for e in evs if e.title.startswith("Don Trip"))
    assert don.title == "Don Trip w/ Tha Landlord (Sold Out)"
    assert don.start == datetime(2026, 11, 20, 20, 0) and don.doors == time(19, 0)
    assert don.url.endswith("/don-trip-w-tha-landlord/the-golden-record/")
    assert not any("etix" in e.url for e in evs)


def test_same_url_on_two_dates_stays_two_events_and_footer_links_ignored():
    v = Venue("slso", "SLSO", "https://slso.org/get-tickets/event-calendar/", link_pattern=r"slso\.org/event/[^/]+")
    evs = links.parse(v, FakeFx(), [read("slso.html")], WINDOW, TODAY)
    salute = [e for e in evs if e.title == "A Salute to America"]
    assert sorted(e.start for e in salute) == [datetime(2026, 11, 20, 19, 30), datetime(2026, 11, 21, 19, 30)]
    assert len(evs) == 4
    assert not any("footer-link" in e.url for e in evs)
    radiance = next(e for e in evs if "Radiance" in e.title)
    assert radiance.location_name == "The Sheldon"


def test_day_heading_layout_gets_dates_from_headings():
    v = Venue("tgp", "Tower Grove", "https://www.towergrovepark.org/calendar",
              link_pattern=r"/calendar/\d{4}/\d{1,2}/\d{1,2}/[^/]+")
    evs = links.parse(v, FakeFx(), [read("day_groups.html")], WINDOW, TODAY)
    assert len(evs) == 4
    sauce = next(e for e in evs if e.title.startswith("Sauce"))
    assert sauce.start == datetime(2026, 11, 20, 16, 0) and sauce.end == datetime(2026, 11, 20, 20, 0)


def test_new_music_circle_reads_event_page_not_post_date():
    v = Venue("nmc", "NMC", "https://newmusiccircle.org/category/upcoming-events/",
              link_pattern=r"newmusiccircle\.org/20\d{2}/\d{2}/\d{2}/[^/]+", detail_only=True)
    fx = FakeFx(texts={
        "https://newmusiccircle.org/2026/07/05/pedestrian-deposit/": read("nmc_pedestrian.html"),
        "https://newmusiccircle.org/2026/10/01/winter-solstice-set/": read("nmc_solstice.html"),
    })
    evs = links.parse(v, fx, [read("nmc_list.html")], WINDOW, TODAY)
    ped = next(e for e in evs if e.title == "Pedestrian Deposit")
    assert ped.start == datetime(2026, 12, 12, 20, 0)      # not Sept 27 / Oct 1 / "tickets on sale" dates
    assert ped.doors == time(19, 0)
    assert ped.location_name == "Off Broadway" and ped.address.startswith("3509 Lemp Ave")
    assert ped.confidence == "text"
    sol = next(e for e in evs if e.title == "Winter Solstice Set")
    assert sol.start == datetime(2026, 11, 27, 20, 0) and sol.location_name == "The Sheldon"


def test_text_blocks_fallback():
    v = Venue("hp", "Hi-Pointe", "https://hipointetheatre.org/calendar/")
    evs = textblocks.parse(v, FakeFx(), [read("hipointe_text.html")], WINDOW, TODAY)
    assert titles(evs) == sorted(["The Apartment (35MM)", "Fatherland", "Raise the Red Lantern (4K Restoration)",
                                  "The Found Footage Fest: Porcelain VHS Treasures"])
    assert next(e for e in evs if e.title == "Fatherland").start == datetime(2026, 11, 20, 17, 0)
    assert next(e for e in evs if e.title.startswith("The Found")).has_time is False
    assert not any("Contact" in e.title or "©" in e.title for e in evs)


# ----------------------------------------------------------------------------- structured sources

def test_jsonld():
    evs = jsonld.events_from_html(read("jsonld.html"), "https://example.org/")
    assert len(evs) == 2
    late = next(e for e in evs if e.title.startswith("Late"))
    assert late.title == "Late Show & Jam" and late.start == datetime(2026, 11, 21, 20, 0)
    assert late.url == "https://example.org/events/late-show"
    assert late.location_name == "The Back Room" and late.address.startswith("100 Main St")
    assert (late.lat, late.lng) == (38.63, -90.2)
    fair = next(e for e in evs if e.title == "All-day Fair")
    assert fair.all_day and not fair.has_time


def test_tribe_api():
    v = Venue("gc", "Grand Center", "https://www.grandcenter.org/calendar/")
    api = "https://www.grandcenter.org/wp-json/tribe/events/v1/events"
    fx = FakeFx(jsons={api: json.loads(read("tribe_events.json"))})
    evs = tribe.parse(v, fx, [], WINDOW, TODAY)
    assert len(evs) == 4
    jazz = next(e for e in evs if e.title.startswith("Marcus"))
    assert jazz.title == "Marcus Roberts & The Modern Jazz Generation"      # HTML entity decoded
    assert jazz.start == datetime(2026, 11, 19, 19, 30) and jazz.location_name == "Jazz St. Louis"
    assert (jazz.lat, jazz.lng) == (38.6379, -90.2305)
    web = next(e for e in evs if "Webster" in e.title)
    assert web.address == "8300 Big Bend Boulevard, Webster Groves, MO, 63119"
    ww = next(e for e in evs if e.title.startswith("Weirdly"))
    assert ww.all_day and ww.last_day == date(2027, 1, 3) and ww.location_name == ""   # empty venue list


def test_tribe_missing_returns_none_and_empty_returns_empty_list():
    v = Venue("x", "X", "https://example.org/calendar/")
    assert tribe.parse(v, FakeFx(), [], WINDOW, TODAY) is None
    api = "https://example.org/wp-json/tribe/events/v1/events"
    assert tribe.parse(v, FakeFx(jsons={api: {"events": []}}), [], WINDOW, TODAY) == []


def test_squarespace_events_use_real_times_and_ignore_new_york_placeholder():
    v = Venue("tgp", "Tower Grove", "https://www.towergrovepark.org/calendar")
    fx = FakeFx(jsons={"https://www.towergrovepark.org/calendar?format=json": json.loads(read("squarespace_events.json"))})
    evs = squarespace.parse(v, fx, [], WINDOW, TODAY)
    assert len(evs) == 3
    sauce = next(e for e in evs if e.title.startswith("Sauce"))
    assert sauce.start == datetime(2026, 11, 20, 16, 0) and sauce.end == datetime(2026, 11, 20, 20, 0)
    assert sauce.lat is None                                # default NYC map point rejected
    assert sauce.url == "https://www.towergrovepark.org/calendar/2026/11/20/sauce-magazine-presents-makers-in-the-garden"
    assert next(e for e in evs if "Soap" in e.title).location_name == "Stupp Center"


def test_squarespace_blog_posts_fall_back_to_dates_in_text():
    v = Venue("lum", "Luminary", "https://theluminaryarts.com/public-programs")
    fx = FakeFx(jsons={"https://theluminaryarts.com/public-programs?format=json": json.loads(read("squarespace_blog.json"))})
    evs = squarespace.parse(v, fx, [], WINDOW, TODAY)
    assert titles(evs) == ["KAIRAT: Soulipsism"]             # the post with no date is skipped, not guessed
    assert evs[0].start == datetime(2026, 11, 27, 19, 0) and evs[0].confidence == "text"


def test_squarespace_not_a_collection_returns_none():
    v = Venue("x", "X", "https://example.org/events")
    assert squarespace.parse(v, FakeFx(jsons={"https://example.org/events?format=json": {"website": {}}}), [], WINDOW, TODAY) is None
    assert squarespace.parse(v, FakeFx(), [], WINDOW, TODAY) is None


def test_ics():
    evs = ics.parse_ics(read("feed.ics"))
    assert len(evs) == 3
    mic = next(e for e in evs if e.title.startswith("Open Mic"))
    assert mic.title == "Open Mic, Poetry & Prose"
    assert mic.start == datetime(2026, 11, 24, 19, 0) and mic.end == datetime(2026, 11, 24, 21, 0)
    assert mic.location_name == "The Back Room" and mic.address.startswith("100 Main St")
    mkt = next(e for e in evs if e.title == "Holiday Market")
    assert mkt.all_day and mkt.start.date() == date(2026, 11, 28) and mkt.last_day == date(2026, 11, 29)
    late = next(e for e in evs if e.title == "Late Set")
    assert late.start == datetime(2026, 11, 25, 20, 0)        # 02:00Z on the 26th = 8 pm on the 25th in St. Louis


def test_wix_inline_events():
    v = Venue("dw", "Dissonant Works", "https://www.dissonantworks.org/events",
              link_pattern=r"/event-details-registration/[^/]+")
    evs = wix.parse(v, FakeFx(), [read("wix.html")], WINDOW, TODAY)
    assert len(evs) == 2
    sand = next(e for e in evs if e.title == "sandalwood")
    assert sand.start == datetime(2026, 12, 2, 20, 0)         # 02:00Z Dec 3 -> 8 pm Dec 2 local
    assert sand.url == "https://www.dissonantworks.org/event-details-registration/sandalwood"


# ----------------------------------------------------------------------------- New Music Circle, shaped like the real pages
# (real event line: "Saturday, December 12th, 2026 | 7pm Doors / 8pm Show", venue: "Off Broadway ( 3509 Lemp Ave, 63118 / map )",
#  with a byline whose <time> tags carry the post's updated/published dates)

def _nmc_fx():
    base = "https://newmusiccircle.org/2026/07/"
    return FakeFx(texts={
        base + "05/pedestrian-deposit/": read("nmc_post_a.html"),
        base + "06/chris-williams-vibration-trio/": read("nmc_post_b.html"),   # event line inside the post's <header>
        base + "09/mv-carbon/": read("nmc_post_c.html"),
    })


def _nmc_venue():
    return Venue("nmc", "NMC", "https://newmusiccircle.org/category/upcoming-events/",
                 link_pattern=r"newmusiccircle\.org/20\d{2}/\d{2}/\d{2}/[^/]+", detail_only=True)


def test_nmc_real_shaped_pages_give_event_dates_not_post_dates():
    evs = links.parse(_nmc_venue(), _nmc_fx(), [read("nmc_list_real.html")], WINDOW, TODAY)
    by = {e.title: e for e in evs}
    assert sorted(by) == ["Chris Williams Vibration Trio", "MV Carbon", "Pedestrian Deposit"]
    ped = by["Pedestrian Deposit"]
    assert ped.start == datetime(2026, 12, 12, 20, 0) and ped.doors == time(19, 0)   # not Sept 27 / July 5
    assert ped.location_name == "Off Broadway" and ped.address == "3509 Lemp Ave, 63118"
    assert by["Chris Williams Vibration Trio"].start == datetime(2027, 1, 23, 20, 0)   # date lives inside <header>
    assert by["Chris Williams Vibration Trio"].location_name == "Off Broadway"
    assert by["MV Carbon"].start == datetime(2027, 4, 3, 20, 0)                       # <time> published tag ignored
    assert all(e.confidence == "text" for e in evs)


def test_publish_time_tags_never_win_over_text_dates_on_listings():
    html = """<ul><li><time class="blog-date" datetime="2026-05-01">May 1</time>
      <a href="https://x.org/events/gala">Winter Gala</a> <span>Sat, Nov 21, 2026 at 6 pm</span></li></ul>"""
    v = Venue("x", "X", "https://x.org/events", link_pattern=r"x\.org/events/[^/]+")
    ev = links.parse(v, FakeFx(), [html], WINDOW, TODAY)[0]
    assert ev.start == datetime(2026, 11, 21, 18, 0)


# ----------------------------------------------------------------------------- fixes after the first real run
# (City Museum's tribe API answered with nothing because it hid a run that closes in January; Luminary's Squarespace feed
#  answered with nothing because it is a blog-style page; New Music Circle's pages were not read)

class RecordingFx(FakeFx):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.params = []

    def json(self, url, params=None):
        self.params.append(params)
        return super().json(url, params)


def test_tribe_includes_runs_that_started_earlier_and_end_after_the_window():
    api = "https://citymuseum.org/wp-json/tribe/events/v1/events"
    data = {"events": [
        {"title": "Autumn Run (over)", "start_date": "2026-09-01 10:00:00", "end_date": "2026-10-31 18:00:00", "url": "https://citymuseum.org/event/a/"},
        {"title": "Weirdly Wonderful Holidays", "start_date": "2026-11-19 00:00:00", "end_date": "2027-01-03 23:59:59", "all_day": True, "url": "https://citymuseum.org/event/ww-holidays/"},
        {"title": "Long Gallery Show", "start_date": "2026-10-02 10:00:00", "end_date": "2027-02-14 17:00:00", "all_day": True, "url": "https://citymuseum.org/event/g/"},
        {"title": "New Year's Eve Party", "start_date": "2026-12-31 20:00:00", "end_date": "2027-01-01 01:00:00", "url": "https://citymuseum.org/event/nye/"},
    ]}
    fx = RecordingFx(jsons={api: data})
    v = Venue("city-museum", "City Museum", "https://citymuseum.org/events/", parsers=("tribe",))
    evs = tribe.parse(v, fx, [], WINDOW, TODAY)
    assert sorted(e.title for e in evs) == ["Long Gallery Show", "Weirdly Wonderful Holidays"]
    assert "end_date" not in fx.params[0] and fx.params[0]["start_date"] < "2026-07-01"


def test_blog_style_feed_with_no_events_does_not_stop_the_search():
    from te.pipeline import scrape_venue
    page = ('<main><article><h2><a href="https://theluminaryarts.com/public-programs-posts/zine-night">Zine Night</a></h2></article></main>')
    detail = ('<main><article><h1>Zine Night</h1><p>Friday, November 20th, 2026, 7PM</p>'
              '<p>2701 Cherokee St, St. Louis, MO 63118</p></article></main>')
    url = "https://theluminaryarts.com/public-programs"
    blog = json.loads(read("squarespace_blog.json"))
    for it in blog.get("items", []):          # a collection whose items carry no event dates
        it.pop("startDate", None); it["excerpt"] = ""; it["body"] = ""
    fx = FakeFx(texts={url: page, "https://theluminaryarts.com/public-programs-posts/zine-night": detail},
                jsons={url + "?format=json": blog})
    v = Venue("luminary", "The Luminary", url, parsers=("squarespace", "links"),
              link_pattern=r"/public-programs-posts/[^/]+", follow_detail=True)
    res = scrape_venue(v, fx, WINDOW, TODAY, log=lambda *_: None, use_browser=False)
    assert res.strategy == "links/static" and [e.title for e in res.raw] == ["Zine Night"]
    assert res.raw[0].start == datetime(2026, 11, 20, 19, 0)


def test_events_feed_with_nothing_upcoming_is_final_and_old_year_less_dates_are_not_dug_up():
    """Untitled Fine Art: Squarespace says upcoming=[]; its page still lists 2023-24 shows with a 'Dec 9' date badge."""
    from te.pipeline import scrape_venue
    url = "https://www.untitledfineart.com/events"
    page = ('<main><div class="eventlist-event"><span>Dec</span> <span>9</span> '
            '<a href="https://www.untitledfineart.com/events/aliens">Aliens from Inner Space</a></div></main>')
    fx = FakeFx(texts={url: page}, jsons={url + "?format=json": {"upcoming": [], "past": [{"title": "Aliens from Inner Space"}]}})
    v = Venue("u", "Untitled", url, parsers=("squarespace", "links"), link_pattern=r"untitledfineart\.com/events/[^/]+")
    res = scrape_venue(v, fx, WINDOW, TODAY, log=lambda *_: None, use_browser=False)
    assert res.strategy == "squarespace/static" and res.raw == []


def test_notes_from_parsers_that_found_nothing_are_hidden_when_a_later_parser_succeeds():
    from te.pipeline import scrape_venue
    v = Venue("hp", "Hi-Pointe", "https://hipointetheatre.org/calendar/", parsers=("links", "textblocks"),
              link_pattern=r"hipointetheatre\.org/film/[^/]+")
    res = scrape_venue(v, FakeFx(texts={v.url: read("hipointe_text.html")}), WINDOW, TODAY, log=lambda *_: None, use_browser=False)
    assert res.strategy == "textblocks/static" and res.parsed == 4 and not res.notes
    bare = scrape_venue(v, FakeFx(texts={v.url: "<p>closed</p>"}), WINDOW, TODAY, log=lambda *_: None, use_browser=False)
    assert bare.strategy == "none" and any("matched" in n for n in bare.notes)


def test_new_music_circle_falls_back_to_the_list_page_when_event_pages_cannot_be_read():
    links.NOTES.clear()
    fx = FakeFx()          # every event page fails to download
    evs = links.parse(_nmc_venue(), fx, [read("nmc_list_real.html")], WINDOW, TODAY)
    by = {e.title: e for e in evs}
    assert by["Pedestrian Deposit"].start == datetime(2026, 12, 12, 20, 0)
    assert by["MV Carbon"].start == datetime(2027, 4, 3, 20, 0)
    assert any("could not download 3" in n for n in links.NOTES)
    links.NOTES.clear()


def test_new_music_circle_falls_back_when_event_pages_hold_no_date():
    blank = "<html><body><main><article><h1>Pedestrian Deposit</h1><p>Tickets at the door.</p></article></main></body></html>"
    fx = FakeFx(texts={"https://newmusiccircle.org/2026/07/05/pedestrian-deposit/": blank})
    evs = links.parse(_nmc_venue(), fx, [read("nmc_list_real.html")], WINDOW, TODAY)
    ped = next(e for e in evs if e.title == "Pedestrian Deposit")
    assert ped.start == datetime(2026, 12, 12, 20, 0)
    links.NOTES.clear()


def test_links_inside_menus_are_reported_and_body_classes_are_ignored():
    html = ('<body class="has-menu footer-fixed"><main><ul><li><a href="https://x.org/event/a">Jazz Night</a> Sat, Nov 21, 2026 8 pm</li></ul></main>'
            '<footer><a href="https://x.org/event/b">Footer link</a></footer></body>')
    v = Venue("x", "X", "https://x.org/events", link_pattern=r"x\.org/event/[^/]+")
    links.NOTES.clear()
    evs = links.parse(v, FakeFx(), [html], WINDOW, TODAY)
    assert [e.title for e in evs] == ["Jazz Night"]
    links.NOTES.clear()
    assert links.parse(v, FakeFx(), ["<p>nothing</p>"], WINDOW, TODAY) is None
    assert any("matched" in n for n in links.NOTES)
    links.NOTES.clear()
