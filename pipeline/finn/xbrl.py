"""Read headline numbers from an NSE/BSE results XBRL filing.

Two traps, both seen in real filings:

1. A results file holds several periods: the quarter ("OneD") and the year to date
   ("FourD"). Filers often stamp both contexts with the quarter's dates, so the
   context's own <period> cannot be trusted. Each context also carries
   DateOfStartOfReportingPeriod / DateOfEndOfReportingPeriod facts with the true
   dates; those decide which context is the quarter.
2. Banks file in a different format ("Banking Format") with different line items:
   interest earned and expended, provisions, no revenue or EBITDA.

Values in the file are whole rupees. FINN reports in ₹ crore (1 crore = 10^7).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date

from .results import BankQuarter, Quarter

CRORE = 1e7
XBRLI = "{http://www.xbrl.org/2003/instance}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass
class Context:
    id: str
    start: date | None = None
    end: date | None = None
    instant: date | None = None
    dimensional: bool = False  # segment or scenario members: a breakdown, not the headline


@dataclass
class Filing:
    symbol: str
    period_start: date
    period_end: date
    consolidated: bool
    bank: bool
    audited: str
    audit_opinion: str
    board_meeting: str
    facts: dict[str, float] = field(default_factory=dict)  # headline values for the quarter, in ₹ crore
    text: dict[str, str] = field(default_factory=dict)


def _date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s.strip()) if s else None
    except ValueError:
        return None


def parse(xml: bytes) -> Filing:
    root = ET.fromstring(xml)
    contexts: dict[str, Context] = {}
    for ctx in root.iter(f"{XBRLI}context"):
        c = Context(ctx.get("id"))
        c.start = _date(ctx.findtext(f"{XBRLI}period/{XBRLI}startDate"))
        c.end = _date(ctx.findtext(f"{XBRLI}period/{XBRLI}endDate"))
        c.instant = _date(ctx.findtext(f"{XBRLI}period/{XBRLI}instant"))
        c.dimensional = ctx.find(f"{XBRLI}entity/{XBRLI}segment") is not None or ctx.find(f"{XBRLI}scenario") is not None
        contexts[c.id] = c

    by_ctx: dict[str, dict[str, str]] = {}
    for el in root:
        ref = el.get("contextRef")
        if ref is None or el.text is None:
            continue
        by_ctx.setdefault(ref, {})[_local(el.tag)] = el.text.strip()

    # True reporting period per context, from its own facts where the filer gave them.
    def period(cid: str) -> tuple[date | None, date | None]:
        facts = by_ctx.get(cid, {})
        c = contexts.get(cid)
        start = _date(facts.get("DateOfStartOfReportingPeriod")) or (c.start if c else None)
        end = _date(facts.get("DateOfEndOfReportingPeriod")) or (c.end if c else None)
        return start, end

    candidates = []
    for cid, c in contexts.items():
        if c.dimensional or c.instant or cid not in by_ctx:
            continue
        start, end = period(cid)
        if start and end:
            days = (end - start).days
            candidates.append((abs(days - 91), cid != "OneD", cid, start, end))
    if not candidates:
        raise ValueError("no duration context with a reporting period")
    _, _, qid, start, end = min(candidates)  # the context closest to three months; "OneD" breaks ties
    if (end - start).days > 100:
        raise ValueError(f"no quarterly context; shortest period is {start} to {end}")

    raw = by_ctx[qid]
    # Some descriptive facts are filed only once, under OneD.
    meta = {**by_ctx.get("OneD", {}), **raw}
    numbers = {}
    for k, v in raw.items():
        try:
            numbers[k] = float(v) / CRORE
        except ValueError:
            pass

    return Filing(
        symbol=meta.get("Symbol", ""),
        period_start=start,
        period_end=end,
        consolidated=meta.get("NatureOfReportStandaloneConsolidated", "").lower().startswith("consolidated"),
        bank="bank" in meta.get("ResultType", "").lower() or "InterestEarned" in raw,
        audited=meta.get("WhetherResultsAreAuditedOrUnaudited", ""),
        audit_opinion=meta.get("DeclarationOfUnmodifiedOpinionOrStatementOnImpactOfAuditQualification", ""),
        board_meeting=meta.get("DateOfBoardMeetingWhenFinancialResultsWereApproved", ""),
        facts=numbers,
        text={k: v for k, v in meta.items() if k not in numbers},
    )


def _first(facts: dict[str, float], *names: str, default: float = 0.0) -> float:
    for n in names:
        if n in facts:
            return facts[n]
    return default


def to_quarter(f: Filing, source: str = "") -> Quarter | BankQuarter:
    x = f.facts
    if f.bank:
        return BankQuarter(
            period_end=f.period_end,
            interest_earned=_first(x, "InterestEarned"),
            interest_expended=_first(x, "InterestExpended"),
            other_income=_first(x, "OtherIncome"),
            operating_expenses=_first(x, "OperatingExpenses"),
            provisions=_first(x, "ProvisionsOtherThanTaxAndContingencies"),
            pbt=_first(x, "ProfitLossFromOrdinaryActivitiesBeforeTax"),
            # For a consolidated bank, the profit owned by its shareholders after minority interest.
            pat=_first(x, "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
                       "ProfitLossForThePeriod"),
            consolidated=f.consolidated,
            source=source,
        )
    return Quarter(
        period_end=f.period_end,
        revenue=_first(x, "RevenueFromOperations"),
        other_income=_first(x, "OtherIncome"),
        finance_costs=_first(x, "FinanceCosts"),
        depreciation=_first(x, "DepreciationDepletionAndAmortisationExpense"),
        exceptional=_first(x, "ExceptionalItemsBeforeTax"),
        pbt=_first(x, "ProfitBeforeTax"),
        # Consolidated profit owned by the company's shareholders, the figure analysts quote.
        pat=_first(x, "ProfitOrLossAttributableToOwnersOfParent", "ProfitLossForPeriod"),
        consolidated=f.consolidated,
        source=source,
    )
