"""Every response has exactly the shape of the examples in docs/API.md, read from that file, so
the contract and the code cannot drift apart without a test failing."""

from __future__ import annotations

import re

from api.tests.helpers import CORE, api_examples, assert_error, same_shape, token_for

TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+05:30$")
EXAMPLES = api_examples()


def times(value: object, key: str = "") -> list[str]:
    """Every time field in a response (keys ts, from, to, data_as_of, expires_at, generated_at)."""
    if isinstance(value, dict):
        return [t for k, v in value.items() for t in times(v, k)]
    if isinstance(value, list):
        return [t for v in value for t in times(v, key)]
    if key in {"ts", "from", "to", "data_as_of", "expires_at", "generated_at"} and isinstance(value, str):
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
