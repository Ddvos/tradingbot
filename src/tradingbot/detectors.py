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


@dataclass(frozen=True, slots=True)
class Level:
    """A level as a detector reads it, with the span of candles that see it.

    A level is the price of a turning point. The candle that confirms the
    turning point is the first to see it; a detector whose levels expire names
    the last one. The dashboard draws exactly this span, so the chart shows what
    the detector read.
    """

    kind: Kind
    price: float
    time: int
    """Start time of the turning point's candle."""
    active_from: int
    """Start time of the candle that confirms the turning point."""
    active_until: int | None
    """Start time of the last candle that sees the level; None when it never expires."""


def level_of(point: TurningPoint, lifetime: int | None) -> Level:
    """The level of `point`, seen until `lifetime` seconds after its candle, or forever."""
    until = None if lifetime is None else point.time + lifetime
    return Level(point.kind, point.price, point.time, point.confirmed_at, until)


class Detector(Protocol):
    """What replay asks of a detector.

    At the close of every candle, `mark`: `candles` are the candles so far,
    oldest first, the latest one last; `levels` are the turning points confirmed
    so far. Replay never hands a detector a later candle or a later turning
    point. The answer is the kind of mark to place on the latest candle, or
    None for no mark.

    Once, at the end, `levels`: the levels the detector reads from the turning
    points, each with the span of candles that see it, so the result can show
    them. Empty for a detector that reads no levels.
    """

    name: str

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None: ...

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]: ...


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

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]:
        return []


ZONE = 0.01
"""Detector one's zone, fixed in slice 3 (#12): within 1% of a level."""


def within_zone(price: float, level: float) -> bool:
    """Whether `price` lies in the zone of `level`: within `ZONE` of it, as a
    fraction of the level."""
    return abs(price - level) / level <= ZONE


def in_zone(price: float, levels: Sequence[float]) -> bool:
    """Whether `price` lies in the zone of any level.

    `levels` must be sorted ascending. Only the nearest level below and the
    nearest level above the price can put it in a zone, so those two are
    checked and the rest is skipped.
    """
    i = bisect_left(levels, price)
    nearest = levels[max(i - 1, 0) : i + 1]
    return any(within_zone(price, level) for level in nearest)


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


def failed_run_mark(candles: Sequence[Candle], in_a_zone: Callable[[float], bool]) -> Kind | None:
    """Detector one's rule (#12), given the zone test: the mark for the latest candle.

    A top on a candle whose high is in a zone, whose previous candle ends a run
    of at least `RUN_LENGTH` higher highs, and whose own high stays below the
    previous candle's: the first failed higher high. A bottom is the mirror
    image on the lows. No mark outside a zone. When one candle fails both runs
    (an inside candle after expanding ranges) the longer run wins and equal
    runs give no mark, since a candle gets at most one mark. Nothing but price
    goes in (ADR-0003).
    """
    if len(candles) < 2:
        return None
    latest, previous = candles[-1], candles[-2]
    previous_index = len(candles) - 2
    failed_higher_high = latest.high < previous.high and in_a_zone(latest.high)
    failed_lower_low = latest.low > previous.low and in_a_zone(latest.low)
    top_run = run_of_higher_highs(candles, previous_index) if failed_higher_high else 0
    bottom_run = run_of_lower_lows(candles, previous_index) if failed_lower_low else 0
    top_due = top_run >= RUN_LENGTH
    bottom_due = bottom_run >= RUN_LENGTH
    if top_due and (not bottom_due or top_run > bottom_run):
        return Kind.TOP
    if bottom_due and (not top_due or bottom_run > top_run):
        return Kind.BOTTOM
    return None


class DetectorOne:
    """Detector one: levels plus the first failed higher high or lower low (#12).

    The levels are the prices of every turning point confirmed so far, each
    usable for tops and for bottoms, never expiring. The rule is
    `failed_run_mark` with those levels' zones.
    """

    name = "one"

    def __init__(self) -> None:
        self._prices: list[float] = []
        """The levels' prices, sorted ascending, grown as turning points are confirmed."""

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        while len(self._prices) < len(levels):
            insort(self._prices, levels[len(self._prices)].price)
        return failed_run_mark(candles, lambda price: in_zone(price, self._prices))

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]:
        return [level_of(point, None) for point in points]


LEVEL_LIFETIME = 30 * 24 * 3600
"""Detector two's level lifetime, fixed in slice 4 (#16): a level is seen until
30 days of calendar time after the start of its turning point's candle,
inclusive. Calendar time, not candles, so a missing hour neither shortens nor
stretches it; counted from the extreme, not from its confirmation."""


class DetectorTwo:
    """Detector two: detector one's rule with levels that expire (#16).

    A level is seen from the candle that confirms its turning point until
    `LEVEL_LIFETIME` after the start of the turning point's own candle. Nothing
    renews or consumes a level: a mark in its zone does not use it up, price
    revisiting it does not extend it, and a new turning point near it is a new
    level with its own lifetime. Everything else is detector one.
    """

    name = "two"

    def __init__(self) -> None:
        self._first_active = 0
        """Index of the oldest level that may still be seen. Turning points are
        confirmed in time order, so once one has expired, all before it have too."""

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        now = candles[-1].time
        while (
            self._first_active < len(levels)
            and levels[self._first_active].time + LEVEL_LIFETIME < now
        ):
            self._first_active += 1
        active = [point.price for point in levels[self._first_active :]]
        return failed_run_mark(
            candles, lambda price: any(within_zone(price, level) for level in active)
        )

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]:
        return [level_of(point, LEVEL_LIFETIME) for point in points]


DETECTORS: dict[str, Callable[[], Detector]] = {
    FloorDetector.name: FloorDetector,
    DetectorOne.name: DetectorOne,
    DetectorTwo.name: DetectorTwo,
}
"""Every detector by name; each entry builds a fresh, stateless-at-start instance."""
