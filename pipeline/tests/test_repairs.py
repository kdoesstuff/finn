"""Regression tests for the defects found by re-verification on 11 Nov 2026.

Each case is a real NSE filing from the fixture week (4-9 Nov 2026), named by NSE's own `seq_id`,
so the test fails on the code that misread it and passes on the repair.
"""

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pytest

from finn.alerts import Thresholds, signals_for
from finn.classify import classify
from finn.models import Announcement, Bar, Signal
from finn.pledges import parse as parse_pledge
from finn.rank import ATTENTION, _file_key, build_digest, group_events, reaction_window, score_item
from finn.sources.nse import parse_announcement
from finn.text import amount_crore, own_words

FIX = Path(__file__).parent / "fixtures"


@lru_cache(maxsize=1)
def week() -> dict[str, Announcement]:
    rows = json.loads((FIX / "nse_announcements.json").read_text(encoding="utf-8"))["rows"]
    return {r["seq_id"]: parse_announcement(r) for r in rows}


def filings(*ids: str) -> list[Announcement]:
    return [week()[i] for i in ids]


def only_event(*ids: str):
    events = group_events(filings(*ids))
    assert len(events) == 1, [[a.id for a, _ in e.filings] for e in events]
    return events[0]


# 1. Identity: nothing distinct is dropped -------------------------------------------------------

def test_no_distinct_filing_is_dropped_across_the_real_week():
    anns = list(week().values())
    kept = {a.id for e in group_events(anns) for a, _ in e.filings}
    dropped = [a for a in anns if a.id not in kept]
    # The only filings not listed are exact re-uploads: same company, label, summary, file name and
    # size as a listed filing, uploaded within the hour. The old de-duplication dropped 264 distinct
    # filings, 54 of them attention-level.
    kept_at: dict[tuple[str, ...], list[datetime]] = {}
    for i in kept:
        kept_at.setdefault(_file_key(week()[i]), []).append(week()[i].ts)
    for a in dropped:
        assert any(timedelta(0) <= a.ts - t <= timedelta(minutes=60) for t in kept_at[_file_key(a)]), a.id
    assert len(dropped) == 30


def test_one_pdf_carrying_several_announcements_stays_several():
    # Motherson attached one PDF (same name, same size) to separate investor-meeting announcements.
    events = group_events(filings("106852300", "106852301", "106852287"))
    assert sum(len(e.filings) for e in events) == 3


def test_refiled_press_releases_with_different_documents_are_all_kept():
    events = group_events(filings("106844095", "106844125", "106845866"))  # Alembic Pharma, 4 Nov
    assert sum(len(e.filings) for e in events) == 3


# 2. One event, one card --------------------------------------------------------------------------

def test_asian_paints_appointment_is_one_card_led_by_the_filing_that_names_the_person():
    d = build_digest(filings("106851762", "106851770"), [])
    items = d["attention"] + d["worth"]
    assert len(items) == 1
    item = items[0]
    assert item.announcement.id == "106851770"  # "Appointment of Mr Leo Puri as Independent Director"
    assert [r.id for r in item.related] == ["106851762"]  # "Change in Director(s) of the company"
    assert item.score == 55


def test_sadbhav_auditor_exit_filed_three_times_is_one_card():
    d = build_digest(filings("106845761", "106845822", "106845824", "106845757", "106845768"), [])
    exits = [i for i in d["attention"] if i.classification.subtype == "auditor_exit"]
    results = [i for i in d["attention"] if i.classification.category == "results"]
    assert len(exits) == 1 and len(exits[0].related) == 2 and exits[0].score == 100
    assert len(results) == 1 and len(results[0].related) == 1


def test_manappuram_cto_exit_is_one_card_below_the_top_team():
    e = only_event("106852000", "106852003")
    d = build_digest([a for a, _ in e.filings], [])
    item = (d["attention"] + d["worth"])[0]
    assert item.announcement.id == "106852003"
    assert (item.classification.role, item.classification.action) == ("senior", "resignation")
    assert item.score == 70


# 3. Roles from the company's own words -----------------------------------------------------------

@pytest.mark.parametrize("seq_id,role,action", [
    ("106844110", "chair", "resignation"),     # "Chairman and Non-Executive Director" was read as MD
    ("106844922", "chair", "resignation"),     # "(Non Executive Non Independent Director) as Chairman"
    ("106844581", "director", "appointment"),  # "Non- Executive Director": not an MD
    ("106852199", "chair", "retirement"),      # Vice Chairman retiring, "Non-Executive, Non-Independent"
    ("106848393", "md", "reappointment"),      # reappointment of an MD
])
def test_roles_come_from_the_filing_text(seq_id, role, action):
    c = classify(week()[seq_id])
    assert (c.role, c.action) == (role, action)


