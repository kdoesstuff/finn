"""ASGI middlewares, outermost first as `app.build` stacks them:

    SecurityHeaders   every response, including refusals, carries the security headers
    Cors              the two allow-listed web origins only; preflights answered here; a /v1
                      request from any other origin is refused (403)
    RateLimit         60 requests a minute per client for /v1, 10 for /v1/session/demo (429)
    BodyLimit         request bodies over 16 KB are refused (413)
    CatchAll          an unexpected error becomes a 500 in the contract's shape

They are plain ASGI (not Starlette's BaseHTTPMiddleware), so they add no task or buffering per
request, and each refusal is sent in the contract's error shape (`errors.send`).
"""

from __future__ import annotations

import logging
from collections.abc import Collection

import sentry_sdk
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import errors
from .ratelimit import Limiter, SlidingWindow, bucket, client_address

log = logging.getLogger("finn.api")

SECURITY_HEADERS = {
    # Two years, the value hstspreload.org asks for; no `preload`: onrender.com is not ours to list.
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # JSON only: nothing may load, run or frame. Browsers apply CSP to documents, so this matters
    # only if a response is ever opened directly, and then it disarms it.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    # Investor data and session tokens must not sit in a browser or proxy cache.
    "Cache-Control": "no-store",
}


class SecurityHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, with_headers)


class Cors:
    """CORS for an exact allow-list. A preflight from an allowed origin asking for an allowed method
    and headers gets 204 with the grant; anything else gets 403 in the contract's shape and no grant
    (the browser then refuses the real request). Non-preflight /v1 requests that carry an Origin not
    on the list are refused here too: browsers always send Origin on cross-site requests, so this
    stops a "simple" cross-site POST (no preflight) from any other website before it does anything."""

    def __init__(self, app: ASGIApp, origins: Collection[str], methods: Collection[str] = ("GET", "POST", "OPTIONS"),
                 headers: Collection[str] = ("Authorization", "Content-Type"),
                 expose: Collection[str] = ("Retry-After",), max_age: int = 600, guarded_prefix: str = "/v1") -> None:
        self.app = app
        self.origins = frozenset(origins)
        self.methods = tuple(m.upper() for m in methods)
        self.headers = tuple(headers)
        self.allowed_headers = frozenset(h.lower() for h in headers)
        self.expose = ", ".join(expose)
        self.max_age = str(max_age)
        self.guarded_prefix = guarded_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Headers(scope=scope)
        origin = request.get("origin")
        if origin is not None and scope["method"] == "OPTIONS" and "access-control-request-method" in request:
            await self._preflight(origin, request, send)
            return
        if origin is not None and origin not in self.origins and scope["path"].startswith(self.guarded_prefix):
            await errors.send(send, 403, "forbidden", "This website may not use FINN's API.", [("Vary", "Origin")])
            return

        async def with_grant(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.add_vary_header("Origin")
                if origin is not None and origin in self.origins:
                    headers["Access-Control-Allow-Origin"] = origin
                    headers["Access-Control-Expose-Headers"] = self.expose
            await send(message)

        await self.app(scope, receive, with_grant)

    async def _preflight(self, origin: str, request: Headers, send: Send) -> None:
        vary = ("Vary", "Origin, Access-Control-Request-Method, Access-Control-Request-Headers")
        method = request["access-control-request-method"].strip().upper()
        wanted = {h.strip().lower() for h in request.get("access-control-request-headers", "").split(",") if h.strip()}
        refused = ("origin" if origin not in self.origins else
                   "method" if method not in self.methods else
                   "headers" if not wanted <= self.allowed_headers else "")
        if refused:
            message = {"origin": "This website may not use FINN's API.",
                       "method": f"FINN's API does not accept {method or 'that method'} requests.",
                       "headers": "FINN's API accepts only the Authorization and Content-Type headers."}[refused]
            await errors.send(send, 403, "forbidden", message, [vary])
            return
        grant = [(b"access-control-allow-origin", origin.encode("latin-1")),
                 (b"access-control-allow-methods", ", ".join(self.methods).encode()),
                 (b"access-control-allow-headers", ", ".join(self.headers).encode()),
                 (b"access-control-max-age", self.max_age.encode()),
                 (b"vary", vary[1].encode()), (b"content-length", b"0")]
        await send({"type": "http.response.start", "status": 204, "headers": grant})
        await send({"type": "http.response.body", "body": b"", "more_body": False})


class RateLimit:
    def __init__(self, app: ASGIApp, limiter: Limiter, per_client: SlidingWindow, sessions: SlidingWindow,
                 client_ip_header: str | None, prefix: str = "/v1", session_path: str = "/v1/session/demo") -> None:
        self.app, self.limiter, self.per_client, self.sessions = app, limiter, per_client, sessions
        self.header, self.prefix, self.session_path = client_ip_header, prefix, session_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == self.prefix or path.startswith(self.prefix + "/")):
            await self.app(scope, receive, send)
            return
        key = bucket(client_address(scope, self.header))
        windows = [(self.per_client, key)]
        if path == self.session_path:
            windows.append((self.sessions, key))
        wait = self.limiter.hit(windows)
        if wait:
            await errors.send(send, 429, "rate_limited", f"Too many requests; try again in {wait} seconds.",
                              [("Retry-After", str(wait))])
            return
        await self.app(scope, receive, send)


class BodyLimit:
    """Refuses bodies over `limit` bytes, by Content-Length up front or while reading a chunked body.
    The body is read here (it is at most `limit` bytes) and replayed to the app, so an oversized
    body is refused even on a route that would never have read it."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        length = headers.get("content-length")
        too_large = f"Request bodies are limited to {self.limit // 1024} KB."
        if length is not None:
            if not length.isascii() or not length.isdigit():
                await errors.send(send, 400, "bad_request", "Content-Length is not a number.")
                return
            if int(length) > self.limit:
                await errors.send(send, 413, "bad_request", too_large)
                return
        elif "transfer-encoding" not in headers:
            await self.app(scope, receive, send)  # HTTP/1.1 without either header has no body
            return

        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":  # the client went away
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await errors.send(send, 413, "bad_request", too_large)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class CatchAll:
    """The last line: an error nothing else handled is reported (Sentry, logs) and answered with a
    500 in the contract's shape. It sits inside the CORS and header middlewares, so the web app can
    still read the answer; Starlette's own last-resort handler sits outside them and could not."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking)
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
            log.exception("unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            await errors.send(send, 500, "unavailable", "Something went wrong on FINN's side; the saved copy is "
                                                         "shown until it is fixed.")
