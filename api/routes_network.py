"""Network routes (Founding brief): served only to sessions started from the `full` site, and only
when the investor has the network switched on. A `core` session gets the same 404 as a route that
does not exist, so the core edition cannot even learn that Network is there.

    GET /v1/network/company/{symbol}?category=   who worked there, who can explain an event there
    GET /v1/network/person/{id}                  diligence on one person
    GET /v1/network/ask?q=                       a short question, answered with the matching type

Reads run as `finn_api` in the investor's scope (finn.network.load_graph); nothing is written.
"""

# No `from __future__ import annotations`: FastAPI reads these routes' annotations at run time, and
# `current_session` is a local of create_app (see api/app.py).

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Path, Query
from starlette.responses import JSONResponse

from finn import network

from . import sessions
from .database import Database
from .errors import ApiError

NOT_FOUND = ApiError(404, "not_found", "There is no such route.")
CATEGORIES = ("results", "management_change", "M&A", "capex", "fund_raise", "credit_rating", "litigation",
              "governance", "pledging", "insider_trading")

Symbol = Annotated[str, Path(pattern=r"^[A-Z0-9&-]{1,20}$")]
PersonId = Annotated[str, Path(pattern=r"^p[0-9]{3}$")]
Question = Annotated[str, Query(min_length=1, max_length=200)]


def register(app: FastAPI, database: Database, current_session: Callable[..., sessions.Session],
             now: Callable[[], datetime]) -> None:
    def full_session(session: Annotated[sessions.Session, Depends(current_session)]) -> sessions.Session:
        if session.deployment != "full":
            raise NOT_FOUND
        return session

    def graph_for(session: sessions.Session, conn: Any) -> network.Graph:
        graph = network.load_graph(conn, session.investor_id)
        if graph is None:  # the investor has the network switched off
            raise NOT_FOUND
        return graph

    @app.get("/v1/network/company/{symbol}")
    def network_company(session: Annotated[sessions.Session, Depends(full_session)], symbol: Symbol,
                        category: Annotated[str | None, Query(max_length=40)] = None) -> JSONResponse:
        if category is not None and category not in CATEGORIES:
            raise ApiError(422, "bad_request", "category must be one of: " + ", ".join(CATEGORIES) + ".")
        with database.connection() as conn:
            graph = graph_for(session, conn)
            return JSONResponse(network.company(graph, symbol, category, today=now().date()))

    @app.get("/v1/network/person/{person_id}")
    def network_person(session: Annotated[sessions.Session, Depends(full_session)],
                       person_id: PersonId) -> JSONResponse:
        with database.connection() as conn:
            graph = graph_for(session, conn)
            found = network.person(graph, person_id)
        if found is None:
            raise ApiError(404, "not_found", "There is no such person in your network.")
        return JSONResponse(found)

    @app.get("/v1/network/ask")
    def network_ask(session: Annotated[sessions.Session, Depends(full_session)], q: Question) -> JSONResponse:
        with database.connection() as conn:
            graph = graph_for(session, conn)
            return JSONResponse(network.ask(conn, session.investor_id, graph, q, today=now().date()))


def enrich_digest(conn: Any, session: sessions.Session, payload: Any, now: datetime) -> None:
    """Adds `who_to_call` to the digest's items, in place, for `full` sessions only (core: nothing)."""
    if session.deployment == "full":
        network.enrich(conn, session.investor_id, payload, today=now.date())