@pytest.mark.parametrize("seq_id,role", [
    ("106851464", "senior"),              # Wipro: CEO "for Americas 2 Strategic Market Unit"
    ("106849859", "senior"),              # Arvind: "Appointment of CFO in Subsidiary Company"
    ("106845094", "senior"),              # BSE: Executive Director, Business (Vertical 3)
    ("106844831", "ceo"),                 # Dabur: Global CEO and Whole-time Director
    ("106844523", "executive_director"),  # C & C Constructions: Executive Director resigns
])
def test_top_titles_for_part_of_the_group_are_senior_management(seq_id, role):
    assert classify(week()[seq_id]).role == role


def test_executive_director_exit_ranks_below_an_md_exit():
    ed = week()["106844523"]
    assert score_item(ed, classify(ed))[1] == 80
    md = Announcement("x", "ABC", "ABC", datetime(2026, 11, 9), "NSE", label="Resignation",
                      subject="Resignation of Mr A as Managing Director of the company")
    assert score_item(md, classify(md))[1] == 95


@pytest.mark.parametrize("seq_id,subtype", [
    ("106850672", "regulator"),  # Dabur: administrative warning letter received from SEBI
    ("106846918", "legal"),      # Kansai Nerolac: only cites SEBI's listing regulations
    ("106844303", "legal"),      # Tenneco: only cites SEBI's listing regulations
])
def test_citing_sebi_regulations_is_not_a_regulator_acting(seq_id, subtype):
    assert classify(week()[seq_id]).subtype == subtype


def test_a_label_alone_names_no_role():
    c = classify(week()["106852000"])  # "has informed the Exchange about Resignation of Director/KMP/SMP"
    assert c.role == "" and c.detail_in_document


def test_reappointment_at_the_top_is_continuity_not_news():
    a = week()["106848393"]
    _, score, reasons = score_item(a, classify(a))
    assert score < ATTENTION and "continuity" in reasons[0]


def test_md_abbreviation_is_case_sensitive():
    c = classify(Announcement("x", "ABC", "ABC", datetime(2026, 11, 9), "NSE", label="Appointment",
                              subject="Appointment of Mr. Md. Rafiq Khan as Director"))
    assert c.role == "director"


# 4. Which auditor ---------------------------------------------------------------------------------

@pytest.mark.parametrize("seq_id,subtype", [
    ("106845822", "auditor_exit"),             # Sadbhav: statutory auditor
    ("106844841", "auditor_exit_subsidiary"),  # Popular Vehicles: statutory auditor of a subsidiary
    ("106847698", "auditor_exit_subsidiary"),  # Enviro Infra: auditor of a material subsidiary
    ("106845647", "auditor_exit_other"),       # Vineet Laboratories: cost auditor
    ("106845640", "auditor_exit_other"),       # Vineet Laboratories: internal auditor
    ("106844963", "auditor_exit_other"),       # TECIL: secretarial auditors
])
def test_auditor_kind(seq_id, subtype):
    assert classify(week()[seq_id]).subtype == subtype


def test_only_statutory_auditor_exits_score_as_red_flags_across_the_week():
    flagged = [a for a in week().values()
               if classify(a).subtype == "auditor_exit" and score_item(a, classify(a))[1] >= 100]
    symbols = {a.symbol for a in flagged}
    # Varvee Global and Sadbhav name the company's own statutory auditor. Enviro Infra and Popular
    # Vehicles also filed under NSE's "Resignation of Statutory Auditor" label with no words of their
    # own; their worded filings say it was a subsidiary's auditor, and group_events scores the event
    # from those words (test_label_only_filing_takes_its_meaning_from_the_worded_one).
    assert symbols == {"VGL", "SADBHAV", "EIEL", "PVSL"}


def test_label_only_filing_takes_its_meaning_from_the_worded_one():
    d = build_digest(filings("106845162", "106844841"), [])  # Popular Vehicles, 3-4 Nov
    items = d["attention"] + d["worth"]
    assert len(items) == 1 and items[0].classification.subtype == "auditor_exit_subsidiary"
    assert items[0].score == 70


# 5. Litigation by kind and size --------------------------------------------------------------------

def test_gst_adjudication_order_without_an_amount_is_worth_knowing_not_attention():
    a = week()["106853509"]  # BHEL: adjudication order under the CGST Act
    c = classify(a)
    tier, score, reasons = score_item(a, c)
    assert c.subtype == "tax" and 40 <= score < ATTENTION
    assert "no amount" in reasons[0]


def test_show_cause_notice_is_a_tax_matter():
    assert classify(week()["106852875"]).subtype == "tax"


@pytest.mark.parametrize("amount,net_worth,expected", [
    (120, 1_000, 85),    # 12% of net worth: material
    (120, 10_000, 70),   # 1.2%
    (30, 10_000, 45),    # 0.3%: small
])
def test_tax_order_rises_only_when_material_against_net_worth(amount, net_worth, expected):
    a = Announcement("x", "ABC", "ABC", datetime(2026, 11, 9, 18), "NSE", label="Updates",
                     subject=f"Receipt of GST demand order of Rs {amount} crore")
    _, score, _ = score_item(a, classify(a), net_worth=net_worth)
    assert score == expected


