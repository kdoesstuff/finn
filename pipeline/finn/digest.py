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

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, TypedDict
from uuid import UUID

import psycopg

from . import db
from .alerts import Thresholds, signals_for
from .models import Announcement, Bar, DigestItem, Signal
from .rank import Prefs, build_digest
from .results import BankQuarter, Quarter, bank_complete, bank_headline
from .results import headline as results_headline
from .stored import filing_from_row
from .taxonomy import CATEGORIES
from .text import own_words
from .xbrl import to_quarter

# India keeps no daylight saving, so a fixed offset is exact. The same value as `ingest.IST`
# (a test keeps them equal); defined here so the API does not import the fetchers.
IST = timezone(timedelta(hours=5, minutes=30))
MIN_HOURS, MAX_HOURS = 1, 744  # the contract's window: one hour to 31 days
DEFAULT_HOURS = 24
# Sessions loaded around the window for `reaction_window` (which moves a filing explains).
_SESSION_MARGIN = timedelta(days=7)
# Run-log jobs that count as a filings ingest ("filings 2026-11-14..2026-11-15").
_FILINGS_JOB = "filings%"
# Results are filed within 45 days of a quarter's end (60 for the March quarter): a results filing
# is about the latest stored quarter that ended up to this long before it.
_RESULTS_LAG = timedelta(days=75)
# Stored quarters loaded for a window: its results quarters, the one before and the year-ago one.
_RESULTS_HISTORY = timedelta(days=_RESULTS_LAG.days + 366 + 100)
# The XBRL facts the results card reads (`xbrl.to_quarter`); only these leave the database.
_CARD_FACTS = [
    "RevenueFromOperations", "OtherIncome", "FinanceCosts", "DepreciationDepletionAndAmortisationExpense",
    "ExceptionalItemsBeforeTax", "ProfitBeforeTax", "ProfitOrLossAttributableToOwnersOfParent",
    "ProfitLossForPeriod", "InterestEarned", "InterestExpended", "OperatingExpenses",
    "ProvisionsOtherThanTaxAndContingencies", "ProfitLossFromOrdinaryActivitiesBeforeTax",
    "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates", "ProfitLossForThePeriod",
]
# Bars loaded before the window: the volatility rule needs 60 sessions of history (about 90 days).
_PRICE_HISTORY = timedelta(days=100)
# NSE's equity session closes at 15:30 IST: a session's move belongs to the window holding its close.
_CLOSE = time(15, 30)
# NSE adjusts the previous close on a split, bonus or rights day. When its previous close differs
# from the stored one by more than this, the day's change is a corporate action, not a move.
_ADJUSTED_DAY = 0.02
_RESULT_FILINGS = {"board_meeting_notice", "results_ad", "deck"}  # results subtypes that are not results


class Related(TypedDict):
    id: str
    ts: str
    label: str
    headline: str
    url: str


class Change(TypedDict):
    pct: float | None
    note: str
    margin_bps: int | None


class ResultsRow(TypedDict):
    metric: str
    value: float
    margin: float | None
    qoq: Change
    yoy: Change


class Results(TypedDict):
    quarter: str
    period_end: str
    basis: str
    template: str
    unit: str
    rows: list[ResultsRow]
    notes: list[str]
    source: str


class Move(TypedDict):
    symbol: str
    company: str
    day: str
    kind: str
    value: float
    threshold: float
    sigma: float | None
    fired_by: str
    detail: str


class Pledge(TypedDict):
    symbol: str
    company: str
    pct_of_promoter: float
    promoter_stake_pct: float
    as_of: str
    published: str
    change_pct_points: float | None


class Person(TypedDict):
    """A management change's person, from the filing's own profile (`finn.reader`)."""
    name: str
    role: str
    action: str
    effective_date: str
    background: list[dict[str, Any]]
    previous_roles: list[dict[str, str]]


