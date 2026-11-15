"""The demo investor: created once by the admin, then given holdings, default preferences and
coverage through the API role, scoped to that investor, exactly as the API itself will write them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg

from . import config, db

SEED = config.ROOT / "db" / "seed" / "demo.json"


def load(path: Path = SEED) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_demo(conn: psycopg.Connection, path: Path = SEED) -> dict[str, int]:
    data = load(path)
    inv = data["investor"]
    investor_id = UUID(inv["id"])
    with conn.transaction():  # investors are created by the admin only; the API role cannot
        conn.execute("""insert into finn.investors (id, display_name, is_demo, network_enabled)
                        values (%s, %s, true, %s)
                        on conflict (id) do update set display_name = excluded.display_name,
                          network_enabled = excluded.network_enabled""",
                     [investor_id, inv["display_name"], bool(inv.get("network_enabled"))])
    with db.as_role(conn, "finn_api", investor_id), conn.cursor() as cur:
        cur.executemany("""insert into finn.holdings (investor_id, symbol) values (%s, %s)
                           on conflict do nothing""", [(investor_id, s) for s in data["holdings"]])
        cur.execute("insert into finn.prefs (investor_id) values (%s) on conflict do nothing", [investor_id])
        cur.executemany("""insert into finn.coverage (symbol, reason) values (%s, %s)
                           on conflict (symbol) do nothing""",
                        [(s, "holding") for s in data["holdings"]] + [(s, "research") for s in data["research"]])
    return {"holdings": len(data["holdings"]), "research": len(data["research"])}
