"""Every response has exactly the shape of the examples in docs/API.md, read from that file, so
the contract and the code cannot drift apart without a test failing."""

from __future__ import annotations

import re

from api.tests.helpers import CORE, api_examples, assert_error, same_shape, token_for

TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+05:30$")
EXAMPLES = api_examples()


def times(value: object, key: str = "") -> list[str]:
    """Every time field in a response (keys ts, from, to, data_as_of, expires_at, generated_at, published)."""
    if isinstance(value, dict):
        return [t for k, v in value.items() for t in times(v, k)]
    if isinstance(value, list):
        return [t for v in value for t in times(v, key)]
    stamps = {"ts", "from", "to", "data_as_of", "expires_at", "generated_at", "published"}
    if key in stamps and isinstance(value, str):
        return [value]
    return []


def test_health_has_the_contract_shape(client):
    body = client.get("/health").json()
    same_shape(body, EXAMPLES["health"])
    assert all(TIME.match(t) for t in times(body))


def test_session_has_the_contract_shape(client):
    body = client.post("/v1/session/demo", headers={"Origin": CORE}).json()
    same_shape(body, EXAMPLES["session"])
    assert TIME.match(body["expires_at"])


def test_digest_and_every_item_have_the_contract_shape(client):
    token = token_for(client)
    body = client.get("/v1/digest", params={"hours": 144}, headers={"Authorization": f"Bearer {token}"}).json()
    same_shape(body, EXAMPLES["digest"])
    items = body["attention"] + body["worth"]
    assert len(items) == 9 and any(i["related"] for i in items)  # the real week: 1 attention, 8 worth knowing
    for n, item in enumerate(items):
        same_shape(item, EXAMPLES["item"], f"$.items[{n}]")
    stamps = times(body)
    assert len(stamps) >= 3 + len(items) and all(TIME.match(t) for t in stamps), stamps


def test_errors_have_the_contract_shape(client):
    error = assert_error(client.get("/v1/digest"), 401, "unauthorised")
    same_shape({"error": error}, EXAMPLES["error"])


def test_results_moves_and_pledges_have_the_contract_shape(client, admin):
    """The optional parts of the digest (tasks D1, D3, D4) with real values in them: an Elgi results
    quarter stored, a quiet ABB that then falls 7% with no filing, and Kalyan's pledge. Removed
    afterwards, so the other tests see the plain fixture week."""
    from datetime import date

    from finn import db
    from tests.test_digest import _bars_for, store_bars, store_elgi_results

    store_elgi_results(admin)
    quiet = [100.0 + (i % 3) * 0.2 for i in range(70)]
    store_bars(admin, _bars_for("ABB", date(2026, 7, 20), quiet, [1000.0] * 70)
               + [("ABB", date(2026, 11, 9), 93.0, 1200.0)])
    with db.as_role(admin, "finn_ingest"):
        admin.execute("""insert into finn.pledges (company_name, as_of, broadcast, symbol, promoter_holding_pct,
                           pledged_of_promoter_pct) values ('Kalyan Jewellers India Limited', '2026-09-30',
                           '2026-11-09 16:31:54+05:30', 'KALYANKJIL', 62.85, 24.85)""")
    try:
        token = token_for(client)
        body = client.get("/v1/digest", params={"hours": 144}, headers={"Authorization": f"Bearer {token}"}).json()
        same_shape(body, EXAMPLES["digest"])
        for n, item in enumerate(body["attention"] + body["worth"]):
            same_shape(item, EXAMPLES["item"], f"$.items[{n}]")
        elgi = next(i for i in body["attention"] if i["id"] == "106849670")
        assert elgi["results"]["quarter"] == "Q2 FY27"
        assert elgi["headline"].startswith("Q2 FY27 results: revenue ₹980 cr")
        assert [m["symbol"] for m in body["unexplained_moves"]] == ["ABB"]
        assert body["portfolio"]["pledges"][0]["symbol"] == "KALYANKJIL"
        assert all(TIME.match(t) for t in times(body))
    finally:
        with db.as_role(admin, "finn_ingest"):
            admin.execute("delete from finn.results where symbol = 'ELGIEQUIP'")
            admin.execute("delete from finn.prices_eod where symbol = 'ABB'")
            admin.execute("delete from finn.trading_days")
            admin.execute("delete from finn.pledges where symbol = 'KALYANKJIL'")
