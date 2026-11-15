"""The database schema and its access rules, tested on a real Postgres shaped like Supabase
(fixtures in conftest.py)."""

from __future__ import annotations

import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from psycopg import errors, sql

from finn import db
from finn.alerts import Thresholds
from finn.rank import Prefs
from tests.dbtools import ADMIN, API_ROLES, INVESTOR_A, INVESTOR_B, denied, finn_tables, select_from

# Migrations -------------------------------------------------------------------------------------

def test_running_migrations_again_changes_nothing(admin):
    assert db.migrate(admin) == []
    assert sorted(db.applied(admin)) == [m.name for m in db.migrations()]


def test_an_edited_migration_is_refused(admin, tmp_path: Path):
    for m in db.migrations():
        (tmp_path / m.name).write_text(m.text + "\n-- edited\n", encoding="utf-8")
    with pytest.raises(db.MigrationError, match="edited"):
        db.migrate(admin, tmp_path)


def test_a_database_ahead_of_the_code_is_refused(admin, tmp_path: Path):
    with pytest.raises(db.MigrationError, match="does not"):
        db.migrate(admin, tmp_path)


def test_migration_files_are_named_in_order(tmp_path: Path):
    shutil.copy(db.MIGRATIONS / "0001_foundation.sql", tmp_path / "foundation.sql")
    with pytest.raises(db.MigrationError, match="NNNN"):
        db.migrations(tmp_path)


# Access rules -----------------------------------------------------------------------------------

def test_every_table_has_row_level_security(admin):
    assert db.tables_without_rls(admin) == []


@pytest.mark.parametrize("role", API_ROLES)
def test_supabase_api_roles_reach_nothing(superuser, role):
    # The publishable key acts as anon, a signed-in browser user as authenticated, the secret key as
    # service_role (which bypasses row-level security). None of them is granted anything in finn.
    for table in finn_tables(superuser):
        superuser.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        try:
            assert denied(superuser, select_from(table)), (role, table)
        finally:
            superuser.execute("reset role")
            superuser.rollback()


@pytest.mark.parametrize("role", API_ROLES)
def test_supabase_api_roles_hold_no_privilege_on_any_table(admin, role):
    # Stricter than trying a read: the schema-level block would hide a stray table grant, and a
    # later change to the schema's privileges would then expose it. No grant may exist at all.
    assert db.api_role_privileges(admin, role) == []


def test_a_stray_grant_is_reported(superuser):
    superuser.execute("grant select on finn.filings to anon")
    try:
        assert db.api_role_privileges(superuser, "anon") == ["filings:select"]
    finally:
        superuser.execute("revoke select on finn.filings from anon")
        superuser.commit()


def test_coverage_is_public_market_data_the_api_may_extend(admin):
    with db.as_role(admin, "finn_api"):
        admin.execute("insert into finn.coverage (symbol, reason) values ('POLYCAB', 'research')")
    with db.as_role(admin, "finn_ingest"):
        assert admin.execute("select reason from finn.coverage where symbol = 'POLYCAB'").fetchone() == ("research",)
        assert denied(admin, "insert into finn.coverage (symbol, reason) values ('DIXON', 'research')")


def test_ingest_writes_market_data_and_never_sees_investors(admin):
    with db.as_role(admin, "finn_ingest"):
        admin.execute("""insert into finn.filings (seq_id, symbol, company, ts, label, subject)
                         values ('9001', 'TCS', 'Tata Consultancy Services Limited', now(), 'Updates', 'x')""")
        assert admin.execute("select count(*) from finn.filings where seq_id = '9001'").fetchone() == (1,)
    with db.as_role(admin, "finn_ingest"):
        for table in ("investors", "holdings", "prefs", "notes"):
            assert denied(admin, select_from(table)), table


def test_api_reads_market_data_but_cannot_change_it(admin):
    with db.as_role(admin, "finn_api"):
        assert admin.execute("select count(*) from finn.filings").fetchone()[0] >= 1
        assert denied(admin, "update finn.filings set subject = 'tampered'")
        assert denied(admin, "delete from finn.prices_eod")
        assert denied(admin, "insert into finn.investors (display_name) values ('intruder')")


def test_an_investor_sees_only_their_own_rows(admin):
    with db.as_role(admin, "finn_api", INVESTOR_A):
        assert admin.execute("select symbol, thesis from finn.holdings").fetchall() == [("TCS", "A thesis")]
        assert admin.execute("select display_name from finn.investors").fetchall() == [("A",)]


def test_without_a_scope_no_investor_rows_are_visible(admin):
    with db.as_role(admin, "finn_api"):
        assert admin.execute("select count(*) from finn.holdings").fetchone() == (0,)
        assert admin.execute("select count(*) from finn.investors").fetchone() == (0,)


def test_an_investor_cannot_write_or_change_another_investors_rows(admin):
    with db.as_role(admin, "finn_api", INVESTOR_A):
        assert denied(admin, "insert into finn.holdings (investor_id, symbol) values (%s, 'LT')", [INVESTOR_B])
    with db.as_role(admin, "finn_api", INVESTOR_A):
        assert admin.execute("update finn.holdings set thesis = 'x' where investor_id = %s",
                             [INVESTOR_B]).rowcount == 0
        assert admin.execute("delete from finn.holdings where investor_id = %s", [INVESTOR_B]).rowcount == 0
    assert admin.execute("select thesis from finn.holdings where investor_id = %s",
                         [INVESTOR_B]).fetchall() == [("B thesis",)]


