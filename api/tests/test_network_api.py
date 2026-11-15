"""/v1/network/* and `who_to_call` in the digest: the full edition only (Founding brief)."""

from __future__ import annotations

import pytest

from api.tests.helpers import CORE, DEMO, FULL, OTHER, assert_error, mint, token_for
from finn import db, network

ROUTES = ("/v1/network/company/TATAPOWER", "/v1/network/person/p001", "/v1/network/ask?q=Who+worked+at+Tata+Power")
ITEM_KEYS = {"person_id", "name", "why", "degree", "via", "caution"}


@pytest.fixture(scope="module", autouse=True)
def demo_network(admin):
    network.load_network(admin, DEMO)
    yield
    with admin.transaction():
        admin.execute("delete from finn.network_people where investor_id = %s", [DEMO])


def get(client, path: str, token: str, origin: str | None = None):
    headers = {"Authorization": f"Bearer {token}"}
    if origin:
        headers["Origin"] = origin
    return client.get(path, headers=headers)


@pytest.mark.parametrize("path", ROUTES)
def test_a_core_session_cannot_tell_network_exists(client, path):
    token = token_for(client, CORE)
    r = get(client, path, token, CORE)
    assert_error(r, 404, "not_found")
    assert r.json()["error"]["message"] == "There is no such route."  # the same answer as an unknown route
    assert_error(get(client, path, token), 404, "not_found")  # no Origin: a non-browser client, still core


@pytest.mark.parametrize("path", ROUTES)
def test_network_routes_need_a_session(client, path):
    assert_error(client.get(path, headers={"Origin": FULL}), 401, "unauthorised")


def test_a_full_session_reads_the_company_answer(client):
    token = token_for(client, FULL)
    r = get(client, "/v1/network/company/TATAPOWER?category=capex", token, FULL)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["company"] == "Tata Power" and body["synthetic"] is True
    assert body["worked_there"] and body["best_placed"]
    first = body["best_placed"][0]
    assert {"person_id", "name", "headline", "degree", "why", "how", "via", "caution", "path"} <= set(first)
    assert first["path"][0]["from"] == "you"


def test_a_full_session_reads_a_person_and_asks(client):
    token = token_for(client, FULL)
    person = get(client, "/v1/network/person/p001", token, FULL).json()
    assert person["id"] == "p001" and person["career"] and person["what_to_ask"] and person["how"]
    assert_error(get(client, "/v1/network/person/p999", token, FULL), 404, "not_found")
    answer = get(client, "/v1/network/ask?q=Who+knows+auto+components%3F", token, FULL).json()
    assert answer["kind"] == "expertise" and answer["answers"]
    help_ = get(client, "/v1/network/ask?q=weather", token, FULL).json()
    assert help_["kind"] == "help" and help_["examples"]


@pytest.mark.parametrize("path", ["/v1/network/company/tatapower", "/v1/network/person/me",
                                  "/v1/network/person/x1", "/v1/network/ask?q=", "/v1/network/ask?q=" + "a" * 201,
                                  "/v1/network/company/TCS?category=gossip"])
def test_bad_parameters_are_refused(client, path):
    r = get(client, path, token_for(client, FULL), FULL)
    assert r.status_code in (404, 422), r.text
    assert r.json()["error"]["code"] in ("bad_request", "not_found")


def test_another_investors_session_sees_no_network(client, admin):
    with admin.transaction():
        admin.execute("update finn.investors set network_enabled = true where id = %s", [OTHER])
    try:
        token = mint(OTHER, deployment="full")
        body = get(client, "/v1/network/company/TATAPOWER", token, FULL).json()
        assert body["worked_there"] == [] and body["best_placed"] == []
    finally:
        with admin.transaction():
            admin.execute("update finn.investors set network_enabled = false where id = %s", [OTHER])
    token = mint(OTHER, deployment="full")  # network switched off: as if Network did not exist
    assert_error(get(client, "/v1/network/company/TATAPOWER", token, FULL), 404, "not_found")


def test_the_digest_names_who_to_call_on_full_and_never_on_core(client):
    full = get(client, "/v1/digest?hours=144", token_for(client, FULL), FULL).json()
    items = full["attention"] + full["worth"]
    assert items and all("who_to_call" in i for i in items)
    named = [c for i in items for c in i["who_to_call"]]
    assert named and all(set(c) == ITEM_KEYS for c in named)
    core = get(client, "/v1/digest?hours=144", token_for(client, CORE), CORE).json()
    assert not any("who_to_call" in i for i in core["attention"] + core["worth"])
    assert "who_to_call" not in str(core)


def test_network_reads_run_as_the_api_role_in_the_investors_scope(admin):
    with db.as_role(admin, "finn_api"):  # unscoped: nothing, so a missing scope can never leak a network
        assert admin.execute("select count(*) from finn.network_people").fetchone() == (0,)
    with db.as_role(admin, "finn_api", DEMO):
        assert admin.execute("select count(*) from finn.network_people").fetchone() == (151,)
