"""Turn classified filings and price signals into a ranked digest.

Order of attention: management and governance, then the business, then price,
then paperwork. Every item carries the reasons it sits where it does, so the
app can answer "why am I seeing this?" without guessing.

Sections:
  attention  score >= 75   shown in full
  worth      40 <= s < 75  one line each
  routine    s < 40        collapsed into a count by kind
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from .classify import classify
from .models import Announcement, Classification, DigestItem, Signal
from .taxonomy import TIER_SCORE, Tier, tier_of

ATTENTION = 75
WORTH = 40
KEY_ROLES = {"ceo", "cfo", "md", "chair", "coo"}


@dataclass
class Prefs:
    alert_categories: set[str] = field(
        default_factory=lambda: {"results", "M&A", "management_change", "litigation", "pledging"}
    )


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def score_item(a: Announcement, c: Classification) -> tuple[int, float, list[str]]:
    """Tier, score and the reasons behind them for one filing."""
    tier = tier_of(c.category)
    score = float(TIER_SCORE[tier])
    reasons: list[str] = []
    text = f"{a.subject} {a.body}"

    if c.needs_model:
        return int(Tier.CONTEXT), 30.0, ["No rule recognised this filing; queued for a model to read"]

    if c.category == "management_change":
        if c.subtype == "auditor_exit":
            score, reasons = 100, ["An auditor leaving mid-term is a governance red flag"]
        elif c.subtype == "demise":
            score = 90
            reasons.append("Death of a director or key person: succession question")
        elif c.role in KEY_ROLES:
            score = 95 if c.action in {"resignation", "cessation"} else 90
            reasons.append(f"Change at the top: {c.role.upper()} {c.action or 'change'}")
        elif c.role == "secretarial":
            tier, score = Tier.ROUTINE, 15
            reasons.append("Company secretary or compliance officer change")
        else:
            score = 55 if _has(text, r"independent") else 65
            reasons.append("Board change below the top team")

    elif c.category == "results":
        if c.subtype == "board_meeting_notice":
            tier, score = Tier.ROUTINE, 15
            reasons.append("Notice of a results date; the results themselves will rank on arrival")
        elif c.subtype == "results_ad":
            tier, score = Tier.ROUTINE, 8
            reasons.append("Newspaper copy of results already filed")
        elif c.subtype == "deck":
            tier, score = Tier.CONTEXT, 45
            reasons.append("Investor presentation; read alongside the results")
        else:
            score = 85
            reasons.append("Quarterly results: headline numbers compared QoQ and YoY")

    elif c.category == "credit_rating":
        if _has(text, r"downgrad|negative|watch with negative|placed under watch"):
            score = 85
            reasons.append("Rating downgrade or negative outlook")
        elif _has(text, r"upgrad|positive"):
            score = 60
            reasons.append("Rating upgrade or positive outlook")
        else:
            tier, score = Tier.ROUTINE, 20
            reasons.append("Rating reaffirmed")

    elif c.category == "pledging":
        if _has(text, r"release|revocation|discharg"):
            score = 55
            reasons.append("Promoter pledge released")
        else:
            score = 92
            reasons.append("Promoter shares pledged or invoked: a leverage risk at the owner level")

    elif c.category == "insider_trading" and c.subtype == "inter_se":
        tier, score = Tier.CONTEXT, 35
        reasons.append("Transfer within the promoter group; total promoter holding unchanged")

    elif c.category == "insider_trading":
        promoter = _has(text, r"promoter")
        selling = _has(text, r"\bsale\b|\bsold\b|dispos|\bsell")
        if promoter and selling:
            score = 85
            reasons.append("Promoter selling")
        elif promoter:
            score = 65
            reasons.append("Promoter buying")
        else:
            tier, score = Tier.CONTEXT, 35
            reasons.append("Insider disclosure; size not material on its own")

    elif c.category == "governance":
        score, reason = {
            "fraud": (100, "Fraud, default or arrest disclosed"),
            "forensic_audit": (100, "Forensic audit initiated"),
            "delayed_results": (90, "Results delayed or not submitted"),
            "related_party": (70, "Related-party transaction: check whether value moves to the promoter"),
        }.get(c.subtype, (80, "Governance disclosure"))
        reasons.append(reason)

    elif c.category == "fund_raise":
        if c.subtype == "debt" or _has(text, r"commercial paper|non[- ]convertible|\bncds?\b"):
            tier, score = Tier.CONTEXT, 45
            reasons.append("Routine debt issuance")
        elif _has(text, r"buy-?back"):
            score = 75
            reasons.append("Buyback: management returning cash")
        else:
            score = 80
            reasons.append("Equity raise: dilution and use of proceeds")

    elif c.category == "M&A":
        if c.subtype == "open_offer":
            score = 90
            reasons.append("Open offer: a change of control may be under way")
        elif c.subtype == "disposal":
            score = 80
            reasons.append("Sale of a business or asset: a capital allocation decision")
        else:
            score = 82
            reasons.append("Acquisition, merger or stake change: a capital allocation decision")

    elif c.category == "capex":
        if c.subtype == "commissioning":
            score = 70
            reasons.append("New capacity has started production: capex turning into revenue")
        else:
            score = 76
            reasons.append("Capacity spend: a capital allocation decision")

    elif c.category == "litigation":
        if c.subtype in {"default", "insolvency", "forensic_audit"}:
            score = 100
            reasons.append({
                "default": "Missed interest or principal payment",
                "insolvency": "Insolvency proceedings",
                "forensic_audit": "Forensic audit initiated",
            }[c.subtype])
        elif c.subtype == "licence":
            score = 75
            reasons.append("Change to a key licence or regulatory approval")
        else:
            score = 85
            reasons.append("Legal or regulatory matter")

    elif c.category == "press_release":
        sub = c.subtype
        if sub == "operations":
            tier, score = Tier.BUSINESS, 82
            reasons.append("Operations disrupted or closed")
        elif sub == "new_business":
            tier, score = Tier.BUSINESS, 70
            reasons.append("Entering a new line of business: check it against the investment thesis")
        elif sub == "guarantee":
            score = 55
            reasons.append("New guarantee for a third party: a contingent liability")
        elif sub == "price_query" or _has(text, r"spurt|clarification"):
            score = 60
            reasons.append("Exchange query or clarification on the stock's movement")
        elif sub == "order" or _has(text, r"\border\b"):
            score = 50
            reasons.append("Order win")
        elif sub == "business_update":
            score = 50
            reasons.append("Monthly business update")
        elif sub == "agreement_end":
            score = 55
            reasons.append("An agreement was cancelled or terminated")
        elif sub in {"agreement", "launch"}:
            score = 45
            reasons.append("Agreement or launch" if sub == "agreement" else "Product launch")
        else:
            reasons.append("General company news")

    elif c.category in {"dividend", "bonus_split"}:
        score = 35 if c.category == "dividend" else 45
        reasons.append("Corporate action")

    elif c.category == "earnings_call":
        reasons.append("Concall notice or transcript; feeds research, not the digest")

    else:
        reasons.append("Routine filing")

    return int(tier), float(score), reasons


def _dedupe(anns: list[Announcement]) -> list[Announcement]:
    """The same filing often appears on NSE and BSE. Keep one, preferring NSE."""
    seen: dict[tuple, Announcement] = {}
    for a in sorted(anns, key=lambda x: (x.source != "NSE", x.ts)):
        key = (a.symbol, a.ts.date(), re.sub(r"\W+", "", a.subject.lower())[:60])
        seen.setdefault(key, a)
    return list(seen.values())


def build_digest(
    anns: list[Announcement],
    signals: list[Signal],
    prefs: Prefs | None = None,
) -> dict:
    prefs = prefs or Prefs()
    items: list[DigestItem] = []
    by_symbol: dict[str, list[Signal]] = {}
    for s in signals:
        by_symbol.setdefault(s.symbol, []).append(s)
    explained: set[int] = set()

    for a in _dedupe(anns):
        c = classify(a)
        tier, score, reasons = score_item(a, c)
        near = [
            s for s in by_symbol.get(a.symbol, [])
            if a.ts.date() <= s.day <= a.ts.date() + timedelta(days=3)
        ]
        if near and tier != Tier.ROUTINE:
            score += 15
            reasons.append("The stock moved on or after this filing: " + "; ".join(s.detail for s in near))
            explained.update(id(s) for s in near)
        item = DigestItem(a, c, tier, min(score, 100.0), reasons, near)
        item.alert = c.category in prefs.alert_categories and item.score >= 60
        items.append(item)

    unexplained = [s for s in signals if id(s) not in explained]

    items.sort(key=lambda i: (-i.score, i.tier, -i.announcement.ts.timestamp()))
    attention = [i for i in items if i.score >= ATTENTION]
    worth = [i for i in items if WORTH <= i.score < ATTENTION]
    routine = [i for i in items if i.score < WORTH]
    routine_counts = Counter(i.classification.subtype or i.classification.category for i in routine)

    return {
        "attention": attention,
        "worth": worth,
        "unexplained_moves": unexplained,
        "routine": routine,
        "routine_counts": dict(routine_counts),
        "summary": _summary(attention, worth, unexplained, routine),
    }


def _summary(attention, worth, unexplained, routine) -> str:
    if not attention and not unexplained:
        lead = "Nothing material across your portfolio."
    else:
        parts = []
        if attention:
            parts.append(f"{len(attention)} {'item needs' if len(attention) == 1 else 'items need'} your attention")
        if unexplained:
            parts.append(f"{len(unexplained)} unexplained price or volume {'move' if len(unexplained) == 1 else 'moves'}")
        lead = ", ".join(parts) + "."
    tail = []
    if worth:
        tail.append(f"{len(worth)} worth knowing")
    if routine:
        tail.append(f"{len(routine)} routine filings set aside")
    return lead + (" " + "; ".join(tail) + "." if tail else "")


def window(anns: list[Announcement], start: date, end: date) -> list[Announcement]:
    return [a for a in anns if start <= a.ts.date() <= end]
