"""Detectors and their marks.

A detector is a set of explicit, readable rules that, at the close of each
candle, decide whether to place a mark: a claim that the latest candle is at a
top or a bottom. A mark is placed only on the latest candle, at its close,
never on an earlier one.
"""

from __future__ import annotations

from bisect import bisect_left, insort
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from tradingbot.candles import Candle, Timeframe
from tradingbot.turning_points import REVERSAL_SIZE, Kind, TurningPoint, fall, rise


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


@dataclass(frozen=True, slots=True)
class SwingExtreme:
    """A swing extreme as detector three read it, with the span of candles that read it.

    The dashboard draws exactly this span, so the chart shows what the detector
    read: the price its next mark is measured against, from the candle it first
    read it on until the candle before a new extreme replaced it.
    """

    kind: Kind
    """TOP for the extreme of an up-swing, a possible top; BOTTOM for a down-swing's."""
    price: float
    time: int
    """Start time of the fifteen-minute candle holding the extreme."""
    active_from: int
    """Start time of the first candle the detector read it on: the extreme's own candle,
    or the candle on which a newly confirmed turning point made it recompute the swing."""
    active_until: int | None
    """Start time of the last candle that read it; None when it still stands at the end."""


class Detector(Protocol):
    """What replay asks of a detector.

    At the close of every candle of its `timeframe`, `mark`: `candles` are the
    candles so far, oldest first, the latest one last; `levels` are the turning
    points confirmed so far, always found on hourly candles. Replay never hands
    a detector a later candle or a later turning point. The answer is the kind
    of mark to place on the latest candle, or None for no mark.

    Once, at the end, `levels`: the levels the detector reads from the turning
    points, each with the span of candles that see it, so the result can show
    them. Empty for a detector that reads no levels. Likewise `swing_extremes`:
    every swing extreme the detector read during the replay, each with the
    span of candles that read it; empty for a detector that tracks no swing.
    """

    name: str
    timeframe: Timeframe
    """The candles the detector reads: fifteen-minute or hourly."""

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None: ...

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]: ...

    def swing_extremes(self) -> list[SwingExtreme]: ...


FLOOR_DISTANCE = 0.03
"""The floor's only parameter, fixed in slice 2 (#11): a close 3% past the extreme."""


class FloorDetector:
    """The reference detector of the hourly harness, kept for comparison; never a
    candidate itself, and since ADR-0005 it sets no bar.

    Marks a top on the first candle that closes 3% below the highest high since
    the last bottom mark, and a bottom on the first candle that closes 3% above
    the lowest low since the last top mark. Before the first mark both extremes
    are tracked from the first candle on. Levels are ignored.
    """

    name = "floor"
    timeframe = Timeframe.H1

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

    def swing_extremes(self) -> list[SwingExtreme]:
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
    timeframe = Timeframe.H1

    def __init__(self) -> None:
        self._prices: list[float] = []
        """The levels' prices, sorted ascending, grown as turning points are confirmed."""

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        while len(self._prices) < len(levels):
            insort(self._prices, levels[len(self._prices)].price)
        return failed_run_mark(candles, lambda price: in_zone(price, self._prices))

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]:
        return [level_of(point, None) for point in points]

    def swing_extremes(self) -> list[SwingExtreme]:
        return []


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
    timeframe = Timeframe.H1

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

    def swing_extremes(self) -> list[SwingExtreme]:
        return []


