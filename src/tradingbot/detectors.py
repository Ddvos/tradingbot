"""Detectors and their marks.

A detector is a set of explicit, readable rules that, at the close of each
candle, decide whether to place a mark: a claim that the latest candle is at a
top or a bottom. A mark is placed only on the latest candle, at its close,
never on an earlier one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from tradingbot.candles import Candle
from tradingbot.turning_points import Kind, TurningPoint, fall, rise


@dataclass(frozen=True, slots=True)
class Mark:
    kind: Kind
    time: int
    """Start time of the candle the mark was placed on: the latest candle then."""
    price: float
    """That candle's close."""


class Detector(Protocol):
    """What replay asks of a detector at the close of every candle.

    `candles` are the candles so far, oldest first, the latest one last;
    `levels` are the turning points confirmed so far. Replay never hands a
    detector a later candle or a later turning point. The answer is the kind of
    mark to place on the latest candle, or None for no mark.
    """

    name: str

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None: ...


FLOOR_DISTANCE = 0.03
"""The floor's only parameter, fixed in slice 2 (#11): a close 3% past the extreme."""


class FloorDetector:
    """The reference every detector must beat; never a candidate itself.

    Marks a top on the first candle that closes 3% below the highest high since
    the last bottom mark, and a bottom on the first candle that closes 3% above
    the lowest low since the last top mark. Before the first mark both extremes
    are tracked from the first candle on. Levels are ignored.
    """

    name = "floor"

    def __init__(self, distance: float = FLOOR_DISTANCE) -> None:
        self._distance = distance
        self._highest: Candle | None = None
        self._lowest: Candle | None = None
        self._last: Kind | None = None

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        latest = candles[-1]
        if self._highest is None or self._lowest is None:
            self._highest = self._lowest = latest
        if self._last is not Kind.TOP and latest.high > self._highest.high:
            self._highest = latest
        if self._last is not Kind.BOTTOM and latest.low < self._lowest.low:
            self._lowest = latest

        top_due = (
            self._last is not Kind.TOP and fall(self._highest.high, latest.close) >= self._distance
        )
        bottom_due = (
            self._last is not Kind.BOTTOM and rise(self._lowest.low, latest.close) >= self._distance
        )
        if top_due and (not bottom_due or self._highest.time <= self._lowest.time):
            self._last = Kind.TOP
            self._lowest = latest
            return Kind.TOP
        if bottom_due:
            self._last = Kind.BOTTOM
            self._highest = latest
            return Kind.BOTTOM
        return None


DETECTORS: dict[str, Callable[[], Detector]] = {FloorDetector.name: FloorDetector}
"""Every detector by name; each entry builds a fresh, stateless-at-start instance."""
