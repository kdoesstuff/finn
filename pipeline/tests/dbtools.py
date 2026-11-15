"""Helpers for tests that need a Postgres shaped like Supabase (fixtures are in conftest.py).

`scratch_database` is also used by the API's tests (api/tests), so both suites test against the
same shape of database."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import errors, sql

SUPER_URL = os.environ.get("FINN_TEST_DB_URL", "")

ADMIN, ADMIN_PASSWORD = "supa_admin", "test-only-password"
API_ROLES = ("anon", "authenticated", "service_role")
INVESTOR_A, INVESTOR_B = uuid.UUID(int=0xA), uuid.UUID(int=0xB)


def with_db(url: str, dbname: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc
    if user:
        host = netloc.rsplit("@", 1)[-1]
        netloc = f"{user}:{password}@{host}"
    return urlunsplit((parts.scheme, netloc, f"/{dbname}", parts.query, parts.fragment))


def needs_postgres() -> None:
    if SUPER_URL:
        return
    if os.environ.get("CI"):
        raise RuntimeError("FINN_TEST_DB_URL must be set in CI: database tests may not be skipped there")
    pytest.skip("FINN_TEST_DB_URL not set: no Postgres to test against")


@contextmanager
def scratch_database() -> Iterator[str]:
    """A new, empty database shaped like Supabase, dropped afterwards; yields its name.

    A non-superuser admin that logs in with a password (as Supabase's `postgres` does), the
    Supabase API roles (anon, authenticated, service_role), and pgvector pre-installed in
    `extensions`. Skips (or, in CI, fails) without FINN_TEST_DB_URL."""
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
    try:
        with psycopg.connect(with_db(SUPER_URL, name), autocommit=True) as su:
            su.execute("create schema extensions")
            su.execute("create extension vector with schema extensions")  # Supabase ships it enabled
            su.execute(f"grant usage on schema extensions to {ADMIN} with grant option")
        yield name
    finally:
        with psycopg.connect(SUPER_URL, autocommit=True) as su:
            su.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


def admin_url(dbname: str) -> str:
    """How the pipeline and the API log in to a scratch database: as the non-superuser admin."""
    return with_db(SUPER_URL, dbname, ADMIN, ADMIN_PASSWORD)


def denied(conn: psycopg.Connection, statement: str | sql.Composed, params: list | None = None) -> bool:
    try:
        with conn.transaction():
            conn.execute(statement, params)
    except errors.InsufficientPrivilege:
        return True
    return False


def select_from(table: str) -> sql.Composed:
    return sql.SQL("select 1 from finn.{} limit 1").format(sql.Identifier(table))


def finn_tables(conn) -> list[str]:
    return [r[0] for r in conn.execute("select tablename from pg_tables where schemaname = 'finn' order by 1")]
