"""GET /v1/digest on the real fixture week, through HTTP, as the web app calls it.

What to expect is not written down by hand: it is the ranker's own output on the same rows parsed
straight from the fixture file (`expected`), and the named events are the ones the filings
themselves describe (docs/DECISIONS.md, "Classifier measurement after the repairs")."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from api.app import HOURS_MESSAGE
from api.tests.helpers import (
    CORE,
    DATA_AS_OF,
    DEMO_HOLDINGS,
    NOW,
    OTHER,
    OTHER_HOLDINGS,
    assert_error,
    fixture_rows,
    mint,
    token_for,
)
from finn import rank
from finn.sources import nse


def expected(holdings: frozenset[str], hours: int) -> dict:
    start, end = (NOW - timedelta(hours=hours)).replace(tzinfo=None), NOW.replace(tzinfo=None)
    anns = [a for a in (nse.parse_announcement(r) for r in fixture_rows())
            if a.symbol in holdings and start < a.ts <= end]
    return rank.build_digest(anns, [])


def get(client, token: str, **params):
    return client.get("/v1/digest", params=params, headers={"Authorization": f"Bearer {token}"})


def test_the_real_week_ranks_as_the_ranker_ranks_it(client):
    r = get(client, token_for(client), hours=144)
    assert r.status_code == 200
    body = r.json()
    want = expected(DEMO_HOLDINGS, 144)

    assert body["window"] == {"hours": 144, "from": "2026-11-03T23:59:00+05:30", "to": "2026-11-09T23:59:00+05:30"}
    assert body["data_as_of"] == DATA_AS_OF
    assert body["portfolio"] == {"holdings": 18, "pledges": []}
    assert [i["id"] for i in body["attention"]] == [i.announcement.id for i in want["attention"]]
    assert [i["id"] for i in body["worth"]] == [i.announcement.id for i in want["worth"]]
    assert body["routine"] == {"count": len(want["routine"]), "by_kind": want["routine_counts"]}
    assert body["summary"] == want["summary"]
    assert body["summary"] == "1 item needs your attention. 8 worth knowing; 18 routine filings set aside."
    assert body["unexplained_moves"] == []

    attention = {i["id"]: i for i in body["attention"]}
    worth = {i["id"]: i for i in body["worth"]}
    elgi = attention["106849670"]
    assert (elgi["symbol"], elgi["category"], elgi["tier"], elgi["score"]) == ("ELGIEQUIP", "results", 2, 85)
    assert elgi["reasons"] == ["Quarterly results: headline numbers compared QoQ and YoY"]
    assert [r["id"] for r in elgi["related"]] == ["106850445"]  # the investor presentation, same card

    cto = worth["106852003"]
    assert (cto["symbol"], cto["role"], cto["action"]) == ("MANAPPURAM", "senior", "resignation")
    assert cto["headline"].startswith("Resignation of Mr Narayanan Easwaran as Group Chief Technology Officer")

    puri = worth["106851770"]
    assert (puri["symbol"], puri["role"], puri["action"]) == ("ASIANPAINT", "director", "appointment")
    assert puri["score"] == 55
    assert puri["headline"].startswith("Appointment of Mr Leo Puri as Independent Director")
    assert puri["reasons"] == ["Board change below the top team"]
    assert puri["related"][0]["id"] == "106851762"

    # Sections are ordered, most important first; every item links to its source document.
    scores = [i["score"] for i in body["worth"]]
    assert scores == sorted(scores, reverse=True)
    assert all(i["url"].startswith("https://nsearchives.nseindia.com/") for i in body["attention"] + body["worth"])
    assert r.headers["content-type"] == "application/json"


def test_default_window_is_24_hours(client):
    body = get(client, token_for(client)).json()
    assert body["window"] == {"hours": 24, "from": "2026-11-08T23:59:00+05:30", "to": "2026-11-09T23:59:00+05:30"}
    want = expected(DEMO_HOLDINGS, 24)
    assert [i["id"] for i in body["worth"]] == [i.announcement.id for i in want["worth"]]


@pytest.mark.parametrize("hours", ["0", "745", "-1", "abc", "1.5", "1.0", "", "+24", " 24", "1e2", "24x", "٢٤"])
def test_hours_outside_1_to_744_are_refused_by_name(client, hours):
    error = assert_error(get(client, token_for(client), hours=hours), 422, "bad_request")
    assert error["message"] == HOURS_MESSAGE


@pytest.mark.parametrize("hours", [1, 744])
def test_hours_at_the_bounds_are_served(client, hours):
    r = get(client, token_for(client), hours=hours)
    assert r.status_code == 200 and r.json()["window"]["hours"] == hours


def test_one_investor_never_sees_another_investors_holdings(client):
    demo = get(client, token_for(client), hours=144).json()
    other = get(client, mint(OTHER), hours=144).json()

    demo_symbols = {i["symbol"] for i in demo["attention"] + demo["worth"]}
    other_symbols = {i["symbol"] for i in other["attention"] + other["worth"]}
    assert demo_symbols <= DEMO_HOLDINGS and not demo_symbols & OTHER_HOLDINGS
    assert other["portfolio"] == {"holdings": 2, "pledges": []} and other_symbols == OTHER_HOLDINGS
    # Sadbhav's statutory auditor left mid-term (100): it is the other investor's, and only theirs.
    assert other["attention"][0]["symbol"] == "SADBHAV" and other["attention"][0]["score"] == 100
    assert not {i["id"] for i in other["attention"] + other["worth"]} & {i["id"] for i in demo["attention"]}


def test_a_token_for_an_unknown_investor_sees_an_empty_portfolio(client):
    body = get(client, mint(UUID(int=0xDEAD)), hours=144).json()
    assert body["portfolio"] == {"holdings": 0, "pledges": []}
    assert body["summary"] == "Nothing material across your portfolio."


def test_digest_needs_a_session(client):
    assert_error(client.get("/v1/digest"), 401, "unauthorised")
    assert_error(client.get("/v1/digest", headers={"Origin": CORE}), 401, "unauthorised")
