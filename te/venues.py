"""The calendars. Addresses were read off each venue's own site (or the Grand Center calendar)."""
from .models import Venue

VENUES = [
    Venue("golden-record", "The Golden Record", "https://thegoldenrecord.live/events/",
          address="2720 Cherokee St, St. Louis, MO 63118",
          parsers=("jsonld", "links"), link_pattern=r"/event/[^/]+", exclude_pattern=r"etix\.com"),

    Venue("luminary", "The Luminary", "https://theluminaryarts.com/public-programs",
          address="2701 Cherokee St, St. Louis, MO 63118",
          parsers=("squarespace", "jsonld", "links"), link_pattern=r"/public-programs-posts/[^/]+", follow_detail=True,
          note="Listing shows no dates, so dates are read from each program's page."),

    Venue("slso", "St. Louis Symphony Orchestra", "https://slso.org/get-tickets/event-calendar/",
          address="718 N Grand Blvd, St. Louis, MO", multi_site=True,
          parsers=("jsonld", "links"), link_pattern=r"slso\.org/event/[^/]+"),

    Venue("pulitzer", "Pulitzer Arts Foundation", "https://pulitzerarts.org/events/current/",
          address="3716 Washington Blvd, St. Louis, MO 63108",
          parsers=("tribe", "jsonld", "links"),
          link_pattern=r"pulitzerarts\.org/(events|exhibitions)/[^/]+",
          exclude_pattern=r"/events/(current|past|upcoming|archive)/?$"),

    Venue("grand-center", "Grand Center Arts District", "https://www.grandcenter.org/calendar/",
          address="Grand Center Arts District, St. Louis, MO", approx=True, multi_site=True, priority=3,
          parsers=("tribe", "ics", "links"), link_pattern=r"grandcenter\.org/event/[^/]+", paginate=True,
          note="Aggregates many Grand Center venues; duplicates of other venues' events are merged."),

    Venue("hi-pointe", "Hi-Pointe Theatre", "https://hipointetheatre.org/calendar/",
          address="1005 McCausland Ave, St. Louis, MO 63117",
          parsers=("jsonld", "links", "textblocks"),
          link_pattern=r"/(film|films|movie|movies|event|events|showtimes?|shows?|screenings?)/[^/?#]+",
          exclude_pattern=r"/(events?|shows?)/?$", paginate=True,
          note="Page shows titles and dates but few per-film links; least certain parser."),

    Venue("untitled-fine-art", "Untitled Fine Art", "https://www.untitledfineart.com/events",
          address="2920 Cherokee St, St. Louis, MO 63118",
          parsers=("squarespace", "ics", "links"), link_pattern=r"untitledfineart\.com/events/[^/]+",
          note="Calendar looked inactive when checked (newest event Sept 2024)."),

    Venue("cam", "Contemporary Art Museum St. Louis", "https://camstl.org/calendar/",
          address="3750 Washington Blvd, St. Louis, MO", multi_site=True,
          parsers=("tribe", "ics", "jsonld", "links"), link_pattern=r"camstl\.org/event/[^/]+"),

    Venue("city-museum", "City Museum", "https://citymuseum.org/events/",
          address="750 N 16th St, St. Louis, MO 63103",
          parsers=("tribe", "ics", "jsonld", "links"), link_pattern=r"citymuseum\.org/event/[^/]+"),

    Venue("dissonant-works", "Dissonant Works", "https://www.dissonantworks.org/events",
          address="2218 S Jefferson Ave, St. Louis, MO 63104",
          parsers=("jsonld", "wix", "links"), link_pattern=r"/event-details-registration/[^/]+", paginate=True),

    Venue("tower-grove-park", "Tower Grove Park", "https://www.towergrovepark.org/calendar",
          address="4257 Northeast Dr, St. Louis, MO 63110",
          parsers=("squarespace", "ics", "jsonld", "links"), link_pattern=r"/calendar/\d{4}/\d{1,2}/\d{1,2}/[^/]+"),

    Venue("new-music-circle", "New Music Circle", "https://newmusiccircle.org/category/upcoming-events/",
          address="", multi_site=True,
          parsers=("links",), link_pattern=r"newmusiccircle\.org/20\d{2}/\d{2}/\d{2}/[^/]+", detail_only=True,
          note="Event posts are blog entries; the date and place are read from each post's text."),

    Venue("kranzberg", "Kranzberg Arts Foundation", "https://kranzbergartsfoundation.org/calendar/",
          address="3224 Locust St, St. Louis, MO 63103", approx=True, multi_site=True, priority=2,
          parsers=("tribe", "ics", "jsonld", "links"),
          link_pattern=r"kranzbergartsfoundation\.org/(events?|shows?|performances?|calendar)/[^/?#]+", paginate=True,
          note="Calendar is loaded by JavaScript; uses the browser renderer if static fetch finds nothing."),

    Venue("washu-music", "WashU Department of Music", "https://music.washu.edu/events",
          address="560 Trinity Ave, University City, MO 63130", approx=True,
          parsers=("ics", "links"), ics_url="https://music.washu.edu/calendar.ics",
          link_pattern=r"music\.washu\.edu/events/[^/?#]+", exclude_pattern=r"/events/(past|upcoming)/?$",
          list_pages=6, match_links=True,
          note="Times and places come from the department's calendar feed; event-page links from the listing. "
               "Events with no place in the feed are pinned at the Music Center (approximate)."),

    Venue("counterpublic", "Counterpublic 2026", "https://counterpublic.org/events/",
          address="3733 Washington Ave, St. Louis, MO", approx=True, multi_site=True,
          parsers=("jsonld", "links"), link_pattern=r"counterpublic\.org/event/[^/?#]+",
          note="Events are spread across the triennial's sites; ones with no place listed are pinned at the Carriage House."),

    Venue("slam", "Saint Louis Art Museum", "https://www.slam.org/events/",
          address="1 Fine Arts Dr, St. Louis, MO 63110",
          parsers=("tribe", "ics", "jsonld", "links"), link_pattern=r"slam\.org/event/[^/?#]+"),
]

SHORT = {
    "golden-record": "Golden Record", "luminary": "Luminary", "slso": "SLSO", "pulitzer": "Pulitzer",
    "grand-center": "Grand Center", "hi-pointe": "Hi-Pointe", "untitled-fine-art": "Untitled",
    "cam": "CAM", "city-museum": "City Museum", "dissonant-works": "Dissonant Works",
    "tower-grove-park": "Tower Grove", "new-music-circle": "New Music Circle", "kranzberg": "Kranzberg",
    "washu-music": "WashU Music", "counterpublic": "Counterpublic", "slam": "SLAM",
}
for _v in VENUES:
    _v.short = _v.short or SHORT.get(_v.id, _v.name)

BY_ID = {v.id: v for v in VENUES}
