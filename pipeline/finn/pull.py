"""The company page exactly as the API serves it (docs/API.md, GET /v1/company/{symbol}).

Pull works for any NSE company FINN knows: every listed company has a name (NSE's equity list),
end-of-day prices (every bhavcopy row is stored) and its filings since 1 October (filings are
ingested market-wide). Covered companies (`finn.coverage`) also have nine quarters of results from
their XBRL filings, their documents and the analyses built from them; for the others the page says
plainly what is missing instead of guessing.

Everything is read in one transaction as finn_api, in four statements: the API (Singapore) and the
database (Mumbai) are in different regions, so each round trip counts. Nothing here is investor data.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, TypedDict

import psycopg

from . import db
from .digest import IST, Item, _announcements, _by_kind, iso, item_json
from .rank import build_digest
from .results import EBITDA_DEFINITION, BankQuarter, Quarter, bank_complete, bank_headline, headline
from .stored import filing_from_row
from .xbrl import to_quarter

SYMBOL = re.compile(r"^[A-Z0-9&-]{1,20}$")
FILINGS_DAYS = 90  # how far back the page lists filings
FILINGS_SHOWN = 15  # attention and worth-knowing items shown; the rest are counted
SEARCH_LIMIT = 10
_FILINGS_JOB = "filings%"
ANALYSIS_KINDS = ("ledger", "snapshot", "bull_bear")


class NotFound(LookupError):
    """No company with this symbol is known."""


class Price(TypedDict):
    day: str
    close: float
    change_1d_pct: float | None
    change_1m_pct: float | None
    change_since_pct: float | None
    since: str
    volume: int
    avg_volume_20d: int | None


def check_symbol(symbol: object) -> str:
    """An NSE symbol as the database stores it (upper case); anything else is refused."""
    if not isinstance(symbol, str):
        raise ValueError("symbol must be text")
    s = symbol.strip().upper()
    if not SYMBOL.match(s):
        raise ValueError("symbol must be 1-20 letters, digits, '&' or '-'")
    return s


def check_query(q: object) -> str:
    if not isinstance(q, str):
        raise ValueError("q must be text")
    q = " ".join(q.split())
    if not 1 <= len(q) <= 60:
        raise ValueError("q must be 1 to 60 characters")
    return q


def _like(q: str) -> str:
    """A LIKE pattern matching `q` literally anywhere (its own % and _ are escaped)."""
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(conn: psycopg.Connection, q: str) -> list[dict[str, Any]]:
    """Up to 10 companies by symbol or name: exact symbol first, then symbol prefix, then name."""
    q = check_query(q)
    with db.as_role(conn, "finn_api"):
        rows = conn.execute(
            """select c.symbol, coalesce(c.name, ''), c.symbol in (select symbol from finn.coverage)
               from finn.companies c
               where c.symbol like %(prefix)s escape '\\' or c.name ilike %(any)s escape '\\'
               order by c.symbol = %(exact)s desc, c.symbol like %(prefix)s escape '\\' desc,
                        length(c.symbol), c.symbol
               limit %(limit)s""",
            {"prefix": _like(q.upper())[1:], "any": _like(q), "exact": q.upper(), "limit": SEARCH_LIMIT},
        ).fetchall()
    return [{"symbol": s, "name": n, "covered": bool(c)} for s, n, c in rows]


def _f(x: Any) -> float:
    return float(x) if isinstance(x, Decimal) else float(x)


def _pct(now: float, then: float | None) -> float | None:
    if not then:
        return None
    return round((now / then - 1) * 100, 1)


def price_summary(bars: list[tuple[date, Any, Any, int]]) -> Price | None:
    """From (day, close, prev_close, volume), oldest first: the last close and its moves."""
    if not bars:
        return None
    day, close, prev_close, volume = bars[-1]
    close = _f(close)
    month_ago = day - timedelta(days=30)
    before = [b for b in bars if b[0] <= month_ago]
    earlier = bars[-21:-1]
    return {
        "day": day.isoformat(),
        "close": round(close, 2),
        "change_1d_pct": _pct(close, _f(prev_close) if prev_close else (_f(bars[-2][1]) if len(bars) > 1 else None)),
        "change_1m_pct": _pct(close, _f(before[-1][1])) if before else None,
        "change_since_pct": _pct(close, _f(bars[0][1])) if len(bars) > 1 else None,
        "since": bars[0][0].isoformat(),
        "volume": int(volume),
        "avg_volume_20d": round(sum(int(b[3]) for b in earlier) / len(earlier)) if len(earlier) >= 5 else None,
    }


def _margin(x: float, base: float) -> float | None:
    return round(x / base * 100, 1) if base else None


def _quarter_row(q: Quarter | BankQuarter) -> dict[str, Any]:
    if isinstance(q, BankQuarter):
        return {"period_end": q.period_end.isoformat(), "nii": round(q.nii, 2), "operating_profit": round(q.ppop, 2),
                "provisions": round(q.provisions, 2), "pat": round(q.pat, 2), "source": q.source}
    return {"period_end": q.period_end.isoformat(), "revenue": round(q.revenue, 2), "ebitda": round(q.ebitda, 2),
            "ebitda_margin": _margin(q.ebitda, q.revenue), "pbt": round(q.pbt, 2), "pat": round(q.pat, 2),
            "pat_margin": _margin(q.pat, q.revenue), "source": q.source}


def results_section(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Up to nine quarters on one basis (consolidated where filed), and the latest quarter's card."""
    if not rows:
        return None
    consolidated = any(r["consolidated"] for r in rows)
    qs = [to_quarter(filing_from_row(symbol, r), source=r["xbrl_url"]) for r in rows
          if r["consolidated"] == consolidated]
    qs.sort(key=lambda q: q.period_end, reverse=True)
    banks = [q for q in qs if isinstance(q, BankQuarter)]
    if banks and not bank_complete(banks[0]):
        return None  # an NBFC read as a bank gives wrong numbers; the page says results are not read
    if banks:
        card = bank_headline(banks)
        series: list[Quarter | BankQuarter] = list(banks)
    else:
        general = [q for q in qs if isinstance(q, Quarter)]
        card = headline(general)
        series = list(general)
    return {
        "template": card["template"],
        "basis": "consolidated" if consolidated else "standalone",
        "unit": "₹ crore",
        "latest": card,
        "quarters": [_quarter_row(q) for q in series],
        "notes": card["notes"] if card["template"] == "bank" else [EBITDA_DEFINITION],
    }


