"""Is the stored data complete and right? The B4 check, re-runnable at any time.

For every covered company: which quarters are stored, whether the latest quarter (and the quarter a
year earlier, for YoY) is there, sessions of price history, filings since a date, and whether its
pledges are matched. Where the latest quarter is missing, the live check asks NSE why: not filed
yet (a reason, not a failure), or filed but not stored (a failure). Three companies' figures are
compared with values verified by hand against their published results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import psycopg

from . import db, stored
from .sources import nse
from .sources.client import Source, SourceError

# Verified against the companies' published results (docs/HANDOFF.md section 7; smoke runs of
# 11 and 15 Nov 2026). Metric name as the card shows it, value in ₹ crore.
KNOWN = {
    ("TCS", date(2026, 9, 30)): ("Revenue", 73188.0),
    ("ASIANPAINT", date(2026, 9, 30)): ("Revenue", 9977.0),
    ("HDFCBANK", date(2026, 9, 30)): ("Net interest income", 44464.0),
}


@dataclass
class CompanyCheck:
    symbol: str
    quarters: int = 0
    latest: date | None = None
    has_target: bool = False
    has_year_ago: bool = False
    template: str = ""
    sessions: int = 0
    filings: int = 0
    pledge_matched: bool = False
    reason: str = ""
    failed: bool = False


@dataclass
class Report:
    target: date
    companies: list[CompanyCheck] = field(default_factory=list)
    known: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def check(conn: psycopg.Connection, target: date, filings_since: date, source: Source | None = None) -> Report:
    report = Report(target)
    year_ago = date(target.year - 1, target.month, target.day)
    with db.as_role(conn, "finn_ingest"):
        symbols = [r[0] for r in conn.execute("select symbol from finn.coverage order by symbol")]
        stats: dict[str, dict[str, Any]] = {s: {} for s in symbols}
        for s, n, latest, tmpl in conn.execute(
                """select symbol, count(*), max(quarter_end), max(template) from finn.results
                   where symbol = any(%s) group by symbol""", [symbols]):
            stats[s].update(quarters=n, latest=latest, template=tmpl)
        for s, ends in conn.execute("""select symbol, array_agg(distinct quarter_end) from finn.results
                                       where symbol = any(%s) group by symbol""", [symbols]):
            stats[s]["ends"] = set(ends)
        for s, n in conn.execute("""select symbol, count(*) from finn.prices_eod
                                    where symbol = any(%s) and day >= %s group by symbol""",
                                 [symbols, target - timedelta(days=180)]):
            stats[s]["sessions"] = n
        for s, n in conn.execute("""select symbol, count(*) from finn.filings where symbol = any(%s) and ts >= %s
                                    group by symbol""", [symbols, filings_since]):
            stats[s]["filings"] = n
        for (s,) in conn.execute("select distinct symbol from finn.pledges where symbol = any(%s)", [symbols]):
            stats[s]["pledge"] = True
    for s in symbols:
        st = stats[s]
        c = CompanyCheck(s, st.get("quarters", 0), st.get("latest"), target in st.get("ends", set()),
                         year_ago in st.get("ends", set()), st.get("template", ""), st.get("sessions", 0),
                         st.get("filings", 0), bool(st.get("pledge")))
        if not c.has_target:
            c.reason, c.failed = _why_missing(source, s, target)
        report.companies.append(c)
        if c.failed:
            report.failures.append(f"{s}: {c.reason}")
    for (symbol, quarter), (metric, expected) in KNOWN.items():
        card = stored.card(conn, symbol)
        if not card or card["period_end"] != quarter.isoformat():
            report.known.append(f"{symbol} {quarter}: not stored")
            report.failures.append(f"{symbol} {quarter}: verified figure cannot be checked, quarter not stored")
            continue
        row = next((r for r in card["rows"] if r["metric"] == metric), None)
        value = row["value"] if row else None
        ok = value is not None and abs(value - expected) <= 1
        report.known.append(f"{symbol} {quarter} {metric}: stored {value:,.0f} vs verified {expected:,.0f} "
                            f"{'OK' if ok else 'MISMATCH'}" if value is not None else f"{symbol}: {metric} missing")
        if not ok:
            report.failures.append(f"{symbol} {quarter} {metric}: stored {value} vs verified {expected}")
    return report


def _why_missing(source: Source | None, symbol: str, target: date) -> tuple[str, bool]:
    if source is None:
        return "not stored (run with --live to ask NSE why)", True
    try:
        listed = [f for f in nse.result_filings(source, symbol) if f.quarter_end == target]
    except SourceError as exc:
        return f"not stored, and NSE could not be asked ({exc})"[:200], True
    if not listed:
        return "NSE lists no results for this quarter yet", False
    return (f"NSE lists {len(listed)} filing(s) for this quarter but none is stored: "
            f"run `ingest.py results {symbol}`"), True


def render(report: Report) -> str:
    lines = [f"Covered companies: {len(report.companies)}; quarter checked: {report.target}", "",
             f"{'symbol':<11} {'qtrs':>4} {'latest':<10} {'target':<6} {'yoy':<4} {'tmpl':<8} {'sessions':>8} "
             f"{'filings':>7} {'pledge':<6} reason"]
    for c in report.companies:
        lines.append(f"{c.symbol:<11} {c.quarters:>4} {str(c.latest or '-'):<10} {'yes' if c.has_target else 'NO':<6} "
                     f"{'yes' if c.has_year_ago else 'no':<4} {c.template or '-':<8} {c.sessions:>8} {c.filings:>7} "
                     f"{'yes' if c.pledge_matched else 'no':<6} {c.reason}")
    lines += ["", "Verified figures:"] + [f"  {k}" for k in report.known]
    lines += ["", "Failures:" if report.failures else "No failures."] + [f"  {f}" for f in report.failures]
    return "\n".join(lines)
