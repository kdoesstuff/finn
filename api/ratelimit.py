"""Per-client rate limits, kept in memory.

FINN runs as one instance with one worker (Render's free plan cannot scale out), so one process
sees every request and an in-memory count is exact. More instances would each count separately and
need a shared store (Postgres or Redis); that is noted in docs/notes/B5-B7.md.

Who the client is: Render puts Cloudflare in front of every service, and Render's proxy *appends*
to an X-Forwarded-For header the client sent, so its left-most entry is whatever the client chose
to write there. The limiter therefore never reads X-Forwarded-For. On Render it reads
True-Client-IP, which Cloudflare sets and overwrites; anywhere else, the connecting address.
IPv6 clients are counted per /64, the block one subscriber is normally given, so rotating
addresses inside it does not reset the count. Sources are in docs/notes/B5-B7.md.
"""

from __future__ import annotations

import ipaddress
import math
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence

from starlette.types import Scope


def client_address(scope: Scope, header: str | None) -> str:
    """The client's address: from `header` when it holds exactly one valid IP, else the peer."""
    if header:
        name = header.encode("latin-1")
        values = [v for k, v in scope.get("headers", []) if k == name]
        if len(values) == 1:
            try:
                return str(ipaddress.ip_address(values[0].decode("latin-1").strip()))
            except ValueError:
                pass
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


def bucket(address: str) -> str:
    """The unit a limit counts: an IPv4 address, or the /64 an IPv6 address sits in."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


class SlidingWindow:
    """At most `limit` requests per `window` seconds for each key, counted over the last `window`
    seconds (no burst at a window boundary, unlike fixed per-minute counters)."""

    def __init__(self, limit: int, window: float = 60.0, max_keys: int = 10_000) -> None:
        self.limit, self.window, self.max_keys = limit, window, max_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def wait(self, key: str, now: float) -> float:
        """Seconds until `key` may make another request; 0 if it may now."""
        hits = self._recent(key, now)
        return 0.0 if len(hits) < self.limit else hits[0] + self.window - now

    def record(self, key: str, now: float) -> None:
        hits = self._hits.setdefault(key, deque())
        hits.append(now)
        self._hits.move_to_end(key)
        if len(self._hits) > self.max_keys:
            self._evict(now)

    def _evict(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]
        while len(self._hits) > self.max_keys:  # still full of active clients: drop the least recent
            self._hits.popitem(last=False)


class Limiter:
    """Several windows checked together: a request is counted in all of them or in none."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()

    def hit(self, windows: Sequence[tuple[SlidingWindow, str]]) -> int:
        """Count one request; returns 0 if allowed, else the whole seconds to wait (Retry-After)."""
        with self._lock:
            now = self._clock()
            wait = max((w.wait(key, now) for w, key in windows), default=0.0)
            if wait > 0:
                return max(1, math.ceil(wait))
            for w, key in windows:
                w.record(key, now)
            return 0