def test_insolvency_stays_at_the_top():
    a = week()["106852923"]  # Auri Grow: Corporate Insolvency Resolution Process
    assert score_item(a, classify(a))[1] == 100


def test_litigation_no_longer_floods_attention():
    attention = [a for a in week().values()
                 if classify(a).category == "litigation" and score_item(a, classify(a))[1] >= ATTENTION]
    assert len(attention) < 30  # was 56, GST show-cause notices among them


# 6. Pledges named for what they are ---------------------------------------------------------------

def pledge_row(company: str) -> dict:
    rows = json.loads((FIX / "pledges.json").read_text(encoding="utf-8"))
    rows = rows["data"] if isinstance(rows, dict) else rows
    return next(r for r in rows if r["comName"].strip() == company)


@pytest.mark.parametrize("company,of_promoter,of_total,all_demat", [
    ("Kalyan Jewellers India Limited", 24.85, 15.62, 16.68),
    ("Asian Paints Limited", 10.35, 5.46, 6.25),
])
def test_pledge_fields_checked_by_arithmetic(company, of_promoter, of_total, all_demat):
    p = parse_pledge(pledge_row(company))
    assert p.pledged_of_promoter_pct == of_promoter
    assert p.promoter_pledged_of_total_pct == of_total
    assert p.all_pledged_of_demat_pct == all_demat
    # The percentages agree with the feed's own share counts.
    assert p.promoter_pledged_shares / p.promoter_shares * 100 == pytest.approx(of_promoter, abs=0.01)
    assert p.promoter_pledged_shares / p.issued_shares * 100 == pytest.approx(of_total, abs=0.01)
    assert p.as_of == date(2026, 9, 30)


# Alerts: the threshold that fired, and the exchange's sessions --------------------------------------

def bars(closes, start=date(2026, 6, 1)):
    return [Bar(start + timedelta(days=i), c, 1_000_000) for i, c in enumerate(closes)]


def test_move_reports_the_rule_that_fired():
    quiet = [100 * (1.001 if i % 2 else 0.999) for i in range(70)]
    sigma_only = signals_for("A", bars(quiet + [quiet[-1] * 1.02]))[0]
    assert (sigma_only.fired_by, sigma_only.threshold) == ("sigma", 3.0)
    both = signals_for("A", bars(quiet + [quiet[-1] * 1.08]))[0]
    assert (both.fired_by, both.threshold) == ("both", 5.0)
    pct_only = signals_for("A", bars([100.0] * 10 + [106.0]), Thresholds(move_rule="either"))[0]
    assert (pct_only.fired_by, pct_only.threshold, pct_only.sigma) == ("pct", 5.0, None)


# Exchange sessions in November 2026: 8 Nov (Sunday) had a Muhurat session; 10 Nov was a holiday.
SESSIONS = [date(2026, 11, 6), date(2026, 11, 8), date(2026, 11, 9), date(2026, 11, 11), date(2026, 11, 12)]


def test_reaction_window_uses_sessions_not_weekdays():
    before, after = reaction_window(datetime(2026, 11, 9, 17, 5), SESSIONS)  # after Monday's close
    assert before == date(2026, 11, 9) and after == [date(2026, 11, 11), date(2026, 11, 12)]
    before, after = reaction_window(datetime(2026, 11, 9, 10, 0), SESSIONS)  # during the session
    assert before is None and after == [date(2026, 11, 9), date(2026, 11, 11)]


def test_a_move_after_a_holiday_is_attached_to_the_filing_before_it():
    filing = Announcement("1", "ABC", "ABC", datetime(2026, 11, 9, 18, 0), "NSE", label="Acquisition",
                          subject="Acquisition of 100% stake in XYZ Private Limited")
    move = Signal("ABC", date(2026, 11, 11), "move", 6.2, 5.0, "Closed up 6.2%", fired_by="pct")
    d = build_digest([filing], [move], trading_days=SESSIONS)
    assert d["attention"][0].signals == [move] and d["unexplained_moves"] == []
    # Without a calendar, the fallback is the filing date and three calendar days: 13 Nov is outside.
    late = Signal("ABC", date(2026, 11, 13), "move", 6.2, 5.0, "Closed up 6.2%", fired_by="pct")
    assert build_digest([filing], [late])["unexplained_moves"] == [late]


# Text helpers -----------------------------------------------------------------------------------

def test_own_words_strips_the_exchange_template():
    assert own_words("Asian Paints Limited has informed the Exchange regarding Change in Director(s) of the company.",
                     "Change in Director(s)") == ""
    assert own_words("Vineet Laboratories Limited has informed the Exchange regarding ''.", "Updates") == ""
    assert own_words("Schedule of virtual Investor Conference on December 2, 2026.").startswith("Schedule")


def test_amount_crore():
    assert amount_crore("demand of Rs. 12.5 crore and penalty of Rs 50 lakh") == 12.5
    assert amount_crore("INR 1,23,45,678") == pytest.approx(1.2345678)
    assert amount_crore("no amount here") is None
