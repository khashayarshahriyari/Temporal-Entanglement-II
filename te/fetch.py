"""Polite HTTP fetching, plus an optional headless-browser renderer for JavaScript-driven calendars."""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 TemporalEntanglements/2")

NEXT_SELECTORS = [
    "[aria-label*='next' i]:not([disabled])", "a[rel='next']", "button:has-text('Next')", "a:has-text('Next')",
    ".fc-next-button", ".tribe-events-c-top-bar__nav-link--next", "button:has-text('›')", "a:has-text('›')",
    "button:has-text('»')", "a:has-text('»')",
]


class Fetcher:
    def __init__(self, debug_dir: Optional[Path] = None, delay: float = 0.6, log=print):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.delay = delay
        self.log = log
        self._last: dict = {}
        self._pw = None
        self._browser = None
        self.browser_error: Optional[str] = None
        self.status: dict = {}   # url -> HTTP status, or the exception name when the request never got an answer

    # -- plain HTTP ---------------------------------------------------------------------
    def _throttle(self, url: str):
        host = urlparse(url).netloc
        wait = self.delay - (time.time() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.time()

    def get(self, url: str, params: Optional[dict] = None, accept: Optional[str] = None) -> requests.Response:
        last_exc: Exception = RuntimeError("no attempt")
        for attempt in range(3):
            self._throttle(url)
            try:
                r = self.s.get(url, params=params, timeout=30, headers={"Accept": accept} if accept else None)
                if r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code} from {url}")
                return r
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        raise last_exc

    def text(self, url: str, **kw) -> Optional[str]:
        try:
            r = self.get(url, **kw)
            self.status[url] = r.status_code
            return r.text if r.status_code == 200 else None
        except requests.RequestException as exc:
            self.status[url] = type(exc).__name__
            return None

    def json(self, url: str, params: Optional[dict] = None) -> Optional[Any]:
        try:
            r = self.get(url, params=params, accept="application/json")
            if r.status_code != 200:
                return None
            return r.json()
        except (requests.RequestException, ValueError):
            return None

    # -- rendered pages -----------------------------------------------------------------
    def _start_browser(self):
        if self._browser or self.browser_error:
            return self._browser
        try:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception as exc:  # playwright missing, or browser not installed
            self.browser_error = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"
            self.log(f"    (browser rendering unavailable: {self.browser_error}; run ./setup.sh to enable)")
        return self._browser

    def render(self, url: str, next_clicks: int = 0) -> List[str]:
        """Load the page in headless Chromium; returns one HTML snapshot per 'next month' click (+1)."""
        browser = self._start_browser()
        if not browser:
            return []
        ctx = browser.new_context(user_agent=UA, locale="en-US", timezone_id="America/Chicago",
                                  viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        snaps: List[str] = []
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            for _ in range(4):  # trigger lazy loading
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(400)
            snaps.append(page.content())
            for _ in range(next_clicks):
                clicked = False
                for sel in NEXT_SELECTORS:
                    try:
                        el = page.locator(sel).first
                        if el.count() and el.is_visible():
                            el.click(timeout=4000)
                            try:
                                page.wait_for_load_state("networkidle", timeout=8000)
                            except Exception:
                                pass
                            page.wait_for_timeout(600)
                            snaps.append(page.content())
                            clicked = True
                            break
                    except Exception:
                        continue
                if not clicked:
                    break
        except Exception as exc:
            self.log(f"    (render failed for {url}: {type(exc).__name__})")
        finally:
            ctx.close()
        return snaps

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # -- debugging ----------------------------------------------------------------------
    def dump(self, name: str, content: str):
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
        (self.debug_dir / safe).write_text(content, encoding="utf-8", errors="replace")
