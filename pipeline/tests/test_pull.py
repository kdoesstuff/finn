"""The company page (Pull) from the database: any NSE company FINN has seen, covered or not.

Data comes in through the real ingest jobs fed by the recorded NSE responses (tests/test_ingest.py's
`Recorded`), so the page is tested on what production stores, not on hand-made rows."""

from __future__ import annotations

import json
from datetime import date, datetime

import psycopg
import pytest

from finn import db, ingest, pull, stored
from finn.digest import IST
from tests.test_ingest import WEEK, Recorded, cover

NOW = datetime(2026, 11, 9, 23, 59, tzinfo=IST)
SESSIONS = (date(2026, 11, 6),)


@pytest.fixture(scope="module")
def loaded(admin: psycopg.Connection) -> psycopg.Connection:
    ingest.ingest_filings(admin, Recorded(), *WEEK)
    ingest.ingest_eod(admin, Recorded(sessions=SESSIONS), list(SESSIONS))
    cover(admin, "TCS", "HDFCBANK")
    for symbol in ("TCS", "HDFCBANK"):
        assert ingest.ingest_results(admin, Recorded(), symbol)["stored"] > 0
    with db.as_role(admin, "finn_ingest"):
        admin.execute(
            """insert into finn.analyses (symbol, kind, payload, sources, model, prompt_version, generated_at)
               values ('TCS', 'ledger', %s, %s, 'test-model', 'ledger-v1', %s)""",
            [json.dumps({"summary": "kept 1 of 1 measurable promises", "statements": []}),
             json.dumps([{"kind": "transcript", "url": "https://example.test/t.pdf"}]),
             datetime(2026, 11, 9, 20, 0, tzinfo=IST)])
    return admin


def test_a_covered_company_has_its_quarters_card_prices_filings_and_analyses(loaded):
    page = pull.company_payload(loaded, "tcs", now=NOW)
    assert page["symbol"] == "TCS" and page["name"].startswith("Tata Consultancy")
    assert page["coverage"]["level"] == "deep" and page["coverage"]["reason"] == "holding"

    results = page["results"]
    assert results["template"] == "standard" and results["basis"] == "consolidated"
    assert results["latest"] == stored.card(loaded, "TCS")  # the same card the digest would show
    ends = [q["period_end"] for q in results["quarters"]]
    assert ends == sorted(ends, reverse=True) and 1 <= len(ends) <= 9
    revenue = next(r for r in results["latest"]["rows"] if r["metric"] == "Revenue")["value"]
    assert results["quarters"][0]["revenue"] == revenue
    assert results["quarters"][0]["source"].startswith("https://")

    price = page["price"]
    assert price["day"] == "2026-11-06" and price["close"] > 0  # the recorded bhavcopy is one session

    assert page["analyses"]["ledger"]["summary"] == "kept 1 of 1 measurable promises"
    assert page["analyses"]["ledger"]["generated_at"] == "2026-11-09T20:00:00+05:30"
    assert page["analyses"]["snapshot"] is None and page["analyses"]["bull_bear"] is None
    assert page["coverage"]["missing"] == [
        "Its annual report and earnings-call transcripts have not been fetched yet.",
        "Not built yet: business snapshot, bull and bear case."]


def test_a_bank_gets_the_bank_template(loaded):
    page = pull.company_payload(loaded, "HDFCBANK", now=NOW)
    assert page["results"]["template"] == "bank"
    q = page["results"]["quarters"][0]
    assert set(q) == {"period_end", "nii", "operating_profit", "provisions", "pat", "source"}
    assert page["results"]["latest"] == stored.card(loaded, "HDFCBANK")


def test_any_other_company_gets_prices_and_filings_and_says_what_is_missing(loaded):
    page = pull.company_payload(loaded, "DABUR", now=NOW)
    assert page["coverage"]["level"] == "basic" and page["coverage"]["reason"] is None
    assert page["results"] is None and page["documents"] == []
    assert "does not cover this company yet" in page["coverage"]["missing"][0]
    assert page["price"] is not None  # every bhavcopy row is stored, covered or not
    shown = page["filings"]["items"]
    assert shown and all(i["symbol"] == "DABUR" for i in shown) and len(shown) <= pull.FILINGS_SHOWN


def test_filings_are_ranked_capped_and_limited_to_ninety_days(loaded):
    page = pull.company_payload(loaded, "TCS", now=NOW)
    scores = [i["score"] for i in page["filings"]["items"]]
    assert scores == sorted(scores, reverse=True)
    later = pull.company_payload(loaded, "TCS", now=datetime(2027, 3, 1, tzinfo=IST))
    assert later["filings"]["items"] == [] and later["filings"]["routine"]["count"] == 0


def test_unknown_and_malformed_symbols_are_refused(loaded):
    with pytest.raises(pull.NotFound):
        pull.company_payload(loaded, "NOSUCHCO", now=NOW)
    for bad in ("", "TCS;", "a" * 21, "TC S", None):
        with pytest.raises(ValueError):
            pull.company_payload(loaded, bad, now=NOW)  # type: ignore[arg-type]


def test_search_finds_by_symbol_then_name_and_escapes_wildcards(loaded):
    first = pull.search(loaded, "tcs")[0]
    assert first == {"symbol": "TCS", "name": first["name"], "covered": True}
    by_name = pull.search(loaded, "asian paints")
    assert by_name and by_name[0]["symbol"] == "ASIANPAINT" and by_name[0]["covered"] is False
    assert pull.search(loaded, "%") == [] and pull.search(loaded, "_") == []
    assert len(pull.search(loaded, "a")) == pull.SEARCH_LIMIT
    for bad in ("", " ", "x" * 61):
        with pytest.raises(ValueError):
            pull.search(loaded, bad)


def test_the_api_role_reads_analyses_but_cannot_write_them(loaded):
    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.as_role(loaded, "finn_api"):
        loaded.execute("insert into finn.analyses (symbol, kind, payload) values ('MRF', 'ledger', '{}')")


def test_price_moves_from_bars():
    bars = [(date(2026, 6, 25), "100", "", 10), *[(date(2026, 9, d), "110", "109", 20) for d in range(1, 21)],
            (date(2026, 10, 30), "120", "110", 30), (date(2026, 11, 6), "126", "120", 60)]
    p = pull.price_summary([(d, c, p or None, v) for d, c, p, v in bars])
    assert p == {"day": "2026-11-06", "close": 126.0, "change_1d_pct": 5.0, "change_1m_pct": 14.5,
                 "change_since_pct": 26.0, "since": "2026-06-25", "volume": 60, "avg_volume_20d": 20}
    assert pull.price_summary([]) is None
    one = pull.price_summary([(date(2026, 11, 6), "50", None, 5)])
    assert one is not None and one["change_1d_pct"] is None and one["change_since_pct"] is None
