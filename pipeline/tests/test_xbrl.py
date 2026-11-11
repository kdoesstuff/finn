"""Results parsing against real NSE XBRL filings (tests/fixtures/xbrl)."""

from datetime import date
from pathlib import Path

import pytest

from finn.results import BankQuarter, Quarter, bank_headline, headline
from finn.xbrl import parse, to_quarter

X = Path(__file__).parent / "fixtures" / "xbrl"


def quarters(symbol):
    return [to_quarter(parse(p.read_bytes()), source=p.name) for p in sorted(X.glob(f"{symbol}_*.xml"))]


def test_quarter_not_year_to_date():
    # TCS Q3 FY25: the file also holds nine-month figures under a context
    # stamped with the quarter's dates. The parser must pick the quarter.
    f = parse((X / "TCS_2024-12-31_Cons.xml").read_bytes())
    assert (f.period_start, f.period_end) == (date(2024, 10, 1), date(2024, 12, 31))
    assert f.facts["RevenueFromOperations"] == pytest.approx(63973.0)  # ₹ crore, not the 9M 190,845
    assert f.consolidated and not f.bank


def test_tcs_headline_against_reported_numbers():
    h = headline(quarters("TCS"))
    rows = {r["metric"]: r for r in h["rows"]}
    assert h["period_end"] == "2024-12-31"
    assert rows["Revenue"]["value"] == pytest.approx(63973.0)
    assert rows["PAT"]["value"] == pytest.approx(12380.0)  # attributable to owners
    # EBITDA = PBT before exceptional + finance costs + D&A - other income
    assert rows["EBITDA"]["value"] == pytest.approx(16666 + 234 + 1377 - 1243)
    assert rows["Revenue"]["qoq"]["pct"] is not None and rows["Revenue"]["yoy"]["pct"] is not None


def test_bank_is_detected_and_uses_the_bank_template():
    qs = quarters("HDFCBANK")
    assert all(isinstance(q, BankQuarter) for q in qs)
    latest = max(qs, key=lambda q: q.period_end)
    assert latest.nii == pytest.approx(85040.17 - 46914.28)
    assert latest.ppop == pytest.approx(27930.16, rel=1e-3)  # matches the filing's own operating profit line
    h = bank_headline(qs)
    assert [r["metric"] for r in h["rows"]] == ["Net interest income", "Operating profit", "Provisions", "PAT"]


IF = Path(__file__).parent / "fixtures" / "xbrl_if"


@pytest.mark.parametrize("folder", [X, IF], ids=["legacy results", "integrated filing"])
def test_every_fixture_parses_to_a_quarter(folder):
    files = list(folder.glob("*.xml"))
    assert files
    for p in files:
        f = parse(p.read_bytes())
        q = to_quarter(f)
        assert isinstance(q, (Quarter, BankQuarter))
        assert 80 <= (f.period_end - f.period_start).days <= 95, p.name  # always the quarter, never year to date
        assert q.pat != 0


def test_integrated_filing_format_reads_the_same_way():
    # SEBI's Integrated Filing (2025 onward) uses the same tags; the same parser serves both.
    f = parse((IF / "TCS_2026-09-30_200121.xml").read_bytes())
    q = to_quarter(f)
    assert isinstance(q, Quarter)
    assert f.consolidated and (f.period_start, f.period_end) == (date(2026, 7, 1), date(2026, 9, 30))
    assert q.revenue == pytest.approx(73188, abs=1)
    bank = parse((IF / "HDFCBANK_2026-09-30_202132.xml").read_bytes())
    assert bank.bank and bank.consolidated


@pytest.mark.parametrize("payload", [
    # Entity expansion ("billion laughs") and an external entity reading a local file.
    b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
    b'<xbrl xmlns="http://www.xbrl.org/2003/instance"><x contextRef="OneD">&b;</x></xbrl>',
    b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    b'<xbrl xmlns="http://www.xbrl.org/2003/instance"><x contextRef="OneD">&x;</x></xbrl>',
], ids=["entity expansion", "external entity"])
def test_hostile_xml_is_refused(payload):
    from defusedxml import DTDForbidden

    with pytest.raises(DTDForbidden):
        parse(payload)
