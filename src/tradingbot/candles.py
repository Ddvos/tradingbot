"""Candles and timeframes.

A candle is the open, high, low, close, volume and number of trades of one
timeframe's period. Times are Unix seconds, UTC, at the start of the period.
Fifteen-minute and hourly candles are stored; 4-hour and daily candles are
built from the hourly ones by `resample`, which also builds hourly candles
from fifteen-minute ones.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum


def iso(seconds: int) -> str:
    """A candle time as an ISO 8601 date-time in UTC, like 2024-10-19T00:00:00Z."""
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Timeframe(Enum):
    """The period one candle covers."""

    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def seconds(self) -> int:
        return {"15m": 900, "1h": 3600, "4h": 4 * 3600, "1d": 24 * 3600}[self.value]

    @property
    def label(self) -> str:
        """The timeframe as an adjective, for messages: "15-minute", "hourly", ..."""
        return {"15m": "15-minute", "1h": "hourly", "4h": "4-hour", "1d": "daily"}[self.value]


@dataclass(frozen=True, slots=True)
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int


def period_start(time: int, timeframe: Timeframe) -> int:
    """Start time of the `timeframe` period that holds `time`; periods are UTC-aligned."""
    return time - time % timeframe.seconds


def merge(current: Candle | None, candle: Candle, start: int) -> Candle:
    """The candle of the period starting at `start` so far, `current`, extended by `candle`;
    started by it when there is no candle of the period yet."""
    if current is None:
        return Candle(
            start, candle.open, candle.high, candle.low, candle.close, candle.volume, candle.trades
        )
    return Candle(
        start,
        current.open,
        max(current.high, candle.high),
        min(current.low, candle.low),
        candle.close,
        current.volume + candle.volume,
        current.trades + candle.trades,
    )


def resample(candles: Iterable[Candle], timeframe: Timeframe) -> list[Candle]:
    """Build candles of `timeframe` from candles of a shorter one.

    Periods are UTC-aligned: an hourly candle starts on the hour, a 4-hour
    candle at 00:00, 04:00, ... UTC and a daily candle at 00:00 UTC. Shorter
    periods without a candle are simply absent from their period; a period
    with no candles at all is not emitted.
    """
    result: list[Candle] = []
    current: Candle | None = None
    for candle in sorted(candles, key=lambda c: c.time):
        start = period_start(candle.time, timeframe)
        if current is not None and current.time != start:
            result.append(current)
            current = None
        current = merge(current, candle, start)
    if current is not None:
        result.append(current)
    return result
