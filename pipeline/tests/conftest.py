"""Shared fixtures: a disposable Postgres shaped like Supabase, for database and ingest tests.

A non-superuser admin that logs in with a password (as Supabase's `postgres` does), the Supabase
API roles (anon, authenticated, service_role), and pgvector pre-installed in `extensions`.

Needs FINN_TEST_DB_URL, a superuser URL for a disposable server. CI always sets it (and fails if
it is missing); on a laptop without Postgres, tests that need it are skipped with that reason.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from finn import db
from tests.dbtools import INVESTOR_A, INVESTOR_B, SUPER_URL, admin_url, scratch_database, with_db


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with scratch_database() as name:
        yield name


@pytest.fixture(scope="module")
def admin(database: str) -> Iterator[psycopg.Connection]:
    conn = db.connect(admin_url(database))
    assert db.migrate(conn) == [m.name for m in db.migrations()]
    with conn.transaction():
        conn.execute("insert into finn.investors (id, display_name, is_demo) values (%s, 'A', true), (%s, 'B', false)",
                     [INVESTOR_A, INVESTOR_B])
        conn.execute("insert into finn.holdings (investor_id, symbol, thesis) values "
                     "(%s, 'TCS', 'A thesis'), (%s, 'MRF', 'B thesis')", [INVESTOR_A, INVESTOR_B])
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def superuser(database: str, admin: psycopg.Connection) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(with_db(SUPER_URL, database))
    yield conn
    conn.close()