class Note(TypedDict):
    """What the filing says, read from its attachment; every sentence carries a verified quote."""
    summary: str
    quote: str
    page: int
    person: Person | None


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
    results: Results | None
    moves: list[Move]
    note: Note | None  # --- Reader stream ---


# "from" is a Python keyword, so this one is declared in the functional form.
WindowJSON = TypedDict("WindowJSON", {"hours": int, "from": str, "to": str})


class Routine(TypedDict):
    count: int
    by_kind: dict[str, int]


class Company(TypedDict):
    symbol: str
    company: str


class Portfolio(TypedDict):
    holdings: int
    companies: list[Company]
    pledges: list[Pledge]


class Digest(TypedDict):
    window: WindowJSON
    data_as_of: str | None
    summary: str
    portfolio: Portfolio
    filings_read: int
    attention: list[Item]
    worth: list[Item]
    routine: Routine
    unexplained_moves: list[Move]


def iso(ts: datetime) -> str:
    """ISO 8601 with the Indian offset, to the second: "2026-11-06T22:06:58+05:30"."""
    if ts.tzinfo is None:
        raise ValueError("a time without a zone is ambiguous here; attach one first")
    return ts.astimezone(IST).isoformat(timespec="seconds")


# --- Controls: the investor's alert settings for one request -------------------------------------
# The demo investor is read-only in the database, so the app keeps its alert settings on the device
# and sends them with each digest request; finn.prefs stays the default. Same ranges as the
# check constraints on finn.prefs (0001_foundation.sql).
MOVE_PCT_RANGE = (0.5, 30.0)
VOLUME_MULTIPLE_RANGE = (1.1, 10.0)
MOVE_RULES = ("pct", "sigma", "either")
ALERT_CATEGORIES = tuple(c for c in CATEGORIES if c != "unclassified")


@dataclass(frozen=True)
class Overrides:
    """Alert settings for one digest, in place of finn.prefs; None keeps the stored (or default) value."""

    move_pct: float | None = None
    volume_multiple: float | None = None
    move_rule: str | None = None
    alerts: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.move_pct is not None and not MOVE_PCT_RANGE[0] <= self.move_pct <= MOVE_PCT_RANGE[1]:
            raise ValueError(f"move_pct must be from {MOVE_PCT_RANGE[0]} to {MOVE_PCT_RANGE[1]}")
        if (self.volume_multiple is not None
                and not VOLUME_MULTIPLE_RANGE[0] <= self.volume_multiple <= VOLUME_MULTIPLE_RANGE[1]):
            raise ValueError(f"volume_multiple must be from {VOLUME_MULTIPLE_RANGE[0]} to {VOLUME_MULTIPLE_RANGE[1]}")
        if self.move_rule is not None and self.move_rule not in MOVE_RULES:
            raise ValueError("move_rule must be one of: " + ", ".join(MOVE_RULES))
        if self.alerts is not None and not self.alerts <= set(ALERT_CATEGORIES):
            unknown = sorted(self.alerts - set(ALERT_CATEGORIES))
            raise ValueError("unknown alert categories: " + ", ".join(unknown))


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
    """The company's own words with NSE's template removed; the label when that is all they say.
    NSE's template leaves a sentence fragment ("the financial results for ..."): it starts with a
    capital, as a headline does."""
    text = own_words(subject, label) or label or subject
    return text[:1].upper() + text[1:]


def _naive_ist(ts: datetime) -> datetime:
    return ts.astimezone(IST).replace(tzinfo=None)


def _related(a: Announcement) -> Related:
    return {"id": a.id, "ts": iso(a.ts.replace(tzinfo=IST)), "label": a.label,
            "headline": headline(a.subject, a.label), "url": a.url}


def fiscal_quarter(period_end: date) -> str:
    """India's financial year runs April to March: the quarter to 30 Sep 2026 is "Q2 FY27"."""
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(period_end.month)
    fy = period_end.year + 1 if period_end.month >= 4 else period_end.year
    return f"Q{q} FY{fy % 100:02d}" if q else f"Quarter to {period_end:%d %b %Y}"


