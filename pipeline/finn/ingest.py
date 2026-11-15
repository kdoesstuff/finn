"""Ingest: fetch from NSE and store, idempotently, as the least-privilege role finn_ingest.

Every job is safe to run again: filings are keyed by NSE's own id, prices by (symbol, day),
results by (symbol, quarter, basis), and an unchanged row is left alone. Each job writes one row to
finn.ingest_runs with its counts, or with the error that stopped it, so a missed run is visible.

Jobs (scripts/ingest.py runs them; .github/workflows/ingest.yml schedules them):
  filings   the last two days of announcements, market-wide; then results for covered companies
            that filed results in that window; then any filings classified by older rules
  eod       end-of-day prices for recent days not yet recorded; a day without a bhavcopy is
            recorded as not a session
  daily     equity master, pledges, board meetings, corporate actions and a results sweep
  backfill  all of the above over a date range
"""

from __future__ import annotations

import hashlib
import json
import re
import traceback
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from . import db
from .classify import classify
from .sources import nse
from .sources.client import Source, SourceError
from .xbrl import parse as parse_xbrl

IST = timezone(timedelta(hours=5, minutes=30))  # India keeps no daylight saving: a fixed offset is exact
RESULT_QUARTERS = 9  # eight quarters of trajectory, plus the year-ago quarter for the oldest YoY
RECLASSIFY_BATCH = 5000

_RULE_FILES = ("classify.py", "taxonomy.py", "text.py")
RULE_VERSION = hashlib.sha256(
    b"".join((Path(__file__).parent / f).read_bytes() for f in _RULE_FILES)).hexdigest()[:12]


def _scalar(row: tuple[Any, ...] | None) -> Any:
    if row is None:
        raise RuntimeError("expected one row, got none")
    return row[0]


def ist(naive: datetime) -> datetime:
    """NSE timestamps are Indian time without a zone; store them with it."""
    return naive.replace(tzinfo=IST) if naive.tzinfo is None else naive


# Run log ------------------------------------------------------------------------------------------

