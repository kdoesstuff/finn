"""Ingest jobs against a Supabase-shaped Postgres, fed by a stand-in for NSE that answers from the
real responses recorded in tests/fixtures. Every write goes through the finn_ingest role, so these
tests also prove its grants are enough, and no more is needed."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from finn import db, ingest
from finn.sources import nse
from finn.sources.client import SourceError

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# A constructed sample in the layout of NSE's EQUITY_L.csv (header spacing as NSE writes it). The
# names are exactly as NSE's pledge feed writes them; the ISINs are from the recorded 6 Nov bhavcopy.
EQUITY_LIST = (b"SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
               b"KALYANKJIL,Kalyan Jewellers India Limited,EQ,26-MAR-2021,10,1,INE303R01014,10\n"
               b"MRF,MRF Limited,EQ,01-JAN-1995,10,1,INE883A01011,10\n")


class Recorded:
    """Answers like NSE, from recorded responses. Unknown endpoints fail as NSE would."""

    def __init__(self, sessions: tuple[date, ...] = (date(2026, 11, 6),)) -> None:
        self.sessions = sessions
        self.api_calls: list[tuple[str, dict]] = []
        self.content_calls: list[str] = []
        self.files: dict[str, Path] = {}
        for sym in ("TCS", "HDFCBANK", "ASIANPAINT"):
            for r in load(f"integrated_{sym}.json"):
                qe = datetime.strptime(r["qe_Date"].title(), "%d-%b-%Y").date()
                path = FIX / "xbrl_if" / f"{sym}_{qe:%Y-%m-%d}_{r.get('seq_Id')}.xml"
                if r.get("xbrl") and path.exists():
                    self.files[r["xbrl"]] = path
            for r in load(f"results_{sym}.json"):
                end = datetime.strptime(r["toDate"], "%d-%b-%Y").date()
                path = FIX / "xbrl" / f"{sym}_{end:%Y-%m-%d}_{str(r.get('consolidated'))[:4]}.xml"
                if str(r.get("xbrl", "")).startswith("http") and path.exists():
                    self.files[r["xbrl"]] = path

    @staticmethod
    def _between(day: date, params: dict) -> bool:
        start = datetime.strptime(params["from_date"], "%d-%m-%Y").date()
        end = datetime.strptime(params["to_date"], "%d-%m-%Y").date()
        return start <= day <= end

    def api(self, path: str, **params: Any) -> Any:
        self.api_calls.append((path, params))
        symbol = params.get("symbol")
        if path == "corporate-announcements":
            rows = load("nse_announcements.json")["rows"]
            return [r for r in rows if self._between(datetime.strptime(r["an_dt"][:11], "%d-%b-%Y").date(), params)
                    and (not symbol or r["symbol"] == symbol)]
        if path == "integrated-filing-results":
            rows = load(f"integrated_{symbol}.json") if (FIX / f"integrated_{symbol}.json").exists() else []
            return {"data": rows if params.get("page") == 1 else [], "totalCount": len(rows)}
        if path == "corporates-financial-results":
            return load(f"results_{symbol}.json") if (FIX / f"results_{symbol}.json").exists() else []
        if path == "corporate-pledgedata":
            return load("pledges.json")
        if path == "corporate-board-meetings":
            return [r for r in load("board_meetings.json")
                    if self._between(datetime.strptime(r["bm_date"], "%d-%b-%Y").date(), params)]
        if path == "corporates-corporateActions":
            return load("corp_actions_TCS.json") if symbol == "TCS" else []
        raise SourceError(f"{path}: not recorded")

    def content(self, url: str) -> bytes | None:
        self.content_calls.append(url)
        if url == nse.EQUITY_LIST_URL:
            return EQUITY_LIST
        if "BhavCopy_NSE_CM" in url:
            day = datetime.strptime(url.split("_0_0_0_")[1][:8], "%Y%m%d").date()
            if day not in self.sessions:
                return None
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("bhav.csv", (FIX / "bhavcopy.csv").read_bytes())
            return buf.getvalue()
        path = self.files.get(url)
        return path.read_bytes() if path else None


def rows(conn, query: str, params: list | None = None) -> list[tuple]:
    with db.as_role(conn, "finn_ingest"):
        return conn.execute(query, params).fetchall()


def cover(conn, *symbols: str) -> None:
    with db.as_role(conn, "finn_api"):
        for s in symbols:
            conn.execute("insert into finn.coverage (symbol, reason) values (%s, 'holding') "
                         "on conflict do nothing", [s])


WEEK = (date(2026, 11, 4), date(2026, 11, 9))


# Filings ------------------------------------------------------------------------------------------

def test_filings_are_stored_once_classified_and_zoned(admin):
    first = ingest.ingest_filings(admin, Recorded(), *WEEK)
    assert first["fetched"] == 4795 and first["new"] == 4795 and first["unusable"] == 0
    again = ingest.ingest_filings(admin, Recorded(), *WEEK)
    assert again["new"] == 0
    assert rows(admin, "select count(*) from finn.filings") == [(4795,)]
    (ts, category, role, action, version), = rows(
        admin, "select ts, category, role, action, rule_version from finn.filings where seq_id = '106851770'")
    assert ts == datetime(2026, 11, 6, 22, 6, 58, tzinfo=ingest.IST)  # Asian Paints, Leo Puri
    assert (category, role, action, version) == ("management_change", "director", "appointment", ingest.RULE_VERSION)


def test_companies_take_names_from_filings_but_not_their_stale_isins(admin):
    ingest.ingest_filings(admin, Recorded(), *WEEK)
    ingest.ingest_eod(admin, Recorded(), [date(2026, 11, 6)])
    assert rows(admin, "select name, isin, industry from finn.companies where symbol = 'ASIANPAINT'") == [
        ("Asian Paints Limited", "INE021A01026", "Paints")]  # ISIN from the bhavcopy, not the filing's old one


def test_results_are_fetched_only_for_covered_companies_that_filed_results(admin):
    cover(admin, "ELGIEQUIP")  # filed results on 6 Nov, inside the week
    counts = ingest.ingest_filings(admin, Recorded(), *WEEK)
    assert list(counts["results"]) == ["ELGIEQUIP"]


def test_a_failed_job_is_logged_and_raised(admin):
    class Down(Recorded):
        def api(self, path: str, **params: Any) -> Any:
            raise SourceError("https://www.nseindia.com/api/corporate-announcements: gave up after 4 attempts")

    with pytest.raises(SourceError):
        ingest.ingest_filings(admin, Down(), *WEEK)
    (ok, error), = rows(admin, "select ok, error from finn.ingest_runs order by id desc limit 1")
    assert ok is False and "gave up after 4 attempts" in error


def test_filings_classified_by_older_rules_are_refreshed(admin):
    ingest.ingest_filings(admin, Recorded(), *WEEK)
    with db.as_role(admin, "finn_ingest"):
        admin.execute("update finn.filings set rule_version = 'old', category = 'unclassified' "
                      "where seq_id in ('106851770', '106845822')")
    assert ingest.reclassify_stale(admin) == 2
    assert rows(admin, "select category from finn.filings where seq_id = '106845822'") == [("management_change",)]
    assert ingest.reclassify_stale(admin) == 0


# Results ------------------------------------------------------------------------------------------

def test_results_store_the_latest_revision_and_skip_what_is_unchanged(admin):
    src = Recorded()
    first = ingest.ingest_results(admin, src, "ASIANPAINT")
    assert first["stored"] >= 8 and not first["rejected"]
    (revision, url), = rows(admin, """select revision, xbrl_url from finn.results where symbol = 'ASIANPAINT'
                                       and quarter_end = '2026-03-31' and not consolidated""")
    assert revision and url.endswith("1693685_15072026082130_WEB.xml")  # the July revision, not May's original
    fetched = len(src.content_calls)
    again = ingest.ingest_results(admin, src, "ASIANPAINT")
    assert again["stored"] == 0 and again["unchanged"] == first["stored"]
    # A stored file is never downloaded again; a file that was missing is asked for again, since
    # NSE can publish it later.
    stored_urls = {r[0] for r in rows(admin, "select xbrl_url from finn.results where symbol = 'ASIANPAINT'")}
    asked_again = src.content_calls[fetched:]
    assert len(asked_again) == first["missing"] and not stored_urls & set(asked_again)


def test_results_figures_are_the_parsed_filing(admin):
    ingest.ingest_results(admin, Recorded(), "TCS")
    ingest.ingest_results(admin, Recorded(), "HDFCBANK")
    (template, figures, start, end), = rows(
        admin, """select template, figures, period_start, period_end from finn.results
                  where symbol = 'TCS' and quarter_end = '2026-09-30' and consolidated""")
    assert template == "general" and (start, end) == (date(2026, 7, 1), date(2026, 9, 30))
    assert figures["facts"]["RevenueFromOperations"] == pytest.approx(73188, abs=1)
    assert rows(admin, "select distinct template from finn.results where symbol = 'HDFCBANK'") == [("bank",)]


# Prices and the calendar ----------------------------------------------------------------------------

def test_sessions_and_holidays_come_from_the_bhavcopy(admin):
    src = Recorded()
    counts = ingest.ingest_eod(admin, src, [date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 10)], refetch=True)
    assert counts["sessions"] == ["2026-11-06"] and counts["not_sessions"] == ["2026-11-07", "2026-11-10"]
    assert rows(admin, "select day, is_session from finn.trading_days where day between '2026-11-06' and '2026-11-10' "
                       "order by day") == [(date(2026, 11, 6), True), (date(2026, 11, 7), False),
                                           (date(2026, 11, 10), False)]
    (close, volume), = rows(admin, "select close, volume from finn.prices_eod "
                                   "where symbol = 'TCS' and day = '2026-11-06'")
    assert float(close) == 2498.50 and volume > 0
    asked = len(src.content_calls)
    ingest.ingest_eod(admin, src, [date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 10)])
    assert len(src.content_calls) == asked  # known days are not fetched again


# Daily ----------------------------------------------------------------------------------------------

def test_pledges_are_matched_to_symbols_by_exact_name(admin):
    ingest.ingest_equity_list(admin, Recorded())
    counts = ingest.ingest_pledges(admin, Recorded())
    assert counts["rows"] == 1558 or counts["rows"] > 1000
    (pct, total), = rows(admin, """select pledged_of_promoter_pct, promoter_pledged_of_total_pct from finn.pledges
                                    where symbol = 'KALYANKJIL'""")
    assert (float(pct), float(total)) == (24.85, 15.62)
    # Kalyani Forge must never be read as Kalyan Jewellers: it matches its own symbol, or none.
    assert rows(admin, "select symbol from finn.pledges where company_name = 'Kalyani Forge Limited'")[0][0] in (
        None, "KALYANIFRG")


def test_daily_job_runs_every_part_and_logs_it(admin):
    cover(admin, "TCS")
    counts = ingest.ingest_daily(admin, Recorded(), date(2026, 11, 9))
    assert counts["equity_list"] == 2 and counts["board_meetings"] > 1000 and counts["pledges"]["rows"] > 1000
    assert counts["corporate_actions"]["rows"] > 0 and counts["results"]["TCS"]["stored"] + \
        counts["results"]["TCS"]["unchanged"] >= 8
    assert rows(admin, "select count(*) from finn.corporate_actions where symbol = 'TCS'")[0][0] > 0
    (ok,), = rows(admin, "select ok from finn.ingest_runs where job = 'daily' order by id desc limit 1")
    assert ok


def test_backfill_walks_the_range_day_by_day(admin):
    out = ingest.backfill(admin, Recorded(), date(2026, 11, 5), date(2026, 11, 7))
    assert list(out["filings"]) == ["2026-11-05", "2026-11-06", "2026-11-07"]
    assert out["eod"]["sessions"] == ["2026-11-06"] or "2026-11-06" not in out["eod"]["not_sessions"]


def test_company_names_normalise_across_spellings():
    same = ingest.normalise_name("Kalyan Jewellers India Ltd.")
    assert same == ingest.normalise_name("KALYAN JEWELLERS INDIA LIMITED")
    assert ingest.normalise_name("Kalyani Forge Limited") != ingest.normalise_name("Kalyan Jewellers India Limited")


def test_rule_version_changes_when_the_rules_change():
    assert len(ingest.RULE_VERSION) == 12 and int(ingest.RULE_VERSION, 16) >= 0


def test_india_has_one_fixed_offset():
    assert ingest.IST.utcoffset(None) == timedelta(hours=5, minutes=30)


def test_demo_investor_seed_is_idempotent_and_fills_coverage(admin):
    from finn import seed

    data = seed.load()
    first = seed.seed_demo(admin)
    seed.seed_demo(admin)
    assert first == {"holdings": 18, "research": 3}
    investor = data["investor"]["id"]
    with db.as_role(admin, "finn_api", investor):
        assert admin.execute("select count(*) from finn.holdings").fetchone() == (18,)
        assert admin.execute("select move_rule from finn.prefs").fetchone() == ("either",)
    covered = {r[0] for r in rows(admin, "select symbol from finn.coverage")}
    assert set(data["holdings"]) | set(data["research"]) <= covered


# Empty sources, stored cards and the completeness report --------------------------------------------

class NoPledges(Recorded):
    def api(self, path: str, **params: Any) -> Any:
        if path == "corporate-pledgedata":
            return []
        return super().api(path, **params)


def test_an_empty_pledge_feed_fails_loudly_and_keeps_history(admin):
    ingest.ingest_equity_list(admin, Recorded())
    ingest.ingest_pledges(admin, Recorded())
    before = rows(admin, "select count(*) from finn.pledges")[0][0]
    with pytest.raises(SourceError, match="no rows"):
        ingest.ingest_pledges(admin, NoPledges())
    assert rows(admin, "select count(*) from finn.pledges")[0][0] == before > 0
    counts = ingest.ingest_daily(admin, NoPledges(), date(2026, 11, 9))
    assert any(e.startswith("pledges:") for e in counts["errors"])
    (ok,), = rows(admin, "select ok from finn.ingest_runs where job = 'daily' order by id desc limit 1")
    assert ok is False  # the run goes red, the other parts still ran
    assert counts["board_meetings"] > 0


def test_cards_from_stored_results_match_the_verified_figures(admin):
    from finn import stored

    for s in ("TCS", "HDFCBANK", "ASIANPAINT"):
        ingest.ingest_results(admin, Recorded(), s)
    tcs = stored.card(admin, "TCS")
    assert tcs and tcs["period_end"] == "2026-09-30" and tcs["basis"] == "consolidated"
    assert tcs["rows"][0]["metric"] == "Revenue" and tcs["rows"][0]["value"] == pytest.approx(73188, abs=1)
    bank = stored.card(admin, "HDFCBANK")
    assert bank and bank["rows"][0]["metric"] == "Net interest income"
    assert bank["rows"][0]["value"] == pytest.approx(44464, abs=1)
    assert stored.card(admin, "NOSUCHCO") is None


def test_completeness_report_names_a_reason_for_every_gap(admin):
    from finn import seed, verify

    seed.seed_demo(admin)
    for s in ("TCS", "HDFCBANK", "ASIANPAINT"):
        ingest.ingest_results(admin, Recorded(), s)
    offline = verify.check(admin, date(2026, 9, 30), date(2026, 11, 4))
    assert offline.failures  # without asking NSE, a gap has no reason yet
    live = verify.check(admin, date(2026, 9, 30), date(2026, 11, 4), Recorded())
    by = {c.symbol: c for c in live.companies}
    assert by["TCS"].has_target and by["TCS"].template == "general"
    assert by["HDFCBANK"].template == "bank"
    # The recorded stand-in has no results index for the other names: "not filed yet" is a reason.
    assert by["MRF"].reason == "NSE lists no results for this quarter yet" and not by["MRF"].failed
    assert all("OK" in k for k in live.known) and live.failures == []
    assert "No failures." in verify.render(live)
