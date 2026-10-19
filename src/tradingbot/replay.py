"""Replay: stored candles go to a detector one at a time, in time order.

At every step the detector is handed the candles so far and the turning points
confirmed so far, and nothing later, so no future candle can leak into a mark.
The dashboard replay and the batch command both go through `run`, so they
place the same marks and read the same score.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from tradingbot.candles import Candle
from tradingbot.detectors import Detector, Mark
from tradingbot.scoring import TOLERANCE, Score, Tolerance, match_marks, score
from tradingbot.turning_points import Kind, TurningPoint, TurningPointFinder


@dataclass(frozen=True)
class Step:
    candle: Candle
    mark: Mark | None
    """The mark the detector placed on this candle, if any."""
    confirmed: tuple[TurningPoint, ...]
    """The turning points this candle confirmed: new levels from now on."""


def replay(candles: Iterable[Candle], detector: Detector) -> Iterator[Step]:
    """One step per candle, oldest first. Candles must be in time order."""
    seen: list[Candle] = []
    levels: list[TurningPoint] = []
    finder = TurningPointFinder()
    for candle in candles:
        if seen and candle.time <= seen[-1].time:
            raise ValueError(
                f"candles must be in time order; {candle.time} follows {seen[-1].time}"
            )
        seen.append(candle)
        confirmed = finder.push(candle)
        levels.extend(confirmed)
        kind = detector.mark(seen, levels)
        mark = Mark(kind, candle.time, candle.close) if kind is not None else None
        yield Step(candle, mark, tuple(confirmed))


@dataclass(frozen=True, slots=True)
class MarkOutcome:
    kind: Kind
    time: int
    price: float
    hit: bool
    turning_point: int | None
    """Time of the turning point this mark is the hit of."""
    timing: int | None
    give_up: float | None
    settled_at: int
    """Time of the first candle from which the outcome can no longer change."""


@dataclass(frozen=True)
class ReplayResult:
    detector: str
    candles: list[Candle]
    turning_points: list[TurningPoint]
    marks: list[MarkOutcome]
    score: Score


def settled_index(
    mark_index: int,
    candles: Sequence[Candle],
    points: Sequence[TurningPoint],
    point_indexes: Sequence[int],
    index: dict[int, int],
    tolerance: Tolerance,
) -> int:
    """The candle index from which a mark's outcome is certain.

    Three things can still change it before then: a mark placed later that is
    nearer to a turning point inside the mark's window (any mark up to two
    tolerances later), the confirmation of the last turning point inside the
    window, and the chance that a not yet confirmed extreme inside the window
    still becomes a turning point, which is over once the next turning point
    beyond the window has made its extreme. If the series ends first, the
    outcome is settled by its last candle.
    """
    last = len(candles) - 1
    window_end = mark_index + tolerance.candles
    settled = mark_index + 2 * tolerance.candles
    beyond = bisect_right(point_indexes, window_end)
    if beyond > 0:
        settled = max(settled, index[points[beyond - 1].confirmed_at])
    settled = max(settled, point_indexes[beyond] if beyond < len(points) else last)
    return min(settled, last)


def run(
    candles: Sequence[Candle], detector: Detector, tolerance: Tolerance = TOLERANCE
) -> ReplayResult:
    """Replay the whole series through the detector and score its marks."""
    marks: list[Mark] = []
    points: list[TurningPoint] = []
    for step in replay(candles, detector):
        if step.mark is not None:
            marks.append(step.mark)
        points.extend(step.confirmed)
    outcome = match_marks(candles, marks, points, tolerance)
    hits = {hit.mark.time: hit for hit in outcome.hits}
    index = {candle.time: i for i, candle in enumerate(candles)}
    point_indexes = [index[point.time] for point in points]
    outcomes: list[MarkOutcome] = []
    for mark in marks:
        hit = hits.get(mark.time)
        settled = settled_index(index[mark.time], candles, points, point_indexes, index, tolerance)
        outcomes.append(
            MarkOutcome(
                mark.kind,
                mark.time,
                mark.price,
                hit=hit is not None,
                turning_point=hit.turning_point.time if hit else None,
                timing=hit.timing if hit else None,
                give_up=hit.give_up if hit else None,
                settled_at=candles[settled].time,
            )
        )
    return ReplayResult(detector.name, list(candles), points, outcomes, score(outcome))