@contextmanager
def run(conn: psycopg.Connection, job: str) -> Iterator[dict[str, Any]]:
    """Record a job in finn.ingest_runs. The body fills `counts`; an exception is recorded, then raised."""
    with db.as_role(conn, "finn_ingest"):
        run_id = _scalar(conn.execute("insert into finn.ingest_runs (job) values (%s) returning id", [job]).fetchone())
    counts: dict[str, Any] = {}
    try:
        yield counts
    except Exception as exc:
        with db.as_role(conn, "finn_ingest"):
            conn.execute("""update finn.ingest_runs set finished_at = now(), ok = false, counts = %s, error = %s
                            where id = %s""",
                         [Jsonb(counts), f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}", run_id])
        raise
    with db.as_role(conn, "finn_ingest"):
        ok = not counts.get("errors")
        conn.execute("update finn.ingest_runs set finished_at = now(), ok = %s, counts = %s where id = %s",
                     [ok, Jsonb(counts), run_id])


# Companies ----------------------------------------------------------------------------------------

def store_companies(conn: psycopg.Connection, companies: Iterable[nse.Company]) -> int:
    """Upsert symbol, name, ISIN and industry; a known value is never replaced by a blank one."""
    unique = {c.symbol: c for c in companies if re.fullmatch(r"[A-Z0-9&-]{1,20}", c.symbol)}
    if not unique:
        return 0
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        cur.executemany(
            """insert into finn.companies (symbol, name, isin, industry) values (%s, %s, %s, %s)
               on conflict (symbol) do update set
                 name = coalesce(excluded.name, companies.name),
                 isin = coalesce(excluded.isin, companies.isin),
                 industry = coalesce(excluded.industry, companies.industry),
                 updated_at = now()
               where (companies.name, companies.isin, companies.industry)
                     is distinct from (coalesce(excluded.name, companies.name),
                                       coalesce(excluded.isin, companies.isin),
                                       coalesce(excluded.industry, companies.industry))""",
            [(c.symbol, c.name, c.isin if c.isin and re.fullmatch(r"IN[A-Z0-9]{10}", c.isin) else None, c.industry)
             for c in unique.values()])
    return len(unique)


def normalise_name(name: str) -> str:
    """Company names as NSE writes them differ only in case, punctuation and "Limited"/"Ltd"."""
    words = re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split()
    while words and words[-1] in ("limited", "ltd"):
        words.pop()
    return " ".join(words)


# Filings ------------------------------------------------------------------------------------------

def _filing_row(raw: dict) -> tuple | None:
    try:
        a = nse.parse_announcement(raw)
    except (SourceError, KeyError):
        return None
    if not re.fullmatch(r"[A-Z0-9&-]{1,20}", a.symbol) or not re.fullmatch(r"[0-9A-Za-z_-]{1,40}", a.id):
        return None
    c = classify(a)
    url = a.url if a.url.startswith("https://") else ""
    return (a.id, a.symbol, a.company, ist(a.ts), a.source, a.label, a.subject, url, a.file_size,
            c.category, c.subtype, c.role, c.action, c.detail_in_document, c.needs_model, c.rule_id, RULE_VERSION)


_FILING_COLUMNS = ("seq_id", "symbol", "company", "ts", "source", "label", "subject", "url", "file_size", "category",
                   "subtype", "role", "action", "detail_in_document", "needs_model", "rule_id", "rule_version")


def _filings_upsert() -> sql.Composed:
    cols = [sql.Identifier(c) for c in _FILING_COLUMNS]
    excluded = [sql.SQL("excluded.{}").format(c) for c in cols]
    return sql.SQL("""insert into finn.filings ({cols}) values ({values})
                      on conflict (seq_id) do update set {updates}
                      where ({target}) is distinct from ({excluded})""").format(
        cols=sql.SQL(", ").join(cols),
        values=sql.SQL(", ").join([sql.Placeholder()] * len(cols)),
        updates=sql.SQL(", ").join(sql.SQL("{} = {}").format(c, e) for c, e in zip(cols[1:], excluded[1:],
                                                                                      strict=True)),
        target=sql.SQL(", ").join(sql.SQL("filings.{}").format(c) for c in cols),
        excluded=sql.SQL(", ").join(excluded))


def store_filings(conn: psycopg.Connection, raw_rows: list[dict]) -> dict[str, int]:
    """Upsert filings. The model-written summary (task C3) is never overwritten by a re-fetch."""
    rows = [r for r in (_filing_row(x) for x in raw_rows) if r]
    rows = list({r[0]: r for r in rows}.values())
    if not rows:
        return {"fetched": len(raw_rows), "stored": 0, "new": 0, "unusable": len(raw_rows)}
    ids = [r[0] for r in rows]
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        before = _scalar(cur.execute("select count(*) from finn.filings where seq_id = any(%s)", [ids]).fetchone())
        cur.executemany(_filings_upsert(), rows)
    store_companies(conn, (nse.company_from_announcement(x) for x in raw_rows if x.get("symbol")))
    return {"fetched": len(raw_rows), "stored": len(rows), "new": len(rows) - before,
            "unusable": len(raw_rows) - len(rows)}


def reclassify_stale(conn: psycopg.Connection, limit: int = RECLASSIFY_BATCH) -> int:
    """Filings classified by older rules get today's classification, a batch per run."""
    with db.as_role(conn, "finn_ingest"):
        stale = conn.execute(
            """select seq_id, symbol, company, ts, source, label, subject, url, file_size from finn.filings
               where rule_version is distinct from %s limit %s""", [RULE_VERSION, limit]).fetchall()
    if not stale:
        return 0
    updates = []
    for seq_id, symbol, company, ts, source, label, subject, url, file_size in stale:
        a = nse.Announcement(seq_id, symbol, company, ts.astimezone(IST).replace(tzinfo=None), source, label, subject,
                             url=url, file_size=file_size)
        c = classify(a)
        updates.append((c.category, c.subtype, c.role, c.action, c.detail_in_document, c.needs_model, c.rule_id,
                        RULE_VERSION, seq_id))
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        cur.executemany("""update finn.filings set category = %s, subtype = %s, role = %s, action = %s,
                             detail_in_document = %s, needs_model = %s, rule_id = %s, rule_version = %s
                           where seq_id = %s""", updates)
    return len(updates)


def covered(conn: psycopg.Connection) -> list[str]:
    with db.as_role(conn, "finn_ingest"):
        return [r[0] for r in conn.execute("select symbol from finn.coverage order by symbol").fetchall()]


def ingest_filings(conn: psycopg.Connection, source: Source, start: date, end: date) -> dict[str, Any]:
    with run(conn, f"filings {start}..{end}") as counts:
        raw = nse.announcement_rows(source, start, end)
        counts.update(store_filings(conn, raw))
        filed = {r.get("symbol") for r in raw}
        with db.as_role(conn, "finn_ingest"):
            results_filed = {r[0] for r in conn.execute(
                """select distinct symbol from finn.filings
                   where category = 'results' and subtype = 'filing' and ts >= %s and symbol = any(%s)""",
                [ist(datetime.combine(start, datetime.min.time())), list(filed)]).fetchall()}
        targets = sorted(results_filed & set(covered(conn)))
        counts["results"] = {s: ingest_results(conn, source, s) for s in targets}
        counts["reclassified"] = reclassify_stale(conn)
        counts["errors"] = [s for s, r in counts["results"].items() if r.get("error")]
    return counts


# End-of-day prices and the trading calendar -------------------------------------------------------

def store_eod(conn: psycopg.Connection, day: date, rows: list[nse.EodRow] | None) -> int:
    """Prices for one day, and whether it was a session. None means NSE published no bhavcopy."""
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        cur.execute("""insert into finn.trading_days (day, is_session) values (%s, %s)
                       on conflict (day) do update set is_session = excluded.is_session, checked_at = now()""",
                    [day, rows is not None])
        if not rows:
            return 0
        good = [r for r in rows if r.close > 0 and re.fullmatch(r"[A-Z0-9&-]{1,20}", r.symbol)]
        cur.executemany(
            """insert into finn.prices_eod (symbol, day, series, close, prev_close, volume, turnover)
               values (%s, %s, %s, %s, %s, %s, %s)
               on conflict (symbol, day) do update set series = excluded.series, close = excluded.close,
                 prev_close = excluded.prev_close, volume = excluded.volume, turnover = excluded.turnover
               where (prices_eod.close, prices_eod.volume) is distinct from (excluded.close, excluded.volume)""",
            [(r.symbol, r.day, r.series, r.close, r.prev_close if r.prev_close > 0 else None, r.volume,
              r.turnover if r.turnover >= 0 else None) for r in good])
    store_companies(conn, (nse.Company(r.symbol, isin=r.isin or None) for r in rows))
    return len(rows)


def ingest_eod(conn: psycopg.Connection, source: Source, days: Iterable[date], refetch: bool = False) -> dict:
    """Prices for each day not yet recorded (or every day, with refetch). Today is always re-checked
    until a bhavcopy appears, since NSE publishes it in the evening."""
    with run(conn, "eod") as counts:
        days = sorted(set(days))
        with db.as_role(conn, "finn_ingest"):
            known = {r[0] for r in conn.execute(
                "select day from finn.trading_days where day = any(%s) and (is_session or day < current_date - 3)",
                [days]).fetchall()}
        todo = [d for d in days if refetch or d not in known]
        counts["sessions"], counts["not_sessions"], counts["rows"] = [], [], 0
        for d in todo:
            rows = nse.bhavcopy(source, d)
            counts["rows"] += store_eod(conn, d, rows)
            counts["sessions" if rows is not None else "not_sessions"].append(d.isoformat())
    return counts


# Results ------------------------------------------------------------------------------------------

def ingest_results(conn: psycopg.Connection, source: Source, symbol: str, quarters: int = RESULT_QUARTERS) -> dict:
    """The latest revision of each recent quarter, both bases, parsed from XBRL. A quarter already
    stored from the same file is skipped; a revision replaces it. Errors are reported, not raised,
    so one company's broken file never stops the rest."""
    out: dict[str, Any] = {"stored": 0, "unchanged": 0, "missing": 0, "rejected": []}
    try:
        filings = nse.result_filings(source, symbol)
    except SourceError as exc:
        return {**out, "error": str(exc)[:200]}
    recent = sorted({f.quarter_end for f in filings}, reverse=True)[:quarters]
    wanted = [f for f in filings if f.quarter_end in recent]
    with db.as_role(conn, "finn_ingest"):
        have = {(r[0], r[1]): r[2] for r in conn.execute(
            "select quarter_end, consolidated, xbrl_url from finn.results where symbol = %s", [symbol]).fetchall()}
    for f in wanted:
        if have.get((f.quarter_end, f.consolidated)) == f.xbrl_url:
            out["unchanged"] += 1
            continue
        blob = source.content(f.xbrl_url)
        if blob is None:
            out["missing"] += 1
            continue
        try:
            parsed = parse_xbrl(blob)
        except Exception as exc:  # noqa: BLE001 - a malformed file is reported and skipped
            out["rejected"].append(f"{f.quarter_end} {'C' if f.consolidated else 'S'}: {type(exc).__name__}")
            continue
        days = (parsed.period_end - parsed.period_start).days
        if not 80 <= days <= 95:
            out["rejected"].append(f"{f.quarter_end}: {days}-day period is not a quarter")
            continue
        figures = {"facts": parsed.facts, "text": parsed.text, "audit_opinion": parsed.audit_opinion,
                   "board_meeting": parsed.board_meeting}
        with db.as_role(conn, "finn_ingest"):
            conn.execute(
                """insert into finn.results (symbol, quarter_end, consolidated, template, period_start, period_end,
                                             audited, revision, broadcast, xbrl_url, figures)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (symbol, quarter_end, consolidated) do update set template = excluded.template,
                     period_start = excluded.period_start, period_end = excluded.period_end,
                     audited = excluded.audited, revision = excluded.revision, broadcast = excluded.broadcast,
                     xbrl_url = excluded.xbrl_url, figures = excluded.figures, parsed_at = now()""",
                [symbol, f.quarter_end, f.consolidated, "bank" if parsed.bank else "general", parsed.period_start,
                 parsed.period_end, parsed.audited or f.audited, f.revision, ist(f.broadcast), f.xbrl_url,
                 Jsonb(json.loads(json.dumps(figures, default=str)))])
        out["stored"] += 1
    return out


# Daily jobs -------------------------------------------------------------------------------------

def ingest_equity_list(conn: psycopg.Connection, source: Source) -> int:
    return store_companies(conn, nse.equity_list(source))


def ingest_pledges(conn: psycopg.Connection, source: Source) -> dict[str, int]:
    pledges = nse.pledges(source)
    with db.as_role(conn, "finn_ingest"):
        by_name: dict[str, str] = {}
        for symbol, name in conn.execute("select symbol, name from finn.companies where name is not null"):
            by_name.setdefault(normalise_name(name), symbol)
    rows = []
    for p in pledges:
        rows.append((p.company, p.as_of, ist(p.broadcast) if p.broadcast else ist(datetime.combine(p.as_of,
                     datetime.min.time())), by_name.get(normalise_name(p.company)), p.promoter_holding_pct,
                     p.pledged_of_promoter_pct, p.promoter_pledged_of_total_pct, p.all_pledged_of_demat_pct,
                     p.promoter_shares, p.promoter_pledged_shares, p.issued_shares))
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        cur.executemany(
            """insert into finn.pledges (company_name, as_of, broadcast, symbol, promoter_holding_pct,
                 pledged_of_promoter_pct, promoter_pledged_of_total_pct, all_pledged_of_demat_pct, promoter_shares,
                 promoter_pledged_shares, issued_shares)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (company_name, as_of, broadcast) do update set symbol = coalesce(excluded.symbol,
                 pledges.symbol)""", rows)
    return {"rows": len(rows), "matched_to_symbol": sum(1 for r in rows if r[3])}


def ingest_board_meetings(conn: psycopg.Connection, source: Source, start: date, end: date) -> int:
    meetings = nse.board_meetings(source, start, end)
    store_companies(conn, (m.company for m in meetings if m.company))
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        cur.executemany(
            """insert into finn.board_meetings (symbol, day, purpose, description, announced)
               values (%s, %s, %s, %s, %s)
               on conflict (symbol, day, purpose) do update set description = excluded.description,
                 announced = excluded.announced""",
            [(m.symbol, m.day, m.purpose[:500], m.description[:2000], ist(m.announced) if m.announced else None)
             for m in meetings if re.fullmatch(r"[A-Z0-9&-]{1,20}", m.symbol)])
    return len(meetings)


def ingest_corporate_actions(conn: psycopg.Connection, source: Source, symbols: list[str]) -> dict[str, Any]:
    stored, errors = 0, []
    for s in symbols:
        try:
            actions = nse.corporate_actions(source, s)
        except SourceError as exc:
            errors.append(f"{s}: {exc}"[:200])
            continue
        with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
            cur.executemany("""insert into finn.corporate_actions (symbol, ex_date, subject) values (%s, %s, %s)
                               on conflict do nothing""", [(s, a.ex_date, a.subject[:500]) for a in actions])
        stored += len(actions)
    return {"rows": stored, "errors": errors}


def ingest_daily(conn: psycopg.Connection, source: Source, today: date) -> dict[str, Any]:
    """Slow-moving data, once a day. Each part is independent: one failing does not stop the rest."""
    with run(conn, "daily") as counts:
        errors: list[str] = []

        def part(name: str, fn: Any) -> None:
            try:
                counts[name] = fn()
            except (SourceError, psycopg.Error) as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}"[:300])

        part("equity_list", lambda: ingest_equity_list(conn, source))
        part("board_meetings", lambda: ingest_board_meetings(conn, source, today - timedelta(days=7),
                                                             today + timedelta(days=30)))
        part("pledges", lambda: ingest_pledges(conn, source))
        symbols = covered(conn)
        part("corporate_actions", lambda: ingest_corporate_actions(conn, source, symbols))
        counts["results"] = {s: ingest_results(conn, source, s) for s in symbols}
        errors += [f"results {s}: {r['error']}" for s, r in counts["results"].items() if r.get("error")]
        counts["errors"] = errors
    return counts


def backfill(conn: psycopg.Connection, source: Source, start: date, end: date,
             prices_start: date | None = None) -> dict[str, Any]:
    """Everything between two dates: the daily jobs first (so names, coverage and the equity list
    are in place), then filings day by day, then prices for every day from `prices_start` (default:
    `start`; price alerts need about 90 sessions of history, filings far less)."""
    out: dict[str, Any] = {"daily": ingest_daily(conn, source, end), "filings": {}}
    day = start
    while day <= end:
        out["filings"][day.isoformat()] = ingest_filings(conn, source, day, day).get("new")
        day += timedelta(days=1)
    first = min(prices_start or start, start)
    out["eod"] = ingest_eod(conn, source, [first + timedelta(days=i) for i in range((end - first).days + 1)])
    return out


def summary(counts: dict[str, Any]) -> str:
    return json.dumps(counts, default=str, indent=1)[:6000]

