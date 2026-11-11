"""Fetchers: the client's retry behaviour against a scripted session, and every parser against
real NSE responses recorded from GitHub's runners (tests/fixtures)."""

import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest
import requests

from finn.sources.client import BASE, NSEClient, SourceError
from finn.sources.nse import (
    bhavcopy,
    latest_per_quarter,
    parse_announcement,
    parse_annual_reports,
    parse_bhavcopy,
    parse_board_meetings,
    parse_corporate_actions,
    parse_integrated,
    parse_legacy,
    unzip_single,
)

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# A scripted stand-in for requests.Session ----------------------------------------------------------

class FakeResponse:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code, self._data, self.content, self.text = status, data, content, str(data)

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class Script:
    """Answers API calls in order; counts home-page warm-ups separately."""

    def __init__(self, *answers):
        self.answers, self.warmups, self.calls = list(answers), 0, []

    def session(self):
        script = self

        class Session:
            headers: dict = {}

            def get(self, url, params=None, timeout=None):
                if url == BASE:
                    script.warmups += 1
                    return FakeResponse(200)
                script.calls.append((url, params))
                answer = script.answers.pop(0)
                if isinstance(answer, Exception):
                    raise answer
                return answer

        return Session()


def client(script, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    clock = iter(range(0, 10_000, 10))  # each reading 10 s later: pacing never needs to wait
    return NSEClient(session_factory=script.session, sleep=sleeps.append, clock=lambda: next(clock))


def test_warms_once_then_reuses_the_session():
    s = Script(FakeResponse(200, [1]), FakeResponse(200, [2]))
    c = client(s)
    assert c.api("a") == [1] and c.api("b") == [2]
    assert s.warmups == 1 and c.requests_made == 2


def test_refused_session_is_rewarmed_and_retried():
    s = Script(FakeResponse(401), FakeResponse(200, {"data": []}))
    assert client(s).api("corporate-announcements") == {"data": []}
    assert s.warmups == 2


def test_rate_limit_backs_off_with_jitter_then_succeeds():
    sleeps: list[float] = []
    s = Script(FakeResponse(429), FakeResponse(503), FakeResponse(200, [1]))
    assert client(s, sleeps).api("x") == [1]
    backoffs = [x for x in sleeps if x >= 1.0]
    assert len(backoffs) == 2 and 1.0 <= backoffs[0] <= 1.5 and 2.0 <= backoffs[1] <= 3.0


def test_gives_up_after_the_last_attempt_and_says_why():
    s = Script(*[requests.Timeout()] * 4)
    with pytest.raises(SourceError, match="gave up after 4 attempts"):
        client(s).api("x")


def test_missing_document_is_none_but_a_missing_api_is_an_error():
    assert client(Script(FakeResponse(404))).content("https://nsearchives.nseindia.com/x.zip") is None
    with pytest.raises(SourceError, match="not found"):
        client(Script(FakeResponse(404))).api("x")


def test_a_bad_request_is_not_retried():
    s = Script(FakeResponse(400), FakeResponse(200, [1]))
    with pytest.raises(SourceError, match="HTTP 400"):
        client(s).api("x")
    assert len(s.calls) == 1


def test_html_instead_of_json_is_an_error():
    with pytest.raises(SourceError, match="not JSON"):
        client(Script(FakeResponse(200, None))).api("x")


def test_pacing_waits_between_requests():
    sleeps: list[float] = []
    ticks = iter([0.0, 0.0, 0.1, 0.1, 0.2, 0.2, 0.3, 0.3])
    c = NSEClient(session_factory=Script(FakeResponse(200, [1]), FakeResponse(200, [2])).session,
                  sleep=sleeps.append, clock=lambda: next(ticks), pace=0.7)
    c.api("a")
    c.api("b")
    assert sleeps and all(0 < x <= 0.7 for x in sleeps)


# Parsers on recorded responses ---------------------------------------------------------------------

def test_announcement_row():
    row = next(r for r in load("nse_announcements.json")["rows"] if r["seq_id"] == "106851770")
    a = parse_announcement(row)
    assert (a.id, a.symbol, a.label) == ("106851770", "ASIANPAINT", "Appointment")
    assert a.ts == datetime(2026, 11, 6, 22, 6, 58)
    assert a.url.endswith(".pdf") and a.file_size == "229.88 KB" and "Leo Puri" in a.subject


def test_every_recorded_announcement_parses():
    rows = load("nse_announcements.json")["rows"]
    assert len([parse_announcement(r) for r in rows]) == 4795


def test_latest_revision_wins_per_quarter_and_basis():
    # Asian Paints revised its Mar 2026 standalone results twice and consolidated once. NSE leaves
    # broadcast_Date empty on revision rows: an earlier reading of this index skipped every revision.
    filings = latest_per_quarter(parse_integrated(load("integrated_ASIANPAINT.json")))
    by = {(f.quarter_end, f.consolidated): f for f in filings}
    assert len(filings) == 14  # Mar 2025 to Sep 2026, standalone and consolidated
    assert by[(date(2026, 3, 31), False)].xbrl_url.endswith("93685_15072026082130_WEB.xml")
    assert by[(date(2026, 3, 31), True)].xbrl_url.endswith("93690_15072026083521_WEB.xml")
    assert by[(date(2026, 3, 31), True)].revision


def test_governance_filings_are_not_results():
    rows = load("integrated_TCS.json")
    assert len(parse_integrated(rows)) == 14 and len(rows) == 22


def test_legacy_index_quarters():
    filings = latest_per_quarter(parse_legacy(load("results_TCS.json")))
    latest = filings[0]
    assert latest.quarter_end == date(2024, 12, 31) and latest.source == "legacy"
    assert all(f.quarter_end <= date(2024, 12, 31) for f in filings)


def zipped(raw: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BhavCopy_NSE_CM_0_0_0_20261106_F_0000.csv", raw)
    return buf.getvalue()


def test_bhavcopy_equities_only():
    rows = parse_bhavcopy(unzip_single(zipped((FIX / "bhavcopy.csv").read_bytes())))
    tcs = next(r for r in rows if r.symbol == "TCS")
    assert tcs.day == date(2026, 11, 6) and tcs.series == "EQ" and tcs.close > 0 and tcs.volume > 0
    assert not any(r.symbol.startswith("SGB") for r in rows)  # gold bonds are not equities
    assert len({r.symbol for r in rows}) > 2000


def test_no_bhavcopy_means_no_session():
    assert bhavcopy(client(Script(FakeResponse(404))), date(2026, 11, 10)) is None  # Diwali Balipratipada


def test_a_non_zip_bhavcopy_is_refused():
    with pytest.raises(SourceError):
        unzip_single(b"<html>blocked</html>")


def test_board_meetings():
    meetings = parse_board_meetings(load("board_meetings.json"))
    assert any(m.symbol == "KALYANKJIL" and m.day == date(2026, 11, 10) for m in meetings)
    assert len(meetings) == 3414


def test_annual_reports_newest_first():
    reports = parse_annual_reports(load("annual_reports_TCS.json")["data"])
    assert reports[0].to_year == 2026 and reports[0].url.startswith("https://")


def test_corporate_actions():
    actions = parse_corporate_actions(load("corp_actions_TCS.json"))
    assert any(a.ex_date == date(2026, 10, 14) and "Dividend" in a.subject for a in actions)
