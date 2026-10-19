"""Candles and timeframes.

A candle is the open, high, low, close, volume and number of trades of one
timeframe's period. Times are Unix seconds, UTC, at the start of the period.
Hourly candles are the stored truth; 4-hour and daily candles are built from
them by `resample`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class Timeframe(Enum):
    """The period one candle covers."""

    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def seconds(self) -> int:
        return {"1h": 3600, "4h": 4 * 3600, "1d": 24 * 3600}[self.value]


@dataclass(frozen=True, slots=True)
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int


def resample(hourly: Iterable[Candle], timeframe: Timeframe) -> list[Candle]:
    """Build candles of `timeframe` from hourly ones.

    Periods are UTC-aligned: a 4-hour candle starts at 00:00, 04:00, ... UTC
    and a daily candle at 00:00 UTC. Hours without a candle are simply absent
    from their period; a period with no hourly candles at all is not emitted.
    """
    size = timeframe.seconds
    result: list[Candle] = []
    current: Candle | None = None
    for candle in sorted(hourly, key=lambda c: c.time):
        start = candle.time - candle.time % size
        if current is None or current.time != start:
            if current is not None:
                result.append(current)
            current = Candle(
                start,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.trades,
            )
        else:
            current = Candle(
                start,
                current.open,
                max(current.high, candle.high),
                min(current.low, candle.low),
                candle.close,
                current.volume + candle.volume,
                current.trades + candle.trades,
            )
    if current is not None:
        result.append(current)
    return result
