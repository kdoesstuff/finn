"""Reading the short text an exchange attaches to a filing.

NSE writes most summaries as "<Company> has informed the Exchange about <label>". About a quarter of
a real week's filings (1,132 of 4,795, 4-9 Nov 2026) say nothing beyond that: the summary restates
the exchange's own category label. Anything FINN infers about people (who, which role, what
happened) must come from the company's own words, so `own_words` strips the template and returns ""
when nothing of the company's own is left.
"""

from __future__ import annotations

import re

_PREFIX = re.compile(
    r"^.*?\bhas\s+(?:informed|intimated|submitted\s+to)\s+the\s+exchange,?\s*(?:about|regarding|that|on)?\s*",
    re.IGNORECASE | re.DOTALL,
)
_TRAILER = re.compile(r"\s*(?:of\s+the\s+company)?\s*[.\s'\"]*$", re.IGNORECASE)
_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def own_words(subject: str, label: str = "") -> str:
    """The company's own words in a filing summary, or "" if it only restates the label."""
    s = (subject or "").strip()
    rest = _PREFIX.sub("", s, count=1) if _PREFIX.match(s) else s
    rest = _ARTICLE.sub("", rest.strip().strip("'\"").strip())
    rest = _TRAILER.sub("", rest).strip().strip("'\"").strip()
    if len(_norm(rest)) < 4:
        return ""
    if label and _norm(rest) == _norm(label):
        return ""
    return rest


_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|lakh|million|mn|billion|bn)?",
    re.IGNORECASE,
)
_UNIT_TO_CRORE = {
    "crore": 1.0, "crores": 1.0, "cr": 1.0, "cr.": 1.0,
    "lakh": 0.01, "lakhs": 0.01, "lac": 0.01, "lacs": 0.01,
    "million": 0.1, "mn": 0.1,
    "billion": 100.0, "bn": 100.0,
}


def amount_crore(text: str) -> float | None:
    """The largest rupee amount stated in the text, in crore, or None if no amount is stated.

    A bare figure without a unit is read as whole rupees ("Rs 12,34,567" = 0.12 crore).
    """
    best = None
    for num, unit in _AMOUNT.findall(text or ""):
        try:
            value = float(num.replace(",", ""))
        except ValueError:
            continue
        crore = value * _UNIT_TO_CRORE[unit.lower()] if unit else value / 1e7
        best = crore if best is None else max(best, crore)
    return best
