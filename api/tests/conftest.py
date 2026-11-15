"""Fixtures for the API's tests.

One Supabase-shaped scratch database for the whole run (built by the pipeline's own helper,
`tests.dbtools.scratch_database`, so both suites test the same shape), migrated, with the demo
investor seeded exactly as `ingest.py seed` does, a second investor with other holdings, the real
week of NSE filings stored through ingest, and one successful filings run in the run log.

Each test gets a fresh app (its own rate limiter, health cache and pool) with a fixed clock, so
the digest window and token expiry are reproducible. Secrets here are obviously fake.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.settings import Settings
from api.tests.helpers import CORE, DATA_AS_OF, FULL, OTHER, OTHER_HOLDINGS, SECRET, Clock, Ticker, fixture_rows
from finn import db, digest, ingest, seed
from tests.dbtools import admin_url, scratch_database


@pytest.fixture(scope="session")
def database() -> Iterator[str]:
    with scratch_database() as name:
        yield name


@pytest.fixture(scope="session")
def admin(database: str) -> Iterator[psycopg.Connection]:
    conn = db.connect(admin_url(database))
    db.migrate(conn)
    seed.seed_demo(conn)
    with conn.transaction():
        conn.execute("insert into finn.investors (id, display_name, is_demo) values (%s, 'Another investor', false)",
                     [OTHER])
    with db.as_role(conn, "finn_api", OTHER):
        for symbol in sorted(OTHER_HOLDINGS):
            conn.execute("insert into finn.holdings (investor_id, symbol) values (%s, %s)", [OTHER, symbol])
    assert ingest.store_filings(conn, fixture_rows())["unusable"] == 0
    with db.as_role(conn, "finn_ingest"):
        conn.execute("""insert into finn.ingest_runs (job, started_at, finished_at, ok)
                        values ('filings 2026-11-08..2026-11-09', %s, %s, true)""",
                     [datetime(2026, 11, 9, 23, 30, tzinfo=digest.IST),
                      datetime.fromisoformat(DATA_AS_OF)])
    yield conn
    conn.close()


@pytest.fixture
def settings(admin: psycopg.Connection, database: str) -> Settings:
    return Settings(db_url=admin_url(database), session_secret=SECRET, origins_core=(CORE,), origins_full=(FULL,),
                    version="abc1234", health_wait_s=1.0, pool_wait_s=2.0)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def ticker() -> Ticker:
    return Ticker()


@pytest.fixture
def client(settings: Settings, clock: Clock, ticker: Ticker) -> Iterator[TestClient]:
    with TestClient(create_app(settings, clock=clock, monotonic=ticker)) as c:
        yield c
