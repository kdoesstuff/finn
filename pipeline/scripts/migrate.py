"""Apply and verify the database schema.

    python scripts/migrate.py status    # applied and pending migrations
    python scripts/migrate.py apply     # apply pending migrations, then verify
    python scripts/migrate.py verify    # check the access rules on the live database

`verify` checks from the outside what the tests prove on a scratch database: every table has
row-level security on; the pipeline and API roles can use pgvector; and neither the publishable
key nor the secret key can read any FINN table through Supabase's REST API. Exits 1 on any failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finn import config, db  # noqa: E402

TABLES_TO_PROBE = ("filings", "holdings", "investors", "notes", "llm_cache")


def status(conn) -> int:
    done = db.applied(conn)
    for m in db.migrations():
        mark = "applied" if m.name in done else "PENDING"
        if m.name in done and done[m.name] != m.sha256:
            mark = "EDITED AFTER APPLY"
        print(f"{mark:<19} {m.name}")
    return 0


def rest_refuses(key_name: str, table: str) -> tuple[bool, str]:
    """True if Supabase's REST API refuses to read finn.<table> with this key."""
    url = f"{config.require('SUPABASE_URL').rstrip('/')}/rest/v1/{table}"
    key = config.require(key_name)
    r = requests.get(url, params={"limit": 1}, timeout=20,
                     headers={"apikey": key, "Accept-Profile": "finn", "Accept": "application/json"})
    if r.status_code < 400:
        return False, f"HTTP {r.status_code}: readable"
    code = ""
    try:
        code = r.json().get("code", "")
    except ValueError:
        pass
    return True, f"HTTP {r.status_code} {code}".strip()


def verify(conn) -> int:
    failures = 0

    def report(ok: bool, what: str, detail: str = "") -> None:
        nonlocal failures
        failures += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {what}{': ' + detail if detail else ''}")

    missing = db.tables_without_rls(conn)
    report(not missing, "row-level security on every table", ", ".join(missing))
    pending = [m.name for m in db.migrations() if m.name not in db.applied(conn)]
    report(not pending, "no pending migrations", ", ".join(pending))
    for api_role in ("anon", "authenticated", "service_role"):
        held = db.api_role_privileges(conn, api_role)
        report(not held, f"{api_role} holds no privilege on any finn table", ", ".join(held[:6]))
    for role in db.ROLES:
        try:
            with db.as_role(conn, role):
                conn.execute("select '[1,2,3]'::vector(3) <=> '[1,2,4]'::vector(3)")
            report(True, f"{role} can use pgvector")
        except Exception as exc:  # noqa: BLE001 - every check reports and the run carries on
            report(False, f"{role} can use pgvector", f"{type(exc).__name__}: {exc}"[:160])
    for key_name in ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY"):
        for table in TABLES_TO_PROBE:
            try:
                ok, detail = rest_refuses(key_name, table)
            except requests.RequestException as exc:
                ok, detail = False, f"could not reach the REST API ({type(exc).__name__})"
            report(ok, f"REST API refuses finn.{table} with {key_name}", detail)
    print(f"\n{'All checks passed' if not failures else f'{failures} check(s) failed'}.")
    return 1 if failures else 0


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command not in ("status", "apply", "verify"):
        print(__doc__)
        return 2
    with db.connect() as conn:
        if command == "status":
            return status(conn)
        if command == "apply":
            applied = db.migrate(conn)
            print("Applied: " + (", ".join(applied) if applied else "nothing (already up to date)") + "\n")
        return verify(conn)


if __name__ == "__main__":
    sys.exit(main())
