"""Helpers for tests that need a Postgres shaped like Supabase (fixtures are in conftest.py)."""

from __future__ import annotations

import os
import uuid
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
