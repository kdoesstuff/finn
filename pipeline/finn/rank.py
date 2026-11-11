"""Turn classified filings and price signals into a ranked digest.

Order of attention: management and governance, then the business, then price,
then paperwork. Every item carries the reasons it sits where it does, so the
app can answer "why am I seeing this?" without guessing.

Sections:
  attention  score >= 75   shown in full
  worth      40 <= s < 75  one line each
  routine    s < 40        collapsed into a count by kind

Companies often file several times about one event (a board reshuffle, an auditor's exit filed under
two labels). Nothing is dropped: filings about one event become one card that lists them all, scored
from the filings that say what actually happened. Only exact re-uploads (same summary, same file,
same size) are counted once.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .classify import classify
from .models import Announcement, Classification, DigestItem, Signal
from .taxonomy import TIER_SCORE, Tier, tier_of
from .text import amount_crore, own_words

ATTENTION = 75
WORTH = 40
KEY_ROLES = {"ceo", "cfo", "md", "chair", "coo"}
EXITS = {"resignation", "cessation", "retirement"}

# Filings by one company in one category this close together are treated as one event.
EVENT_GAP = timedelta(hours=6)
# An identical document uploaded again this soon after the first is a re-upload, counted once.
REUPLOAD_WINDOW = timedelta(minutes=60)
# NSE's equity session closes at 15:30 IST; a filing after that can only move the next session.
MARKET_CLOSE = time(15, 30)
REACTION_SESSIONS = 2


@dataclass
class Prefs:
    alert_categories: set[str] = field(
        default_factory=lambda: {"results", "M&A", "management_change", "litigation", "pledging"}
    )


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def _sized(base: float, what: str, amount: float | None, net_worth: float | None) -> tuple[float, str]:
    """Score a claim, order or dispute by its size against the company's net worth, when both are known."""
    if amount is None:
        return base, f"{what}; the summary states no amount"
    if not net_worth or net_worth <= 0:
        return base, f"{what} of ₹{amount:,.2f} crore; net worth not yet known, so its size cannot be judged"
    share = amount / net_worth * 100
    score = 85.0 if share >= 5 else 70.0 if share >= 1 else 45.0
    return score, f"{what} of ₹{amount:,.2f} crore, {share:.1f}% of net worth"


def score_item(a: Announcement, c: Classification, net_worth: float | None = None) -> tuple[int, float, list[str]]:
    """Tier, score and the reasons behind them for one filing. `net_worth` (₹ crore) sizes disputes."""
    tier = tier_of(c.category)
    score = float(TIER_SCORE[tier])
    reasons: list[str] = []
    text = f"{a.subject} {a.body}"

    if c.needs_model:
        return int(Tier.CONTEXT), 30.0, ["No rule recognised this filing; queued for a model to read"]

    if c.category == "management_change":
        role_name = {"ceo": "CEO", "cfo": "CFO", "md": "MD", "chair": "Chair", "coo": "COO",
                     "executive_director": "Executive director"}.get(c.role, c.role)
        if c.subtype == "auditor_exit":
            score, reasons = 100, ["The company's statutory auditor is leaving mid-term: a governance red flag"]
        elif c.subtype == "auditor_exit_subsidiary":
            score = 70
            reasons.append("An auditor of a subsidiary resigned: worth asking why")
        elif c.subtype == "auditor_exit_other":
            tier, score = Tier.CONTEXT, 40
            reasons.append("A cost, internal or secretarial auditor changed; routine unless it recurs")
        elif c.subtype == "demise":
            score = 90
            reasons.append("Death of a director or key person: succession question")
        elif c.role in KEY_ROLES | {"executive_director"} and c.action == "reappointment":
            tier, score = Tier.CONTEXT, 45
            reasons.append(f"{role_name} reappointed: continuity, not a change")
        elif c.role in KEY_ROLES:
            score = 95 if c.action in {"resignation", "cessation"} else 90
            reasons.append(f"Change at the top: {role_name} {c.action or 'change'}")
        elif c.role == "executive_director":
            score = 80 if c.action in EXITS else 70
            reasons.append(f"Whole-time board member: {c.action or 'change'}")
        elif c.role == "secretarial":
            tier, score = Tier.ROUTINE, 15
            reasons.append("Company secretary or compliance officer change")
        elif c.role == "senior":
            score = 70 if c.action in EXITS else 60
            reasons.append("Senior management change below the top team")
        elif c.role == "director" and c.action == "reappointment":
            tier, score = Tier.ROUTINE, 30
            reasons.append("Director reappointed")
        elif c.role == "director":
            score = 55 if _has(text, r"independent") else 65
            reasons.append("Board change below the top team")
        elif c.detail_in_document:
            score = 65
            reasons.append("Management change; the summary does not say who, the filing does")
        else:
            score = 60
            reasons.append("Management change")

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
        elif c.subtype == "regulator":
            score = 90
            reasons.append("Action by a regulator or an investigating agency")
        else:
            if c.subtype == "tax":
                base, what = 55.0, "Tax or duty order"
            else:
                base, what = 70.0, "Court, tribunal or legal matter"
            score, reason = _sized(base, what, amount_crore(text), net_worth)
            if score < ATTENTION:
                tier = Tier.CONTEXT
            reasons.append(reason)

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


