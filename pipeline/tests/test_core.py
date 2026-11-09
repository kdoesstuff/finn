from datetime import date, datetime, timedelta

import pytest

from finn.alerts import Thresholds, signals_for
from finn.classify import classify
from finn.models import Announcement, Bar
from finn.rank import build_digest
from finn.results import Quarter, headline, pct_change

NSE_MEET = "Analysts/Institutional Investor Meet/Con. Call Updates"
NSE_KMP = "Change in Directors/ Key Managerial Personnel/ Auditor/ Compliance Officer/ Share Transfer Agent"


def ann(subject, label="", body="", symbol="ABC", source="NSE", ts=None, id_="1"):
    return Announcement(id=id_, symbol=symbol, company=symbol, ts=ts or datetime(2026, 11, 9, 18, 0),
                        source=source, label=label, subject=subject, body=body)


@pytest.mark.parametrize("subject,label,category,subtype", [
    ("Unaudited Financial Results for the quarter ended September 30, 2026", "Outcome of Board Meeting",
     "results", "filing"),
    ("Board Meeting Intimation for considering financial results", "Board Meeting Intimation",
     "results", "board_meeting_notice"),
    ("Copy of newspaper publication of financial results", "Copy of Newspaper Publication",
     "results", "results_ad"),
    ("Transcript of the earnings call held on November 5, 2026", NSE_MEET, "earnings_call", ""),
    ("Schedule of analyst / institutional investor meetings", NSE_MEET, "investor_meetings", ""),
    ("Closure of Trading Window", "Trading Window", "unclassified", "trading_window"),
    ("Allotment of equity shares under ESOP Scheme 2021", "Allotment of ESOP / ESPS", "unclassified", "esop"),
    ("Credit rating reaffirmed by CRISIL", "Credit Rating", "credit_rating", ""),
    ("Acquisition of 51% stake in XYZ Pvt Ltd", "Acquisition", "M&A", ""),
    ("Disclosure under Regulation 31(1) of SEBI SAST - creation of pledge", "", "pledging", ""),
    ("Resignation of Statutory Auditor", NSE_KMP, "management_change", "auditor_exit"),
    ("Appointment of M/s ABC & Co. as Secretarial Auditor", NSE_KMP, "unclassified", "auditor_appointment"),
    ("Order received from GST department imposing penalty", "Updates", "litigation", ""),
    ("Company bags order worth Rs 1,200 crore from NHAI", "Press Release", "press_release", ""),
    ("Commencement of commercial production at the new plant in Dahej", "Updates", "capex", ""),
])
def test_classifier(subject, label, category, subtype):
    c = classify(ann(subject, label))
    assert c.category == category
    assert c.subtype == subtype


def test_management_role_and_action():
    c = classify(ann("Resignation of Mr. Rajesh Kumar, Chief Financial Officer", NSE_KMP))
    assert (c.category, c.role, c.action) == ("management_change", "cfo", "resignation")


def test_label_only_match_is_less_confident():
    c = classify(ann("Updates", label="Credit Rating"))
    assert c.category == "credit_rating" and c.confidence < 0.9


def test_unknown_goes_to_model():
    assert classify(ann("Intimation under Regulation 30")).needs_model


def bars(closes, volumes=None, start=date(2026, 6, 1)):
    volumes = volumes or [1_000_000] * len(closes)
    return [Bar(start + timedelta(days=i), c, v) for i, (c, v) in enumerate(zip(closes, volumes))]


def test_volume_spike_needs_history():
    short = bars([100] * 5, [1e6] * 4 + [5e6])
    assert signals_for("ABC", short) == []
    long = bars([100] * 25, [1e6] * 24 + [3e6])
    sig = signals_for("ABC", long)
    assert sig[0].kind == "volume" and sig[0].value == pytest.approx(3.0)


def test_sigma_move_catches_a_quiet_stock():
    closes = [100 * (1.001 if i % 2 else 0.999) ** 1 for i in range(70)]  # ~0.1% daily noise
    closes.append(closes[-1] * 1.02)  # a 2% day: under a 5% rule, far out in sigma
    sig = signals_for("ABC", bars(closes), Thresholds(move_rule="either"))
    move = [s for s in sig if s.kind == "move"][0]
    assert abs(move.value) < 5 and move.sigma > 3
    assert signals_for("ABC", bars(closes), Thresholds(move_rule="pct")) == []


def test_digest_orders_management_first_and_collapses_routine():
    anns = [
        ann("Closure of Trading Window", "Trading Window", id_="1", symbol="A"),
        ann("Resignation of Chief Executive Officer", NSE_KMP, id_="2", symbol="B"),
        ann("Unaudited Financial Results for the quarter ended Sep 30, 2026", "Outcome of Board Meeting",
            id_="3", symbol="C"),
        ann("Dividend record date", "Record Date", id_="4", symbol="D"),
    ]
    d = build_digest(anns, [])
    assert [i.announcement.symbol for i in d["attention"]] == ["B", "C"]
    assert d["routine_counts"] == {"trading_window": 1, "dividend": 1}
    assert "2 items need your attention" in d["summary"]


def test_nse_and_bse_copies_are_deduplicated():
    a = ann("Unaudited Financial Results", "Outcome of Board Meeting", source="NSE", id_="n")
    b = ann("Unaudited Financial Results", "Result", source="BSE", id_="b")
    d = build_digest([a, b], [])
    assert len(d["attention"]) == 1 and d["attention"][0].announcement.source == "NSE"


def test_quiet_day_says_so():
    d = build_digest([ann("Closure of Trading Window", "Trading Window")], [])
    assert d["summary"].startswith("Nothing material")


def test_results_headline():
    qs = [
        Quarter(date(2025, 9, 30), revenue=1000, other_income=20, finance_costs=30, depreciation=50, pbt=200, pat=150),
        Quarter(date(2026, 6, 30), revenue=1100, other_income=25, finance_costs=30, depreciation=55, pbt=210, pat=160),
        Quarter(date(2026, 9, 30), revenue=1200, other_income=20, finance_costs=35, depreciation=60, pbt=240,
                pat=180, exceptional=-10),
    ]
    h = headline(qs)
    rows = {r["metric"]: r for r in h["rows"]}
    assert rows["Revenue"]["yoy"]["pct"] == 20.0
    # EBITDA = (240 + 10) + 35 + 60 - 20 = 325
    assert rows["EBITDA"]["value"] == 325
    assert rows["PAT"]["qoq"]["pct"] == pytest.approx(12.5)
    assert any("Exceptional" in n for n in h["notes"])


def test_pct_change_never_misleads_on_sign_flips():
    assert pct_change(50, -20)["note"] == "turned positive"
    assert pct_change(-30, -50)["note"] == "loss narrowed"
