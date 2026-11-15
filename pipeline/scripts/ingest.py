"""Run an ingest job. The scheduled workflow (.github/workflows/ingest.yml) calls this.

    python scripts/ingest.py filings [--days 2]          announcements, then results for covered filers
    python scripts/ingest.py eod [--days 7] [--refetch]  end-of-day prices and the trading calendar
    python scripts/ingest.py daily                       equity list, pledges, board meetings, actions, results
    python scripts/ingest.py results SYMBOL [SYMBOL ...] results for named companies
    python scripts/ingest.py backfill --from 2026-10-01 --to 2026-11-15 [--prices-from 2026-06-25]
    python scripts/ingest.py seed                        create the demo investor, holdings and coverage
    python scripts/ingest.py status                      last run of each job, rows per table, database size
    python scripts/ingest.py verify [--live] [--quarter 2026-09-30] [--since 2026-10-01]
                                                         is every covered company's data complete and right?
    python scripts/ingest.py import-pledges FILE         a saved response of NSE's pledge feed, for when
                                                         the live feed is down (keeps NSE's publication time)

Exits 1 if the job failed or reported errors, so the workflow goes red.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finn import db, ingest, seed, verify  # noqa: E402
from finn.sources.client import NSEClient  # noqa: E402

TABLES = ("filings", "results", "prices_eod", "trading_days", "pledges", "board_meetings", "corporate_actions",
          "companies", "coverage", "ingest_runs")


def day(text: str) -> date:
    return date.fromisoformat(text)


def symbol(text: str) -> str:
    if not re.fullmatch(r"[A-Z0-9&-]{1,20}", text):
        raise argparse.ArgumentTypeError(f"not an NSE symbol: {text!r}")
    return text


def report(name: str, counts: Any) -> int:
    """Errors first, up to 40 of them, so a long run's cut-off counts can never hide why it failed;
    then warnings; then the counts. Exit status 1 if there were any errors; warnings never fail a run
    (under GitHub Actions they are annotations on the run)."""
    errors = (counts.get("errors") or []) if isinstance(counts, dict) else []
    warnings = (counts.get("warnings") or []) if isinstance(counts, dict) else []
    head = f"{name}: {'FAILED, ' + str(len(errors)) + ' error(s)' if errors else 'OK'}"
    shown = errors[:40] + ([f"... and {len(errors) - 40} more (all of them are in finn.ingest_runs)"]
                           if len(errors) > 40 else [])
    lines = [head] + [f"  error: {e}" for e in shown] + [f"  warning: {w}" for w in warnings]
    if os.environ.get("GITHUB_ACTIONS") == "true":
        lines += [f"::warning title={name}::{w}" for w in warnings]
    text = ingest.summary(counts)
    print("\n".join(lines) + f"\n{text}")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"### {head}\n\n" + "".join(f"- {e}\n" for e in shown)
                     + "".join(f"- warning: {w}\n" for w in warnings) + f"\n```json\n{text}\n```\n")
    return 1 if errors else 0


def status(conn: Any) -> int:
    with db.as_role(conn, "finn_ingest"):
        runs = conn.execute("""select distinct on (split_part(job, ' ', 1)) split_part(job, ' ', 1), started_at,
                                      finished_at, ok,
                                      left(coalesce(error, array_to_string(array(
                                        select jsonb_array_elements_text(counts -> 'errors')), ' | '), ''), 400)
                               from finn.ingest_runs order by split_part(job, ' ', 1), started_at desc""").fetchall()
        counts = {t: conn.execute(sql.SQL("select count(*) from finn.{}").format(sql.Identifier(t))).fetchone()[0]
                  for t in TABLES}
    size = conn.execute("select pg_size_pretty(pg_database_size(current_database()))").fetchone()
    print("Last run of each job (IST):")
    for job, started, finished, ok, error in runs:
        state = "running" if finished is None else ("ok" if ok else "FAILED")
        print(f"  {job:<9} {started.astimezone(ingest.IST):%d %b %H:%M}  {state}  {error}")
    print("Rows: " + ", ".join(f"{t} {n:,}" for t, n in counts.items()))
    print(f"Database size: {size[0] if size else '?'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="job", required=True)
    f = sub.add_parser("filings")
    f.add_argument("--days", type=int, default=2, choices=range(1, 15))
    e = sub.add_parser("eod")
    e.add_argument("--days", type=int, default=7, choices=range(1, 32))
    e.add_argument("--refetch", action="store_true")
    sub.add_parser("daily")
    r = sub.add_parser("results")
    r.add_argument("symbols", nargs="+", type=symbol)
    b = sub.add_parser("backfill")
    b.add_argument("--from", dest="start", type=day, required=True)
    b.add_argument("--to", dest="end", type=day, required=True)
    b.add_argument("--prices-from", dest="prices_start", type=day)
    sub.add_parser("seed")
    sub.add_parser("status")
    ip = sub.add_parser("import-pledges")
    ip.add_argument("file", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("--live", action="store_true", help="ask NSE why a missing quarter is missing")
    v.add_argument("--quarter", type=day, default=date(2026, 9, 30))
    v.add_argument("--since", type=day, default=date(2026, 10, 1))
    args = p.parse_args()

    today = datetime.now(ingest.IST).date()
    with db.connect() as conn:
        if args.job == "status":
            return status(conn)
        if args.job == "seed":
            return report("seed", seed.seed_demo(conn))
        if args.job == "import-pledges":
            return report("import-pledges", ingest.import_pledges(conn, args.file))
        if args.job == "verify":
            result = verify.check(conn, args.quarter, args.since, NSEClient() if args.live else None)
            text = verify.render(result)
            print(text)
            summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_path:
                with open(summary_path, "a", encoding="utf-8") as fh:
                    fh.write(f"### verify\n\n```\n{text}\n```\n")
            return 1 if result.failures else 0
        source = NSEClient()
        if args.job == "filings":
            return report("filings", ingest.ingest_filings(conn, source, today - timedelta(days=args.days - 1), today))
        if args.job == "eod":
            days = [today - timedelta(days=i) for i in range(args.days)]
            return report("eod", ingest.ingest_eod(conn, source, days, refetch=args.refetch))
        if args.job == "daily":
            return report("daily", ingest.ingest_daily(conn, source, today))
        if args.job == "results":
            out = {s: ingest.ingest_results(conn, source, s) for s in args.symbols}
            return report("results", {"results": out, "errors": [s for s, v in out.items() if v.get("error")]})
        if args.start > args.end or (args.end - args.start).days > 400:
            p.error("--from must be before --to, and the range at most 400 days")
        return report("backfill", ingest.backfill(conn, source, args.start, args.end, args.prices_start))


if __name__ == "__main__":
    sys.exit(main())
