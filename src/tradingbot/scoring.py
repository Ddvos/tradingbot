"""Scoring a detector's marks against the turning points found in hindsight.

A mark is a hit when a turning point of its kind lies within the tolerance:
at most `Tolerance.candles` candles before or after it, with the mark's close
within `Tolerance.percent` of the turning point's extreme price. Each turning
point takes at most one hit, the nearest eligible mark in candles (the earlier
one on a tie), and each mark can be the hit of at most one turning point.
Turning points are matched in time order, so when one mark lies inside the
tolerance of two turning points of its kind the earlier turning point takes
it. Every other mark is a false mark; every turning point without a hit is a
miss.

Distances are counted in candles of the replayed series, not in hours, so a
missing hour does not widen or narrow the tolerance.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from tradingbot.candles import Candle
from tradingbot.detectors import Mark
from tradingbot.turning_points import Kind, TurningPoint


@dataclass(frozen=True)
class Tolerance:
    candles: int = 24
    """How many candles before or after a turning point a mark may be."""
    percent: float = 2.0
    """How far the mark's close may be from the turning point's extreme price."""


TOLERANCE = Tolerance()
"""Fixed in slice 2 (#11): 24 candles and 2%."""


@dataclass(frozen=True, slots=True)
class Hit:
    mark: Mark
    turning_point: TurningPoint
    timing: int
    """Candles between the turning point and the mark: negative is early, positive late."""
    give_up: float
    """Percent between the turning point's extreme price and the mark's close,
    positive when the close is below a top or above a bottom."""


@dataclass(frozen=True)
class Outcome:
    hits: list[Hit]
    false_marks: list[Mark]
    misses: list[TurningPoint]


@dataclass(frozen=True)
class Score:
    turning_points: int
    marks: int
    hits: int
    false_marks: int
    hit_rate: float
    """Hits divided by turning points; 0 without turning points."""
    false_mark_rate: float
    """False marks divided by marks; 0 without marks."""
    median_timing: float | None
    """Median timing of the hits in candles; None without hits."""
    median_give_up: float | None
    """Median give-up of the hits in percent; None without hits."""


def give_up(mark: Mark, point: TurningPoint) -> float:
    """Percent from the extreme to the close, positive below a top or above a bottom."""
    away = point.price - mark.price if point.kind is Kind.TOP else mark.price - point.price
    return away / point.price * 100


def match_marks(
    candles: Sequence[Candle],
    marks: Sequence[Mark],
    points: Sequence[TurningPoint],
    tolerance: Tolerance = TOLERANCE,
) -> Outcome:
    """Pair every turning point with its nearest mark inside the tolerance."""
    index = {candle.time: i for i, candle in enumerate(candles)}
    ordered = sorted(marks, key=lambda m: m.time)
    mark_indexes = [index[m.time] for m in ordered]
    taken: set[int] = set()
    hits: list[Hit] = []
    misses: list[TurningPoint] = []
    for point in points:
        point_index = index[point.time]
        first = bisect_left(mark_indexes, point_index - tolerance.candles)
        last = bisect_right(mark_indexes, point_index + tolerance.candles)
        nearest: int | None = None
        for i in range(first, last):
            mark = ordered[i]
            if i in taken or mark.kind is not point.kind:
                continue
            if abs(mark.price - point.price) / point.price > tolerance.percent / 100:
                continue
            if nearest is None or abs(mark_indexes[i] - point_index) < abs(
                mark_indexes[nearest] - point_index
            ):
                nearest = i
        if nearest is None:
            misses.append(point)
            continue
        taken.add(nearest)
        mark = ordered[nearest]
        hits.append(Hit(mark, point, mark_indexes[nearest] - point_index, give_up(mark, point)))
    false_marks = [mark for i, mark in enumerate(ordered) if i not in taken]
    return Outcome(hits, false_marks, misses)


def score(outcome: Outcome) -> Score:
    points = len(outcome.hits) + len(outcome.misses)
    marks = len(outcome.hits) + len(outcome.false_marks)
    hits = outcome.hits
    return Score(
        turning_points=points,
        marks=marks,
        hits=len(hits),
        false_marks=len(outcome.false_marks),
        hit_rate=len(hits) / points if points else 0.0,
        false_mark_rate=len(outcome.false_marks) / marks if marks else 0.0,
        median_timing=median(hit.timing for hit in hits) if hits else None,
        median_give_up=median(hit.give_up for hit in hits) if hits else None,
    )
