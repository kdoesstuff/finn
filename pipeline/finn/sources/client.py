"""One careful HTTP client for NSE.

NSE's API checks for cookies set by its home page, a browser-like User-Agent and a Referer, and it
rate-limits bursts. The client:

- warms a session on the home page before the first API call, and again after a 401 or 403;
- spaces requests at least `pace` seconds apart;
- retries timeouts, connection errors, 429 and 5xx with exponential backoff and jitter;
- returns None for 404 (a bhavcopy that does not exist is a holiday, not an error);
- raises SourceError, naming the URL and the last failure, when retries run out.

Session factory, sleep and clock are injectable so the behaviour is tested without the network.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import requests

BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/",
}
RETRY_STATUS = {429, 500, 502, 503, 504}
REWARM_STATUS = {401, 403}


class SourceError(RuntimeError):
    """An outside source did not give a usable answer after retries."""


class NSEClient:
    def __init__(
        self,
        session_factory: Callable[[], requests.Session] = requests.Session,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        pace: float = 0.7,
        timeout: tuple[float, float] = (10.0, 30.0),
        attempts: int = 4,
        backoff_cap: float = 20.0,
    ) -> None:
        self._factory, self._sleep, self._clock = session_factory, sleep, clock
        self.pace, self.timeout, self.attempts, self.backoff_cap = pace, timeout, attempts, backoff_cap
        self._session: requests.Session | None = None
        self._last = -1e9
        self.requests_made = 0

    # session ------------------------------------------------------------------------------------
    def _warm(self) -> requests.Session:
        s = self._factory()
        s.headers.update(HEADERS)
        self._wait()
        try:
            s.get(BASE, timeout=self.timeout)  # sets the cookies the API checks
        except requests.RequestException:
            pass  # the API call that follows reports the real failure
        self._session = s
        return s

    @property
    def session(self) -> requests.Session:
        return self._session or self._warm()

    # pacing and backoff -------------------------------------------------------------------------
    def _wait(self) -> None:
        gap = self._clock() - self._last
        if gap < self.pace:
            self._sleep(self.pace - gap)
        self._last = self._clock()

    def _backoff(self, attempt: int) -> None:
        base = min(self.backoff_cap, 1.0 * 2 ** (attempt - 1))
        self._sleep(base + random.uniform(0, base / 2))  # noqa: S311 - jitter, not security

    # requests -----------------------------------------------------------------------------------
    def get(self, url: str, params: dict[str, Any] | None = None) -> requests.Response | None:
        """GET with retries. None means the resource does not exist (404)."""
        last = "no attempt made"
        for attempt in range(1, self.attempts + 1):
            session = self.session
            self._wait()
            self.requests_made += 1
            try:
                r = session.get(url, params=params, timeout=self.timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                last = f"{type(exc).__name__}"
                self._backoff(attempt)
                continue
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
            last = f"HTTP {r.status_code}"
            if r.status_code in REWARM_STATUS:
                self._session = None  # cookies expired or refused: start a fresh session
                self._backoff(attempt)
                continue
            if r.status_code in RETRY_STATUS:
                self._backoff(attempt)
                continue
            raise SourceError(f"{url}: {last}")
        raise SourceError(f"{url}: gave up after {self.attempts} attempts ({last})")

    def api(self, path: str, **params: Any) -> Any:
        """JSON from https://www.nseindia.com/api/<path>."""
        url = f"{BASE}/api/{path}"
        r = self.get(url, params=params)
        if r is None:
            raise SourceError(f"{url}: not found")
        try:
            return r.json()
        except ValueError as exc:
            raise SourceError(f"{url}: not JSON ({r.text[:80]!r})") from exc

    def content(self, url: str) -> bytes | None:
        """Raw bytes of a document (PDF, XBRL, zip), or None if it does not exist."""
        r = self.get(url)
        return None if r is None else r.content
