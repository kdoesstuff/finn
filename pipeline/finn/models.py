"""Plain data records passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Announcement:
    """One filing as an exchange publishes it, before any interpretation."""

    id: str
    symbol: str
    company: str
    ts: datetime
    source: str  # "NSE" or "BSE"
    label: str = ""  # the exchange's own category text, e.g. NSE "desc"
    subject: str = ""  # headline / subject line
    body: str = ""  # short text the exchange attaches, if any
    url: str = ""  # link to the PDF or page


@dataclass
class Classification:
    category: str
    subtype: str = ""
    confidence: float = 0.0
    rule_id: str = ""
    needs_model: bool = False  # no rule fired; send to a cheap model
    role: str = ""  # management changes: ceo, cfo, md, chair, director, secretarial, auditor
    action: str = ""  # management changes: appointment, resignation, cessation, retirement


@dataclass
class Bar:
    """End-of-day price and volume for one trading day."""

    day: date
    close: float
    volume: float


@dataclass
class Signal:
    """A price or volume observation that crossed one of the investor's thresholds."""

    symbol: str
    day: date
    kind: str  # "volume" or "move"
    value: float  # volume multiple, or the day's % move
    threshold: float
    detail: str  # one line a person can read
    sigma: float | None = None  # the move in units of recent daily volatility
    sample: int = 0  # trading days the baseline rests on


@dataclass
class DigestItem:
    announcement: Announcement
    classification: Classification
    tier: int
    score: float
    reasons: list[str] = field(default_factory=list)  # why it sits where it does
    signals: list[Signal] = field(default_factory=list)  # same-day price/volume signals
    alert: bool = False  # crossed one of the investor's alert rules
