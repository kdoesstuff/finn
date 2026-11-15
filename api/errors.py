"""The one error shape of docs/API.md: {"error": {"code": ..., "message": ...}}.

Used both by route handlers (`ApiError`) and by the ASGI middlewares, which answer before FastAPI
is reached (rate limits, body size, origins), so every refusal looks the same to the web app.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Literal

from starlette.responses import JSONResponse
from starlette.types import Send

Code = Literal["bad_request", "unauthorised", "forbidden", "not_found", "rate_limited", "unavailable"]


class ApiError(Exception):
    def __init__(self, status: int, code: Code, message: str, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, dict(headers or {})


def body(code: Code, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def response(status: int, code: Code, message: str, headers: Mapping[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


async def send(send_: Send, status: int, code: Code, message: str,
               headers: Iterable[tuple[str, str]] = ()) -> None:
    """Send a complete error response from inside an ASGI middleware."""
    payload = body(code, message)
    raw = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    raw += [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers]
    await send_({"type": "http.response.start", "status": status, "headers": raw})
    await send_({"type": "http.response.body", "body": payload, "more_body": False})
