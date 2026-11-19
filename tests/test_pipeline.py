import json
from datetime import date, datetime

from te.models import Venue, Window
from te.pipeline import build, write
from tests.fakes import FakeFx, FakeGeocoder, read

TODAY = date(2026, 11, 19)
WINDOW = Window(TODAY, date(2026, 12, 3))


def make():
    venues = [
        Venue("grand-center", "Grand Center Arts District", "https://www.grandcenter.org/calendar/",
              address="Grand Center Arts District, St. Louis, MO", approx=True, multi_site=True, priority=3,
              parsers=("tribe", "links"), link_pattern=r"grandcenter\.org/event/[^/]+"),
        Venue("cam", "Contemporary Art Museum St. Louis", "https://camstl.org/calendar/",
              address="3750 Washington Blvd, St. Louis, MO 63108", multi_site=True, parsers=("tribe",)),
        Venue("slso", "St. Louis Symphony Orchestra", "https://slso.org/get-tickets/event-calendar/",
              address="718 N Grand Blvd, St. Louis, MO 63103", multi_site=True,
              parsers=("jsonld", "links"), link_pattern=r"slso\.org/event/[^/]+"),
        Venue("tower-grove-park", "Tower Grove Park", "https://www.towergrovepark.org/calendar",
              address="4257 Northeast Dr, St. Louis, MO 63110", parsers=("squarespace",)),
        Venue("empty", "Nothing On", "https://example.org/events", parsers=("jsonld",)),
    ]
    cam_json = {"events": [{
        "title": "Talk: Jane Panetta on Juanita McNeely", "url": "https://camstl.org/event/talk-jane-panetta-on-juanita-mcneely/",
        "start_date": "2026-11-19 18:00:00", "end_date": "2026-11-19 20:00:00", "all_day": False, "venue": []}]}
    fx = FakeFx(
        texts={"https://slso.org/get-tickets/event-calendar/": read("slso.html"),
               "https://example.org/events": "<html><body>nothing</body></html>"},
        jsons={
            "https://www.grandcenter.org/wp-json/tribe/events/v1/events": json.loads(read("tribe_events.json")),
            "https://camstl.org/wp-json/tribe/events/v1/events": cam_json,
            "https://www.towergrovepark.org/calendar?format=json": json.loads(read("squarespace_events.json")),
        })
    return venues, fx


def test_end_to_end():
    venues, fx = make()
    data = build(venues, fx, WINDOW, TODAY, FakeGeocoder(), log=lambda *_: None)
    ev = {e["title"]: e for e in data["events"]}

    # cross-venue duplicate: the CAM listing wins over the Grand Center aggregator's copy
    talk = ev["Talk: Jane Panetta on Juanita McNeely"]
    assert talk["venue_id"] == "cam" and talk["also_on"] == ["Grand Center Arts District"]
    assert [e["title"] for e in data["events"]].count("Talk: Jane Panetta on Juanita McNeely") == 1

    # Tribe supplied its own venue + coordinates
    jazz = ev["Marcus Roberts & The Modern Jazz Generation"]
    assert jazz["location"] == "Jazz St. Louis" and (jazz["lat"], jazz["lng"]) == (38.6379, -90.2305) and not jazz["approx"]
    # Webster Groves talk geocoded from its own address, not the museum's
    web = ev["Artist Talk at Webster University"]
    assert web["location"] == "Sverdrup Hall 123" and web["lng"] < -90.3

    # multi-site venue: location text "The Sheldon" overrides the Powell Hall default
    assert ev["Live at The Sheldon: Radiance"]["location"] == "The Sheldon"
    assert ev["Live at The Sheldon: Radiance"]["address"].startswith("3648 Washington")
    assert ev["A Salute to America"]["location"] == "Powell Hall"
    assert len([e for e in data["events"] if e["title"] == "A Salute to America"]) == 2

    # ongoing run is flagged; one-offs are not
    assert ev["Weirdly Wonderful Holidays"]["ongoing"] is True and ev["Weirdly Wonderful Holidays"]["all_day"]
    assert ev["Weirdly Wonderful Holidays"]["location"] == "City Museum" or ev["Weirdly Wonderful Holidays"]["approx"]
    assert ev["Marcus Roberts & The Modern Jazz Generation"]["ongoing"] is False

    # cancelled events are dropped; Squarespace placeholder coordinates ignored (place comes from the venue address)
    assert "Dutch Oven Friendsgiving (CANCELLED)" not in ev
    sauce = ev["Sauce Magazine presents Makers in the Garden"]
    assert (sauce["lat"], sauce["lng"]) == (38.6103, -90.2560)

    # venue report
    by = {v["id"]: v for v in data["venues"]}
    assert by["empty"]["count"] == 0 and by["empty"]["strategy"] == "none"
    assert by["slso"]["count"] == 4 and by["tower-grove-park"]["count"] == 2
    # everything is inside the window
    assert all("2026-11-19" <= e["start"][:10] <= "2026-12-03" or e["ongoing"] for e in data["events"])


