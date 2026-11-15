"""Pull routes (docs/API.md, "Company research"): company search and the company page.

Authenticated like /v1/digest; each request reads in one transaction as finn_api. Nothing here is
investor data, but a session is still required, so the same rate limits and origin rules apply.
`register` is called once from `create_app`, which owns the session dependency and the pool."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query
from starlette.responses import JSONResponse

from finn import pull

from . import sessions
from .database import Database
from .errors import ApiError

Q = Annotated[str, Query(min_length=1, max_length=60, description="Symbol or part of a company's name")]


def register(app: FastAPI, database: Database, current_session: Callable[..., sessions.Session],
             now: Callable[[], datetime]) -> None:
    @app.get("/v1/companies")
    def companies(session: Annotated[sessions.Session, Depends(current_session)], q: Q) -> JSONResponse:
        try:
            query = pull.check_query(q)
        except ValueError as exc:
            raise ApiError(422, "bad_request", f"{exc}.") from None
        with database.connection() as conn:
            found: list[dict[str, Any]] = pull.search(conn, query)
        return JSONResponse({"query": query, "companies": found})

    @app.get("/v1/company/{symbol}")
    def company(session: Annotated[sessions.Session, Depends(current_session)], symbol: str) -> JSONResponse:
        try:
            checked = pull.check_symbol(symbol)
        except ValueError:
            raise ApiError(422, "bad_request", "A symbol is 1 to 20 letters, digits, '&' or '-'.") from None
        try:
            with database.connection() as conn:
                payload = pull.company_payload(conn, checked, now=now())
        except pull.NotFound:
            raise ApiError(404, "not_found", f"FINN knows no NSE company with the symbol {checked}.") from None
        return JSONResponse(payload)
