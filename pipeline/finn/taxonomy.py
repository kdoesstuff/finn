"""Announcement categories and how much attention each one earns.

The categories follow the ENAM reference glossary. The tiers are FINN's own
reading of what a long-term, management-first investor looks at first:

    1  Management and governance   who runs the company and whether they can be trusted
    2  Business                    what the company did or committed to
    3  Context                     useful, rarely decision-changing
    4  Routine                     compliance paperwork; collapsed into a count

A tier is the default. The ranker moves individual items up or down from it
(a CFO leaving outranks a director retiring; a reaffirmed rating is routine).
"""

from enum import IntEnum


class Tier(IntEnum):
    MANAGEMENT = 1
    BUSINESS = 2
    CONTEXT = 3
    ROUTINE = 4


CATEGORIES = {
    "results": Tier.BUSINESS,
    "M&A": Tier.BUSINESS,
    "fund_raise": Tier.BUSINESS,
    "management_change": Tier.MANAGEMENT,
    "litigation": Tier.MANAGEMENT,
    "insider_trading": Tier.MANAGEMENT,
    "earnings_call": Tier.ROUTINE,
    "investor_meetings": Tier.ROUTINE,
    "credit_rating": Tier.BUSINESS,
    "dividend": Tier.CONTEXT,
    "bonus_split": Tier.CONTEXT,
    "capex": Tier.BUSINESS,
    "press_release": Tier.CONTEXT,
    "postal_ballot": Tier.ROUTINE,
    "agm_egm": Tier.ROUTINE,
    "pledging": Tier.MANAGEMENT,
    # Not in the reference glossary: SEBI's event list has governance events that fit
    # none of its categories (related-party deals, fraud, delayed results).
    "governance": Tier.MANAGEMENT,
    "unclassified": Tier.ROUTINE,
}

TIER_LABEL = {
    Tier.MANAGEMENT: "Management and governance",
    Tier.BUSINESS: "Business",
    Tier.CONTEXT: "Context",
    Tier.ROUTINE: "Routine",
}

# Base score per tier. Modifiers in rank.py add to or subtract from these.
TIER_SCORE = {
    Tier.MANAGEMENT: 90,
    Tier.BUSINESS: 70,
    Tier.CONTEXT: 40,
    Tier.ROUTINE: 10,
}


def tier_of(category: str) -> Tier:
    return CATEGORIES.get(category, Tier.ROUTINE)
