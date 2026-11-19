"""Where things are: a small gazetteer of venues plus an OpenStreetMap (Nominatim) geocoder with a disk cache."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

# Greater St. Louis (city + county + a margin). Anything geocoded outside this box is treated as a wrong match.
BBOX = (38.40, 38.95, -90.80, -90.05)  # south, north, west, east


def in_region(lat: Optional[float], lng: Optional[float]) -> bool:
    return lat is not None and lng is not None and BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lng <= BBOX[3]


# name as it appears in listings (lower case) -> (display name, street address).
# Every address here was read off a venue's own site or the Grand Center calendar.
ALIASES: Dict[str, Tuple[str, str]] = {
    "powell hall": ("Powell Hall", "718 N Grand Blvd, St. Louis, MO"),
    "sheldon concert hall": ("The Sheldon", "3648 Washington Blvd, St. Louis, MO"),
    "the sheldon": ("The Sheldon", "3648 Washington Blvd, St. Louis, MO"),
    "jazz st. louis": ("Jazz St. Louis", "3536 Washington Ave, St. Louis, MO"),
    "the grandel": ("The Grandel", "3610 Grandel Square, St. Louis, MO"),
    "grandel theatre": ("The Grandel", "3610 Grandel Square, St. Louis, MO"),
    "the marcelle": ("The Marcelle", "3310 Samuel Shepard Dr, St. Louis, MO"),
    "sophie's artist lounge": ("Sophie's Artist Lounge", "3333 Washington Ave, St. Louis, MO"),
    "the sovereign": ("The Sovereign", "3306 Washington Ave, St. Louis, MO"),
    "key burger bar": ("The Key Burger Bar & Boogie", "3225 Olive St, St. Louis, MO"),
    "contemporary art museum": ("Contemporary Art Museum", "3750 Washington Blvd, St. Louis, MO"),
    "pulitzer arts foundation": ("Pulitzer Arts Foundation", "3716 Washington Blvd, St. Louis, MO"),
    "city museum": ("City Museum", "750 N 16th St, St. Louis, MO"),
    "dissonant works": ("Dissonant Works", "2218 S Jefferson Ave, St. Louis, MO"),
    "golden record": ("The Golden Record", "2720 Cherokee St, St. Louis, MO"),
    "the luminary": ("The Luminary", "2701 Cherokee St, St. Louis, MO"),
    "untitled fine art": ("Untitled Fine Art", "2920 Cherokee St, St. Louis, MO"),
    "hi-pointe": ("Hi-Pointe Theatre", "1005 McCausland Ave, St. Louis, MO"),
    "off broadway": ("Off Broadway", "3509 Lemp Ave, St. Louis, MO"),
    "tower grove park": ("Tower Grove Park", "4257 Northeast Dr, St. Louis, MO"),
    # WashU Department of Music: its calendar feed gives bare street addresses (560 Trinity Ave = the Music Center)
    "560 trinity ave": ("WashU Music Center", "560 Trinity Ave, University City, MO 63130"),
    "560 music center": ("WashU Music Center", "560 Trinity Ave, University City, MO 63130"),
    "e. desmond lee concert hall": ("E. Desmond Lee Concert Hall", "560 Trinity Ave, University City, MO 63130"),
    "4580 scott ave": ("WashU Medical Campus", "4580 Scott Ave, St. Louis, MO"),
    # Counterpublic 2026 sites named on its calendar
    "counterpublic carriage house": ("Counterpublic Carriage House", "3733 Washington Ave, St. Louis, MO"),
    "tandy community center": ("Tandy Community Center", "4206 Kennerly Ave, St. Louis, MO 63113"),
    "international institute": ("International Institute of St. Louis", "3401 Arsenal St, St. Louis, MO 63118"),
    "chouteau's landing": ("Chouteau's Landing", "101 Chouteau Ave, St. Louis, MO"),
    "chouteau\u2019s landing": ("Chouteau's Landing", "101 Chouteau Ave, St. Louis, MO"),
    "saint louis art museum": ("Saint Louis Art Museum", "1 Fine Arts Dr, St. Louis, MO 63110"),
}
_ALIAS_ORDER = sorted(ALIASES, key=len, reverse=True)


def find_alias(text: str) -> Optional[Tuple[str, str]]:
    low = (text or "").lower()
    for key in _ALIAS_ORDER:
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", low):
            return ALIASES[key]
    return None


STREET_RE = re.compile(
    r"\b\d{1,5}\s+(?:[NSEW]\.?\s+)?[A-Za-z0-9'.\- ]{2,40}?\s"
    r"(?:Ave(?:nue)?|St(?:reet)?|Blvd|Boulevard|Rd|Road|Dr(?:ive)?|Pl(?:ace)?|Ln|Lane|Way|Ct|Court|Pkwy|Parkway|Sq(?:uare)?|Hwy|Highway)\b\.?"
    r"(?:,?\s*(?:Suite|Ste|Unit|#)\s*\w+)?"
    r"(?:,\s*[A-Za-z. ]+)?(?:,\s*(?:MO|Missouri))?(?:,?\s*\d{5})?", re.I)


def looks_like_address(s: str) -> bool:
    return bool(s and STREET_RE.search(s))


def extract_address(s: str) -> str:
    m = STREET_RE.search(s or "")
    return m.group(0).strip(" ,") if m else ""


class Geocoder:
    """Nominatim (OpenStreetMap). One request per second, results cached in a JSON file."""

    URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, cache_path: Path, enabled: bool = True, session=None):
        self.path = Path(cache_path)
        self.enabled = enabled
        self.session = session
        self._last = 0.0
        try:
            self.cache: Dict[str, Optional[list]] = json.loads(self.path.read_text())
        except Exception:
            self.cache = {}
        self.failures = 0

    @staticmethod
    def _key(address: str) -> str:
        return re.sub(r"\s+", " ", address.lower()).strip(" ,")

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
        except OSError:
            pass

    def _query(self, q: str) -> Optional[Tuple[float, float]]:
        import requests

        wait = 1.1 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        sess = self.session or requests
        r = sess.get(self.URL, params={
            "q": q, "format": "json", "limit": 1, "countrycodes": "us",
            "viewbox": f"{BBOX[2]},{BBOX[1]},{BBOX[3]},{BBOX[0]}", "bounded": 1,
        }, headers={"User-Agent": "TemporalEntanglements/2 (personal St. Louis events map)"}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data:
            lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
            if in_region(lat, lng):
                return lat, lng
        return None

    def lookup(self, address: str) -> Optional[Tuple[float, float]]:
        if not address:
            return None
        key = self._key(address)
        if key in self.cache:
            v = self.cache[key]
            return (v[0], v[1]) if v else None
        if not self.enabled:
            return None
        base = re.sub(r",?\s*(Suite|Ste|Unit|#)\s*\w+", "", address, flags=re.I).strip(" ,")
        if not re.search(r"\b(MO|Missouri)\b", base):
            base += ", St. Louis, MO"
        tries = [base]
        street = base.split(",")[0]
        if street != base:
            tries.append(street + ", St. Louis, MO")
        try:
            for q in dict.fromkeys(tries):
                hit = self._query(q)
                if hit:
                    self.cache[key] = [hit[0], hit[1]]
                    self._save()
                    return hit
            self.cache[key] = None  # looked, nothing there: don't ask again every run
            self._save()
        except Exception:
            self.failures += 1  # network trouble: don't cache, try again next run
        return None
