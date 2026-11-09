"""Rule-based announcement classifier.

Exchange filings are formulaic: the subject line and the exchange's own label
name the event in a small vocabulary ("Outcome of Board Meeting", "Change in
Directors/ Key Managerial Personnel", "Credit Rating"). Rules catch most of
them at zero cost and with a traceable reason. Only filings no rule
recognises are marked `needs_model` for a cheap model to read.

Each rule matches against two texts:
  content  the subject and body, written by the company about this filing
  label    the exchange's category, shared by many unrelated filings

A content match beats a label match, because one NSE label ("Analysts/
Institutional Investor Meet/Con. Call Updates") covers both meeting notices
and call transcripts, and only the subject says which this one is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Announcement, Classification

LABEL_PENALTY = 20


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    priority: int
    any_of: tuple[str, ...]
    all_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()
    subtype: str = ""


def _rx(words: tuple[str, ...]) -> list[re.Pattern]:
    return [re.compile(w, re.IGNORECASE) for w in words]


RULES: list[Rule] = [
    # Routine paperwork first: these phrases override whatever else the filing mentions.
    Rule("trading-window", "unclassified", 96, (r"trading window",), subtype="trading_window"),
    Rule("share-certificates", "unclassified", 96,
         (r"loss of share certificate", r"duplicate share certificate", r"issue of duplicate"),
         subtype="share_certificates"),
    Rule("reg-74-5", "unclassified", 96, (r"regulation\s*74\s*\(5\)", r"reg\.?\s*74\s*\(5\)"), subtype="compliance"),
    Rule("compliance-cert", "unclassified", 94,
         (r"compliance certificate", r"certificate under (sebi|regulation)", r"secretarial compliance"),
         subtype="compliance"),
    Rule("esop-allotment", "unclassified", 94, (r"\bes(op|os|ps)\b", r"employee stock option"),
         none_of=(r"\bqip\b", r"preferential"), subtype="esop"),
    Rule("esg-report", "unclassified", 92,
         (r"\bbrsr\b", r"business responsibility", r"sustainability report", r"\besg\b"), subtype="esg"),
    Rule("results-ad", "results", 90, (r"newspaper", r"publication"), all_of=(r"result",), subtype="results_ad"),
    Rule("newspaper", "unclassified", 88, (r"newspaper publication", r"copy of newspaper"), subtype="newspaper"),

    # Governance red flag: an auditor leaving mid-term.
    Rule("auditor-exit", "management_change", 95, (r"auditor",),
         all_of=(r"resign|cessation|withdraw",), subtype="auditor_exit"),
    Rule("auditor-appoint", "unclassified", 85, (r"(statutory|secretarial|internal|cost) auditor",),
         all_of=(r"appoint",), subtype="auditor_appointment"),

    Rule("pledge", "pledging", 84, (r"pledg", r"encumbrance", r"regulation\s*31\s*\(1\)")),
    Rule("board-meeting-notice", "results", 83,
         (r"board meeting intimation", r"prior intimation", r"intimation of board meeting",
          r"board meeting to (be held|consider)"),
         all_of=(r"result",), subtype="board_meeting_notice"),
    Rule("results", "results", 80,
         (r"financial results?", r"\bunaudited\b", r"audited (standalone|consolidated)",
          r"results for the (quarter|half|year)", r"quarterly results?"),
         none_of=(r"intimation", r"to consider"), subtype="filing"),
    Rule("mgmt-change", "management_change", 79,
         (r"appoint", r"resign", r"cessation", r"retire", r"re-?designat",
          r"change in (directors|directorate|key managerial|kmp|management)",
          r"key managerial personnel", r"step(s|ped)? down")),
    Rule("earnings-call", "earnings_call", 78,
         (r"transcript", r"earnings call", r"\bcon(\.|ference)?\s?call\b", r"concall",
          r"audio (and |/)?(video )?recording")),
    Rule("litigation", "litigation", 77,
         (r"litigation", r"\bcourt\b", r"tribunal", r"\bnclt\b", r"\bnclat\b", r"show cause", r"penalty",
          r"\bfine\b", r"(tax|gst|demand) (order|notice)", r"\binsolvency\b", r"\bcirp\b", r"arbitra",
          r"order (passed|received) (by|from)", r"search (and|&) seizure", r"regulatory action")),
    Rule("credit-rating", "credit_rating", 75,
         (r"credit rating", r"\bcrisil\b", r"\bicra\b", r"care ratings", r"india ratings", r"\brating(s)? (action|assigned|reaffirm|upgrade|downgrade)")),
    Rule("m-and-a", "M&A", 74,
         (r"acqui(re|sition)", r"\bmerger\b", r"amalgamat", r"demerger", r"joint venture", r"scheme of arrangement",
          r"divest", r"(sale|transfer) of (stake|shares|business|undertaking)", r"investment in (its )?(wholly[- ]owned )?subsidiar",
          r"incorporation of (a )?(new )?(wholly[- ]owned )?subsidiar")),
    Rule("fund-raise", "fund_raise", 74,
         (r"rights issue", r"\bqip\b", r"qualified institution", r"preferential (issue|allotment)", r"buy-?back",
          r"commercial paper", r"non-convertible debenture", r"\bncds?\b", r"fund rais", r"raising of funds",
          r"\bwarrants?\b")),
    Rule("insider", "insider_trading", 72,
         (r"insider trading", r"\bpit\b", r"regulation\s*7\s*\(2\)", r"\bsast\b", r"takeover regulations",
          r"regulation\s*29")),
    Rule("capex", "capex", 71,
         (r"\bcapex\b", r"capital expenditure", r"capacity expansion", r"new (plant|facility|unit|line)",
          r"greenfield", r"brownfield", r"commercial production", r"commission(ed|ing) of")),
    Rule("bonus-split", "bonus_split", 70, (r"\bbonus\b", r"stock split", r"sub-?division", r"split of (equity )?shares")),
    Rule("dividend", "dividend", 69, (r"dividend",)),
    Rule("investor-meet", "investor_meetings", 68,
         (r"analysts?\s*/\s*institutional", r"investor meet", r"institutional investor", r"analyst meet",
          r"investor conference", r"one[- ]on[- ]one", r"group meeting")),
    Rule("postal-ballot", "postal_ballot", 66, (r"postal ballot", r"e-voting results?", r"scrutini[sz]er")),
    Rule("agm-egm", "agm_egm", 65, (r"\bagm\b", r"\begm\b", r"annual general meeting", r"extra-?ordinary general meeting")),
    Rule("investor-deck", "results", 60, (r"investor presentation", r"earnings presentation", r"shareholders?'? letter"),
         subtype="deck"),
    Rule("press-release", "press_release", 50,
         (r"press release", r"media release", r"order (win|received|inflow)", r"\bbags?\b", r"receipt of (an? )?order",
          r"\blaunch", r"partnership", r"\bmou\b", r"memorandum of understanding", r"clarification",
          r"spurt in (price|volume)")),
]

_COMPILED = [(r, _rx(r.any_of), _rx(r.all_of), _rx(r.none_of)) for r in RULES]

ROLES = [
    ("ceo", r"chief executive|\bceo\b"),
    ("cfo", r"chief financial|\bcfo\b"),
    ("md", r"managing director|\bm\.?d\.?\b|whole[- ]time director|executive director"),
    ("chair", r"chair(man|person|woman)?\b"),
    ("coo", r"chief operating|\bcoo\b"),
    ("secretarial", r"company secretary|compliance officer|registrar|share transfer agent"),
    ("director", r"\bdirector\b"),
]
ACTIONS = [
    ("resignation", r"resign|step(s|ped)? down"),
    ("cessation", r"cessation|ceas|vacat"),
    ("retirement", r"retire"),
    ("appointment", r"appoint|induct|designat"),
]


def _matches(rule_parts, text: str) -> bool:
    rule, any_of, all_of, none_of = rule_parts
    if not any(p.search(text) for p in any_of):
        return False
    if not all(p.search(text) for p in all_of):
        return False
    return not any(p.search(text) for p in none_of)


def _first(pairs, text: str) -> str:
    for name, pattern in pairs:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return ""


def classify(a: Announcement) -> Classification:
    content = f"{a.subject} {a.body[:800]}"
    label = a.label

    best = None
    for parts in _COMPILED:
        rule = parts[0]
        if _matches(parts, content):
            score, where = rule.priority, "content"
        elif label and _matches(parts, label):
            score, where = rule.priority - LABEL_PENALTY, "label"
        else:
            continue
        if best is None or score > best[0]:
            best = (score, rule, where)

    if best is None:
        return Classification(category="unclassified", confidence=0.0, rule_id="", needs_model=True)

    _, rule, where = best
    out = Classification(
        category=rule.category,
        subtype=rule.subtype,
        confidence=0.95 if where == "content" else 0.7,
        rule_id=f"{rule.id}@{where}",
    )
    if rule.category == "management_change":
        text = f"{content} {label}"
        out.role = "auditor" if rule.subtype == "auditor_exit" else _first(ROLES, text)
        out.action = _first(ACTIONS, text)
    return out