def _change(c: dict[str, Any]) -> Change:
    return {"pct": c.get("pct"), "note": c.get("note", ""), "margin_bps": c.get("margin_bps")}


def results_json(card: dict[str, Any]) -> Results:
    """The parser's results card (`results.headline` / `bank_headline`) in the contract's shape:
    every key always present, null where a figure does not apply."""
    period_end = date.fromisoformat(card["period_end"])
    return {
        "quarter": fiscal_quarter(period_end),
        "period_end": card["period_end"],
        "basis": card["basis"],
        "template": card["template"],
        "unit": card["unit"],
        "rows": [{"metric": r["metric"], "value": r["value"], "margin": r.get("margin"),
                  "qoq": _change(r["qoq"]), "yoy": _change(r["yoy"])} for r in card["rows"]],
        "notes": list(card["notes"]),
        "source": card["source"],
    }


def _money(value: float, metric: str) -> str:
    name = metric if metric.isupper() else metric.lower()
    if value < 0:
        return f"a loss of ₹{abs(value):,.0f} cr" if metric == "PAT" else f"{name} -₹{abs(value):,.0f} cr"
    return f"{name} ₹{value:,.0f} cr"


def _yoy_phrase(c: Change) -> str:
    if c["pct"] is None:
        return "" if c["note"] in ("not available", "no base") else f", {c['note']} YoY"
    if c["pct"] == 0:
        return ", flat YoY"
    return f", {'up' if c['pct'] > 0 else 'down'} {abs(c['pct']):.1f}% YoY"


def results_headline_text(results: Results) -> str:
    """"Q2 FY27 results: revenue ₹73,188 cr, up 11.2% YoY; PAT ₹12,075 cr, up 1.4% YoY"."""
    lead = results["rows"][0]
    parts = [_money(lead["value"], lead["metric"]) + _yoy_phrase(lead["yoy"])]
    pat = next((r for r in results["rows"][1:] if r["metric"] == "PAT"), None)
    if pat is not None:
        parts.append(_money(pat["value"], pat["metric"]) + _yoy_phrase(pat["yoy"]))
    return f"{results['quarter']} results: " + "; ".join(parts)


def results_card(symbol: str, rows: list[dict[str, Any]], filed: date) -> Results | None:
    """The card for the quarter a results filing on `filed` reports: the latest stored quarter that
    ended up to _RESULTS_LAG before it, consolidated where the company files it. Computed by the
    parser's own code (`stored.filing_from_row`, `xbrl.to_quarter`, `results.headline`), exactly as
    `stored.card` computes it. None when that quarter is not stored yet: no numbers are guessed."""
    mine = [r for r in rows if r["symbol"] == symbol]
    ends = [r["quarter_end"] for r in mine if filed - _RESULTS_LAG <= r["quarter_end"] <= filed]
    if not ends:
        return None
    target = max(ends)
    consolidated = any(r["consolidated"] for r in mine)
    quarters = [to_quarter(filing_from_row(symbol, r), source=r["xbrl_url"]) for r in mine
                if r["consolidated"] == consolidated and r["quarter_end"] <= target]
    if not quarters or max(q.period_end for q in quarters) != target:
        return None
    if isinstance(quarters[0], BankQuarter):
        banks = [q for q in quarters if isinstance(q, BankQuarter)]
        if not bank_complete(max(banks, key=lambda q: q.period_end)):
            return None  # a lender the bank template cannot read: the company's own words stay
        card = bank_headline(banks)
    else:
        card = results_headline([q for q in quarters if isinstance(q, Quarter)])
    return results_json(card)


def move_json(s: Signal, company: str) -> Move:
    return {"symbol": s.symbol, "company": company, "day": s.day.isoformat(), "kind": s.kind,
            "value": s.value, "threshold": s.threshold, "sigma": s.sigma, "fired_by": s.fired_by,
            "detail": s.detail}