def test_write_outputs_are_loadable(tmp_path):
    venues, fx = make()
    data = build(venues, fx, WINDOW, TODAY, FakeGeocoder(), log=lambda *_: None)
    write(data, tmp_path)
    assert json.loads((tmp_path / "events.json").read_text())["events"]
    js = (tmp_path / "events.js").read_text()
    assert js.startswith("window.TE_DATA = ") and js.rstrip().endswith(";")
    assert json.loads(js[len("window.TE_DATA = "):].rstrip().rstrip(";"))["window"]["start"] == "2026-11-19"


def test_calendar_read_fine_but_nothing_in_range_says_so():
    from tests.test_parsers import _nmc_fx, _nmc_venue
    fx = _nmc_fx()
    fx.texts["https://newmusiccircle.org/category/upcoming-events/"] = read("nmc_list_real.html")
    data = build([_nmc_venue()], fx, WINDOW, TODAY, FakeGeocoder(), log=lambda *_: None)
    v = data["venues"][0]
    assert v["count"] == 0 and v["parsed"] == 3 and v["strategy"] == "links/static"
    assert "none in range; next is Dec 12" in v["note"]
    # ...and ten days later the Dec 12 show is inside the window, placed at Off Broadway
    later = Window(date(2026, 12, 3), date(2026, 12, 17))
    data = build([_nmc_venue()], fx, later, date(2026, 12, 3), FakeGeocoder(), log=lambda *_: None)
    e = data["events"][0]
    assert (e["title"], e["start"], e["location"]) == ("Pedestrian Deposit", "2026-12-12T20:00", "Off Broadway")
    assert (e["lat"], e["lng"]) == (38.5960, -90.2150)


# ----------------------------------------------------------------------------- washu music / counterpublic / four weeks

from te.venues import BY_ID, VENUES
from te.pipeline import scrape_venue

WINDOW4 = Window(TODAY, date(2026, 12, 17))
ICS_URL = "https://music.washu.edu/calendar.ics"


def _washu_fx():
    base = "https://music.washu.edu/events"
    return FakeFx(texts={
        ICS_URL: read("washu_calendar.ics"),
        base: read("washu_listing_0.html"),
        base + "?page=1": read("washu_listing_1.html"),
        base + "?page=2": read("washu_listing_2.html"),      # nothing new: paging must stop here
    })


def test_washu_music_feed_places_and_page_links():
    v = BY_ID["washu-music"]
    data = build([v], _washu_fx(), WINDOW4, TODAY, FakeGeocoder(), log=lambda *_: None)
    by = {(e["title"], e["start"]): e for e in data["events"]}
    assert len(data["events"]) == 7                                # the October and February events are out of range
    wind = by[("WashU Wind Ensemble Concert", "2026-11-19T19:30")]
    assert wind["location"] == "WashU Music Center" and wind["approx"] is False and wind["lat"] is not None
    assert wind["url"] == "https://music.washu.edu/events/washu-wind-ensemble-concert"
    assert by[("Friends of Music Concerto & Aria Competition", "2026-11-20T15:50")]["location"] == "WashU Music Center"
    trio = by[("Oliver/Lenihan/Hicks Trio at the Med Campus", "2026-12-03T12:00")]
    assert trio["location"] == "WashU Medical Campus" and trio["address"].startswith("4580 Scott Ave")
    assert trio["url"].endswith("/oliver-lenihan-hicks-trio-med-campus")           # matched from the URL's words
    kemper = by[("Kemper Unplugged: EcoTones", "2026-11-20T12:00")]
    assert kemper["approx"] is True and kemper["location"] == "WashU Department of Music"   # feed gave no place
    assert by[("Wind Division Recital", "2026-11-24T15:00")]["url"].endswith("/events/wind-division-recital")
    assert by[("Wind Division Recital", "2026-12-08T15:00")]["url"].endswith("/events/wind-division-recital-0")
    assert data["venues"][0]["strategy"] == "ics/static"


