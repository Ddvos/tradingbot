"""Detectors and their marks.

A detector is a set of explicit, readable rules that, at the close of each
candle, decide whether to place a mark: a claim that the latest candle is at a
top or a bottom. A mark is placed only on the latest candle, at its close,
never on an earlier one.
"""

from __future__ import annotations

from bisect import bisect_left, insort
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


ZONE = 0.01
"""Detector one's zone, fixed in slice 3 (#12): within 1% of a level."""


def in_zone(price: float, levels: Sequence[float]) -> bool:
    """Whether `price` lies in the zone of any level: within `ZONE` of it, as a
    fraction of that level.

    `levels` must be sorted ascending. Only the nearest level below and the
    nearest level above the price can put it in a zone, so those two are
    checked and the rest is skipped.
    """
    i = bisect_left(levels, price)
    nearest = levels[max(i - 1, 0) : i + 1]
    return any(abs(price - level) / level <= ZONE for level in nearest)


def run_of_higher_highs(candles: Sequence[Candle], ending_at: int) -> int:
    """The length of the run of higher highs ending at `candles[ending_at]`.

    A higher high is a candle whose high is above the previous candle's high.
    The run is counted backwards from `candles[ending_at]` and stops at the
    first candle that is not a higher high; the first candle of the series
    never is, having nothing to beat.
    """
    count = 0
    while ending_at - count > 0 and (
        candles[ending_at - count].high > candles[ending_at - count - 1].high
    ):
        count += 1
    return count


def run_of_lower_lows(candles: Sequence[Candle], ending_at: int) -> int:
    """The length of the run of lower lows ending at `candles[ending_at]`: the mirror image."""
    count = 0
    while ending_at - count > 0 and (
        candles[ending_at - count].low < candles[ending_at - count - 1].low
    ):
        count += 1
    return count


RUN_LENGTH = 3
"""Detector one's run, fixed in slice 3 (#12): at least 3 consecutive higher
highs (or lower lows) ending at the previous candle."""


class DetectorOne:
    """Detector one: levels plus the first failed higher high or lower low (#12).

    The levels are the prices of every turning point confirmed so far, each
    usable for tops and for bottoms, never expiring. A top is marked on a candle
    whose high is in the zone of a level, whose previous candle ends a run of at
    least three higher highs, and whose own high stays below the previous
    candle's: the first failed higher high. A bottom is the mirror image on the
    lows. No mark outside a zone, and nothing but price goes in (ADR-0003).
    """

    name = "one"

    def __init__(self) -> None:
        self._prices: list[float] = []
        """The levels' prices, sorted ascending, grown as turning points are confirmed."""

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        while len(self._prices) < len(levels):
            insort(self._prices, levels[len(self._prices)].price)
        if len(candles) < 2:
            return None
        latest, previous = candles[-1], candles[-2]
        previous_index = len(candles) - 2
        failed_higher_high = latest.high < previous.high and in_zone(latest.high, self._prices)
        failed_lower_low = latest.low > previous.low and in_zone(latest.low, self._prices)
        top_run = run_of_higher_highs(candles, previous_index) if failed_higher_high else 0
        bottom_run = run_of_lower_lows(candles, previous_index) if failed_lower_low else 0
        top_due = top_run >= RUN_LENGTH
        bottom_due = bottom_run >= RUN_LENGTH
        # Both at once is an inside candle after expanding ranges: the longer run
        # wins, and equal runs cancel out, since a candle gets at most one mark.
        if top_due and (not bottom_due or top_run > bottom_run):
            return Kind.TOP
        if bottom_due and (not top_due or bottom_run > top_run):
            return Kind.BOTTOM
        return None


DETECTORS: dict[str, Callable[[], Detector]] = {
    FloorDetector.name: FloorDetector,
    DetectorOne.name: DetectorOne,
}
"""Every detector by name; each entry builds a fresh, stateless-at-start instance."""