class Swing:
    """One side of detector three: the up-swing whose end would be a top, or its mirror.

    On the top side the swing starts at the swing low, the lowest fifteen-minute
    low at or after the start of the hour holding the last confirmed top, and
    its extreme is the highest high since that low, the low's candle included.
    The bottom side mirrors every comparison: it starts at the swing high since
    the last confirmed bottom's hour and its extreme is the lowest low since.
    """

    def __init__(self, kind: Kind) -> None:
        self.kind = kind
        self.start: float | None = None
        """The swing low (top side) or swing high (bottom side); None until a turning
        point of this side's kind has been confirmed."""
        self.extreme: Candle | None = None
        """The candle holding the swing extreme."""
        self.armed = False
        """Whether the next candle short of the extreme gets a mark."""
        self.extremes: list[SwingExtreme] = []
        """Every extreme read so far with its span; the last one is still standing."""
        self._latest: int | None = None
        """Start time of the latest candle this side has been read on."""

    def _start_of(self, candle: Candle) -> float:
        return candle.low if self.kind is Kind.TOP else candle.high

    def _extreme_of(self, candle: Candle) -> float:
        return candle.high if self.kind is Kind.TOP else candle.low

    def _extends(self, price: float, beyond: float) -> bool:
        """Whether `price` lies further along the swing than `beyond`: above it on the
        top side, below it on the bottom side."""
        return price > beyond if self.kind is Kind.TOP else price < beyond

    def reset(self, candles: Sequence[Candle], since: int) -> None:
        """Recompute the swing from the candles at or after `since`, the start of the hour
        holding a newly confirmed turning point of this side's kind, and arm.

        Equal lows (or highs) keep the earlier candle, as the candle-by-candle
        update does, since only a strictly lower low moves the swing low.
        """
        first = bisect_left(candles, since, key=lambda c: c.time)
        start = first
        for i in range(first, len(candles)):
            if self._extends(self._start_of(candles[start]), self._start_of(candles[i])):
                start = i
        extreme = candles[start]
        for candle in candles[start:]:
            if self._extends(self._extreme_of(candle), self._extreme_of(extreme)):
                extreme = candle
        self.start = self._start_of(candles[start])
        self._stand(extreme, read_from=candles[-1].time)
        self.armed = True

    def update(self, candle: Candle) -> None:
        """Extend the swing by the latest candle: a new swing low restarts the extreme at
        this candle and arms; a new extreme arms."""
        if self.start is None or self.extreme is None:
            return
        if self._extends(self.start, self._start_of(candle)):
            self.start = self._start_of(candle)
            self._stand(candle, read_from=candle.time)
            self.armed = True
        elif self._extends(self._extreme_of(candle), self._extreme_of(self.extreme)):
            self._stand(candle, read_from=candle.time)
            self.armed = True

    def _stand(self, candle: Candle, read_from: int) -> None:
        """Make `candle` hold the extreme, read from `read_from` on. The extreme standing
        until now was last read on the previous candle; a recompute that lands on the
        candle already holding it changes nothing."""
        if self.extreme is not None and self.extreme.time == candle.time:
            return
        if self.extremes:
            self.extremes[-1] = replace(self.extremes[-1], active_until=self._latest)
        self.extreme = candle
        self.extremes.append(
            SwingExtreme(self.kind, self._extreme_of(candle), candle.time, read_from, None)
        )

    def read_on(self, time: int) -> None:
        """Note that the side has been read on the candle starting at `time`."""
        self._latest = time

    def reached(self) -> bool:
        """Whether the swing has reached the reversal size: `extreme >= swing low x 1.08`
        on the top side, `extreme <= swing high x 0.92` on the bottom side."""
        if self.start is None or self.extreme is None:
            return False
        extreme = self._extreme_of(self.extreme)
        if self.kind is Kind.TOP:
            return extreme >= self.start * (1 + REVERSAL_SIZE)
        return extreme <= self.start * (1 - REVERSAL_SIZE)

    def size(self) -> float:
        """The swing as a fraction of its start, for the tie rule; 0 before it exists."""
        if self.start is None or self.extreme is None:
            return 0.0
        extreme = self._extreme_of(self.extreme)
        return rise(self.start, extreme) if self.kind is Kind.TOP else fall(self.start, extreme)

    def due(self, candle: Candle) -> bool:
        """Whether this side marks `candle`: armed, the candle short of the extreme, and
        the swing at least the reversal size."""
        if self.extreme is None or not self.armed:
            return False
        short = self._extends(self._extreme_of(self.extreme), self._extreme_of(candle))
        return short and self.reached()


class DetectorThree:
    """Detector three: the swing rule on fifteen-minute candles (#20), the first
    iteration of family two.

    It reads the fifteen-minute candles so far and the hourly turning points
    confirmed so far, nothing else (ADR-0003); its only number is the reversal
    size. A top mark goes on the first candle whose high stays below the swing
    extreme once the up-swing, from the swing low to that extreme, is at least
    the reversal size; a new extreme, a new swing low or a newly confirmed top
    arms the next mark, and a mark disarms its side until then. Bottoms are the
    mirror image. When one candle qualifies for both, the side whose swing is
    larger in percent wins and equal swings give no mark; the other side keeps
    its arming. At most one mark per candle.
    """

    name = "three"
    timeframe = Timeframe.M15

    def __init__(self) -> None:
        self._up = Swing(Kind.TOP)
        self._down = Swing(Kind.BOTTOM)
        self._known = 0
        """How many of the turning points handed over have been read."""

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        latest = candles[-1]
        for point in levels[self._known :]:
            side = self._up if point.kind is Kind.TOP else self._down
            side.reset(candles, point.time)
        self._known = len(levels)
        self._up.update(latest)
        self._down.update(latest)
        top_due, bottom_due = self._up.due(latest), self._down.due(latest)
        kind: Kind | None = None
        if top_due and (not bottom_due or self._up.size() > self._down.size()):
            self._up.armed = False
            kind = Kind.TOP
        elif bottom_due and (not top_due or self._down.size() > self._up.size()):
            self._down.armed = False
            kind = Kind.BOTTOM
        self._up.read_on(latest.time)
        self._down.read_on(latest.time)
        return kind

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]:
        return []

    def swing_extremes(self) -> list[SwingExtreme]:
        """Every extreme either side read, in the order the detector started reading them."""
        return sorted(self._up.extremes + self._down.extremes, key=lambda e: e.active_from)


DETECTORS: dict[str, Callable[[], Detector]] = {
    FloorDetector.name: FloorDetector,
    DetectorOne.name: DetectorOne,
    DetectorTwo.name: DetectorTwo,
    DetectorThree.name: DetectorThree,
}
"""Every detector by name; each entry builds a fresh, stateless-at-start instance."""
