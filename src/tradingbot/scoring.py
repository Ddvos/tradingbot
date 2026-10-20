"""Scoring a detector's marks against the turning points found in hindsight.

A mark is a hit when a turning point of its kind lies within the tolerance:
at most `Tolerance.candles` hourly candles before or after the hour the mark
falls in, with the mark's close within `Tolerance.percent` of the turning
point's extreme price, or no further from it than the extreme hourly candle's
own close when that is further (tolerance B, ADR-0005). Each turning point
takes at most one hit, the nearest eligible mark in hourly candles (the
earlier one on a tie), and each mark can be the hit of at most one turning
point. Turning points are matched in time order, so when one mark lies inside
the tolerance of two turning points of its kind the earlier turning point
takes it. Every other mark is a false mark; every turning point without a hit
is a miss.

Distances are counted in hourly candles of the replayed series, not in hours,
so a missing hour does not widen or narrow the tolerance. A fifteen-minute
mark is placed at its own candle's close but counted by the hour it falls in;
its give-up is measured from that close.

The score covers the scoring period, from 2016 on, and is also given per era
(ADR-0005). A hit belongs to the era of its turning point, a false mark to the
era of its mark.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from tradingbot.candles import Candle, Timeframe, period_start
from tradingbot.detectors import Mark
from tradingbot.turning_points import Kind, TurningPoint


@dataclass(frozen=True)
class Tolerance:
    candles: int = 24
    """How many hourly candles before or after a turning point a mark may be."""
    percent: float = 2.0
    """How far the mark's close may be from the turning point's extreme price, unless
    the extreme candle's own close is further still."""


TOLERANCE = Tolerance()
"""Fixed in slice 2 (#11): 24 candles and 2%; widened to the extreme candle's own
close by ADR-0005 (slice 5, #19)."""


@dataclass(frozen=True)
class Era:
    """A fixed block of years within the scoring period, `start` inclusive, `end` exclusive."""

    name: str
    start: int
    end: int

    def holds(self, time: int) -> bool:
        return self.start <= time < self.end


SCORING_START = 1_451_606_400
"""2016-01-01T00:00:00Z: the scoring period runs from here to the out-of-sample
boundary (ADR-0005). Replays still start at the first stored candle."""

ERAS = (
    Era("2016-2018", SCORING_START, 1_546_300_800),
    Era("2019-2021", 1_546_300_800, 1_640_995_200),
    Era("2022-2024", 1_640_995_200, 1_735_689_600),
)
"""The eras of the scoring period (ADR-0005); the hit-rate bar must hold in every one."""


@dataclass(frozen=True, slots=True)
class Hit:
    mark: Mark
    turning_point: TurningPoint
    timing: int
    """Hourly candles between the turning point and the mark: negative is early, positive late."""
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
    """Median timing of the hits in hourly candles; None without hits."""
    median_give_up: float | None
    """Median give-up of the hits in percent; None without hits."""
    eras: tuple[EraScore, ...] = ()
    """The same numbers per era, in era order; empty when the score has no eras."""


@dataclass(frozen=True)
class EraScore:
    era: Era
    score: Score


def describe_timing(score: Score) -> tuple[str, str]:
    """The median timing and the median give-up as the commands print them."""
    if score.median_timing is None or score.median_give_up is None:
        return "n/a (no hits)", "n/a (no hits)"
    early_or_late = (
        "early" if score.median_timing < 0 else "late" if score.median_timing > 0 else "on time"
    )
    return f"{score.median_timing:+.1f} candles ({early_or_late})", f"{score.median_give_up:.2f}%"


def describe_score(score: Score) -> list[tuple[str, str]]:
    """The score as (label, value) pairs, in the order the commands print them: the
    period's numbers one per line, then one line per era."""
    timing, give_up_ = describe_timing(score)
    lines = [
        ("turning points", str(score.turning_points)),
        ("marks", str(score.marks)),
        ("hits", f"{score.hits}  (hit rate {score.hit_rate:.1%})"),
        ("false marks", f"{score.false_marks}  (false-mark rate {score.false_mark_rate:.1%})"),
        ("median timing", timing),
        ("median give-up", give_up_),
    ]
    for scored in score.eras:
        s = scored.score
        era_timing, era_give_up = describe_timing(s)
        lines.append(
            (
                scored.era.name,
                f"{s.turning_points} turning points, {s.marks} marks, {s.hits} hits "
                f"(hit rate {s.hit_rate:.1%}), {s.false_marks} false marks "
                f"(false-mark rate {s.false_mark_rate:.1%}), median timing {era_timing}, "
                f"median give-up {era_give_up}",
            )
        )
    return lines


def give_up(mark: Mark, point: TurningPoint) -> float:
    """Percent from the extreme to the close, positive below a top or above a bottom."""
    away = point.price - mark.price if point.kind is Kind.TOP else mark.price - point.price
    return away / point.price * 100


def allowed_distance(point: TurningPoint, extreme_candle: Candle, tolerance: Tolerance) -> float:
    """How far in price a mark's close may lie from the extreme: `tolerance.percent` of
    it, or the extreme candle's own close when that is further (tolerance B)."""
    return max(point.price * tolerance.percent / 100, abs(extreme_candle.close - point.price))


def match_marks(
    candles: Sequence[Candle],
    marks: Sequence[Mark],
    points: Sequence[TurningPoint],
    tolerance: Tolerance = TOLERANCE,
) -> Outcome:
    """Pair every turning point with its nearest mark inside the tolerance.

    `candles` are the hourly candles the turning points were found on; a mark
    of any timeframe is counted by the hour it falls in.
    """
    index = {candle.time: i for i, candle in enumerate(candles)}
    ordered = sorted(marks, key=lambda m: m.time)
    mark_indexes = [index[period_start(m.time, Timeframe.H1)] for m in ordered]
    taken: set[int] = set()
    hits: list[Hit] = []
    misses: list[TurningPoint] = []
    for point in points:
        point_index = index[point.time]
        allowed = allowed_distance(point, candles[point_index], tolerance)
        first = bisect_left(mark_indexes, point_index - tolerance.candles)
        last = bisect_right(mark_indexes, point_index + tolerance.candles)
        nearest: int | None = None
        for i in range(first, last):
            mark = ordered[i]
            if i in taken or mark.kind is not point.kind:
                continue
            if abs(mark.price - point.price) > allowed:
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


def within(outcome: Outcome, era: Era) -> Outcome:
    """The part of the outcome that falls in the era: hits by their turning point,
    false marks by their mark, misses by their turning point."""
    return Outcome(
        [hit for hit in outcome.hits if era.holds(hit.turning_point.time)],
        [mark for mark in outcome.false_marks if era.holds(mark.time)],
        [point for point in outcome.misses if era.holds(point.time)],
    )


def score(outcome: Outcome, eras: Sequence[Era] = ()) -> Score:
    """The outcome summed up, and the same per era when eras are given."""
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
        eras=tuple(EraScore(era, score(within(outcome, era))) for era in eras),
    )
