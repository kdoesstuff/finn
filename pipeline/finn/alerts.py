"""Price and volume signals from end-of-day bars.

The investor sets what "unusual" means; FINN watches for it. Two thresholds:

  volume  today's volume as a multiple of the average of the previous N days
  move    today's close-to-close change, either as a plain % (the brief's ±X%)
          or in units of the stock's own recent daily volatility (sigma)

The sigma view exists because a 4% day means different things for a quiet
large-cap and a volatile small-cap. Both views are always computed and shown;
the investor's rule decides which one fires.

A signal is only reported when its baseline rests on enough history. Below the
minimum the stock gets no signal at all rather than a guess.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .models import Bar, Signal


@dataclass
class Thresholds:
    volume_multiple: float = 2.0
    volume_window: int = 20
    move_pct: float = 5.0
    move_sigma: float = 3.0
    vol_window: int = 60
    move_rule: str = "either"  # "pct", "sigma" or "either"
    min_volume_days: int = 15
    min_vol_days: int = 40


def _log_returns(closes: list[float]) -> list[float]:
    return [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]


def signals_for(symbol: str, bars: list[Bar], th: Thresholds | None = None) -> list[Signal]:
    """Signals for the last bar in `bars` (oldest first)."""
    th = th or Thresholds()
    if len(bars) < 2:
        return []
    bars = sorted(bars, key=lambda b: b.day)
    today, prior = bars[-1], bars[:-1]
    out: list[Signal] = []

    vol_base = [b.volume for b in prior[-th.volume_window:] if b.volume > 0]
    if len(vol_base) >= th.min_volume_days:
        avg = statistics.fmean(vol_base)
        multiple = today.volume / avg if avg else 0.0
        if multiple >= th.volume_multiple:
            out.append(Signal(
                symbol=symbol, day=today.day, kind="volume", value=round(multiple, 2),
                threshold=th.volume_multiple, sample=len(vol_base),
                detail=f"Volume {multiple:.1f}x its {len(vol_base)}-day average",
            ))

    prev_close = prior[-1].close
    if prev_close > 0 and today.close > 0:
        pct = (today.close / prev_close - 1) * 100
        rets = _log_returns([b.close for b in prior[-(th.vol_window + 1):]])
        sigma = None
        if len(rets) >= th.min_vol_days:
            sd = statistics.stdev(rets)
            if sd > 0:
                sigma = math.log(today.close / prev_close) / sd

        by_pct = abs(pct) >= th.move_pct
        by_sigma = sigma is not None and abs(sigma) >= th.move_sigma
        fired = {"pct": by_pct, "sigma": by_sigma, "either": by_pct or by_sigma}[th.move_rule]
        if fired:
            direction = "up" if pct > 0 else "down"
            detail = f"Closed {direction} {abs(pct):.1f}%"
            if sigma is not None:
                detail += f", a {abs(sigma):.1f} sigma day against its last {len(rets)} sessions"
            out.append(Signal(
                symbol=symbol, day=today.day, kind="move", value=round(pct, 2),
                threshold=th.move_pct if th.move_rule == "pct" else th.move_sigma,
                sigma=None if sigma is None else round(sigma, 2), sample=len(rets), detail=detail,
            ))
    return out
