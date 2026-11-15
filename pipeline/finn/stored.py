"""Reading stored results back as the parser's own objects, so every card is computed by the same
code whether the numbers came straight from NSE or from the database."""

from __future__ import annotations

from typing import Any

import psycopg

from . import db
from .results import BankQuarter, Quarter, bank_complete, bank_headline, headline
from .xbrl import Filing, to_quarter


def filing_from_row(symbol: str, row: dict[str, Any]) -> Filing:
    figures = row["figures"]
    return Filing(symbol=symbol, period_start=row["period_start"], period_end=row["period_end"],
                  consolidated=row["consolidated"], bank=row["template"] == "bank", audited=row.get("audited", ""),
                  audit_opinion=figures.get("audit_opinion", ""), board_meeting=figures.get("board_meeting", ""),
                  facts={k: float(v) for k, v in figures.get("facts", {}).items()}, text=figures.get("text", {}))


def quarters(conn: psycopg.Connection, symbol: str, consolidated: bool | None = None) -> list[Quarter | BankQuarter]:
    """Stored quarters for one company, newest first. With consolidated=None: consolidated where the
    company files it, else standalone (a bank's NPAs, for instance, are only in standalone filings)."""
    with db.as_role(conn, "finn_api"), conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        rows = cur.execute("""select quarter_end, consolidated, template, period_start, period_end, audited,
                                     xbrl_url, figures
                              from finn.results where symbol = %s order by quarter_end desc""", [symbol]).fetchall()
    if consolidated is None:
        consolidated = any(r["consolidated"] for r in rows)
    return [to_quarter(filing_from_row(symbol, r), source=r["xbrl_url"]) for r in rows
            if r["consolidated"] == consolidated]


def card(conn: psycopg.Connection, symbol: str) -> dict[str, Any] | None:
    """The results card (latest quarter, QoQ and YoY) from stored data, or None if nothing is stored."""
    qs = quarters(conn, symbol)
    if not qs:
        return None
    if isinstance(qs[0], BankQuarter):
        banks = [q for q in qs if isinstance(q, BankQuarter)]
        if not bank_complete(max(banks, key=lambda q: q.period_end)):
            return None  # read as a bank, an NBFC's filing gives wrong numbers; show none
        return bank_headline(banks)
    return headline([q for q in qs if isinstance(q, Quarter)])
