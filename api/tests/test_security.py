"""The API's outer defences: security headers, CORS, rate limits and who counts as a client, the
body limit, unknown routes, hidden docs, and the last-resort error handler. Every refusal is checked
for the contract's error shape."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.middleware import SECURITY_HEADERS
from api.tests.helpers import CORE, DEMO, ELSEWHERE, FULL, Clock, Ticker, assert_error, make_client, mint

PREFLIGHT = {"Origin": CORE, "Access-Control-Request-Method": "GET",
             "Access-Control-Request-Headers": "authorization"}


def has_security_headers(response) -> bool:
    return all(response.headers.get(name) == value for name, value in SECURITY_HEADERS.items())


# Security headers ---------------------------------------------------------------------------------

def test_security_headers_on_every_kind_of_response(client, settings):
    auth = {"Authorization": f"Bearer {mint(DEMO)}"}
    responses = [
        client.get("/health"),
        client.post("/v1/session/demo", headers={"Origin": CORE}),
        client.get("/v1/digest", headers=auth),
        client.get("/v1/digest"),  # 401
        client.get("/v1/digest", params={"hours": 0}, headers=auth),  # 422
        client.get("/nowhere"),  # 404
        client.get("/v1/session/demo"),  # 405
        client.post("/v1/session/demo"),  # 403
        client.options("/v1/digest", headers=PREFLIGHT),  # 204
        client.options("/v1/digest", headers={**PREFLIGHT, "Origin": ELSEWHERE}),  # 403
        client.post("/v1/session/demo", headers={"Origin": CORE}, content=b"x" * 20_000),  # 413
    ]
    with make_client(settings, db_url="postgresql://u:p@127.0.0.1:1/x", pool_wait_s=0.3) as down:
        responses.append(down.get("/v1/digest", headers=auth))  # 503
    assert [r.status_code for r in responses] == [200, 200, 200, 401, 422, 404, 405, 403, 204, 403, 413, 503]
    assert all(has_security_headers(r) for r in responses)
    assert all("server" not in r.headers for r in responses)


# CORS -----------------------------------------------------------------------------------------------

def test_preflight_from_an_allowed_site_is_granted_exactly(client):
    for origin in (CORE, FULL):
        r = client.options("/v1/digest", headers={**PREFLIGHT, "Origin": origin})
        assert r.status_code == 204 and r.content == b""
        assert r.headers["access-control-allow-origin"] == origin
        assert r.headers["access-control-allow-methods"] == "GET, POST, OPTIONS"
        assert r.headers["access-control-allow-headers"] == "Authorization, Content-Type"
        assert r.headers["access-control-max-age"] == "600"
        assert "access-control-allow-credentials" not in r.headers
        assert "Origin" in r.headers["vary"]
    r = client.options("/v1/session/demo", headers={"Origin": CORE, "Access-Control-Request-Method": "POST",
                                                     "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 204


@pytest.mark.parametrize("change", [
    {"Origin": ELSEWHERE},
    {"Origin": "null"},
    {"Origin": CORE + ":8443"},
    {"Access-Control-Request-Method": "DELETE"},
    {"Access-Control-Request-Method": "PUT"},
    {"Access-Control-Request-Headers": "authorization, x-api-key"},
    {"Access-Control-Request-Headers": "cookie"},
])
def test_preflight_is_refused_for_anything_else(client, change):
    r = client.options("/v1/digest", headers={**PREFLIGHT, **change})
    assert_error(r, 403, "forbidden")
    assert "access-control-allow-origin" not in r.headers


def test_allowed_sites_can_read_responses_including_refusals(client):
    for r in (client.get("/health", headers={"Origin": CORE}),
              client.get("/v1/digest", headers={"Origin": CORE})):  # a 401 the web app must be able to read
        assert r.headers["access-control-allow-origin"] == CORE
        assert r.headers["access-control-expose-headers"] == "Retry-After"
        assert "Origin" in r.headers["vary"]


def test_other_sites_get_no_grant_and_v1_refuses_them(client):
    r = client.get("/health", headers={"Origin": ELSEWHERE})  # public, but not readable from their pages
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers
    assert_error(client.get("/v1/digest", headers={"Origin": ELSEWHERE, "Authorization": f"Bearer {mint(DEMO)}"}),
                 403, "forbidden")
    # A "simple" cross-site POST needs no preflight; it must still do nothing.
    assert_error(client.post("/v1/session/demo", headers={"Origin": ELSEWHERE}), 403, "forbidden")


# Rate limits ----------------------------------------------------------------------------------------

def test_sessions_are_limited_to_10_a_minute_per_client(client, ticker):
    for _ in range(10):
        assert client.post("/v1/session/demo", headers={"Origin": CORE}).status_code == 200
    r = client.post("/v1/session/demo", headers={"Origin": CORE})
    assert_error(r, 429, "rate_limited")
    assert r.headers["retry-after"] == "60"
    assert r.headers["access-control-allow-origin"] == CORE  # the web app can read the wait
    ticker.t += 30
    assert client.post("/v1/session/demo", headers={"Origin": CORE}).headers["retry-after"] == "30"
    ticker.t += 30  # a minute after the first ten: the window has slid past them
    assert client.post("/v1/session/demo", headers={"Origin": CORE}).status_code == 200


def test_v1_is_limited_to_60_a_minute_per_client_counting_sessions(client, ticker):
    for _ in range(10):
        client.post("/v1/session/demo", headers={"Origin": CORE})
    for _ in range(50):
        assert client.get("/v1/digest").status_code == 401  # refused requests count too
    r = client.get("/v1/digest")
    assert_error(r, 429, "rate_limited")
    assert 1 <= int(r.headers["retry-after"]) <= 60
    assert client.get("/health").status_code == 200  # /health is outside /v1 and never limited
    ticker.t += 60
    assert client.get("/v1/digest").status_code == 401


def test_preflights_are_not_counted(client):
    for _ in range(80):
        assert client.options("/v1/digest", headers=PREFLIGHT).status_code == 204
    assert client.get("/v1/digest").status_code == 401


def test_on_render_the_client_is_the_true_client_ip_not_x_forwarded_for(settings):
    with make_client(settings, client_ip_header="true-client-ip") as c:
        def session(**headers: str) -> int:
            return c.post("/v1/session/demo", headers={"Origin": CORE, **headers}).status_code

        # A client that rotates X-Forwarded-For (which Render passes through) is still one client.
        for n in range(10):
            assert session(**{"True-Client-IP": "203.0.113.7", "X-Forwarded-For": f"198.51.100.{n}"}) == 200
        assert session(**{"True-Client-IP": "203.0.113.7", "X-Forwarded-For": "198.51.100.99"}) == 429
        # Another client has its own allowance.
        assert session(**{"True-Client-IP": "203.0.113.8"}) == 200
        # IPv6: one /64 is one client; another /64 is another.
        for n in range(10):
            assert session(**{"True-Client-IP": f"2001:db8:1:2::{n + 1:x}"}) == 200
        assert session(**{"True-Client-IP": "2001:db8:1:2:ffff::1"}) == 429
        assert session(**{"True-Client-IP": "2001:db8:1:3::1"}) == 200


def test_a_missing_or_doubled_client_header_falls_back_to_the_connection(settings):
    with make_client(settings, client_ip_header="true-client-ip") as c:
        statuses = []
        for n in range(11):  # garbage, doubled and absent headers all count as the connecting peer
            headers = [("Origin", CORE)]
            headers += [[("True-Client-IP", "not-an-ip")], [("True-Client-IP", f"203.0.113.{n}"),
                                                            ("True-Client-IP", "203.0.113.200")], []][n % 3]
            statuses.append(c.post("/v1/session/demo", headers=headers).status_code)
        assert statuses == [200] * 10 + [429]


def test_without_a_trusted_header_forwarding_headers_are_ignored(client):
    for n in range(10):
        assert client.post("/v1/session/demo", headers={"Origin": CORE, "X-Forwarded-For": f"192.0.2.{n}",
                                                         "True-Client-IP": f"192.0.2.{n}"}).status_code == 200
    assert client.post("/v1/session/demo", headers={"Origin": CORE, "X-Forwarded-For": "192.0.2.77"}).status_code \
        == 429


# Request bodies -------------------------------------------------------------------------------------

def test_bodies_over_16_kb_are_refused(client):
    ok = client.post("/v1/session/demo", headers={"Origin": CORE}, content=b"x" * 16 * 1024)
    assert ok.status_code == 200
    error = assert_error(client.post("/v1/session/demo", headers={"Origin": CORE}, content=b"x" * (16 * 1024 + 1)),
                         413, "bad_request")
    assert "16 KB" in error["message"]


def test_chunked_bodies_over_16_kb_are_refused_while_reading(client):
    def chunks():
        for _ in range(5):
            yield b"y" * 4096

    r = client.post("/v1/session/demo", headers={"Origin": CORE}, content=chunks())
    assert r.request.headers.get("transfer-encoding") == "chunked"
    assert_error(r, 413, "bad_request")

    def small():
        yield b"{}"

    assert client.post("/v1/session/demo", headers={"Origin": CORE}, content=small()).status_code == 200


def test_a_non_numeric_content_length_is_refused(client):
    r = client.post("/v1/session/demo", headers={"Origin": CORE, "Content-Length": "12abc"}, content=b"")
    assert_error(r, 400, "bad_request")


# Routes and documentation ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/nowhere", "/v1", "/v1/", "/v1/digest/", "/health/", "/v1/session",
                                  "/docs", "/redoc", "/openapi.json"])
def test_unknown_routes_are_404_in_the_contract_shape(client, path):
    assert_error(client.get(path), 404, "not_found")


@pytest.mark.parametrize("method,path", [("GET", "/v1/session/demo"), ("POST", "/v1/digest"), ("DELETE", "/health"),
                                         ("PUT", "/v1/digest"), ("PATCH", "/v1/session/demo")])
def test_wrong_methods_are_405_in_the_contract_shape(client, method, path):
    r = client.request(method, path, headers={"Origin": CORE})
    error = assert_error(r, 405, "not_found")
    assert r.headers["allow"] and r.headers["allow"] in error["message"]


def test_the_schema_only_behind_the_flag_and_never_a_docs_page(settings):
    with make_client(settings, docs=True) as c:
        assert c.get("/openapi.json").json()["info"]["title"] == "FINN API"
        assert_error(c.get("/docs"), 404, "not_found")


def test_an_unexpected_error_is_a_500_in_the_contract_shape(settings):
    app = create_app(settings, clock=Clock(), monotonic=Ticker())

    @app.get("/v1/boom")
    def boom() -> None:
        raise RuntimeError("a bug")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/v1/boom", headers={"Origin": CORE})
    assert_error(r, 500, "unavailable")
    assert has_security_headers(r) and r.headers["access-control-allow-origin"] == CORE
