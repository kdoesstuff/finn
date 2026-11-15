"""Error reporting to Sentry, only when SENTRY_DSN_API is set, with nothing personal or secret in it.

What is collected is set with `data_collection`, which in the pinned sentry-sdk (2.75) supersedes
`send_default_pii` (deprecated there): no user identity, no cookies, no request bodies, no local
variables from stack frames (they would hold tokens and settings), no database query data, and
only a few harmless request headers. `scrub` then removes, from every event and breadcrumb, any
Authorization or cookie header, anything shaped like a FINN session token or a bearer credential,
and any database URL, wherever it appears (messages, exception text, URLs). Errors are sampled in
full; traces at 5%, enough for latency on a demo's traffic within the free quota.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from .settings import Settings

TRACES_SAMPLE_RATE = 0.05
REDACTED = "[redacted]"
_DROP_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization", "true-client-ip",
                 "cf-connecting-ip", "x-forwarded-for", "x-real-ip", "forwarded"}
_SECRETS = [
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{43}\b"),  # a FINN session token (32-byte MAC)
    re.compile(r"(?i)\bpostgres(?:ql)?://\S+"),
]


def _clean_text(text: str) -> str:
    for pattern in _SECRETS:
        text = pattern.sub(REDACTED, text)
    return text


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        return {k: (REDACTED if isinstance(k, str) and k.lower() in _DROP_HEADERS else _clean(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_clean(v) for v in value)
    return value


class RedactingFormatter(logging.Formatter):
    """Log lines, tracebacks included, with tokens and database URLs redacted (Render keeps logs)."""

    def format(self, record: logging.LogRecord) -> str:
        return _clean_text(super().format(record))


def configure_logging(level: int = logging.INFO) -> None:
    """Root logging for the service: one stream handler whose output is redacted. Uvicorn's own
    loggers keep their handlers; they log requests by path, never headers."""
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def scrub(event: Any, hint: Any = None) -> Any:
    """Sentry's before_send / before_send_transaction / before_breadcrumb: the event, cleaned."""
    request = event.get("request") if isinstance(event, dict) else None
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() not in _DROP_HEADERS}
    return _clean(event)


def options(settings: Settings) -> dict[str, Any]:
    return {
        "dsn": settings.sentry_dsn,
        "environment": settings.environment,
        "release": None if settings.version == "unknown" else f"finn-api@{settings.version}",
        "traces_sample_rate": TRACES_SAMPLE_RATE,
        "data_collection": {
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {"request": {"mode": "allowlist", "terms": ["user-agent", "content-type", "origin"]}},
            "http_bodies": [],
            "url_query_params": {"mode": "allowlist", "terms": ["hours"]},
            "database_query_data": False,
            "stack_frame_variables": False,
        },
        "max_request_body_size": "never",
        "before_send": scrub,
        "before_send_transaction": scrub,
        "before_breadcrumb": scrub,
        "server_name": "finn-api",  # not the host name of the machine
        "integrations": [StarletteIntegration(transaction_style="endpoint"),
                         FastApiIntegration(transaction_style="endpoint")],
    }


def init(settings: Settings) -> bool:
    """Start Sentry if a DSN is configured. Call before the app is built. True if started."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(**options(settings))
    return True