def window_signals(bars: dict[str, list[Bar]], adjusted: dict[str, set[date]], th: Thresholds,
                   start: datetime, end: datetime) -> list[Signal]:
    """Price and volume signals for every session whose close falls in (start, end], each judged
    against the bars before it (`alerts.signals_for`). Corporate-action days are skipped."""
    out: list[Signal] = []
    for symbol, series in bars.items():
        for i, bar in enumerate(series):
            closed = datetime.combine(bar.day, _CLOSE, tzinfo=IST)
            if i == 0 or not start < closed <= end or bar.day in adjusted.get(symbol, set()):
                continue
            out.extend(signals_for(symbol, series[: i + 1], th))
    return out


def reader_note(raw: Any) -> Note | None:
    """A stored filing note (finn.filing_notes, written by `finn.reader`) in the contract's shape.
    Kept here, not imported from finn.reader: the API must not import the fetchers (or their
    dependencies) that the reader needs."""
    n = raw if isinstance(raw, dict) else json.loads(raw)
    p = n.get("person") or None
    who: Person | None = None
    if p is not None:
        who = {"name": str(p.get("name", "")), "role": str(p.get("role", "")),
               "action": str(p.get("action", "")), "effective_date": str(p.get("effective_date", "")),
               "background": [{"text": str(b.get("text", "")), "quote": str(b.get("quote", "")),
                               "page": int(b.get("page") or 0)} for b in p.get("background") or []],
               "previous_roles": [{"org": str(r.get("org", "")), "title": str(r.get("title", ""))}
                                  for r in p.get("previous_roles") or []]}
    return {"summary": str(n.get("summary") or ""), "quote": str(n.get("quote") or ""),
            "page": int(n.get("page") or 0), "person": who}


