"""Constants and helpers shared by the API's tests (fixtures are in conftest.py)."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from api import sessions
from api.app import create_app
from api.settings import Settings
from finn import digest, seed

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "pipeline" / "tests" / "fixtures"
SECRET = b"test-only-session-secret-0123456789-not-a-real-one"
CORE, FULL, ELSEWHERE = "https://finn-core.test.invalid", "https://finn.test.invalid", "https://evil.test.invalid"
NOW = datetime(2026, 11, 9, 23, 59, tzinfo=digest.IST)
DEMO = UUID(seed.load()["investor"]["id"])
DEMO_HOLDINGS = frozenset(seed.load()["holdings"])
OTHER = UUID("0b0b0b0b-0000-4000-8000-00000000000b")
OTHER_HOLDINGS = frozenset({"SADBHAV", "DABUR"})  # both have attention-level filings in the fixture week
DATA_AS_OF = "2026-11-09T23:31:05+05:30"


def fixture_rows() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "nse_announcements.json").read_text(encoding="utf-8"))["rows"]


class Clock:
    """A settable wall clock (aware datetimes) for the digest window and token expiry."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Ticker:
    """A settable monotonic clock for the rate limiter and the health cache."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make_client(settings: Settings, clock: Clock | None = None, ticker: Ticker | None = None, **overrides: Any
                ) -> TestClient:
    """A client for an app with changed settings (use as a context manager)."""
    return TestClient(create_app(replace(settings, **overrides), clock=clock or Clock(), monotonic=ticker or Ticker()))


def token_for(client: TestClient, origin: str = CORE) -> str:
    r = client.post("/v1/session/demo", headers={"Origin": origin})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def mint(investor: UUID, *, deployment: str = "core", now: datetime = NOW, secret: bytes = SECRET,
         ttl: timedelta = timedelta(hours=12)) -> str:
    """A token signed like the server signs them, for an investor the demo endpoint does not serve."""
    token, _ = sessions.issue(secret, investor, read_only=False, deployment=deployment,  # type: ignore[arg-type]
                              now=now, ttl=ttl)
    return token


def claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def assert_error(response: Any, status: int, code: str) -> dict[str, Any]:
    """The contract's one error shape, exactly: {"error": {"code", "message"}}."""
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]


def api_examples() -> dict[str, Any]:
    """The JSON examples in docs/API.md, keyed by what they show. The digest example writes its
    item lists as `[Item]`; those are read as empty lists and items are checked against the Item
    example instead."""
    text = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    out: dict[str, Any] = {}
    for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL):
        example = json.loads(re.sub(r"\[(Item|Move|Pledge)\]", "[]", block))
        kind = next(k for k, key in (("error", "error"), ("session", "token"), ("health", "ok"),
                                     ("digest", "window"), ("companies", "companies"), ("company", "coverage"),
                                     ("item", "headline"), ("results", "quarter"),
                                     ("move", "fired_by"), ("pledge", "pct_of_promoter"),
                                     ("note", "person")) if key in example)
        out[kind] = example
    assert set(out) == {"error", "session", "health", "digest", "item", "results", "move", "pledge",
                        "companies", "company", "note"}, \
        "docs/API.md examples changed"
    return out


# Fields the contract allows to be null, and fields whose shape is a named example of its own.
NULLABLE = {"results", "margin", "pct", "margin_bps", "sigma", "change_pct_points", "data_as_of", "note",
            "person"}
NAMED = {"results": "results", "moves": "move", "unexplained_moves": "move", "pledges": "pledge", "note": "note"}
_examples: dict[str, Any] = {}


def _named(kind: str) -> Any:
    if not _examples:
        _examples.update(api_examples())
    return _examples[kind]


def same_shape(actual: Any, example: Any, path: str = "$") -> None:
    """`actual` has exactly the example's keys, recursively, with values of the same JSON types.
    Lists are checked element by element against the example's first element; `by_kind` maps
    kinds (data, not schema) to counts."""
    key = re.sub(r"\[\d+\]$", "", path).rsplit(".", 1)[-1]
    if actual is None and key in NULLABLE:
        return
    if key in NAMED and example in (None, []):
        example = _named(NAMED[key]) if key in ("results", "note") else [_named(NAMED[key])]
    if path.endswith(".by_kind"):
        assert isinstance(actual, dict) and all(isinstance(k, str) and type(v) is int for k, v in actual.items()), path
        return
    if isinstance(example, dict):
        assert isinstance(actual, dict), f"{path}: expected an object"
        differ = sorted(set(actual) ^ set(example))
        assert not differ, f"{path}: keys differ from the contract: {differ}"
        for key, value in example.items():
            same_shape(actual[key], value, f"{path}.{key}")
    elif isinstance(example, list):
        assert isinstance(actual, list), f"{path}: expected a list"
        for i, element in enumerate(actual):
            if example:
                same_shape(element, example[0], f"{path}[{i}]")
    else:
        assert type(actual) is type(example), \
            f"{path}: {type(actual).__name__} where the contract shows {type(example).__name__}"
