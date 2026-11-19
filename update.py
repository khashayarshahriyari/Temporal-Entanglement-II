#!/usr/bin/env python3
"""Step 1 - collect the next four weeks of events from the venue calendars and write web/data/events.js.

    python3 update.py                    # everything, 28 days
    python3 update.py --only slso,cam    # just some venues (ids are in te/venues.py)
    python3 update.py --days 21          # longer window
    python3 update.py --no-browser       # skip the headless-browser fallback (faster)
    python3 update.py --no-geocode       # reuse cached coordinates only

Raw pages and API responses from every run are saved in debug/ - if a venue comes back empty, that folder is what
to look at (or send along) to fix its parser.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from te.fetch import Fetcher  # noqa: E402
from te.models import Window  # noqa: E402
from te.pipeline import build, write  # noqa: E402
from te.places import Geocoder  # noqa: E402
from te.venues import VENUES  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=28, help="how many days after today to include (default 28 = four weeks)")
    ap.add_argument("--only", default="", help="comma-separated venue ids")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-geocode", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite the saved events even if this run found none")
    ap.add_argument("--today", default="", help="pretend today is YYYY-MM-DD (testing)")
    ap.add_argument("--out", default=str(ROOT / "web" / "data"))
    args = ap.parse_args(argv)

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    window = Window(today, today + timedelta(days=args.days))
    wanted = {x.strip() for x in args.only.split(",") if x.strip()}
    venues = [v for v in VENUES if not wanted or v.id in wanted]
    unknown = wanted - {v.id for v in VENUES}
    if unknown:
        print("unknown venue id(s):", ", ".join(sorted(unknown)), "\nknown:", ", ".join(v.id for v in VENUES))
        return 2

    print(f"Collecting {window.start} -> {window.end} from {len(venues)} calendars\n")
    fx = Fetcher(debug_dir=ROOT / "debug")
    geo = Geocoder(ROOT / "data" / "geocode_cache.json", enabled=not args.no_geocode)
    try:
        data = build(venues, fx, window, today, geo, use_browser=not args.no_browser)
    finally:
        fx.close()
    events = data["events"]
    out_dir = Path(args.out)
    previous = out_dir / "events.json"
    if not events and not args.force and previous.exists():
        try:
            had = len(json.loads(previous.read_text()).get("events", []))
        except Exception:
            had = 0
        if had:
            print(f"\nThis run found no events at all, so the {had} events from your last update were kept."
                  "\nIf you're offline, reconnect and run again; use --force to overwrite anyway.")
            return 1
    write(data, out_dir)

    unplaced = [e for e in events if e["lat"] is None]
    print(f"\n{len(events)} events from {sum(1 for v in data['venues'] if v['count'])} venues "
          f"-> {Path(args.out) / 'events.js'}")
    if unplaced:
        print(f"{len(unplaced)} could not be placed on the map (listed in the side panel only)")
    if geo.failures:
        print(f"geocoder had {geo.failures} network failure(s); run again to retry those addresses")
    if data["venues"] and all("did not load" in v["note"] for v in data["venues"]):
        print("\nNo calendar page loaded at all - check your internet connection.")
    empty = [v for v in data["venues"] if not v["count"]]
    quiet = [v for v in empty if v["strategy"] != "none"]
    unread = [v for v in empty if v["strategy"] == "none"]
    if quiet:
        print("\nRead fine, but nothing scheduled in range:")
        for v in quiet:
            print(f"  - {v['name']}" + (f"  ({v['note'].split('; ')[-1]})" if "next is" in v["note"] else ""))
    if unread:
        print("\nCould NOT read any events from: " + ", ".join(v["name"] for v in unread))
        print("  check debug/<venue-id>-*.html (or send me the debug/ folder)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