def item_json(item: DigestItem, results: Results | None = None, companies: dict[str, str] | None = None,
              note: Note | None = None) -> Item:
    a, c = item.announcement, item.classification
    names = companies or {}
    return {
        "id": a.id,
        "symbol": a.symbol,
        "company": a.company,
        "ts": iso(a.ts.replace(tzinfo=IST)),
        "headline": results_headline_text(results) if results else headline(a.subject, a.label),
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
        "results": results,
        "moves": [move_json(s, names.get(s.symbol, a.company)) for s in item.signals],
        "note": note,
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


def _thresholds(prefs: list[Any] | None, overrides: Overrides | None = None) -> Thresholds:
    th = Thresholds()
    if prefs:
        volume_multiple, move_pct, move_sigma, move_rule = prefs[:4]
        th = Thresholds(volume_multiple=float(volume_multiple), move_pct=float(move_pct),
                        move_sigma=float(move_sigma), move_rule=str(move_rule))
    if overrides is not None:
        if overrides.volume_multiple is not None:
            th.volume_multiple = overrides.volume_multiple
        if overrides.move_pct is not None:
            th.move_pct = overrides.move_pct
        if overrides.move_rule is not None:
            th.move_rule = overrides.move_rule
    return th


def _rank_prefs(prefs: list[Any] | None, overrides: Overrides | None = None) -> Prefs:
    """Which categories are on the investor's alert list: this request's, else finn.prefs', else the default."""
    if overrides is not None and overrides.alerts is not None:
        return Prefs(alert_categories=set(overrides.alerts))
    if prefs and len(prefs) > 4 and prefs[4] is not None:
        return Prefs(alert_categories=set(prefs[4]))
    return Prefs()


def _bars(rows: list[list[Any]]) -> tuple[dict[str, list[Bar]], dict[str, set[date]]]:
    """Bars by symbol, oldest first, and the days NSE adjusted the previous close (corporate actions)."""
    bars: dict[str, list[Bar]] = {}
    adjusted: dict[str, set[date]] = {}
    for symbol, day, close, prev_close, volume in rows:
        series = bars.setdefault(symbol, [])
        bar = Bar(date.fromisoformat(day), float(close), float(volume))
        if series and prev_close and abs(float(prev_close) / series[-1].close - 1) > _ADJUSTED_DAY:
            adjusted.setdefault(symbol, set()).add(bar.day)
        series.append(bar)
    return bars, adjusted


def _results_rows(rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [{"symbol": symbol, "quarter_end": date.fromisoformat(quarter_end), "consolidated": consolidated,
             "template": template, "period_start": date.fromisoformat(period_start),
             "period_end": date.fromisoformat(period_end), "audited": audited, "xbrl_url": xbrl_url,
             "figures": {"facts": facts or {}}}
            for symbol, quarter_end, consolidated, template, period_start, period_end, audited, xbrl_url, facts
            in rows]


def _pledges(rows: list[list[Any]], companies: dict[str, str]) -> list[Pledge]:
    """Holdings whose promoters have pledged shares (or had, in the previous snapshot), latest first
    per company, with the change since NSE's previous snapshot when there is one."""
    by_symbol: dict[str, list[list[Any]]] = {}
    for row in rows:
        by_symbol.setdefault(row[0], []).append(row)  # newest publication first (the query's order)
    out: list[Pledge] = []
    for symbol in sorted(by_symbol):
        latest, *older = by_symbol[symbol]
        _, as_of, published, pct, stake = latest
        before = float(older[0][3]) if older and older[0][3] is not None else None
        if not float(pct or 0) and not before:
            continue
        out.append({"symbol": symbol, "company": companies.get(symbol, symbol), "pct_of_promoter": float(pct or 0),
                    "promoter_stake_pct": float(stake or 0), "as_of": as_of,
                    "published": iso(datetime.fromisoformat(published)),
                    "change_pct_points": None if before is None else round(float(pct or 0) - before, 2)})
    return out


def digest_payload(conn: psycopg.Connection, investor_id: UUID | str, hours: int,
                   now: datetime | None = None, overrides: Overrides | None = None) -> Digest:
    """The /v1/digest JSON for one investor: filings with ts in (now - hours, now], their results
    numbers, the price and volume moves in the window (attached to the filing that explains them, or
    listed as unexplained), and the promoter pledges on the holdings.

    `now` defaults to the current time; pass one (with its zone) for a reproducible digest.
    `overrides` (alert categories and move thresholds for this request) replace finn.prefs.
    `conn` must be in autocommit with no transaction open (`db.connect` or the API's pool)."""
    hours = check_hours(hours)
    now = datetime.now(IST) if now is None else now
    if now.tzinfo is None:
        raise ValueError("now must carry its time zone")
    now = now.astimezone(IST).replace(microsecond=0)
    start = now - timedelta(hours=hours)
    investor = UUID(str(investor_id))

    # Two statements, not more: the API and the database sit in different regions, so each round
    # trip counts. Both name the investor and both are filtered again by row-level security. The
    # first carries everything about the holdings (results, prices, thresholds, pledges) as JSON.
    with db.as_role(conn, "finn_api", investor):
        holdings, sessions, as_of, names, results, prices, prefs, pledges = conn.execute(
            """with mine as (select symbol from finn.holdings where investor_id = %(investor)s)
               select array(select symbol from mine order by symbol),
                      array(select day from finn.trading_days
                            where is_session and day between %(first)s and %(last)s order by day),
                      (select max(finished_at) from finn.ingest_runs where ok and job like %(job)s),
                      (select coalesce(json_object_agg(c.symbol, c.name), '{}') from finn.companies c
                       where c.symbol in (select symbol from mine) and c.name is not null),
                      (select coalesce(json_agg(json_build_array(r.symbol, r.quarter_end, r.consolidated, r.template,
                                                r.period_start, r.period_end, r.audited, r.xbrl_url,
                                                (select jsonb_object_agg(k, v) from jsonb_each(r.figures -> 'facts')
                                                   as f(k, v) where k = any(%(facts)s)))), '[]')
                       from finn.results r
                       where r.symbol in (select symbol from mine) and r.quarter_end >= %(results_from)s),
                      (select coalesce(json_agg(json_build_array(p.symbol, p.day, p.close, p.prev_close, p.volume)
                                                order by p.symbol, p.day), '[]')
                       from finn.prices_eod p
                       where p.symbol in (select symbol from mine) and p.day between %(prices_from)s and %(last)s),
                      (select json_build_array(volume_multiple, move_pct, move_sigma, move_rule, alert_categories)
                       from finn.prefs
                       where investor_id = %(investor)s),
                      (select coalesce(json_agg(json_build_array(x.symbol, x.as_of, x.broadcast,
                                                x.pledged_of_promoter_pct, x.promoter_holding_pct)
                                                order by x.symbol, x.broadcast desc), '[]')
                       from (select p.*, row_number() over (partition by p.symbol
                                                            order by p.broadcast desc, p.as_of desc) as n
                             from finn.pledges p where p.symbol in (select symbol from mine)) x
                       where x.n <= 2)""",
            {"investor": investor, "first": (start - _SESSION_MARGIN).date(), "last": (now + _SESSION_MARGIN).date(),
             "job": _FILINGS_JOB, "facts": _CARD_FACTS, "results_from": (start - _RESULTS_HISTORY).date(),
             "prices_from": (start - _PRICE_HISTORY).date()}).fetchone() or ([], [], None, {}, [], [], None, [])
        # --- Reader stream: each filing's note (finn.filing_notes), joined in the same statement ---
        rows = conn.execute(
            """select f.seq_id, f.symbol, f.company, f.ts, f.source, f.label, f.subject, f.url, f.file_size,
                      case when n.seq_id is null then null
                           else json_build_object('summary', n.summary, 'quote', n.quote, 'page', n.page,
                                                  'person', n.person) end
               from finn.filings f left join finn.filing_notes n on n.seq_id = f.seq_id
               where f.symbol in (select symbol from finn.holdings where investor_id = %s)
                 and f.ts > %s and f.ts <= %s
               order by f.ts, f.seq_id""", [investor, start, now]).fetchall()
    notes = {r[0]: reader_note(r[9]) for r in rows if r[9] is not None}

    bars, adjusted = _bars(prices)
    signals = window_signals(bars, adjusted, _thresholds(prefs, overrides), start, now)
    stored_results = _results_rows(results)
    digest = build_digest(_announcements(r[:9] for r in rows), signals, _rank_prefs(prefs, overrides),
                          trading_days=sessions or None)

    def entry(item: DigestItem) -> Item:
        c = item.classification
        card = None
        if c.category == "results" and c.subtype not in _RESULT_FILINGS:
            card = results_card(item.announcement.symbol, stored_results, item.announcement.ts.date())
        return item_json(item, card, names, notes.get(item.announcement.id))

    return {
        "window": {"hours": hours, "from": iso(start), "to": iso(now)},
        "data_as_of": iso(as_of) if as_of else None,
        "summary": digest["summary"],
        "portfolio": {"holdings": len(holdings),
                      "companies": [{"symbol": s, "company": names.get(s) or s} for s in holdings],
                      "pledges": _pledges(pledges, names)},
        "filings_read": len(rows),
        "attention": [entry(i) for i in digest["attention"]],
        "worth": [entry(i) for i in digest["worth"]],
        "routine": {"count": len(digest["routine"]), "by_kind": _by_kind(digest["routine_counts"])},
        "unexplained_moves": [move_json(s, names.get(s.symbol, s.symbol))
                              for s in sorted(digest["unexplained_moves"], key=_move_order)],
    }


def _move_order(s: Signal) -> tuple[int, float]:
    """Newest session first; within a day, the largest move or volume multiple first."""
    return -s.day.toordinal(), -abs(s.value)
