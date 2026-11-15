"""FINN's API (docs/API.md): GET /health, POST /v1/session/demo, GET /v1/digest.

`create_app` builds the service from checked `Settings`; tests build it with a scratch database, a
fixed clock and fake secrets. Route handlers are plain functions, run by FastAPI in its thread pool
next to the synchronous psycopg pool.

No `from __future__ import annotations` here: FastAPI reads the route functions' annotations at
run time, and a postponed annotation cannot name `current_session`, which is local to create_app.
"""

import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any

import psycopg
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BeforeValidator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from finn import db as fdb
from finn.digest import DEFAULT_HOURS, IST, MAX_HOURS, MIN_HOURS, data_as_of, digest_payload, iso

from . import errors, routes_network, routes_pull, sessions
from .database import Database, Unavailable
from .errors import ApiError
from .middleware import BodyLimit, CatchAll, Cors, RateLimit, SecurityHeaders
from .ratelimit import Limiter, SlidingWindow
from .settings import Settings

log = logging.getLogger("finn.api")

HEALTH_CACHE_S = 10.0  # /health needs no auth, so its database check is shared, not per request
HOURS_MESSAGE = f"hours must be a whole number from {MIN_HOURS} to {MAX_HOURS} (default {DEFAULT_HOURS})."


def _now_ist() -> datetime:
    return datetime.now(IST)


def _whole_number(value: object) -> object:
    """Digits only: refuse "1.0", "+24", " 24" and "1e2", which a lenient integer parse accepts."""
    if isinstance(value, str) and not (value.isascii() and value.isdigit()):
        raise ValueError("not a whole number")
    return value


Hours = Annotated[int, BeforeValidator(_whole_number),
                  Query(ge=MIN_HOURS, le=MAX_HOURS, description="The window in hours, 1 to 744")]


@dataclass
class _HealthCache:
    at: float = float("-inf")
    db: bool = False
    data_as_of: str | None = None


class Health:
    """/health's database check: never an error (Render restarts a service whose health check
    fails), and at most one database call per HEALTH_CACHE_S however often it is asked."""

    def __init__(self, database: Database, wait_s: float, monotonic: Callable[[], float]) -> None:
        self.database, self.wait_s, self.monotonic = database, wait_s, monotonic
        self._cache = _HealthCache()
        self._lock = threading.Lock()

    def check(self) -> tuple[bool, str | None]:
        with self._lock:
            now = self.monotonic()
            if now - self._cache.at < HEALTH_CACHE_S:
                return self._cache.db, self._cache.data_as_of
            try:
                with self.database.connection(wait_s=self.wait_s) as conn:
                    as_of = data_as_of(conn)
                self._cache = _HealthCache(now, True, iso(as_of) if as_of else None)
            except Unavailable:
                self._cache = _HealthCache(now, False, None)
            except psycopg.Error as exc:  # reachable but wrong (say, a migration not applied): say so, loudly
                log.error("health check failed: %s", type(exc).__name__)
                self._cache = _HealthCache(now, False, None)
            return self._cache.db, self._cache.data_as_of


def _validation_message(exc: RequestValidationError) -> str:
    names = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        names.append(str(loc[-1]) if loc else "request")
    if names and all(n == "hours" for n in names):
        return HOURS_MESSAGE
    return "Invalid parameter: " + ", ".join(sorted(set(names))) + "."