def _coverage(level: str, reason: str | None, has_results: bool, analyses: dict[str, Any],
              documents: int) -> dict[str, Any]:
    missing: list[str] = []
    if level == "basic":
        missing.append("FINN does not cover this company yet, so this page shows only its prices and filings "
                       "from NSE: no quarterly results, documents or analyses.")
    else:
        if not has_results:
            missing.append("No quarterly results have been read from its XBRL filings yet.")
        if not documents:
            missing.append("Its annual report and earnings-call transcripts have not been fetched yet.")
        absent = [k for k in ANALYSIS_KINDS if not analyses.get(k)]
        if absent:
            names = {"ledger": "promise ledger", "snapshot": "business snapshot", "bull_bear": "bull and bear case"}
            missing.append("Not built yet: " + ", ".join(names[k] for k in absent) + ".")
    return {"level": level, "reason": reason, "missing": missing}


def company_payload(conn: psycopg.Connection, symbol: str, now: datetime | None = None) -> dict[str, Any]:
    """The /v1/company/{symbol} JSON. Raises NotFound for a symbol FINN has never seen."""
    symbol = check_symbol(symbol)
    now = (datetime.now(IST) if now is None else now).astimezone(IST).replace(microsecond=0)
    start = now - timedelta(days=FILINGS_DAYS)
    with db.as_role(conn, "finn_api"), conn.cursor() as cur:
        head = cur.execute(
            """select c.name, c.isin, c.industry,
                      (select reason from finn.coverage where symbol = c.symbol),
                      (select max(finished_at) from finn.ingest_runs where ok and job like %(job)s),
                      array(select array[p.day::text, p.close::text, coalesce(p.prev_close::text, ''), p.volume::text]
                            from finn.prices_eod p where p.symbol = c.symbol order by p.day)
               from finn.companies c where c.symbol = %(symbol)s""",
            {"symbol": symbol, "job": _FILINGS_JOB}).fetchone()
        if head is None:
            raise NotFound(symbol)
        name, isin, industry, reason, as_of, bars = head
        with conn.cursor(row_factory=psycopg.rows.dict_row) as dcur:
            result_rows = dcur.execute(
                """select quarter_end, consolidated, template, period_start, period_end, audited, xbrl_url, figures
                   from finn.results where symbol = %s order by quarter_end desc limit 18""", [symbol]).fetchall()
        filing_rows = cur.execute(
            """select seq_id, symbol, company, ts, source, label, subject, url, file_size from finn.filings
               where symbol = %s and ts > %s and ts <= %s order by ts, seq_id""", [symbol, start, now]).fetchall()
        docs, analyses_rows = cur.execute(
            """select coalesce((select json_agg(json_build_object(
                         'kind', kind, 'title', title, 'period', period, 'published', published,
                         'url', url, 'pages', pages) order by published desc nulls last, id desc)
                       from finn.documents where symbol = %(s)s), '[]'),
                      coalesce((select json_object_agg(kind, json_build_object(
                         'payload', payload, 'sources', sources, 'model', model,
                         'generated_at', generated_at))
                       from finn.analyses where symbol = %(s)s), '{}')""", {"s": symbol}).fetchone() or ([], {})

    parsed = [(date.fromisoformat(d), c, p or None, int(v)) for d, c, p, v in bars]
    digest = build_digest(_announcements(filing_rows), [])
    shown: list[Item] = [item_json(i) for i in (digest["attention"] + digest["worth"])[:FILINGS_SHOWN]]
    more = len(digest["attention"]) + len(digest["worth"]) - len(shown)
    analyses = {k: _analysis(analyses_rows.get(k)) for k in ANALYSIS_KINDS}
    results = results_section(symbol, result_rows)
    level = "deep" if reason else "basic"
    return {
        "symbol": symbol,
        "name": name or symbol,
        "isin": isin,
        "industry": industry,
        "data_as_of": iso(as_of) if as_of else None,
        "coverage": _coverage(level, reason, results is not None, analyses, len(docs)),
        "price": price_summary(parsed),
        "results": results,
        "filings": {
            "days": FILINGS_DAYS,
            "items": shown,
            "more": more,
            "routine": {"count": len(digest["routine"]), "by_kind": _by_kind(digest["routine_counts"])},
        },
        "documents": [{**d, "published": d["published"]} for d in docs],
        "analyses": analyses,
    }


def _analysis(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    generated = row.get("generated_at")
    if isinstance(generated, str):
        generated = datetime.fromisoformat(generated)
    return {**row["payload"], "sources": row["sources"], "model": row["model"],
            "generated_at": iso(generated) if isinstance(generated, datetime) else None}