def test_listing_paging_stops_when_a_page_brings_nothing_new():
    asked = []
    fx = _washu_fx()
    orig = fx.text
    fx.text = lambda url, **kw: (asked.append(url), orig(url, **kw))[1]
    scrape_venue(BY_ID["washu-music"], fx, WINDOW4, TODAY, log=lambda *_: None, use_browser=False)
    assert "https://music.washu.edu/events?page=2" in asked and "https://music.washu.edu/events?page=3" not in asked


def test_counterpublic_cards_dates_places_and_ongoing_runs():
    v = BY_ID["counterpublic"]
    fx = FakeFx(texts={v.url: read("counterpublic_events.html")})
    data = build([v], fx, WINDOW4, TODAY, FakeGeocoder(), log=lambda *_: None)
    by = {e["title"]: e for e in data["events"]}
    assert sorted(by) == ["Carriage House Radio", "Meetup: Latinx Arts Network + Latin Adrenaline Motorsports Club",
                          "Open Studio", "Talk: Jane Panetta on Juanita McNeely", "The People’s Ball"]   # archive row is past
    talk = by["Talk: Jane Panetta on Juanita McNeely"]
    assert talk["start"] == "2026-11-19T18:00" and talk["end"] == "2026-11-19T20:00"
    assert talk["location"] == "Contemporary Art Museum" and talk["lat"] is not None and not talk["approx"]
    meet = by["Meetup: Latinx Arts Network + Latin Adrenaline Motorsports Club"]
    assert meet["start"] == "2026-11-21T12:00" and meet["lat"] == 38.6180            # address found in the card's text
    ball = by["The People’s Ball"]
    assert ball["location"] == "Tandy Community Center" and ball["lat"] == 38.6590
    radio = by["Carriage House Radio"]
    assert radio["ongoing"] is True and radio["start"].startswith("2026-09-26") and radio["end"].startswith("2026-12-12")
    assert radio["location"] == "Counterpublic Carriage House"
    studio = by["Open Studio"]
    assert studio["approx"] is True and studio["lat"] == 38.6392                     # no place listed: pinned at the Carriage House


def test_every_venue_is_configured_sanely():
    import re
    from te.parsers import PARSERS
    ids = [v.id for v in VENUES]
    assert len(ids) == len(set(ids)) >= 16 and {"washu-music", "counterpublic", "slam"} <= set(ids)
    for v in VENUES:
        assert v.url.startswith("https://") and v.short and set(v.parsers) <= set(PARSERS), v.id
        if v.link_pattern:
            re.compile(v.link_pattern)
        if "links" in v.parsers:
            assert v.link_pattern, v.id


def test_month_grid_calendars_click_once_per_month_boundary():
    class Rec(FakeFx):
        def render(self, url, next_clicks=0):
            self.clicks = next_clicks
            return []
    v = Venue("g", "G", "https://example.org/c", parsers=("links",), link_pattern=r"/e/", paginate=True, render="browser")
    for start, end, want in [(date(2026, 11, 19), date(2026, 12, 17), 1), (date(2026, 11, 3), date(2026, 11, 30), 0),
                             (date(2027, 1, 31), date(2027, 3, 1), 2)]:
        fx = Rec()
        scrape_venue(v, fx, Window(start, end), start, log=lambda *_: None)
        assert fx.clicks == want


def test_merged_event_remembers_every_calendar_that_lists_it():
    cam, cp = BY_ID["cam"], BY_ID["counterpublic"]
    api = "https://camstl.org/wp-json/tribe/events/v1/events"
    talk = {"events": [{"title": "Talk: Jane Panetta on Juanita McNeely", "start_date": "2026-11-19 18:00:00",
                        "end_date": "2026-11-19 20:00:00", "url": "https://camstl.org/event/talk-jane-panetta-on-juanita-mcneely/"}]}
    fx = FakeFx(texts={cp.url: read("counterpublic_events.html")}, jsons={api: talk})
    data = build([cam, cp], fx, WINDOW4, TODAY, FakeGeocoder(), log=lambda *_: None)
    t = [e for e in data["events"] if e["title"].startswith("Talk: Jane")]
    assert len(t) == 1 and t[0]["venue_id"] == "cam" and t[0]["also_on_ids"] == ["counterpublic"]
    assert {v["id"]: v["short"] for v in data["venues"]}["cam"] == "CAM"
