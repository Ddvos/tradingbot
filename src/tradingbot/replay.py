"""Replay: stored candles go to a detector one at a time, in time order.

At every step the detector is handed the candles so far and the turning points
confirmed so far, and nothing later, so no future candle can leak into a mark.
The dashboard replay and the batch command both go through `run`, so they
place the same marks and read the same score.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
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
    pending_from: int
    """Start time of the earliest candle that can still become a turning point."""


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
        pending_from = finder.pending_from
        assert pending_from is not None  # the finder has seen this candle
        yield Step(candle, mark, tuple(confirmed), pending_from)


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


def settled_index(mark_index: int, pending_index: Sequence[int], tolerance: Tolerance) -> int:
    """The step from which a mark's outcome is certain.

    Two things can still change it before then: a mark placed later that is
    nearer to a turning point inside this mark's tolerance (possible until two
    tolerances after the mark), and a turning point still to be confirmed
    inside the tolerance (possible until the earliest candle that can still
    become a turning point lies beyond it). `pending_index` holds, per step,
    the index of that candle; it never moves backwards. If the series ends
    first, the outcome is settled by its last step.
    """
    last = len(pending_index) - 1
    tolerance_end = mark_index + tolerance.candles
    competitors_placed = mark_index + 2 * tolerance.candles
    tolerance_settled = bisect_right(pending_index, tolerance_end)
    return min(max(competitors_placed, tolerance_settled), last)


def run(
    candles: Sequence[Candle],
    detector: Detector,
    tolerance: Tolerance = TOLERANCE,
    score_from: int | None = None,
) -> ReplayResult:
    """Replay the whole series through the detector and score its marks.

    With `score_from`, the detector and the turning-point finder still see
    every candle, so the levels carry over, but only the candles, marks and
    turning points from that time on are kept, and they are scored among
    themselves as a series of their own. The out-of-sample check uses this.
    """
    index = {candle.time: i for i, candle in enumerate(candles)}
    marks: list[Mark] = []
    points: list[TurningPoint] = []
    pending_index: list[int] = []
    for step in replay(candles, detector):
        if step.mark is not None:
            marks.append(step.mark)
        points.extend(step.confirmed)
        pending_index.append(index[step.pending_from])
    if score_from is not None:
        first = bisect_left(candles, score_from, key=lambda c: c.time)
        candles = candles[first:]
        index = {candle.time: i for i, candle in enumerate(candles)}
        marks = [m for m in marks if m.time >= score_from]
        points = [p for p in points if p.time >= score_from]
        # A candle before the cut that can still become a turning point counts
        # as the first kept candle: nothing earlier exists in this series.
        pending_index = [max(i - first, 0) for i in pending_index[first:]]
    outcome = match_marks(candles, marks, points, tolerance)
    hits = {hit.mark.time: hit for hit in outcome.hits}
    outcomes: list[MarkOutcome] = []
    for mark in marks:
        hit = hits.get(mark.time)
        settled = settled_index(index[mark.time], pending_index, tolerance)
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
