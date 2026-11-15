"""The digest as the API serves it, from filings stored in a Supabase-shaped Postgres.

The week of real NSE filings in tests/fixtures is stored through ingest (as finn_ingest, exactly as
the scheduled job stores it) and read back through `digest_payload` (as finn_api, scoped to one
investor). The expected digest is computed independently, by running the ranker on the same
fixture rows parsed straight from the file: the two paths must agree item for item.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
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
    assert out["portfolio"] == {"holdings": 18, "pledges": []}
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
    assert b["portfolio"] == {"holdings": 1, "pledges": []}
    assert {i["symbol"] for i in b["attention"] + b["worth"]} <= {"MRF"}
    a = digest.digest_payload(stored, INVESTOR_A, HOURS, now=NOW)
    assert {i["symbol"] for i in a["attention"] + a["worth"]} == {"TCS"}
    nobody = digest.digest_payload(stored, UUID(int=0xC), HOURS, now=NOW)
    assert nobody["portfolio"] == {"holdings": 0, "pledges": []}
    assert nobody["summary"] == "Nothing material across your portfolio."


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


# Results, moves and pledges (tasks D1, D4, D3) -----------------------------------------------------

ELGI_FACTS = {  # ₹ crore; one quarter of Elgi's general template, made up for the test, consistent
    date(2026, 9, 30): (980.0, 12.0, 4.0, 18.0, 0.0, 140.0, 104.0),
    date(2026, 6, 30): (900.0, 10.0, 4.0, 17.0, 0.0, 120.0, 90.0),
    date(2025, 9, 30): (880.0, 11.0, 5.0, 16.0, -6.0, 110.0, 80.0),
}


def store_elgi_results(conn: psycopg.Connection, consolidated: bool = True) -> None:
    rows = []
    for end, (rev, oth, fin, dep, exc, pbt, pat) in ELGI_FACTS.items():
        facts = {"RevenueFromOperations": rev, "OtherIncome": oth, "FinanceCosts": fin,
                 "DepreciationDepletionAndAmortisationExpense": dep, "ExceptionalItemsBeforeTax": exc,
                 "ProfitBeforeTax": pbt, "ProfitOrLossAttributableToOwnersOfParent": pat,
                 "SomethingTheCardDoesNotRead": 1.0}
        start = date(end.year, end.month - 2, 1)
        rows.append(("ELGIEQUIP", end, consolidated, "general", start, end,
                     json.dumps({"facts": facts, "text": {"Notes": "long text"}}),
                     f"https://nsearchives.nseindia.com/corporate/xbrl/ELGIEQUIP_{end:%Y%m%d}.xml"))
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        cur.executemany("""insert into finn.results (symbol, quarter_end, consolidated, template, period_start,
                             period_end, figures, xbrl_url, broadcast)
                           values (%s, %s, %s, %s, %s, %s, %s, %s, now())
                           on conflict (symbol, quarter_end, consolidated) do nothing""", rows)


def test_a_results_filing_shows_the_quarter_numbers_from_xbrl(stored):
    store_elgi_results(stored)
    out = digest.digest_payload(stored, DEMO, HOURS, now=NOW)
    elgi = {i["id"]: i for i in out["attention"]}["106849670"]
    r = elgi["results"]
    assert r is not None
    assert (r["quarter"], r["period_end"], r["basis"], r["template"], r["unit"]) == \
        ("Q2 FY27", "2026-09-30", "consolidated", "standard", "₹ crore")
    rows = {row["metric"]: row for row in r["rows"]}
    assert list(rows) == ["Revenue", "EBITDA", "PBT", "PAT"]
    assert rows["Revenue"]["value"] == 980.0 and rows["Revenue"]["margin"] is None
    assert rows["Revenue"]["qoq"] == {"pct": 8.9, "note": "", "margin_bps": None}
    assert rows["Revenue"]["yoy"] == {"pct": 11.4, "note": "", "margin_bps": None}
    # EBITDA = PBT before exceptional + finance costs + depreciation - other income = 140+4+18-12 = 150
    assert rows["EBITDA"]["value"] == 150.0 and rows["EBITDA"]["margin"] == 15.3
    assert rows["PAT"]["yoy"]["pct"] == 30.0
    assert r["source"].endswith("ELGIEQUIP_20260930.xml")
    assert elgi["headline"] == "Q2 FY27 results: revenue ₹980 cr, up 11.4% YoY; PAT ₹104 cr, up 30.0% YoY"
    # Exactly what `stored.card` computes from the same rows: one parser, two readers.
    from finn import stored as stored_cards
    card = stored_cards.card(stored, "ELGIEQUIP")
    assert card is not None and digest.results_json(card) == r
    # The investor presentation on the same card is not a results filing; other items carry no card.
    assert all(i["results"] is None for i in out["attention"] + out["worth"] if i["id"] != "106849670")


def test_no_numbers_are_guessed_when_the_quarter_is_not_stored(stored):
    # The filing reports the September quarter; only June and earlier stored: no card, NSE's words.
    assert digest.results_card("ELGIEQUIP", [], date(2026, 11, 6)) is None
    rows = [{"symbol": "ELGIEQUIP", "quarter_end": date(2026, 3, 31), "consolidated": True, "template": "general",
             "period_start": date(2026, 1, 1), "period_end": date(2026, 3, 31), "audited": "", "xbrl_url": "https://x",
             "figures": {"facts": {"RevenueFromOperations": 1.0}}}]
    assert digest.results_card("ELGIEQUIP", rows, date(2026, 11, 6)) is None  # 220 days before: not this filing's


def test_fiscal_quarters_and_headline_wording():
    assert digest.fiscal_quarter(date(2026, 9, 30)) == "Q2 FY27"
    assert digest.fiscal_quarter(date(2026, 12, 31)) == "Q3 FY27"
    assert digest.fiscal_quarter(date(2027, 3, 31)) == "Q4 FY27"
    assert digest.fiscal_quarter(date(2026, 6, 30)) == "Q1 FY27"
    change: digest.Change = {"pct": None, "note": "turned positive", "margin_bps": None}
    results: digest.Results = {
        "quarter": "Q2 FY27", "period_end": "2026-09-30", "basis": "standalone", "template": "bank", "unit": "₹ crore",
        "rows": [{"metric": "Net interest income", "value": 44464.0, "margin": None,
                  "qoq": change, "yoy": {"pct": 10.5, "note": "", "margin_bps": None}},
                 {"metric": "PAT", "value": -120.0, "margin": None, "qoq": change, "yoy": change}],
        "notes": [], "source": "https://x"}
    assert digest.results_headline_text(results) == \
        "Q2 FY27 results: net interest income ₹44,464 cr, up 10.5% YoY; a loss of ₹120 cr, turned positive YoY"
    fragment = "the financial results for the period ended September 30, 2026"
    assert digest.headline(fragment, "Outcome of Board Meeting") == \
        "Financial results for the period ended September 30, 2026"


def _bars_for(symbol: str, first: date, closes: list[float], volumes: list[float]) -> list[tuple]:
    rows, day = [], first
    for close, volume in zip(closes, volumes, strict=True):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        rows.append((symbol, day, close, volume))
        day += timedelta(days=1)
    return rows


def store_bars(conn: psycopg.Connection, rows: list[tuple], prev: dict[date, float] | None = None) -> None:
    with db.as_role(conn, "finn_ingest"), conn.cursor() as cur:
        cur.executemany("""insert into finn.prices_eod (symbol, day, close, prev_close, volume)
                           values (%s, %s, %s, %s, %s)
                           on conflict (symbol, day) do update set close = excluded.close,
                             prev_close = excluded.prev_close, volume = excluded.volume""",
                        [(s, d, c, (prev or {}).get(d), v) for s, d, c, v in rows])
        cur.executemany("insert into finn.trading_days (day, is_session) values (%s, true) on conflict do nothing",
                        [(d,) for _, d, _, _ in rows])


def store_moving_week(conn: psycopg.Connection) -> None:
    """70 quiet sessions for two holdings, then: Elgi jumps 9% on 6 Nov, the day of its results
    (filed 12:14, before the close); ABB falls 7% on 9 Nov with no filing that week."""
    first = date(2026, 7, 20)
    quiet = [100.0 + (i % 3) * 0.2 for i in range(70)]
    elgi = _bars_for("ELGIEQUIP", first, quiet, [1000.0] * 70)
    elgi += [("ELGIEQUIP", date(2026, 11, 6), 109.0, 5000.0)]
    power = _bars_for("ABB", first, quiet, [1000.0] * 70)
    power += [("ABB", date(2026, 11, 9), 93.0, 1200.0)]
    store_bars(conn, elgi + power)


def test_moves_attach_to_the_filing_that_explains_them_or_stand_alone(stored):
    store_moving_week(stored)
    out = digest.digest_payload(stored, DEMO, HOURS, now=NOW)

    elgi_item = {i["id"]: i for i in out["attention"]}["106849670"]
    kinds = {m["kind"]: m for m in elgi_item["moves"]}
    assert set(kinds) == {"move", "volume"}
    assert kinds["move"]["day"] == "2026-11-06" and kinds["move"]["value"] > 8.5
    assert kinds["move"]["detail"].startswith("Closed up") and kinds["move"]["fired_by"] in {"pct", "both"}
    assert kinds["volume"]["value"] == 5.0 and kinds["volume"]["company"] == "Elgi Equipments Limited"
    assert any(r.startswith("The stock moved after this filing") for r in elgi_item["reasons"])

    [power_move] = out["unexplained_moves"]
    assert (power_move["symbol"], power_move["day"], power_move["kind"]) == ("ABB", "2026-11-09", "move")
    assert power_move["value"] < -6.5 and power_move["detail"].startswith("Closed down")
    assert "1 unexplained price or volume move" in out["summary"]
    # Every item carries `moves`, empty when its company did not move.
    assert all(i["moves"] == [] for i in out["attention"] + out["worth"] if i["symbol"] != "ELGIEQUIP")


def test_a_corporate_action_day_is_not_a_move(stored):
    # A 1:2 split halves the close; NSE's previous close for that day is adjusted to match.
    first = date(2026, 7, 21)
    quiet = [200.0 + (i % 2) * 0.4 for i in range(70)]
    bars = _bars_for("NMDC", first, quiet, [1000.0] * 70) + [("NMDC", date(2026, 11, 6), 100.0, 1000.0)]
    store_bars(stored, bars, prev={date(2026, 11, 6): 100.2})
    out = digest.digest_payload(stored, DEMO, HOURS, now=NOW)
    assert not [m for m in out["unexplained_moves"] if m["symbol"] == "NMDC"]


def test_the_investors_thresholds_decide_what_is_a_move(stored):
    store_moving_week(stored)
    assert [m for m in digest.digest_payload(stored, DEMO, HOURS, now=NOW)["unexplained_moves"]
            if m["symbol"] == "ABB"]  # the default rule: 5% or 3 sigma
    with db.as_role(stored, "finn_api", DEMO):
        stored.execute("""insert into finn.prefs (investor_id, move_pct, move_rule) values (%s, 10, 'pct')
                          on conflict (investor_id) do update set move_pct = 10, move_rule = 'pct'""", [DEMO])
    try:
        out = digest.digest_payload(stored, DEMO, HOURS, now=NOW)
        assert not [m for m in out["unexplained_moves"] if m["symbol"] == "ABB"]  # a 7% fall is below 10%
    finally:
        with db.as_role(stored, "finn_api", DEMO):
            stored.execute("delete from finn.prefs where investor_id = %s", [DEMO])


def test_pledged_holdings_show_nse_figures_and_the_change(stored):
    ingest.ingest_equity_list(stored, _Equity())
    ingest.import_pledges(stored, FIX / "pledges.json")
    out = digest.digest_payload(stored, DEMO, HOURS, now=NOW)
    pledges = {p["symbol"]: p for p in out["portfolio"]["pledges"]}
    kalyan = pledges["KALYANKJIL"]
    assert (kalyan["pct_of_promoter"], kalyan["promoter_stake_pct"], kalyan["as_of"]) == (24.85, 62.85, "2026-09-30")
    assert kalyan["published"] == "2026-11-09T16:31:54+05:30" and kalyan["change_pct_points"] is None
    assert "TCS" not in pledges and "ABB" not in pledges  # nothing pledged: not listed

    # A later snapshot: Kalyan's promoters pledge more; the change is reported in percentage points.
    with db.as_role(stored, "finn_ingest"):
        stored.execute("""insert into finn.pledges (company_name, as_of, broadcast, symbol, promoter_holding_pct,
                            pledged_of_promoter_pct) values ('Kalyan Jewellers India Limited', '2026-09-30',
                            '2026-11-20 16:00+05:30', 'KALYANKJIL', 62.85, 26.10)""")
    later = {p["symbol"]: p for p in digest.digest_payload(stored, DEMO, HOURS, now=NOW)["portfolio"]["pledges"]}
    assert later["KALYANKJIL"]["pct_of_promoter"] == 26.1 and later["KALYANKJIL"]["change_pct_points"] == 1.25


class _Equity:
    """NSE's company list for the pledge names this test needs (pledges carry names, not symbols)."""

    def content(self, url: str) -> bytes:
        names = [("KALYANKJIL", "Kalyan Jewellers India Limited"), ("ASIANPAINT", "Asian Paints Limited"),
                 ("TCS", "Tata Consultancy Services Limited"), ("ABB", "ABB India Limited")]
        lines = ["SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE"]
        lines += [f"{s},{n},EQ,01-JAN-2010,1,1,INE000A0100{i},1" for i, (s, n) in enumerate(names)]
        return "\n".join(lines).encode()

    def api(self, path: str, **params: Any) -> Any:
        raise AssertionError("not used")
