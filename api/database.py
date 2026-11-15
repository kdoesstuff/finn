"""The API's database connections: a small pool, opened on first use.

Connections are made the way `finn.db.connect` makes them (autocommit, FINN's search path), plus a
5-second statement timeout, and are checked before each use, so a connection the pooler dropped
while idle is replaced instead of failing a request. Work never runs as the connecting admin: every
query goes through `finn.db.as_role` as finn_api, scoped to the investor where investor data is read.

When the database cannot be reached, a pool timeout, a refused connection, a lost connection or a
cancelled statement all become `Unavailable`, which the API answers with 503 (and /health with
"db": false); the web app then shows its saved copy.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from finn import db

log = logging.getLogger("finn.api.db")


class Unavailable(Exception):
    """The database could not answer. Carries the error's class name only, never its text."""


class Database:
    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 4, statement_timeout_ms: int = 5000,
                 connect_timeout_s: int = 5, wait_s: float = 5.0) -> None:
        self._statement_timeout = f"{int(statement_timeout_ms)}ms"
        self._wait_s = wait_s
        self._lock = threading.Lock()
        self._opened = False
        self._pool = ConnectionPool(
            url, min_size=min_size, max_size=max_size, open=False, name="finn-api", timeout=wait_s,
            kwargs={"autocommit": True, "connect_timeout": connect_timeout_s, "application_name": "finn-api"},
            configure=self._configure, check=ConnectionPool.check_connection,
            # Retry a lost database for a minute at a time; requests keep failing fast with 503 meanwhile.
            reconnect_timeout=60.0, max_idle=300.0,
        )

    def _configure(self, conn: psycopg.Connection) -> None:
        conn.execute(f"set search_path = {db.SEARCH_PATH}")
        conn.execute("select set_config('statement_timeout', %s, false)", [self._statement_timeout])

    def _open(self) -> None:
        if self._opened:
            return
        with self._lock:
            if not self._opened:
                self._pool.open(wait=False)  # never blocks start-up or a request on a database that is down
                self._opened = True

    @contextmanager
    def connection(self, wait_s: float | None = None) -> Iterator[psycopg.Connection]:
        """A connection with no transaction open, ready for `finn.db.as_role`."""
        self._open()
        try:
            with self._pool.connection(timeout=self._wait_s if wait_s is None else wait_s) as conn:
                yield conn
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:  # PoolTimeout is an OperationalError
            log.warning("database unavailable: %s", type(exc).__name__)
            raise Unavailable(type(exc).__name__) from exc

    def close(self) -> None:
        with self._lock:
            if self._opened:
                self._pool.close(timeout=5.0)
                self._opened = False
