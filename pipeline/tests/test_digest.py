"""The digest as the API serves it, from filings stored in a Supabase-shaped Postgres.

The week of real NSE filings in tests/fixtures is stored through ingest (as finn_ingest, exactly as
the scheduled job stores it) and read back through `digest_payload` (as finn_api, scoped to one
investor). The expected digest is computed independently, by running the ranker on the same
fixture rows parsed straight from the file: the two paths must agree item for item.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

import psycopg
import pytest

from finn import db, digest, ingest, rank, seed
from finn.sources import nse
from tests.dbtools import INVESTOR_A, INVESTOR_B, admin_url

FIX = Path(__file__).parent / "fixtures"
DEMO = UUID(seed.load()["investor"]["id"])
NOW = datetime(2026, 11, 9, 23, 59, tzinfo=digest.IST)
HOURS = 144  # back to 3 Nov 23:59: the whole fixture week


def fixture_rows() -> list[dict[str, Any]]:
    return json.loads((FIX / "nse_announcements.json").read_text(encoding="utf-8"))["rows"]


@pytest.fixture(scope="module")
def stored(admin: psycopg.Connection) -> psycopg.Connection:
    counts = ingest.store_filings(admin, fixture_rows())
    assert counts["unusable"] == 0
    seed.seed_demo(admin)
    return admin


def expected(symbols: set[str], now: datetime = NOW, hours: int = HOURS) -> dict:
    """The ranker on the fixture file itself, for the same holdings and window."""
    start, end = (now - timedelta(hours=hours)).replace(tzinfo=None), now.replace(tzinfo=None)
    anns = [a for a in (nse.parse_announcement(r) for r in fixture_rows())
            if a.symbol in symbols and start < a.ts <= end]
    return rank.build_digest(anns, [])


def ids(items: list) -> list[str]:
    return [i["id"] if isinstance(i, dict) else i.announcement.id for i in items]


def test_digest_agrees_with_the_ranker_on_the_real_week(stored):
    out = digest.digest_payload(stored, DEMO, HOURS, now=NOW)
    want = expected(set(seed.load()["holdings"]))
    assert out["portfolio"] == {"holdings": 18}
    assert ids(out["attention"]) == ids(want["attention"])
    assert ids(out["worth"]) == ids(want["worth"])
    assert out["routine"] == {"count": len(want["routine"]), "by_kind": want["routine_counts"]}
    assert out["summary"] == want["summary"]
    assert out["window"] == {"hours": 144, "from": "2026-11-03T23:59:00+05:30", "to": "2026-11-09T23:59:00+05:30"}
    assert out["unexplained_moves"] == []
    for got, item in zip(out["attention"] + out["worth"], want["attention"] + want["worth"], strict=True):
        assert got["score"] == item.score and got["reasons"] == item.reasons
        assert [r["id"] for r in got["related"]] == [r.id for r in item.related]


def test_named_events_land_where_the_filings_put_them(stored):
    out = digest.digest_payload(stored, DEMO, HOURS, now=NOW)
    attention = {i["id"]: i for i in out["attention"]}
    worth = {i["id"]: i for i in out["worth"]}

    elgi = attention["106849670"]  # Elgi's Sep 2026 results, its investor presentation on the same card
    assert (elgi["symbol"], elgi["category"], elgi["score"]) == ("ELGIEQUIP", "results", 85)
    assert [r["id"] for r in elgi["related"]] == ["106850445"]

    cto = worth["106852003"]  # Manappuram's Group CTO resigned: below the top team, so worth knowing
    assert (cto["role"], cto["action"], cto["score"]) == ("senior", "resignation", 70)
    assert "Group Chief Technology Officer" in cto["headline"]

    puri = worth["106851770"]  # Asian Paints: one card for two filings about one appointment
    assert puri["headline"].startswith("Appointment of Mr Leo Puri as Independent Director")
    assert puri["ts"] == "2026-11-06T22:06:58+05:30"
    assert puri["detail_in_document"] is False
    assert [(r["id"], r["headline"]) for r in puri["related"]] == [("106851762", "Change in Director(s)")]

    hdfc = worth["106850382"]  # the summary only restates NSE's label: the PDF says who
    assert hdfc["headline"] == hdfc["label"] == "Change in Management"
    assert hdfc["detail_in_document"] is True
    assert all(i["url"].startswith("https://nsearchives.nseindia.com/") for i in out["attention"] + out["worth"])


def test_window_is_open_at_the_start_and_closed_at_the_end(stored):
    filed = datetime(2026, 11, 6, 12, 14, 12, tzinfo=digest.IST)  # Elgi's results

    def has_elgi(now: datetime, hours: int) -> bool:
        out = digest.digest_payload(stored, DEMO, hours, now=now)
        return "106849670" in ids(out["attention"])

    assert has_elgi(filed, 1)  # published exactly at `now`: in
    assert not has_elgi(filed - timedelta(seconds=1), 1)  # a second before it was published: not yet
    assert not has_elgi(filed + timedelta(hours=1), 1)  # exactly `hours` ago: out
    assert has_elgi(filed + timedelta(hours=1) - timedelta(seconds=1), 1)


def test_quiet_window_says_so(stored):
    out = digest.digest_payload(stored, DEMO, 24, now=datetime(2026, 10, 1, 9, 0, tzinfo=digest.IST))
    assert out["summary"] == "Nothing material across your portfolio."
    assert out["attention"] == out["worth"] == [] and out["routine"] == {"count": 0, "by_kind": {}}


def test_an_investor_sees_only_their_own_holdings(stored):
    # Investor B holds MRF only; A holds TCS only (conftest). The demo investor holds 18 names.
    b = digest.digest_payload(stored, INVESTOR_B, HOURS, now=NOW)
    assert b["portfolio"] == {"holdings": 1}
    assert {i["symbol"] for i in b["attention"] + b["worth"]} <= {"MRF"}
    a = digest.digest_payload(stored, INVESTOR_A, HOURS, now=NOW)
    assert {i["symbol"] for i in a["attention"] + a["worth"]} == {"TCS"}
    nobody = digest.digest_payload(stored, UUID(int=0xC), HOURS, now=NOW)
    assert nobody["portfolio"] == {"holdings": 0} and nobody["summary"] == "Nothing material across your portfolio."


def test_hours_outside_the_contract_are_refused(stored):
    for bad in (0, 745, -1, True, 1.5, "24", None):
        with pytest.raises(ValueError, match="hours must be a whole number"):
            digest.digest_payload(stored, DEMO, bad, now=NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="zone"):
        digest.digest_payload(stored, DEMO, 24, now=NOW.replace(tzinfo=None))
    assert digest.digest_payload(stored, DEMO, 744, now=NOW)["window"]["hours"] == 744


def test_data_as_of_is_the_last_successful_filings_run(stored):
    assert digest.data_as_of(stored) is None
    with db.as_role(stored, "finn_ingest"):
        # A success, then a later failure, a later success of another job, and a run still going.
        stored.execute("""insert into finn.ingest_runs (job, started_at, finished_at, ok) values
                          ('filings 2026-11-08..09', '2026-11-09 23:30+05:30', '2026-11-09 23:31:05+05:30', true),
                          ('filings 2026-11-08..09', '2026-11-09 23:45+05:30', '2026-11-09 23:46:00+05:30', false),
                          ('eod', '2026-11-09 23:50+05:30', '2026-11-09 23:52:00+05:30', true),
                          ('filings 2026-11-09..10', '2026-11-09 23:55+05:30', null, null)""")
    as_of = digest.data_as_of(stored)
    assert as_of is not None and digest.iso(as_of) == "2026-11-09T23:31:05+05:30"
    assert digest.digest_payload(stored, DEMO, HOURS, now=NOW)["data_as_of"] == "2026-11-09T23:31:05+05:30"


def test_times_are_indian_with_the_offset():
    assert digest.IST == ingest.IST
    assert digest.iso(datetime(2026, 11, 6, 16, 36, 58, tzinfo=timezone.utc)) == "2026-11-06T22:06:58+05:30"
    with pytest.raises(ValueError):
        digest.iso(datetime(2026, 11, 6, 22, 6, 58))


def _script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "export_snapshot.py"
    spec = importlib.util.spec_from_file_location("export_snapshot", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_is_the_digest_plus_its_label(stored, database, tmp_path, monkeypatch):
    script = _script()
    snap = script.snapshot(stored, DEMO, HOURS, now=NOW)
    assert snap["snapshot"] is True and snap["generated_at"] == "2026-11-09T23:59:00+05:30"
    assert {k: v for k, v in snap.items() if k not in ("snapshot", "generated_at")} == \
        dict(digest.digest_payload(stored, DEMO, HOURS, now=NOW))

    # The command itself: default seven-day window, reading SUPABASE_DB_URL, written in one step.
    monkeypatch.setenv("SUPABASE_DB_URL", admin_url(database))
    out = tmp_path / "public" / "snapshot.json"
    assert script.main(["--out", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["snapshot"] is True and written["window"]["hours"] == 168
    assert set(written) == set(snap)
    assert [p.name for p in out.parent.iterdir()] == ["snapshot.json"]  # no temporary file left behind
    with pytest.raises(SystemExit):
        script.main(["--out", str(out), "--hours", "745"])
