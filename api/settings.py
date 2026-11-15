"""The API's settings, read once at start-up and checked, so a misconfigured service refuses to
start (a red deploy on Render) instead of running half-secured.

Secrets (the database URL, the session secret, the Sentry DSN) are kept out of `repr`, so they
cannot reach a log line or an error report by printing the settings.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from finn import seed

Deployment = Literal["core", "full"]

MIN_SECRET_BYTES = 32
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_HEADER_NAME = re.compile(r"^[a-z0-9-]{1,64}$")


class ConfigError(RuntimeError):
    """A setting is missing or unsafe; the message names it and never contains its value."""


def parse_origins(name: str, raw: str) -> tuple[str, ...]:
    """A comma-separated allow-list of web origins (scheme://host[:port], nothing else).

    https only, except http on localhost for development. No wildcards: an origin on this list
    may obtain sessions, so each one is named exactly."""
    out: list[str] = []
    for part in raw.split(","):
        origin = part.strip().rstrip("/")
        if not origin:
            continue
        parts = urlsplit(origin)
        try:
            parts.port  # noqa: B018 - raises ValueError on a malformed port
        except ValueError:
            raise ConfigError(f"{name}: {origin!r} has a malformed port") from None
        local = parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS
        if (parts.scheme != "https" and not local) or not parts.hostname or "*" in origin \
                or parts.path or parts.query or parts.fragment or parts.username or parts.password:
            raise ConfigError(f"{name}: {origin!r} is not an origin like https://finn.example.app")
        out.append(f"{parts.scheme}://{parts.netloc.lower()}")
    return tuple(dict.fromkeys(out))


def short_version(commit: str | None) -> str:
    """The deployed commit as git shows it (seven characters), or "unknown"."""
    commit = (commit or "").strip()
    return commit[:7] if re.fullmatch(r"[0-9a-f]{7,40}", commit) else "unknown"


@dataclass(frozen=True)
class Settings:
    db_url: str = field(repr=False)
    session_secret: bytes = field(repr=False)
    origins_core: tuple[str, ...] = ()
    origins_full: tuple[str, ...] = ()
    demo_investor_id: UUID = field(default_factory=lambda: UUID(seed.load()["investor"]["id"]))
    version: str = "unknown"
    environment: str = "development"
    sentry_dsn: str | None = field(default=None, repr=False)
    # Header carrying the client's address, set by the platform's edge and not by the client
    # (Render: Cloudflare's True-Client-IP). None: use the connecting address.
    client_ip_header: str | None = None
    docs: bool = False  # API_DOCS=1: serve the OpenAPI schema at /openapi.json (never a docs page)
    statement_timeout_ms: int = 5000
    pool_min: int = 1
    pool_max: int = 4
    pool_wait_s: float = 5.0  # how long a request waits for a free connection
    health_wait_s: float = 2.0  # /health answers well inside Render's 5-second health check
    connect_timeout_s: int = 5
    session_hours: int = 12
    rate_v1_per_minute: int = 60
    rate_session_per_minute: int = 10
    body_limit_bytes: int = 16 * 1024

    def __post_init__(self) -> None:
        if not self.db_url:
            raise ConfigError("SUPABASE_DB_URL is not set: the API has no database to serve from")
        if len(self.session_secret) < MIN_SECRET_BYTES:
            raise ConfigError(f"SESSION_SECRET must be at least {MIN_SECRET_BYTES} bytes (Render generates one; "
                              "locally: python -c \"import secrets; print(secrets.token_urlsafe(48))\")")
        both = set(self.origins_core) & set(self.origins_full)
        if both:
            raise ConfigError(f"an origin cannot belong to both deployments: {sorted(both)}")
        if self.client_ip_header is not None and not _HEADER_NAME.match(self.client_ip_header):
            raise ConfigError("CLIENT_IP_HEADER must be a header name such as true-client-ip")
        if not 1 <= self.pool_min <= self.pool_max:
            raise ConfigError("pool sizes must satisfy 1 <= min <= max")

    @property
    def origins(self) -> frozenset[str]:
        return frozenset(self.origins_core + self.origins_full)

    def deployment_for(self, origin: str | None) -> Deployment | None:
        """Which deployment a web origin belongs to; None if it is not on either allow-list."""
        if origin in self.origins_core:
            return "core"
        if origin in self.origins_full:
            return "full"
        return None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        on_render = env.get("RENDER") == "true"
        header = env.get("CLIENT_IP_HEADER", "true-client-ip" if on_render else "").strip().lower() or None
        return cls(
            db_url=env.get("SUPABASE_DB_URL", ""),
            session_secret=env.get("SESSION_SECRET", "").encode(),
            origins_core=parse_origins("ALLOWED_ORIGINS_CORE", env.get("ALLOWED_ORIGINS_CORE", "")),
            origins_full=parse_origins("ALLOWED_ORIGINS_FULL", env.get("ALLOWED_ORIGINS_FULL", "")),
            version=short_version(env.get("RENDER_GIT_COMMIT")),
            environment=env.get("SENTRY_ENVIRONMENT") or ("production" if on_render else "development"),
            sentry_dsn=env.get("SENTRY_DSN_API") or None,
            client_ip_header=header,
            docs=env.get("API_DOCS") == "1",
        )
