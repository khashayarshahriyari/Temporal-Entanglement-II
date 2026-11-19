"""Date/time strings are copied from the venues' real listings (as read on 2026-11-19)."""
from datetime import date, datetime, time

from te.textparse import best_date, date_range, extract_times, find_dates, parse_iso

REF = date(2026, 11, 19)


def d(text):
    return best_date(find_dates(text, REF)).date


def test_full_dates():
    assert d("Fri, Nov 20, 2026") == date(2026, 11, 20)
    assert d("Saturday, December 12th, 2026 | 7pm Doors / 8pm Show") == date(2026, 12, 12)
    assert d("Sun, Dec 20, 2026") == date(2026, 12, 20)
    assert d("2026-12-04") == date(2026, 12, 4)
    assert d("12/4/2026") == date(2026, 12, 4)


def test_year_is_inferred_from_weekday():
    assert d("Fri, Nov 20") == date(2026, 11, 20)
    assert d("Thu, Jan 7") == date(2027, 1, 7)       # Jan 7 2027 is a Thursday
    assert d("Dec 3") == date(2026, 12, 3)
    assert d("Jan 5") == date(2027, 1, 5)            # no weekday: next occurrence


def test_month_year_alone_is_not_a_date():
    assert find_dates("Programs through March 2027", REF) == []


def test_ranges():
    s, e, ranged = date_range("Nov. 19, 2026 to Jan. 3, 2027", REF)
    assert (s, e, ranged) == (date(2026, 11, 19), date(2027, 1, 3), True)
    s, e, ranged = date_range("Dec 28 - Jan 3", REF)
    assert (s, e) == (date(2026, 12, 28), date(2027, 1, 3))
    s, e, ranged = date_range("Nov 20 & Nov 21", REF)
    assert ranged is False


def test_doors_and_show():
    t = extract_times("Doors 7 pm / Show 8 pm")
    assert (t.start, t.doors) == (time(20, 0), time(19, 0))
    t = extract_times("Saturday, December 12th, 2026 | 7pm Doors / 8pm Show")
    assert (t.start, t.doors) == (time(20, 0), time(19, 0))
    t = extract_times("Doors 8:30 pm / Show 9:30 pm")
    assert (t.start, t.doors) == (time(21, 30), time(20, 30))


def test_ranges_of_time():
    t = extract_times("5:00–8:00 pm")
    assert (t.start, t.end) == (time(17, 0), time(20, 0))
    t = extract_times("10:00 AM – 1:00 PM")
    assert (t.start, t.end) == (time(10, 0), time(13, 0))
    t = extract_times("10-1 pm")
    assert (t.start, t.end) == (time(10, 0), time(13, 0))
    t = extract_times("7:30pm")
    assert (t.start, t.end) == (time(19, 30), None)
    t = extract_times("12:00 PM – 1:00 PM")
    assert (t.start, t.end) == (time(12, 0), time(13, 0))


def test_date_digits_are_not_times():
    # "Nov 12 - 8 pm" is the 12th of November, 8 pm - not a 12-to-8 time range
    t = extract_times("Fri, Nov 12 - 8 pm")
    assert t.start == time(20, 0) and t.end is None
    assert extract_times("Fri, Nov 20, 2026").start is None


def test_all_day():
    t = extract_times("All day")
    assert t.all_day and t.start is None


def test_iso_with_timezone_becomes_local():
    # 02:00 UTC on Nov 21 is 8 pm Nov 20 in St. Louis (CST, UTC-6)
    assert parse_iso("2026-11-21T02:00:00.000Z") == datetime(2026, 11, 20, 20, 0)
    assert parse_iso("2026-11-20T20:00:00-06:00") == datetime(2026, 11, 20, 20, 0)
    assert parse_iso("2026-11-20 19:30:00") == datetime(2026, 11, 20, 19, 30)
    assert parse_iso("2026-11-20") == datetime(2026, 11, 20, 0, 0)
    assert parse_iso("garbage") is None


def test_date_ranges_with_the_year_written_once_or_not_at_all():
    from te.textparse import date_range
    ref = date(2026, 11, 19)
    assert date_range("Sep 26 – Dec 12, 2026, 11AM–5PM", ref) == (date(2026, 9, 26), date(2026, 12, 12), True)
    assert date_range("Nov 19 - Jan 3, 2027", ref) == (date(2026, 11, 19), date(2027, 1, 3), True)
    assert date_range("Sep 26 – Dec 12", ref) == (date(2026, 9, 26), date(2026, 12, 12), True)      # under way now
    assert date_range("Dec 20 – Jan 5", ref) == (date(2026, 12, 20), date(2027, 1, 5), True)         # starts next month
    assert date_range("Nov 19, 2026 to Jan 3, 2027", ref) == (date(2026, 11, 19), date(2027, 1, 3), True)
