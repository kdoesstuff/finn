"""Database access: connecting, migrations, and least-privilege roles.

Connections use SUPABASE_DB_URL (the Supabase session pooler: IPv4, session mode, so SET ROLE and
settings hold for the whole session). Work never runs as the connecting admin: `as_role` switches
to finn_ingest or finn_api inside a transaction, and for investor data also sets the investor the
request is scoped to, which row-level security checks on every row.

Migrations are plain SQL files in db/migrations, applied in name order, each in its own
transaction, recorded with a checksum. A migration that was applied and later edited is refused:
the fix for a released migration is a new migration.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg import sql

from . import config

MIGRATIONS = config.ROOT / "db" / "migrations"
ROLES = ("finn_ingest", "finn_api")
SEARCH_PATH = "finn, extensions, public"
_NAME = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
_LOCK = 72_116_101  # advisory lock id: one migration run at a time


class MigrationError(RuntimeError):
    pass


def connect(url: str | None = None) -> psycopg.Connection:
    """A connection with the schema search path set, in autocommit mode: every unit of work opens
    its own transaction (`as_role`, `migrate`), so nothing set inside one can outlive it."""
    conn = psycopg.connect(url or config.require("SUPABASE_DB_URL"), connect_timeout=10,
                           application_name="finn", autocommit=True)
    conn.execute(f"set search_path = {SEARCH_PATH}")
    return conn


@contextmanager
def as_role(conn: psycopg.Connection, role: str, investor_id: UUID | None = None) -> Iterator[psycopg.Connection]:
    """One transaction as a least-privilege role, optionally scoped to one investor.

    `set local` ends with the transaction, so a pooled connection never carries a role or an
    investor into the next request. That only holds for a real transaction: inside one already
    open, this block would be a savepoint and the role would outlast it, so that is refused."""
    if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        raise RuntimeError("as_role needs a connection with no open transaction (use db.connect: autocommit)")
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    if investor_id is not None and role != "finn_api":
        raise ValueError("only finn_api reads investor data")
    with conn.transaction():
        conn.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
        if investor_id is not None:
            conn.execute("select set_config('finn.investor_id', %s, true)", [str(UUID(str(investor_id)))])
        yield conn


@dataclass
class Migration:
    name: str
    sha256: str
    text: str


def migrations(directory: Path = MIGRATIONS) -> list[Migration]:
    out = []
    for path in sorted(directory.glob("*.sql")):
        if not _NAME.match(path.name):
            raise MigrationError(f"{path.name}: migration files are named NNNN_words.sql")
        text = path.read_text(encoding="utf-8")
        out.append(Migration(path.name, hashlib.sha256(text.encode()).hexdigest(), text))
    return out


def _ensure_table(conn: psycopg.Connection) -> None:
    conn.execute("create schema if not exists finn")
    conn.execute("""create table if not exists finn.schema_migrations (
                      name text primary key, sha256 text not null, applied_at timestamptz not null default now())""")
    conn.execute("alter table finn.schema_migrations enable row level security")
    conn.execute("revoke all on finn.schema_migrations from public")


def applied(conn: psycopg.Connection) -> dict[str, str]:
    exists = conn.execute("select to_regclass('finn.schema_migrations') is not null").fetchone()
    if not exists or not exists[0]:
        return {}
    return dict(conn.execute("select name, sha256 from finn.schema_migrations").fetchall())


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS) -> list[str]:
    """Apply every pending migration; return the names applied. Refuses edited migrations."""
    done: list[str] = []
    with conn.transaction():
        conn.execute("select pg_advisory_xact_lock(%s)", [_LOCK])
        _ensure_table(conn)
        already = applied(conn)
        files = migrations(directory)
        for m in files:
            if m.name in already and already[m.name] != m.sha256:
                raise MigrationError(f"{m.name} was applied and has since been edited; add a new migration instead")
        unknown = set(already) - {m.name for m in files}
        if unknown:
            raise MigrationError(f"the database has migrations this code does not: {sorted(unknown)}")
        for m in files:
            if m.name in already:
                continue
            try:
                conn.execute(m.text.encode())  # whole file, no parameters: simple query protocol
            except psycopg.Error as exc:
                raise MigrationError(f"{m.name}: {exc}") from exc
            conn.execute("insert into finn.schema_migrations (name, sha256) values (%s, %s)", [m.name, m.sha256])
            conn.execute(f"set search_path = {SEARCH_PATH}")
            done.append(m.name)
    return done


def tables_without_rls(conn: psycopg.Connection) -> list[str]:
    """Every table in schema finn must have row-level security on; this lists any that do not."""
    rows = conn.execute("""select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           where n.nspname = 'finn' and c.relkind in ('r', 'p') and not c.relrowsecurity
                           order by 1""").fetchall()
    return [r[0] for r in rows]


def api_role_privileges(conn: psycopg.Connection, role: str) -> list[str]:
    """Privileges a Supabase API role holds on tables in schema finn, as "table:privilege".
    Must be empty: the REST API reaches the database as these roles. Empty too where the role
    does not exist (a plain Postgres)."""
    exists = conn.execute("select 1 from pg_roles where rolname = %s", [role]).fetchone()
    if not exists:
        return []
    rows = conn.execute("""select c.relname || ':' || p.priv
                           from pg_class c join pg_namespace n on n.oid = c.relnamespace
                           cross join unnest(array['select', 'insert', 'update', 'delete']) as p(priv)
                           where n.nspname = 'finn' and c.relkind in ('r', 'p', 'v', 'm')
                             and has_table_privilege(%s, c.oid, p.priv)
                           order by 1""", [role]).fetchall()
    usage = conn.execute("select has_schema_privilege(%s, 'finn', 'usage')", [role]).fetchone()
    return [r[0] for r in rows] + (["schema:usage"] if usage and usage[0] else [])
