"""Parser registry.

A parser is `parse(venue, fetcher, pages, window, today) -> list[RawEvent] | None`.
  * API-kind parsers (tribe, squarespace, ics) fetch their own data and return [] when the source answered but had
    nothing in range, or None when the source isn't there / isn't recognisable.
  * HTML-kind parsers (jsonld, wix, links) read the calendar page(s) in `pages` and return None when they find nothing.
"""
from . import ics, jsonld, links, squarespace, textblocks, tribe, wix

PARSERS = {
    "tribe": tribe, "squarespace": squarespace, "ics": ics,
    "jsonld": jsonld, "wix": wix, "links": links, "textblocks": textblocks,
}
API_PARSERS = {name for name, mod in PARSERS.items() if mod.API_KIND}