def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return errors.response(exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(Unavailable)
    async def unavailable(_: Request, exc: Unavailable) -> JSONResponse:
        return errors.response(503, "unavailable", "FINN's data store cannot be reached right now.")

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        return errors.response(422, "bad_request", _validation_message(exc))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        headers = dict(exc.headers or {})
        if exc.status_code == 404:
            return errors.response(404, "not_found", "There is no such route.", headers)
        if exc.status_code == 405:
            allow = headers.get("Allow") or headers.get("allow") or ""
            return errors.response(405, "not_found", f"This route does not take that method (it takes {allow}).",
                                   headers)
        if exc.status_code < 500:
            return errors.response(exc.status_code, "bad_request", "The request could not be understood.", headers)
        return errors.response(exc.status_code, "unavailable", "FINN cannot answer right now.", headers)


def create_app(settings: Settings, *, database: Database | None = None,
               clock: Callable[[], datetime] | None = None, monotonic: Callable[[], float] = time.monotonic) -> FastAPI:
    """The API. `clock` (aware datetimes) decides "now" for the digest window and token expiry."""
    now = clock or _now_ist
    database = database or Database(settings.db_url, min_size=settings.pool_min, max_size=settings.pool_max,
                                    statement_timeout_ms=settings.statement_timeout_ms,
                                    connect_timeout_s=settings.connect_timeout_s, wait_s=settings.pool_wait_s)
    health_check = Health(database, settings.health_wait_s, monotonic)
    ttl = timedelta(hours=settings.session_hours)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if not settings.origins:
            log.warning("ALLOWED_ORIGINS_CORE and ALLOWED_ORIGINS_FULL are empty: no website can start a session")
        yield
        database.close()

    # No documentation pages: their scripts would break the JSON-only content security policy, and
    # production exposes nothing beyond the contract. API_DOCS=1 serves the schema as JSON.
    app = FastAPI(
        title="FINN API", version=settings.version, lifespan=lifespan, redirect_slashes=False,
        docs_url=None, redoc_url=None, openapi_url="/openapi.json" if settings.docs else None,
    )
    _install_handlers(app)

    def current_session(request: Request) -> sessions.Session:
        header = request.headers.get("authorization")
        if not header:
            raise ApiError(401, "unauthorised", "Sign in: this needs a session token.", {"WWW-Authenticate": "Bearer"})
        scheme, _, token = header.partition(" ")
        invalid = ApiError(401, "unauthorised", "Sign in again: your session is not valid.",
                           {"WWW-Authenticate": 'Bearer error="invalid_token"'})
        if scheme.lower() != "bearer":
            raise invalid
        try:
            session = sessions.verify(settings.session_secret, token.strip(), now=now(), max_ttl=ttl)
        except sessions.ExpiredToken:
            raise ApiError(401, "unauthorised", "Sign in again: your session has expired.",
                           {"WWW-Authenticate": 'Bearer error="invalid_token"'}) from None
        except sessions.InvalidToken:
            raise invalid from None
        # A session belongs to the site that started it: the Network switch differs between the two.
        deployment = settings.deployment_for(request.headers.get("origin"))
        if deployment is not None and deployment != session.deployment:
            raise invalid
        return session

    @app.get("/health")
    def health() -> dict[str, Any]:
        db_ok, as_of = health_check.check()
        return {"ok": True, "db": db_ok, "data_as_of": as_of, "version": settings.version}

    # Some uptime monitors check with HEAD; same answer, no body, kept out of the schema.
    app.add_api_route("/health", health, methods=["HEAD"], include_in_schema=False)

    @app.post("/v1/session/demo")
    def demo_session(request: Request) -> dict[str, Any]:
        deployment = settings.deployment_for(request.headers.get("origin"))
        if deployment is None:
            raise ApiError(403, "forbidden", "Sessions are started only from FINN's own web app.")
        investor = settings.demo_investor_id
        with database.connection() as conn, fdb.as_role(conn, "finn_api", investor):
            row = conn.execute("select display_name, is_demo, network_enabled from finn.investors where id = %s",
                               [investor]).fetchone()
        if row is None:
            raise ApiError(503, "unavailable", "The demo investor is not set up yet.")
        name, is_demo, network_enabled = row
        token, session = sessions.issue(settings.session_secret, investor, read_only=True, deployment=deployment,
                                        now=now(), ttl=ttl)
        return {"token": token, "expires_at": iso(datetime.fromtimestamp(session.expires_at, IST)),
                "investor": {"name": name, "demo": bool(is_demo),
                             "network": deployment == "full" and bool(network_enabled)}}

    routes_pull.register(app, database, current_session, now)  # Pull: /v1/companies, /v1/company/{symbol}

    @app.get("/v1/digest")
    def digest(session: Annotated[sessions.Session, Depends(current_session)],
               hours: Hours = DEFAULT_HOURS) -> JSONResponse:
        with database.connection() as conn:
            payload = digest_payload(conn, session.investor_id, hours, now=now())
            # --- Network stream: who to call, full edition only ---
            routes_network.enrich_digest(conn, session, payload, now())
        return JSONResponse(payload)

    # --- Network stream: /v1/network/*, full edition only ---
    routes_network.register(app, database, current_session, now)

    # Outermost last: SecurityHeaders wraps everything, so every answer carries its headers.
    limiter = Limiter(monotonic)
    app.add_middleware(CatchAll)
    app.add_middleware(BodyLimit, limit=settings.body_limit_bytes)
    app.add_middleware(RateLimit, limiter=limiter, per_client=SlidingWindow(settings.rate_v1_per_minute),
                       sessions=SlidingWindow(settings.rate_session_per_minute),
                       client_ip_header=settings.client_ip_header)
    app.add_middleware(Cors, origins=settings.origins)
    app.add_middleware(SecurityHeaders)
    return app
