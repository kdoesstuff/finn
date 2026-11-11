"""Promoter pledges from NSE's pledge disclosure feed (`api/corporate-pledgedata`).

NSE's field names do not say what each percentage is a share of. Checked by arithmetic against the
feed's own share counts (Kalyan Jewellers and Asian Paints, quarter to 30 Sep 2026):

    percPromoterHolding  promoter shares / issued shares                  (Kalyan 62.85%)
    percPromoterShares   pledged promoter shares / promoter shares        (Kalyan 24.85%)
    percTotShares        pledged promoter shares / issued shares          (Kalyan 15.62%)
    percSharesPledged    all pledged shares, any holder / demat shares    (Kalyan 16.68%)

The figure that matters for owner-level leverage is the second: how much of their own stake the
promoters have borrowed against. The last one includes pledges by anyone, so FINN never calls it a
promoter pledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Pledge:
    company: str
    as_of: date  # shareholding date the disclosure refers to
    promoter_holding_pct: float  # promoters' stake in the company
    pledged_of_promoter_pct: float  # share of the promoters' own stake that is pledged
    promoter_pledged_of_total_pct: float  # promoter pledges as a share of all issued shares
    all_pledged_of_demat_pct: float  # every pledge by any holder, as a share of demat shares
    promoter_shares: int
    promoter_pledged_shares: int
    issued_shares: int

    @property
    def headline(self) -> str:
        return (f"Promoters have pledged {self.pledged_of_promoter_pct:.2f}% of their "
                f"{self.promoter_holding_pct:.2f}% stake ({self.promoter_pledged_of_total_pct:.2f}% of the company)")


def _f(row: dict, key: str) -> float:
    v = str(row.get(key) or "0").strip()
    return float(v) if v else 0.0


def _i(row: dict, key: str) -> int:
    v = str(row.get(key) or "0").strip().replace(",", "")
    return int(float(v)) if v else 0


def parse(row: dict) -> Pledge:
    return Pledge(
        company=row["comName"].strip(),
        as_of=datetime.strptime(row["shp"].strip(), "%d-%b-%Y").date(),
        promoter_holding_pct=_f(row, "percPromoterHolding"),
        pledged_of_promoter_pct=_f(row, "percPromoterShares"),
        promoter_pledged_of_total_pct=_f(row, "percTotShares"),
        all_pledged_of_demat_pct=_f(row, "percSharesPledged"),
        promoter_shares=_i(row, "totPromoterHolding"),
        promoter_pledged_shares=_i(row, "totPromoterShares"),
        issued_shares=_i(row, "totIssuedShares"),
    )


def change(before: Pledge, after: Pledge) -> float:
    """Change in the pledged share of the promoters' stake, in percentage points."""
    return round(after.pledged_of_promoter_pct - before.pledged_of_promoter_pct, 2)
