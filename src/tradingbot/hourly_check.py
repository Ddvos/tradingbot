"""The check behind a fifteen-minute replay: do the hourly candles built from the
fifteen-minute stream match the stored hourly table?

A fifteen-minute replay finds its turning points on hourly candles it builds
itself (ADR-0006), so those candles must be the stored hourly ones. The check
builds them the way replay does, over the whole development period so the
turning-point finder carries the same state, and compares them with the stored
table over the scoring period: hour by hour on open, high, low, close and
trades exactly and on volume to within float rounding (the archive's hourly
volume is the same sum in another order), and turning point by turning point,
found on both series at the hindsight route's 8%.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from tradingbot.candles import Candle, Timeframe
from tradingbot.replay import build_hourly
from tradingbot.turning_points import TurningPoint, find_turning_points


@dataclass(frozen=True)
class HourlyCheck:
    fifteen_minute: int
    """Fifteen-minute candles read over the scoring period."""
    built: int
    """Hourly candles built from them over the scoring period."""
    stored: int
    """Hourly candles in the stored table over the scoring period."""
    first: int
    last: int
    """Start times of the first and the last hourly candle compared."""
    only_built: list[int]
    """Hours with a built candle and no stored one."""
    only_stored: list[int]
    """Hours with a stored candle and no built one."""
    differing: list[int]
    """Hours whose two candles differ."""
    points_built: int
    points_stored: int
    """Turning points over the scoring period, found on the built and on the stored series."""
    differing_points: list[TurningPoint]
    """Turning points found on one series and not on the other, oldest first."""


def same_candle(a: Candle, b: Candle) -> bool:
    return (a.open, a.high, a.low, a.close, a.trades) == (
        b.open,
        b.high,
        b.low,
        b.close,
        b.trades,
    ) and math.isclose(a.volume, b.volume, rel_tol=1e-9, abs_tol=1e-9)


def check_hourly(
    fifteen_minute: Sequence[Candle], stored: Sequence[Candle], score_from: int
) -> HourlyCheck:
    """Compare the hourly candles built from the fifteen-minute candles with `stored`, from
    `score_from` on.

    Both series are whole development series; the turning points are found over
    all of them and compared from `score_from` on, like the candles. Raises
    `ValueError` when neither series has a candle from `score_from` on.
    """
    built = build_hourly(fifteen_minute, Timeframe.M15)
    built_period = {c.time: c for c in built if c.time >= score_from}
    stored_period = {c.time: c for c in stored if c.time >= score_from}
    both = sorted(built_period.keys() & stored_period.keys())
    times = sorted(built_period.keys() | stored_period.keys())
    if not times:
        raise ValueError(f"no hourly candle of either series falls from {score_from} on")
    built_points = {p for p in find_turning_points(built) if p.time >= score_from}
    stored_points = {p for p in find_turning_points(stored) if p.time >= score_from}
    return HourlyCheck(
        fifteen_minute=sum(c.time >= score_from for c in fifteen_minute),
        built=len(built_period),
        stored=len(stored_period),
        first=times[0],
        last=times[-1],
        only_built=sorted(built_period.keys() - stored_period.keys()),
        only_stored=sorted(stored_period.keys() - built_period.keys()),
        differing=[t for t in both if not same_candle(built_period[t], stored_period[t])],
        points_built=len(built_points),
        points_stored=len(stored_points),
        differing_points=sorted(built_points ^ stored_points, key=lambda p: p.time),
    )
