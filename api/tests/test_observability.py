"""Sentry: off without a DSN; when on, nothing personal or secret leaves the server. The end-to-end
test captures what the SDK would send (a transport that keeps envelopes instead of posting them)
for a real failing request that carries a token, a cookie and a database URL."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from api import observability
from api.app import create_app
from api.tests.helpers import CORE, DEMO, Clock, Ticker, mint

FAKE_DSN = "https://0123456789abcdef0123456789abcdef@o0.ingest.sentry.invalid/0"
DB_URL = "postgresql://postgres.project:not-a-real-password@pooler.invalid:5432/postgres"


class Keep(Transport):
    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.envelopes: list[Any] = []

    def capture_envelope(self, envelope: Any) -> None:
        self.envelopes.append(envelope)


def test_sentry_stays_off_without_a_dsn(settings, monkeypatch):
    def refuse(**_: Any) -> None:
        raise AssertionError("sentry_sdk.init must not be called without a DSN")

    monkeypatch.setattr(sentry_sdk, "init", refuse)
    assert observability.init(settings) is False


def test_sentry_options_collect_nothing_personal(settings):
    opts = observability.options(replace(settings, sentry_dsn=FAKE_DSN, environment="production"))
    dc = opts["data_collection"]
    assert dc["user_info"] is False and dc["stack_frame_variables"] is False and dc["http_bodies"] == []
    assert dc["cookies"] == {"mode": "off"} and dc["database_query_data"] is False
    assert dc["http_headers"]["request"]["mode"] == "allowlist"
    assert "send_default_pii" not in opts  # deprecated in sentry-sdk 2.75; data_collection supersedes it
    assert opts["traces_sample_rate"] == 0.05 and opts["environment"] == "production"
    assert opts["release"] == "finn-api@abc1234"
    assert opts["before_send"] is opts["before_breadcrumb"] is observability.scrub


def test_scrub_removes_credentials_wherever_they_appear():
    token = mint(DEMO)
    event = {
        "request": {"headers": {"Authorization": f"Bearer {token}", "Cookie": "a=b", "True-Client-IP": "203.0.113.9",
                                "User-Agent": "test"}, "cookies": {"a": "b"}, "data": {"x": 1}},
        "message": f"failed with {token}",
        "exception": {"values": [{"type": "OperationalError", "value": f"could not use {DB_URL} (Bearer abc.def)"}]},
        "breadcrumbs": {"values": [{"message": f"retry {DB_URL}"}]},
        "extra": {"authorization": "Bearer x", "nested": [{"token_text": token}]},
    }
    clean = json.dumps(observability.scrub(event))
    for secret in (token, "not-a-real-password", "Bearer abc", "203.0.113.9", "a=b"):
        assert secret not in clean
    out = observability.scrub(event)
    assert out["request"]["headers"] == {"User-Agent": "test"}
    assert "cookies" not in out["request"] and "data" not in out["request"]
    assert out["exception"]["values"][0]["type"] == "OperationalError"


@pytest.fixture
def captured(settings) -> Iterator[Keep]:
    keep = Keep()
    sentry_sdk.init(**observability.options(replace(settings, sentry_dsn=FAKE_DSN)), transport=keep)
    yield keep
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # no DSN: a client that sends nothing, for the tests that follow


def test_a_real_error_report_carries_no_token_cookie_ip_or_database_url(settings, captured):
    token = mint(DEMO)
    app = create_app(settings, clock=Clock(), monotonic=Ticker())

    @app.get("/v1/boom")
    def boom() -> None:
        session_token = token  # a local variable holding the token: must not be sent
        raise RuntimeError(f"failed for {session_token} against {DB_URL}")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/v1/boom", params={"hours": 24}, headers={"Origin": CORE, "Authorization": f"Bearer {token}",
                                                              "Cookie": "session=abc", "True-Client-IP": "203.0.113.9"})
    assert r.status_code == 500
    sentry_sdk.flush()

    events = [item.payload.json for env in captured.envelopes for item in env.items if item.type == "event"]
    assert len(events) == 1
    frames = [f for v in events[0]["exception"]["values"] for f in v.get("stacktrace", {}).get("frames", [])]
    assert frames and not any("vars" in f for f in frames)
    for f in frames:  # source lines around each frame are this file's code, which spells the fakes out
        for key in ("pre_context", "context_line", "post_context"):
            f.pop(key, None)
    sent = json.dumps(events[0])
    assert "RuntimeError" in sent  # the error itself is reported
    for secret in (token, token.split(".")[1], "not-a-real-password", "session=abc", "203.0.113.9"):
        assert secret not in sent
    headers = {k.lower() for k in events[0].get("request", {}).get("headers", {})}
    assert not headers & {"authorization", "cookie", "true-client-ip", "x-forwarded-for"}


def test_log_lines_are_redacted_tracebacks_included():
    token = mint(DEMO)
    formatter = observability.RedactingFormatter("%(message)s")
    try:
        raise RuntimeError(f"connect {DB_URL} failed for {token}")
    except RuntimeError:
        record = logging.LogRecord("finn.api", logging.ERROR, __file__, 1, "request with %s", (f"Bearer {token}",),
                                   sys.exc_info())
    text = formatter.format(record)
    assert "RuntimeError" in text and "Traceback" in text
    assert token not in text and "not-a-real-password" not in text
