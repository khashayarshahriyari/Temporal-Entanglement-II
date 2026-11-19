"""Test doubles shared by the pipeline test and the demo-data script."""
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return (FIX / name).read_text()


class FakeFx:
    """Stands in for te.fetch.Fetcher: serves canned pages / JSON, no network."""

    def __init__(self, texts=None, jsons=None, rendered=None):
        self.texts, self.jsons, self.rendered = texts or {}, jsons or {}, rendered or {}

    def text(self, url, **kw):
        return self.texts.get(url)

    def json(self, url, params=None):
        return self.jsons.get(url)

    def render(self, url, next_clicks=0):
        return self.rendered.get(url, [])

    def dump(self, *a, **k):
        pass

    def close(self):
        pass


class FakeGeocoder:
    """Test-only coordinates (rough, by hand) so the map has something to draw. Real runs use OpenStreetMap."""

    PLACES = {
        "2720 cherokee st, st. louis, mo 63118": (38.5970, -90.2250),
        "2701 cherokee st, st. louis, mo 63118": (38.5972, -90.2262),
        "718 n grand blvd, st. louis, mo 63103": (38.6391, -90.2300),
        "718 n grand blvd, st. louis, mo": (38.6391, -90.2300),
        "3648 washington blvd, st. louis, mo": (38.6393, -90.2325),
        "3750 washington blvd, st. louis, mo 63108": (38.6400, -90.2350),
        "3536 washington ave, st. louis, mo": (38.6385, -90.2290),
        "grand center arts district, st. louis, mo": (38.6390, -90.2300),
        "4257 northeast dr, st. louis, mo 63110": (38.6103, -90.2560),
        "4257 northeast dr, st. louis, mo": (38.6103, -90.2560),
        "3509 lemp ave, st. louis, mo": (38.5960, -90.2150),
        "750 n 16th st, st. louis, mo 63103": (38.6330, -90.2000),
        "8300 big bend boulevard, webster groves, mo, 63119": (38.5890, -90.3350),
        "3750 washington blvd": (38.6400, -90.2350),
        "3536 washington ave": (38.6385, -90.2290),
        "3648 washington blvd": (38.6393, -90.2325),
        "3509 lemp ave": (38.5960, -90.2150),
        "3509 lemp ave, 63118": (38.5960, -90.2150),   # as written on newmusiccircle.org event pages
        "560 trinity ave, university city, mo 63130": (38.6495, -90.3040),
        "560 trinity ave, university city, 63130": (38.6495, -90.3040),
        "4580 scott ave, st. louis, mo": (38.6350, -90.2640),
        "3750 washington blvd, st. louis, mo": (38.6400, -90.2350),
        "3750 washington ave": (38.6400, -90.2350),
        "3733 washington ave, st. louis, mo": (38.6392, -90.2345),
        "3733 washington ave": (38.6392, -90.2345),
        "101 chouteau ave, st. louis, mo": (38.6180, -90.1880),
        "101 chouteau ave": (38.6180, -90.1880),
        "4206 kennerly ave, st. louis, mo 63113": (38.6590, -90.2420),
        "1 fine arts dr, st. louis, mo 63110": (38.6393, -90.2943),
    }
    failures = 0

    def lookup(self, address):
        return self.PLACES.get(" ".join(address.lower().split()).strip(" ,"))