def _file_key(a: Announcement) -> tuple[str, str, str, str, str]:
    """What an exact re-upload repeats: company, label, summary, file name (without NSE's timestamp
    prefix) and file size. One PDF attached to several announcements with different summaries
    (Motherson, 7 Nov 2026) is several announcements, not a re-upload."""
    name = a.url.rsplit("/", 1)[-1].lower()
    stem = re.sub(r"^[a-z0-9&\-]+_\d{14}_", "", name)
    words = re.sub(r"\W+", "", (own_words(a.subject, a.label) or a.subject).lower())
    return a.symbol, a.label, words, stem, a.file_size


@dataclass
class Event:
    """Filings by one company about one thing, close together in time."""

    filings: list[tuple[Announcement, Classification]]

    @property
    def symbol(self) -> str:
        return self.filings[0][0].symbol

    @property
    def first_ts(self) -> datetime:
        return min(a.ts for a, _ in self.filings)


def group_events(anns: list[Announcement]) -> list[Event]:
    """Group filings by company and category; a filing within EVENT_GAP of the previous one joins
    its event. Exact re-uploads count once. Identity is the exchange's own filing id: two filings
    with different ids are never merged into one, only listed together."""
    seen_ids: set[str] = set()
    first_upload: dict[tuple[str, str, str, str, str], datetime] = {}
    classified = []
    for a in sorted(anns, key=lambda x: (x.source != "NSE", x.ts)):
        if a.id in seen_ids:
            continue
        key = _file_key(a)
        if key[3] and key in first_upload and a.ts - first_upload[key] <= REUPLOAD_WINDOW:
            continue
        seen_ids.add(a.id)
        first_upload.setdefault(key, a.ts)
        classified.append((a, classify(a)))

    classified.sort(key=lambda p: (p[0].symbol, p[1].category, p[0].ts))
    events: list[Event] = []
    for a, c in classified:
        last = events[-1] if events else None
        if (last and last.symbol == a.symbol and last.filings[-1][1].category == c.category
                and a.ts - last.filings[-1][0].ts <= EVENT_GAP):
            last.filings.append((a, c))
        else:
            events.append(Event([(a, c)]))
    return events


def reaction_window(ts: datetime, trading_days: list[date] | None) -> tuple[date | None, list[date]]:
    """Sessions a filing can explain: the first REACTION_SESSIONS sessions after it was published,
    and, for a filing published after the close, that day's session ("moved before the filing").

    Without a trading calendar, falls back to the filing date and the three calendar days after it."""
    if not trading_days:
        return None, [ts.date() + timedelta(days=i) for i in range(4)]
    days = sorted(set(trading_days))
    after = [d for d in days if d > ts.date() or (d == ts.date() and ts.time() < MARKET_CLOSE)]
    before = ts.date() if ts.date() in days and ts.time() >= MARKET_CLOSE else None
    return before, after[:REACTION_SESSIONS]


def build_digest(
    anns: list[Announcement],
    signals: list[Signal],
    prefs: Prefs | None = None,
    trading_days: list[date] | None = None,
    net_worth: dict[str, float] | None = None,
) -> dict:
    """The ranked digest for a set of filings and price/volume signals.

    trading_days  the exchange's sessions (from bhavcopies); decides which moves a filing explains
    net_worth     ₹ crore by symbol, where known; sizes tax orders and disputes
    """
    prefs = prefs or Prefs()
    net_worth = net_worth or {}
    items: list[DigestItem] = []
    by_symbol: dict[str, list[Signal]] = {}
    for s in signals:
        by_symbol.setdefault(s.symbol, []).append(s)
    explained: set[int] = set()

    for event in group_events(anns):
        scored = []
        for a, c in event.filings:
            tier, score, reasons = score_item(a, c, net_worth.get(a.symbol))
            scored.append((a, c, tier, score, reasons))
        # Score the event from the filings that say what happened; a summary that only restates
        # the exchange's label is evidence of nothing beyond the label.
        pool = [x for x in scored if not x[1].detail_in_document] or scored
        a, c, tier, score, reasons = max(pool, key=lambda x: (x[3], x[0].source == "NSE", -x[0].ts.timestamp()))
        reasons = list(reasons)
        related = sorted((x[0] for x in scored if x[0] is not a), key=lambda r: r.ts)

        before_day, after_days = reaction_window(event.first_ts, trading_days)
        mine = by_symbol.get(event.symbol, [])
        after = [s for s in mine if s.day in after_days]
        before = [s for s in mine if before_day is not None and s.day == before_day]
        if (after or before) and tier != Tier.ROUTINE:
            score += 15
            if after:
                reasons.append("The stock moved after this filing: " + "; ".join(s.detail for s in after))
            if before:
                reasons.append("The stock moved that day, before this filing was published after the close: "
                               + "; ".join(s.detail for s in before))
            explained.update(id(s) for s in after + before)
        item = DigestItem(a, c, tier, min(score, 100.0), reasons, after + before, related=related)
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
            moves = "move" if len(unexplained) == 1 else "moves"
            parts.append(f"{len(unexplained)} unexplained price or volume {moves}")
        lead = ", ".join(parts) + "."
    tail = []
    if worth:
        tail.append(f"{len(worth)} worth knowing")
    if routine:
        tail.append(f"{len(routine)} routine filings set aside")
    return lead + (" " + "; ".join(tail) + "." if tail else "")


def window(anns: list[Announcement], start: date, end: date) -> list[Announcement]:
    return [a for a in anns if start <= a.ts.date() <= end]
