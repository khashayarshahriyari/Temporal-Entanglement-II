# Temporal Entanglements 2

A private map of St. Louis cultural events for the next four weeks, built from 16 calendars.
Pick a day, see that day's events on the map. Each event shows its title, location, time and a link to the venue's page.

## Run it (Mac)

```bash
bash setup.sh     # once: private Python environment + libraries (+ a headless browser, ~150 MB)
bash run.sh       # collects fresh events, then opens http://127.0.0.1:8765
```

Later: `bash run.sh` again to refresh, or `bash run.sh serve` to just reopen the map with the events you already have.
The map is served on your own machine only (127.0.0.1). Left/right arrow keys move between days.

Useful options: `bash run.sh update --only slso,cam` &middot; `--days 14` (default is 28) &middot; `--no-browser` (faster, skips JavaScript-only sites).

## How the scraper reads each calendar

There is no per-site CSS to break. Each venue gets a ladder of strategies and the first that yields events wins:

1. **Structured feeds**: The Events Calendar API (WordPress), Squarespace `?format=json`, `.ics` calendars
2. **schema.org JSON-LD** and Wix's embedded event data
3. **Generic link-and-date reader**: finds the links to event pages, reads title/date/time from the card around each
   (handles "day heading" layouts, repeated listings, and pages whose dates only appear on the event page)
4. **Headless browser** for the same steps when the page needs JavaScript

| Venue | Platform (as found) | Tried, in order |
|---|---|---|
| Grand Center, CAM, City Museum | WordPress + The Events Calendar | Events API, .ics, page |
| Tower Grove Park, The Luminary, Untitled Fine Art | Squarespace | JSON, .ics, page |
| Dissonant Works | Wix | JSON-LD, embedded data, page |
| The Golden Record, SLSO, Pulitzer | WordPress | JSON-LD, page |
| New Music Circle | WordPress blog posts | each post's text (date + address) |
| Hi-Pointe Theatre | Nightjar/Filmbot | JSON-LD, page, plain-text fallback |
| WashU Department of Music | Drupal | its `calendar.ics` feed (times, places) + the paged listing (event-page links) |
| Counterpublic 2026 | WordPress, custom listing | JSON-LD, page (each card carries its own venue and address) |
| Saint Louis Art Museum | WordPress + The Events Calendar | Events API, .ics, page |
| Kranzberg Arts Foundation | WordPress, JS-loaded calendar | Events API, .ics, JSON-LD, browser |

Locations: events that carry an address (or coordinates) are placed from it; known Grand Center venues
(Powell Hall, The Sheldon, Jazz St. Louis, ...) are recognised by name; everything else falls back to the venue's own
address, drawn as a dashed pin and tagged "approximate location". Addresses are geocoded with OpenStreetMap and cached in
`data/geocode_cache.json` (the first run takes a minute for this).

Things the map flags honestly: dates read from page text rather than a calendar field are tagged **date inferred**;
events that couldn't be placed say **not on map**; multi-week runs are held back unless you tick the
*ongoing runs & exhibitions* box; cancelled events are dropped; duplicates across calendars are merged.

## Organizations filter

The **Organizations** panel (under the date strip) lists every calendar with its colour and how many events it has on the
selected day. Click a name to hide or show it, double-click to show only that one, **All** / **None** for the whole list.
Pins, the day strip's counts and the event list all follow the filter, and it is remembered between visits. A place with
events from several organizations gets a multicolour ring. An event that two calendars both list (e.g. a CAM talk that is
also in Counterpublic's schedule) counts for both.

## Map background

Uses OpenStreetMap's own tiles, darkened in the browser: no account, no API key. Settings are in `web/config.js`.
If you ever want the true dark basemap, CARTO offers a free key (https://carto.com/basemaps/apikey/); paste it into `cartoKey` there.
If the background ever fails to load, the side panel says so; the pins and list keep working.

## If a venue comes back empty

Open **Sources** (bottom of the side panel): green = events found, amber = none in range, red = nothing could be read.
An empty calendar can be genuine. If it looks wrong, every run saves the raw pages in `debug/` (`<venue-id>-*.html`, `.json`).
The usual fix is one line in `te/venues.py` (`link_pattern`), or send me the `debug/` folder.

## Layout

```
update.py        step 1: collect events -> web/data/events.js
serve.py         step 2: serve web/ locally and open it
te/venues.py     the 13 calendars (add or tweak venues here)
te/parsers/      one module per strategy
te/pipeline.py   scrape, place, merge duplicates, write
web/             the map (Leaflet is bundled; background tiles come from OpenStreetMap, no key needed)
tests/           python3 -m pytest
```


## When a calendar comes up empty

`update.py` tells two cases apart: "read fine, but nothing scheduled in range" (normal - the venue just has nothing in
the next two weeks; the next date is shown) and "could NOT read any events". For the second, run

    bash run.sh diagnose <venue-id>      # e.g. new-music-circle, luminary, city-museum

It prints what the scraper sees on that calendar (links found, dates found on each event page, what it made of them) and
saves the same text to `debug/diagnose-<venue-id>.txt`. The raw pages are in `debug/` too.
