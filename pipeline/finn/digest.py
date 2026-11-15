"""The digest exactly as the API serves it (docs/API.md, GET /v1/digest).

One investor's holdings, the filings about them in a window, ranked by `rank.build_digest` and
written in the contract's JSON shape. The API and `scripts/export_snapshot.py` (the web app's saved
copy) both call `digest_payload`, so the live digest and the fallback can never differ in shape.

Everything is read in one transaction as finn_api scoped to the investor: row-level security shows
only that investor's holdings, and the query names the investor as well, so a mistake in either
layer alone still leaks nothing. Filings come back from the database as Indian time without a zone,
which is how the ranker and the classifier were built and tested (`ingest.reclassify_stale` maps
rows back the same way).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict
from uuid import UUID

import psycopg

from . import db
from .models import Announcement, DigestItem
from .rank import build_digest
from .text import own_words

# India keeps no daylight saving, so a fixed offset is exact. The same value as `ingest.IST`
# (a test keeps them equal); defined here so the API does not import the fetchers.
IST = timezone(timedelta(hours=5, minutes=30))
MIN_HOURS, MAX_HOURS = 1, 744  # the contract's window: one hour to 31 days
DEFAULT_HOURS = 24
# Sessions loaded around the window for `reaction_window` (which moves a filing explains).
_SESSION_MARGIN = timedelta(days=7)
# Run-log jobs that count as a filings ingest ("filings 2026-11-14..2026-11-15").
_FILINGS_JOB = "filings%"


class Related(TypedDict):
    id: str
    ts: str
    label: str
    headline: str
    url: str


class Item(TypedDict):
    id: str
    symbol: str
    company: str
    ts: str
    headline: str
    label: str
    url: str
    category: str
    subtype: str
    role: str
    action: str
    detail_in_document: bool
    tier: int
    score: int
    alert: bool
    reasons: list[str]
    related: list[Related]


# "from" is a Python keyword, so this one is declared in the functional form.
WindowJSON = TypedDict("WindowJSON", {"hours": int, "from": str, "to": str})


class Routine(TypedDict):
    count: int
    by_kind: dict[str, int]


class Portfolio(TypedDict):
    holdings: int


class Digest(TypedDict):
    window: WindowJSON
    data_as_of: str | None
    summary: str
    portfolio: Portfolio
    attention: list[Item]
    worth: list[Item]
    routine: Routine
    unexplained_moves: list[Any]


def iso(ts: datetime) -> str:
    """ISO 8601 with the Indian offset, to the second: "2026-11-06T22:06:58+05:30"."""
    if ts.tzinfo is None:
        raise ValueError("a time without a zone is ambiguous here; attach one first")
    return ts.astimezone(IST).isoformat(timespec="seconds")


def check_hours(hours: object) -> int:
    """The window in whole hours, 1 to 744; anything else is refused with a message naming it."""
    if isinstance(hours, bool) or not isinstance(hours, int) or not MIN_HOURS <= hours <= MAX_HOURS:
        raise ValueError(f"hours must be a whole number from {MIN_HOURS} to {MAX_HOURS}")
    return hours


def data_as_of(conn: psycopg.Connection) -> datetime | None:
    """When the last successful filings ingest finished, or None if none has succeeded yet."""
    with db.as_role(conn, "finn_api"):
        row = conn.execute("select max(finished_at) from finn.ingest_runs where ok and job like %s",
                           [_FILINGS_JOB]).fetchone()
    return row[0] if row else None


def headline(subject: str, label: str) -> str:
    """The company's own words with NSE's template removed; the label when that is all they say."""
    return own_words(subject, label) or label or subject


def _naive_ist(ts: datetime) -> datetime:
    return ts.astimezone(IST).replace(tzinfo=None)


def _related(a: Announcement) -> Related:
    return {"id": a.id, "ts": iso(a.ts.replace(tzinfo=IST)), "label": a.label,
            "headline": headline(a.subject, a.label), "url": a.url}


def item_json(item: DigestItem) -> Item:
    a, c = item.announcement, item.classification
    return {
        "id": a.id,
        "symbol": a.symbol,
        "company": a.company,
        "ts": iso(a.ts.replace(tzinfo=IST)),
        "headline": headline(a.subject, a.label),
        "label": a.label,
        "url": a.url,
        "category": c.category,
        "subtype": c.subtype,
        "role": c.role,
        "action": c.action,
        "detail_in_document": c.detail_in_document,
        "tier": int(item.tier),
        "score": round(item.score),
        "alert": item.alert,
        "reasons": list(item.reasons),
        "related": [_related(r) for r in item.related],
    }


def _count_order(pair: tuple[str, int]) -> tuple[int, str]:
    return -pair[1], pair[0]


def _by_kind(counts: dict[str, int]) -> dict[str, int]:
    """Largest kind first, then by name, so the same data always serialises the same way."""
    return dict(sorted(counts.items(), key=_count_order))


def _announcements(rows: Iterable[tuple[Any, ...]]) -> list[Announcement]:
    return [Announcement(seq_id, symbol, company, _naive_ist(ts), source, label, subject, url=url,
                         file_size=file_size)
            for seq_id, symbol, company, ts, source, label, subject, url, file_size in rows]


def digest_payload(conn: psycopg.Connection, investor_id: UUID | str, hours: int,
                   now: datetime | None = None) -> Digest:
    """The /v1/digest JSON for one investor: filings with ts in (now - hours, now].

    `now` defaults to the current time; pass one (with its zone) for a reproducible digest.
    `conn` must be in autocommit with no transaction open (`db.connect` or the API's pool)."""
    hours = check_hours(hours)
    now = datetime.now(IST) if now is None else now
    if now.tzinfo is None:
        raise ValueError("now must carry its time zone")
    now = now.astimezone(IST).replace(microsecond=0)
    start = now - timedelta(hours=hours)
    investor = UUID(str(investor_id))

    # Two statements, not four: the API and the database sit in different regions, so each round
    # trip counts. Both name the investor and both are filtered again by row-level security.
    with db.as_role(conn, "finn_api", investor):
        holdings, sessions, as_of = conn.execute(
            """select array(select symbol from finn.holdings where investor_id = %(investor)s order by symbol),
                      array(select day from finn.trading_days
                            where is_session and day between %(first)s and %(last)s order by day),
                      (select max(finished_at) from finn.ingest_runs where ok and job like %(job)s)""",
            {"investor": investor, "first": (start - _SESSION_MARGIN).date(), "last": (now + _SESSION_MARGIN).date(),
             "job": _FILINGS_JOB}).fetchone() or ([], [], None)
        rows = conn.execute(
            """select seq_id, symbol, company, ts, source, label, subject, url, file_size from finn.filings
               where symbol in (select symbol from finn.holdings where investor_id = %s)
                 and ts > %s and ts <= %s
               order by ts, seq_id""", [investor, start, now]).fetchall()

    # Price and volume signals arrive with task D4; until then there is nothing to attach or report.
    digest = build_digest(_announcements(rows), [], trading_days=sessions or None)
    return {
        "window": {"hours": hours, "from": iso(start), "to": iso(now)},
        "data_as_of": iso(as_of) if as_of else None,
        "summary": digest["summary"],
        "portfolio": {"holdings": len(holdings)},
        "attention": [item_json(i) for i in digest["attention"]],
        "worth": [item_json(i) for i in digest["worth"]],
        "routine": {"count": len(digest["routine"]), "by_kind": _by_kind(digest["routine_counts"])},
        "unexplained_moves": [],
    }
