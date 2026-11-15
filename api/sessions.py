"""Session tokens: a small set of claims, signed with HMAC-SHA256 under SESSION_SECRET.

    token = base64url(claims JSON) "." base64url(HMAC-SHA256(secret, "finn.session.v1." + first part))

The signature is checked in constant time before anything in the token is parsed, so unsigned input
never reaches the JSON decoder. Claims are checked strictly (exact keys and types), and the token is
refused after `exp`. There is one algorithm and no header naming it, so there is nothing to
downgrade (the "alg: none" class of JWT mistakes cannot arise).

The token is a bearer credential sent in the Authorization header, never a cookie (docs/API.md).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID

VERSION = 1
_CONTEXT = b"finn.session.v1."
_PART = re.compile(r"^[A-Za-z0-9_-]+$")
_CLAIMS = {"v", "sub", "ro", "dep", "iat", "exp"}
MAX_TOKEN_CHARS = 1024
CLOCK_SKEW = 60  # seconds a token's issue time may lie in the future (another clock, same secret)


class InvalidToken(Exception):
    """Not a token this server issued, or altered since. The message is for logs, never for clients."""


class ExpiredToken(InvalidToken):
    pass


@dataclass(frozen=True)
class Session:
    investor_id: UUID
    read_only: bool
    deployment: Literal["core", "full"]
    issued_at: int  # Unix seconds
    expires_at: int


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    if not _PART.match(text):
        raise InvalidToken("not base64url")
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise InvalidToken("not base64url") from exc
    if _b64(raw) != text:  # one encoding per value: no malleable variants of a valid token
        raise InvalidToken("non-canonical base64url")
    return raw


def _mac(secret: bytes, payload: str) -> bytes:
    return hmac.new(secret, _CONTEXT + payload.encode("ascii"), hashlib.sha256).digest()


def issue(secret: bytes, investor_id: UUID, *, read_only: bool, deployment: Literal["core", "full"],
          now: datetime, ttl: timedelta) -> tuple[str, Session]:
    iat = int(now.timestamp())
    session = Session(investor_id, read_only, deployment, iat, iat + int(ttl.total_seconds()))
    claims = {"v": VERSION, "sub": str(investor_id), "ro": read_only, "dep": deployment, "iat": iat,
              "exp": session.expires_at}
    payload = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{payload}.{_b64(_mac(secret, payload))}", session


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidToken("time claim is not an integer")
    return value


def verify(secret: bytes, token: str, *, now: datetime, max_ttl: timedelta) -> Session:
    """The session a token carries; InvalidToken if it was not signed with `secret` or is malformed,
    ExpiredToken if it is past its expiry."""
    if not token or len(token) > MAX_TOKEN_CHARS or token.count(".") != 1:
        raise InvalidToken("wrong shape")
    payload, signature = token.split(".")
    if not hmac.compare_digest(_mac(secret, payload), _unb64(signature)):
        raise InvalidToken("bad signature")

    try:
        claims = json.loads(_unb64(payload))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidToken("claims are not JSON") from exc
    if not isinstance(claims, dict) or set(claims) != _CLAIMS or claims["v"] != VERSION:
        raise InvalidToken("unexpected claims")
    if not isinstance(claims["sub"], str) or not isinstance(claims["ro"], bool) \
            or claims["dep"] not in ("core", "full"):
        raise InvalidToken("claim of the wrong type")
    try:
        investor = UUID(claims["sub"])
    except ValueError as exc:
        raise InvalidToken("subject is not an investor id") from exc
    iat, exp = _int(claims["iat"]), _int(claims["exp"])
    t = int(now.timestamp())
    if exp <= iat or exp - iat > max_ttl.total_seconds() or iat > t + CLOCK_SKEW:
        raise InvalidToken("implausible times")
    if t >= exp:
        raise ExpiredToken("expired")
    return Session(investor, claims["ro"], cast(Literal["core", "full"], claims["dep"]), iat, exp)
