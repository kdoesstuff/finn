"""Shared fixtures: a disposable Postgres shaped like Supabase, for database and ingest tests.

A non-superuser admin that logs in with a password (as Supabase's `postgres` does), the Supabase
API roles (anon, authenticated, service_role), and pgvector pre-installed in `extensions`.

Needs FINN_TEST_DB_URL, a superuser URL for a disposable server. CI always sets it (and fails if
it is missing); on a laptop without Postgres, tests that need it are skipped with that reason.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from finn import db
from tests.dbtools import ADMIN, ADMIN_PASSWORD, INVESTOR_A, INVESTOR_B, SUPER_URL, needs_postgres, with_db


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    needs_postgres()
    name = f"finn_test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(SUPER_URL, autocommit=True) as su:
        existing = {r[0] for r in su.execute("select rolname from pg_roles")}
        if ADMIN not in existing:
            su.execute(sql.SQL("create role {} login createrole nosuperuser password {}").format(
                sql.Identifier(ADMIN), sql.Literal(ADMIN_PASSWORD)))
        for role, extra in (("anon", ""), ("authenticated", ""), ("service_role", " bypassrls")):
            if role not in existing:
                su.execute(sql.SQL("create role {} nologin" + extra).format(sql.Identifier(role)))
        su.execute(sql.SQL("create database {} owner {}").format(sql.Identifier(name), sql.Identifier(ADMIN)))
    with psycopg.connect(with_db(SUPER_URL, name), autocommit=True) as su:
        su.execute("create schema extensions")
        su.execute("create extension vector with schema extensions")  # Supabase ships it enabled
        su.execute(f"grant usage on schema extensions to {ADMIN} with grant option")
    yield name
    with psycopg.connect(SUPER_URL, autocommit=True) as su:
        su.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


@pytest.fixture(scope="module")
def admin(database: str) -> Iterator[psycopg.Connection]:
    conn = db.connect(with_db(SUPER_URL, database, ADMIN, ADMIN_PASSWORD))
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
