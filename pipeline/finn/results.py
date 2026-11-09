"""Headline results: this quarter against last quarter and the same quarter last year.

Numbers come from the filing's structured data (XBRL), never from a model.
EBITDA is not a line item in Indian results, so it is derived, and the
definition is stated wherever it is shown:

    EBITDA = PBT before exceptional items + finance costs + depreciation
             and amortisation - other income

i.e. operating profit from the core business, before financing, accounting
charges and one-offs. Banks and NBFCs have no meaningful EBITDA; they get a
different template (net interest income, operating profit, provisions, PAT).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

EBITDA_DEFINITION = (
    "EBITDA = PBT before exceptional items + finance costs + depreciation and amortisation - other income"
)


@dataclass
class Quarter:
    period_end: date
    revenue: float  # revenue from operations
    other_income: float = 0.0
    finance_costs: float = 0.0
    depreciation: float = 0.0
    exceptional: float = 0.0  # signed as reported: a loss is negative
    pbt: float = 0.0  # after exceptional items, as reported
    pat: float = 0.0
    consolidated: bool = True
    source: str = ""  # link to the filing the numbers came from

    @property
    def ebitda(self) -> float:
        pbt_before_exceptional = self.pbt - self.exceptional
        return pbt_before_exceptional + self.finance_costs + self.depreciation - self.other_income


@dataclass
class BankQuarter:
    period_end: date
    interest_earned: float
    interest_expended: float
    other_income: float
    operating_expenses: float
    provisions: float
    pbt: float
    pat: float
    consolidated: bool = True
    source: str = ""

    @property
    def nii(self) -> float:
        return self.interest_earned - self.interest_expended

    @property
    def ppop(self) -> float:
        return self.nii + self.other_income - self.operating_expenses


def _same_quarter_last_year(d: date) -> tuple[int, int]:
    return d.year - 1, d.month


def _previous_quarter(d: date) -> tuple[int, int]:
    m = d.month - 3
    return (d.year, m) if m > 0 else (d.year - 1, m + 12)


def pct_change(now: float, then: float) -> dict:
    """% change, or a plain-words note when a % would mislead (loss to profit, zero base)."""
    if then == 0:
        return {"pct": None, "note": "no base"}
    if then < 0 and now >= 0:
        return {"pct": None, "note": "turned positive"}
    if then > 0 and now < 0:
        return {"pct": None, "note": "turned negative"}
    if then < 0 and now < 0:
        return {"pct": None, "note": "loss narrowed" if now > then else "loss widened"}
    return {"pct": round((now / then - 1) * 100, 1), "note": ""}


def _margin(x: float, revenue: float) -> float | None:
    return round(x / revenue * 100, 1) if revenue else None


def _rows(quarters, metrics, base=None) -> tuple:
    """QoQ and YoY for each metric of the latest quarter. `base` (if given) is the
    denominator for margins, e.g. revenue."""
    q = max(quarters, key=lambda x: x.period_end)
    index = {(x.period_end.year, x.period_end.month): x for x in quarters}
    prev = index.get(_previous_quarter(q.period_end))
    yago = index.get(_same_quarter_last_year(q.period_end))

    rows = []
    for name, get, has_margin in metrics:
        now = get(q)
        row = {"metric": name, "value": round(now, 2)}
        if has_margin and base:
            row["margin"] = _margin(now, base(q))
        for label, other in (("qoq", prev), ("yoy", yago)):
            if other is None:
                row[label] = {"pct": None, "note": "not available"}
                continue
            row[label] = pct_change(now, get(other))
            if "margin" in row:
                then_margin = _margin(get(other), base(other))
                if row["margin"] is not None and then_margin is not None:
                    row[label]["margin_bps"] = round((row["margin"] - then_margin) * 100)
        rows.append(row)
    return q, rows, prev is not None, yago is not None


def headline(quarters: list[Quarter]) -> dict:
    """First cut for the latest quarter: Revenue, EBITDA, PBT, PAT, QoQ and YoY. Values in ₹ crore."""
    q, rows, _, _ = _rows(quarters, [
        ("Revenue", lambda x: x.revenue, False),
        ("EBITDA", lambda x: x.ebitda, True),
        ("PBT", lambda x: x.pbt, True),
        ("PAT", lambda x: x.pat, True),
    ], base=lambda x: x.revenue)
    notes = [EBITDA_DEFINITION]
    if q.exceptional:
        notes.append(f"Exceptional items of ₹{q.exceptional:,.0f} cr are in PBT and PAT but excluded from EBITDA")
    return {
        "template": "standard",
        "period_end": q.period_end.isoformat(),
        "basis": "consolidated" if q.consolidated else "standalone",
        "unit": "₹ crore",
        "rows": rows,
        "notes": notes,
        "source": q.source,
    }


def bank_headline(quarters: list[BankQuarter]) -> dict:
    """Banks and NBFCs: net interest income, operating profit, provisions, PAT. Values in ₹ crore."""
    q, rows, _, _ = _rows(quarters, [
        ("Net interest income", lambda x: x.nii, False),
        ("Operating profit", lambda x: x.ppop, False),
        ("Provisions", lambda x: x.provisions, False),
        ("PAT", lambda x: x.pat, False),
    ])
    return {
        "template": "bank",
        "period_end": q.period_end.isoformat(),
        "basis": "consolidated" if q.consolidated else "standalone",
        "unit": "₹ crore",
        "rows": rows,
        "notes": [
            "Banks have no revenue or EBITDA in the usual sense.",
            "Net interest income = interest earned - interest expended; "
            "operating profit = NII + other income - operating expenses (before provisions).",
        ],
        "source": q.source,
    }
