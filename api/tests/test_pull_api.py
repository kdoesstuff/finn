"""GET /v1/companies and GET /v1/company/{symbol} through HTTP, as the web app calls them.

The session database gets TCS's recorded results and the recorded bhavcopy through the real ingest
jobs, plus one stored ledger, so the page is tested on what production stores."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from api.tests.helpers import CORE, ELSEWHERE, api_examples, assert_error, same_shape, token_for
from finn import db, digest, ingest, stored
from tests.test_ingest import Recorded

EXAMPLES = api_examples()


@pytest.fixture(scope="module", autouse=True)
def tcs_data(admin):
    ingest.ingest_eod(admin, Recorded(), [date(2026, 11, 6)])
    assert ingest.ingest_results(admin, Recorded(), "TCS")["stored"] > 0
    with db.as_role(admin, "finn_ingest"):
        admin.execute(
            """insert into finn.analyses (symbol, kind, payload, sources, model, prompt_version, generated_at)
               values ('TCS', 'ledger', %s, '[]', 'test-model', 'ledger-v1', %s)
               on conflict (symbol, kind) do nothing""",
            [json.dumps({"summary": "kept 1 of 1 measurable promises"}),
             datetime(2026, 11, 9, 20, 0, tzinfo=digest.IST)])


def get(client, path: str, token: str | None = None, origin: str = CORE, **params):
    headers = {"Origin": origin}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.get(path, params=params, headers=headers)


def test_a_covered_company_page(client, admin):
    r = get(client, "/v1/company/TCS", token_for(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "TCS" and body["coverage"]["level"] == "deep"
    assert body["results"]["latest"] == json.loads(json.dumps(stored.card(admin, "TCS")))
    assert body["analyses"]["ledger"]["summary"] == "kept 1 of 1 measurable promises"
    assert body["price"]["day"] == "2026-11-06"
    # One recorded session, so the price changes are null here; their keys still match the contract.
    assert set(body["price"]) == set(EXAMPLES["company"]["price"])
    page = {**body, "analyses": EXAMPLES["company"]["analyses"], "price": EXAMPLES["company"]["price"],
            "results": {**body["results"], "latest": EXAMPLES["company"]["results"]["latest"]}}  # card: equal above
    page["coverage"] = {**body["coverage"], "missing": body["coverage"]["missing"][:1]}
    same_shape(page, EXAMPLES["company"])
    for item in body["filings"]["items"]:
        same_shape(item, EXAMPLES["item"])


def test_symbols_are_case_insensitive_and_any_known_company_answers(client):
    token = token_for(client)
    assert get(client, "/v1/company/tcs", token).json()["symbol"] == "TCS"
    basic = get(client, "/v1/company/DABUR", token).json()
    assert basic["coverage"]["level"] == "basic" and basic["results"] is None


def test_unknown_and_malformed_symbols(client):
    token = token_for(client)
    assert_error(get(client, "/v1/company/NOSUCHCO", token), 404, "not_found")
    assert_error(get(client, "/v1/company/TC%20S", token), 422, "bad_request")
    assert_error(get(client, "/v1/company/" + "A" * 21, token), 422, "bad_request")


def test_search(client):
    token = token_for(client)
    body = get(client, "/v1/companies", token, q="tcs").json()
    same_shape(body, EXAMPLES["companies"])
    assert body["companies"][0] == {"symbol": "TCS", "name": body["companies"][0]["name"], "covered": True}
    assert_error(get(client, "/v1/companies", token), 422, "bad_request")
    assert_error(get(client, "/v1/companies", token, q="x" * 61), 422, "bad_request")
    assert_error(get(client, "/v1/companies", token, q="   "), 422, "bad_request")


def test_pull_needs_a_session_and_an_allowed_site(client):
    assert_error(get(client, "/v1/company/TCS"), 401, "unauthorised")
    assert_error(get(client, "/v1/companies", q="tcs"), 401, "unauthorised")
    assert_error(get(client, "/v1/company/TCS", token_for(client), origin=ELSEWHERE), 403, "forbidden")
