"""Turning points: the tops and bottoms of the hourly history, found in hindsight.

A top is the highest high before a fall of at least the reversal size, measured
from that high to a later candle's low; a bottom is the lowest low before a rise
of at least the reversal size, measured to a later candle's high. Tops and
bottoms alternate, so every two neighbouring turning points differ by at least
the reversal size. A candle never confirms its own extreme.

The finder is incremental: it is given one candle at a time and answers the
turning points that candle confirms. Replay uses that, so at every step the
detector only sees the turning points confirmed by then. `find_turning_points`
is the same finder run over a whole series.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from tradingbot.candles import Candle

REVERSAL_SIZE = 0.08
"""The move against the prevailing direction that, in hindsight, makes the
preceding extreme a turning point: 8%, fixed in slice 2 (#11)."""


class Kind(Enum):
    """Whether a turning point or a mark is a top or a bottom."""

    TOP = "top"
    BOTTOM = "bottom"


@dataclass(frozen=True, slots=True)
class TurningPoint:
    kind: Kind
    time: int
    """Start time of the hourly candle holding the extreme."""
    price: float
    """The extreme: the candle's high for a top, its low for a bottom."""
    confirmed_at: int
    """Start time of the later candle whose low (top) or high (bottom) completed
    the reversal. From that candle on, the turning point is a known level."""


def fall(from_price: float, to_price: float) -> float:
    """The fall from `from_price` to `to_price` as a fraction of `from_price`."""
    return (from_price - to_price) / from_price


def rise(from_price: float, to_price: float) -> float:
    """The rise from `from_price` to `to_price` as a fraction of `from_price`."""
    return (to_price - from_price) / from_price


class TurningPointFinder:
    """Finds turning points one candle at a time, in time order."""

    def __init__(self, reversal: float = REVERSAL_SIZE) -> None:
        self._reversal = reversal
        self._highest: Candle | None = None
        """The candidate top: the highest high since the last bottom."""
        self._lowest: Candle | None = None
        """The candidate bottom: the lowest low since the last top."""
        self._last: Kind | None = None
        """The kind of the last turning point found; None until the first."""

    @property
    def pending_from(self) -> int | None:
        """Start time of the earliest candle that can still become a turning point.

        Every candle before it is settled: it either holds a confirmed turning
        point or never will. None before the first candle.
        """
        if self._highest is None or self._lowest is None:
            return None
        if self._last is Kind.TOP:
            return self._lowest.time
        if self._last is Kind.BOTTOM:
            return self._highest.time
        return min(self._highest.time, self._lowest.time)

    def push(self, candle: Candle) -> list[TurningPoint]:
        """Take the next candle and answer the turning points it confirms, oldest first.

        Before the first turning point both candidates are tracked, because the
        direction is unknown. One candle can confirm two turning points then:
        an extreme and the opposite extreme that followed it.
        """
        if self._highest is None or self._lowest is None:
            self._highest = self._lowest = candle
        if self._last is not Kind.TOP and candle.high > self._highest.high:
            self._highest = candle
        if self._last is not Kind.BOTTOM and candle.low < self._lowest.low:
            self._lowest = candle

        confirmed: list[TurningPoint] = []
        while True:
            highest, lowest = self._highest, self._lowest
            top_due = (
                self._last is not Kind.TOP
                and candle.time != highest.time
                and fall(highest.high, candle.low) >= self._reversal
            )
            bottom_due = (
                self._last is not Kind.BOTTOM
                and candle.time != lowest.time
                and rise(lowest.low, candle.high) >= self._reversal
            )
            if top_due and (not bottom_due or highest.time <= lowest.time):
                confirmed.append(TurningPoint(Kind.TOP, highest.time, highest.high, candle.time))
                self._last = Kind.TOP
                # The next bottom lies after this top: keep the candidate if it does,
                # else the confirming candle is the lowest low since the top.
                if lowest.time <= highest.time:
                    self._lowest = candle
            elif bottom_due:
                confirmed.append(TurningPoint(Kind.BOTTOM, lowest.time, lowest.low, candle.time))
                self._last = Kind.BOTTOM
                if highest.time <= lowest.time:
                    self._highest = candle
            else:
                return confirmed


def find_turning_points(
    candles: Iterable[Candle], reversal: float = REVERSAL_SIZE
) -> list[TurningPoint]:
    """All turning points of `candles` (in time order), oldest first."""
    finder = TurningPointFinder(reversal)
    points: list[TurningPoint] = []
    for candle in candles:
        points.extend(finder.push(candle))
    return points
