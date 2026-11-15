"""POST /v1/session/demo and the tokens it issues: signed, scoped to one deployment, read-only,
12 hours long, and refused once altered or expired."""

from __future__ import annotations

import base64
import json
from datetime import timedelta
from uuid import UUID

import pytest

from api import sessions
from api.tests.helpers import (
    CORE,
    DEMO,
    ELSEWHERE,
    FULL,
    NOW,
    SECRET,
    assert_error,
    claims,
    make_client,
    mint,
    token_for,
)

TTL = timedelta(hours=12)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def digest(client, token: str, origin: str | None = None):
    headers = {"Authorization": f"Bearer {token}"}
    if origin:
        headers["Origin"] = origin
    return client.get("/v1/digest", params={"hours": 1}, headers=headers)


def test_core_site_gets_a_read_only_demo_session(client):
    r = client.post("/v1/session/demo", headers={"Origin": CORE})
    assert r.status_code == 200
    body = r.json()
    assert body["expires_at"] == "2026-11-10T11:59:00+05:30"  # issued 9 Nov 23:59 IST, 12 hours
    assert body["investor"] == {"name": "Demo investor", "demo": True, "network": False}
    c = claims(body["token"])
    assert c == {"v": 1, "sub": str(DEMO), "ro": True, "dep": "core", "iat": int(NOW.timestamp()),
                 "exp": int((NOW + TTL).timestamp())}
    assert r.headers["access-control-allow-origin"] == CORE
    assert digest(client, body["token"], CORE).status_code == 200


def test_full_site_gets_network_when_the_investor_has_it_on(client):
    body = client.post("/v1/session/demo", headers={"Origin": FULL}).json()
    assert body["investor"]["network"] is True  # the demo investor's network switch is on (db/seed/demo.json)
    assert claims(body["token"])["dep"] == "full"


@pytest.mark.parametrize("origin", [None, ELSEWHERE, "null", CORE + "/", CORE.replace("https", "http"),
                                    "https://finn-core.test.invalid.evil.example"])
def test_sessions_start_only_from_an_allow_listed_site(client, origin):
    headers = {"Origin": origin} if origin else {}
    assert_error(client.post("/v1/session/demo", headers=headers), 403, "forbidden")


def test_a_missing_demo_investor_is_reported_not_invented(settings):
    with make_client(settings, demo_investor_id=UUID(int=0xD00D)) as c:
        assert_error(c.post("/v1/session/demo", headers={"Origin": CORE}), 503, "unavailable")


def tampered(token: str) -> list[str]:
    payload, sig = token.split(".")
    c = claims(token)
    as_full = b64(json.dumps({**c, "dep": "full"}, separators=(",", ":"), sort_keys=True).encode())
    other = b64(json.dumps({**c, "sub": "0b0b0b0b-0000-4000-8000-00000000000b"}, separators=(",", ":"),
                           sort_keys=True).encode())
    flip = "A" if sig[0] != "A" else "B"
    standard_alphabet = f"{payload}.{sig}".replace("-", "+").replace("_", "/")
    return [standard_alphabet] * (standard_alphabet != token) + [
        f"{as_full}.{sig}",  # a claim changed, the old signature kept
        f"{other}.{sig}",  # another investor
        f"{payload}.{flip}{sig[1:]}",  # the signature changed
        f"{payload}.{sig[:-1]}",  # the signature truncated
        f"{payload}.{sig}=",  # padding added
        f"{payload}.{sig}.{sig}",  # three parts
        payload,  # no signature
        f".{sig}",
        f"{payload}.",
        "",
        "x" * 2000,
        mint(DEMO, secret=b"another-secret-of-thirty-two-or-more-bytes!"),  # signed with another key
    ]


def test_altered_or_foreign_tokens_are_refused(client):
    good = token_for(client)
    for bad in tampered(good):
        error = assert_error(digest(client, bad), 401, "unauthorised")
        assert error["message"] == "Sign in again: your session is not valid."
    assert digest(client, good).status_code == 200


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Basic dXNlcjpwYXNz", "Token abc", "bearer"])
def test_malformed_authorization_is_refused(client, header):
    r = client.get("/v1/digest", headers={"Authorization": header} if header else {})
    assert_error(r, 401, "unauthorised")
    assert r.headers["www-authenticate"].startswith("Bearer")


def test_the_bearer_scheme_is_case_insensitive(client):
    token = token_for(client)
    assert client.get("/v1/digest", headers={"Authorization": f"bearer {token}"}).status_code == 200


def test_a_session_expires_after_12_hours(client, clock):
    token = token_for(client)
    clock.now = NOW + TTL - timedelta(seconds=1)
    assert digest(client, token).status_code == 200
    clock.now = NOW + TTL
    error = assert_error(digest(client, token), 401, "unauthorised")
    assert error["message"] == "Sign in again: your session has expired."


def test_tokens_from_the_future_or_too_long_lived_are_refused(client):
    assert_error(digest(client, mint(DEMO, now=NOW + timedelta(minutes=5))), 401, "unauthorised")
    assert digest(client, mint(DEMO, now=NOW + timedelta(seconds=30))).status_code == 200  # within clock skew
    assert_error(digest(client, mint(DEMO, ttl=timedelta(hours=13))), 401, "unauthorised")


def test_a_session_works_only_on_the_site_that_started_it(client):
    core = token_for(client, CORE)
    assert digest(client, core, CORE).status_code == 200
    assert digest(client, core).status_code == 200  # no Origin: a non-browser client
    assert_error(digest(client, core, FULL), 401, "unauthorised")
    assert_error(digest(client, core, ELSEWHERE), 403, "forbidden")


def test_a_token_survives_a_restart_but_not_a_new_secret(settings, clock):
    with make_client(settings, clock) as first:
        token = token_for(first)
    with make_client(settings, clock) as second:
        assert digest(second, token).status_code == 200
    with make_client(settings, clock, session_secret=b"rotated-secret-0123456789-abcdefghij") as rotated:
        assert_error(digest(rotated, token), 401, "unauthorised")


def test_verify_checks_claims_strictly():
    def signed(c: dict) -> str:
        payload = b64(json.dumps(c).encode())
        return f"{payload}.{b64(sessions._mac(SECRET, payload))}"

    base = {"v": 1, "sub": str(DEMO), "ro": True, "dep": "core", "iat": int(NOW.timestamp()),
            "exp": int((NOW + TTL).timestamp())}
    assert sessions.verify(SECRET, signed(base), now=NOW, max_ttl=TTL).investor_id == DEMO
    for change in ({"v": 2}, {"dep": "both"}, {"ro": 1}, {"sub": "not-a-uuid"}, {"sub": 7}, {"iat": True},
                   {"exp": "soon"}, {"exp": base["iat"]}, {"extra": 1}):
        with pytest.raises(sessions.InvalidToken):
            sessions.verify(SECRET, signed({**base, **change}), now=NOW, max_ttl=TTL)
    for missing in base:
        with pytest.raises(sessions.InvalidToken):
            sessions.verify(SECRET, signed({k: v for k, v in base.items() if k != missing}), now=NOW, max_ttl=TTL)
    for not_an_object in ([1, 2], "text", 3):
        with pytest.raises(sessions.InvalidToken):
            sessions.verify(SECRET, signed(not_an_object), now=NOW, max_ttl=TTL)  # type: ignore[arg-type]
    payload = b64(b"\xff\xfe not json")
    with pytest.raises(sessions.InvalidToken):
        sessions.verify(SECRET, f"{payload}.{b64(sessions._mac(SECRET, payload))}", now=NOW, max_ttl=TTL)