def test_an_investor_can_keep_their_own_notes(admin):
    with db.as_role(admin, "finn_api", INVESTOR_A):
        admin.execute("insert into finn.notes (investor_id, symbol, kind, body) values (%s, 'TCS', 'decision', 'Hold')",
                      [INVESTOR_A])
    with db.as_role(admin, "finn_api", INVESTOR_B):
        assert admin.execute("select count(*) from finn.notes").fetchone() == (0,)


def test_role_and_scope_end_with_the_transaction(admin):
    with db.as_role(admin, "finn_api", INVESTOR_A):
        pass
    who, scope = admin.execute("select current_user, current_setting('finn.investor_id', true)").fetchone()
    assert who == ADMIN and not scope


def test_switching_role_inside_an_open_transaction_is_refused(admin):
    # Inside an open transaction the block would only be a savepoint, and `set local role`
    # would outlive it: the API role (and an investor's scope) would leak into what follows.
    with admin.transaction():
        with pytest.raises(RuntimeError, match="no open transaction"):
            with db.as_role(admin, "finn_api", INVESTOR_A):
                pass


def test_as_role_refuses_unknown_roles_and_scoped_ingest(admin):
    with pytest.raises(ValueError):
        with db.as_role(admin, "postgres"):
            pass
    with pytest.raises(ValueError):
        with db.as_role(admin, "finn_ingest", INVESTOR_A):
            pass


# Constraints ------------------------------------------------------------------------------------

@pytest.mark.parametrize("statement", [
    # a nine-month period is the year-to-date trap, never a quarter
    """insert into finn.results (symbol, quarter_end, consolidated, template, period_start, period_end, broadcast,
                                  xbrl_url, figures)
       values ('TCS', '2026-12-31', true, 'general', '2026-04-01', '2026-12-31', now(), 'https://x/y.xml', '{}')""",
    "insert into finn.filings (seq_id, symbol, company, ts) values ('9002', 'tcs; drop', 'x', now())",
    "insert into finn.filings (seq_id, symbol, company, ts, url) values ('9003', 'TCS', 'x', now(), 'http://x')",
    "insert into finn.prices_eod (symbol, day, close, volume) values ('TCS', '2026-11-11', -1, 0)",
])
def test_bad_data_is_refused(admin, statement):
    with pytest.raises(errors.CheckViolation):
        with db.as_role(admin, "finn_ingest"):
            admin.execute(statement)


def test_prefs_defaults_match_the_code(admin):
    with db.as_role(admin, "finn_api", INVESTOR_A):
        admin.execute("insert into finn.prefs (investor_id) values (%s)", [INVESTOR_A])
        row = admin.execute("""select window_hours, volume_multiple, move_pct, move_sigma, move_rule, alert_categories
                               from finn.prefs""").fetchone()
    t, p = Thresholds(), Prefs()
    assert row[0] == 24
    assert (float(row[1]), float(row[2]), float(row[3]), row[4]) == (t.volume_multiple, t.move_pct, t.move_sigma,
                                                                     t.move_rule)
    assert set(row[5]) == p.alert_categories


# Retrieval --------------------------------------------------------------------------------------

def unit(i: int) -> str:
    v = [0.0] * 768
    v[i] = 1.0
    return "[" + ",".join(str(x) for x in v) + "]"


def test_nearest_chunk_by_cosine_distance(admin):
    with db.as_role(admin, "finn_ingest"):
        doc = admin.execute("""insert into finn.documents (symbol, kind, url, published)
                               values ('TCS', 'transcript', 'https://example.org/t.pdf', %s) returning id""",
                            [date(2026, 10, 9)]).fetchone()[0]
        for ord_, axis in enumerate((0, 1, 2)):
            admin.execute("insert into finn.chunks (document_id, page, ord, text, embedding) "
                          "values (%s, %s, %s, %s, %s)", [doc, ord_ + 1, ord_, f"chunk {axis}", unit(axis)])
    with db.as_role(admin, "finn_api"):
        best = admin.execute("select text, page from finn.chunks order by embedding <=> %s::vector limit 1",
                             [unit(1)]).fetchone()
    assert best == ("chunk 1", 2)


def test_a_wrong_sized_embedding_is_refused(admin):
    with pytest.raises(errors.DataException):
        with db.as_role(admin, "finn_ingest"):
            admin.execute("""insert into finn.chunks (document_id, page, ord, text, embedding)
                             select id, 1, 99, 'x', '[1,2,3]' from finn.documents limit 1""")


def test_timestamps_are_stored_with_their_zone(admin):
    ist = datetime(2026, 11, 6, 22, 6, 58).replace(tzinfo=timezone.utc)
    with db.as_role(admin, "finn_ingest"):
        admin.execute("insert into finn.filings (seq_id, symbol, company, ts) values ('9004', 'ASIANPAINT', 'x', %s)",
                      [ist])
        assert admin.execute("select ts from finn.filings where seq_id = '9004'").fetchone()[0] == ist
