"""Live check of every fetcher against NSE. Run from a machine NSE answers (GitHub's runners):

    python scripts/smoke_sources.py [SYMBOL ...]       (default: TCS ASIANPAINT HDFCBANK)

Prints one line per fetcher (rows, seconds, a sample) and, under GitHub Actions, a Markdown table in
the job summary. Exits 1 if any fetcher fails, so the workflow goes red.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finn.results import BankQuarter, bank_headline, headline  # noqa: E402
from finn.sources import nse  # noqa: E402
from finn.sources.client import NSEClient  # noqa: E402
from finn.xbrl import parse, to_quarter  # noqa: E402

RESULTS: list[tuple[str, bool, int, float, str]] = []


def check(name: str, fn: Callable[[], tuple[int, str]]) -> Any:
    start = time.monotonic()
    try:
        rows, sample = fn()
        ok = True
    except Exception as exc:  # noqa: BLE001 - a smoke test reports every failure and carries on
        rows, sample, ok = 0, f"{type(exc).__name__}: {exc}"[:200], False
    seconds = round(time.monotonic() - start, 1)
    RESULTS.append((name, ok, rows, seconds, sample))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<38} rows={rows:<6} {seconds:>5}s  {sample}")


def results_card(c: NSEClient, symbol: str) -> tuple[int, str]:
    filings = [f for f in nse.result_filings(c, symbol) if f.consolidated] or nse.result_filings(c, symbol)
    quarters = []
    for f in filings[:5]:
        blob = c.content(f.xbrl_url)
        if blob:
            quarters.append(to_quarter(parse(blob), source=f.xbrl_url))
    if not quarters:
        raise RuntimeError("no XBRL could be read")
    if isinstance(quarters[0], BankQuarter):
        h = bank_headline([q for q in quarters if isinstance(q, BankQuarter)])
    else:
        h = headline([q for q in quarters if not isinstance(q, BankQuarter)])
    first = h["rows"][0]
    return len(filings), f"{h['period_end']} {first['metric']} ₹{first['value']:,.0f} cr, YoY {first['yoy']}"


def main() -> int:
    symbols = sys.argv[1:] or ["TCS", "ASIANPAINT", "HDFCBANK"]
    c = NSEClient()
    today = date.today()

    def anns() -> tuple[int, str]:
        rows = nse.announcements(c, today - timedelta(days=1), today)
        return len(rows), (rows[0].subject[:80] if rows else "none in the window")

    def company_anns(symbol: str) -> tuple[int, str]:
        rows = nse.announcements(c, today - timedelta(days=30), today, symbol)
        return len(rows), (rows[0].label if rows else "none")

    def eod(day: date) -> tuple[int, str]:
        rows = nse.bhavcopy(c, day)
        if rows is None:
            return 0, "no file: not a session"
        tcs = next((r.close for r in rows if r.symbol == "TCS"), "missing")
        return len(rows), f"TCS close {tcs}"

    def pledges() -> tuple[int, str]:
        rows = nse.pledges(c)
        return len(rows), (rows[0].headline if rows else "none")

    def meetings() -> tuple[int, str]:
        rows = nse.board_meetings(c, today, today + timedelta(days=14))
        return len(rows), (f"{rows[0].symbol} {rows[0].day}" if rows else "none")

    def reports(symbol: str) -> tuple[int, str]:
        rows = nse.annual_reports(c, symbol)
        return len(rows), (f"FY{rows[0].to_year} {rows[0].url[-40:]}" if rows else "none")

    def insider(symbol: str) -> tuple[int, str]:
        rows = nse.insider_trades(c, symbol)
        return len(rows), (str(rows[0].get("acqName", ""))[:40] if rows else "none")

    def actions(symbol: str) -> tuple[int, str]:
        rows = nse.corporate_actions(c, symbol)
        return len(rows), (f"{rows[0].ex_date} {rows[0].subject}" if rows else "none")

    check("announcements, last 2 days, market", anns)
    for s in symbols:
        check(f"announcements, 30 days, {s}", partial(company_anns, s))
        check(f"results XBRL to headline, {s}", partial(results_card, c, s))
    for back in range(5):
        day = today - timedelta(days=back)
        check(f"bhavcopy {day:%a %d %b}", partial(eod, day))
    check("pledges", pledges)
    check("board meetings, next 14 days", meetings)
    check(f"annual reports, {symbols[0]}", partial(reports, symbols[0]))
    check(f"insider trades, {symbols[0]}", partial(insider, symbols[0]))
    check(f"corporate actions, {symbols[0]}", partial(actions, symbols[0]))

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} fetchers OK; {c.requests_made} requests")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("| Fetcher | OK | Rows | Seconds | Sample |\n| --- | --- | --- | --- | --- |\n")
            for name, ok, rows, seconds, sample in RESULTS:
                fh.write(f"| {name} | {'yes' if ok else 'NO'} | {rows} | {seconds} | {sample.replace('|', '/')} |\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
