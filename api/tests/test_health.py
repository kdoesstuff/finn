"""GET /health with the database up and down, and the database connections the API makes."""

from __future__ import annotations

import time

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.app import HEALTH_CACHE_S, create_app
from api.database import Database, Unavailable
from api.tests.helpers import CORE, DATA_AS_OF, DEMO, assert_error, make_client, mint
from finn import db
from tests.dbtools import admin_url

DOWN = "postgresql://nobody:not-a-real-password@127.0.0.1:1/none"  # nothing listens on port 1


def test_health_with_the_database_up(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": True, "data_as_of": DATA_AS_OF, "version": "abc1234"}
    head = client.head("/health")  # some uptime monitors check with HEAD
    assert head.status_code == 200 and head.content == b""


def test_health_with_the_database_down_is_still_200(settings):
    with make_client(settings, db_url=DOWN, health_wait_s=0.5, pool_wait_s=0.5) as c:
        started = time.monotonic()
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "db": False, "data_as_of": None, "version": "abc1234"}
        assert time.monotonic() - started < 3  # well inside Render's 5-second health check
        # /v1 answers 503, and the web app falls back to its saved copy.
        assert_error(c.post("/v1/session/demo", headers={"Origin": CORE}), 503, "unavailable")
        error = assert_error(c.get("/v1/digest", headers={"Authorization": f"Bearer {mint(DEMO)}"}), 503,
                             "unavailable")
        assert "not-a-real-password" not in error["message"] and "127.0.0.1" not in error["message"]


class CountingDatabase:
    """Stands in for the pool: counts how often /health reaches the database."""

    def __init__(self) -> None:
        self.calls = 0

    def connection(self, wait_s: float | None = None):
        self.calls += 1
        raise Unavailable("OperationalError")

    def close(self) -> None:
        pass


def test_health_reaches_the_database_at_most_once_per_window(settings, ticker):
    counting = CountingDatabase()
    with TestClient(create_app(settings, database=counting, monotonic=ticker)) as c:  # type: ignore[arg-type]
        for _ in range(20):
            assert c.get("/health").json()["db"] is False
        assert counting.calls == 1
        ticker.t += HEALTH_CACHE_S
        c.get("/health")
        assert counting.calls == 2


def test_api_connections_are_autocommit_scoped_and_time_limited(settings):
    database = Database(settings.db_url, statement_timeout_ms=5000)
    try:
        with database.connection() as conn:
            assert conn.autocommit
            assert conn.execute("show statement_timeout").fetchone() == ("5s",)
            assert conn.execute("show search_path").fetchone() == (db.SEARCH_PATH,)
            assert conn.execute("select current_setting('application_name')").fetchone() == ("finn-api",)
            with db.as_role(conn, "finn_api"):
                assert conn.execute("select current_user").fetchone() == ("finn_api",)
            # The role and scope end with the transaction: the next request starts as the admin again.
            assert conn.execute("select current_user, current_setting('finn.investor_id', true)").fetchone() in \
                {("supa_admin", None), ("supa_admin", "")}
    finally:
        database.close()


def test_a_slow_statement_is_cancelled_and_reported_unavailable(database):
    slow = Database(admin_url(database), statement_timeout_ms=200)
    try:
        with pytest.raises(Unavailable, match="QueryCanceled"):
            with slow.connection() as conn, db.as_role(conn, "finn_api"):
                conn.execute("select pg_sleep(2)")
        with slow.connection() as conn:  # the pool replaced nothing it did not have to: still usable
            assert conn.execute("select 1").fetchone() == (1,)
    finally:
        slow.close()


def test_the_pool_opens_only_when_first_used(settings):
    database = Database(DOWN, wait_s=0.3)
    assert database._opened is False  # constructing it made no connection attempt
    with pytest.raises(Unavailable, match="PoolTimeout"):
        with database.connection():
            pass
    database.close()


class BrokenDatabase(CountingDatabase):
    """Reachable but wrong: the query fails with a database error, not a connection error."""

    def connection(self, wait_s: float | None = None):
        self.calls += 1
        raise psycopg.errors.UndefinedTable("relation finn.ingest_runs does not exist")


def test_health_never_errors_even_on_a_misconfigured_database(settings, ticker, caplog):
    with TestClient(create_app(settings, database=BrokenDatabase(), monotonic=ticker)) as c:  # type: ignore[arg-type]
        r = c.get("/health")
    assert r.status_code == 200 and r.json()["db"] is False
    assert "health check failed: UndefinedTable" in caplog.text
