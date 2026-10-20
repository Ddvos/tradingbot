"""Replay: stored candles go to a detector one at a time, in time order.

At every step the detector is handed the candles so far and the turning points
confirmed so far, and nothing later, so no future candle can leak into a mark.
The turning points are always found on hourly candles. An hourly detector's
candles are those hourly candles themselves. A fifteen-minute detector reads
fifteen-minute candles, and the hourly candles are built from that stream as
hours complete: with the candle that ends on the hour, with the first candle
of a later hour when the hour's last fifteen-minute candle had no trades, or
with the last candle of the series. The completed hour goes to the
turning-point finder before the detector sees the candle, so a turning point
confirmed by the hour a candle completes is visible to the detector on that
candle (ADR-0006).

`replay_all` replays a whole series and keeps everything the replay produced;
`score_replayed` scores that under the tolerance, the scoring period and the
eras. `run` is both in one. The result records the whole run, every candle
the detector read and every mark it placed, so the run can be re-scored under
later definitions (ADR-0004); the score counts the scored period only. The
dashboard replay, the batch command and the re-scoring all go through them,
so they place the same marks and read the same score.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from tradingbot.candles import Candle, Timeframe, merge, period_start
from tradingbot.detectors import Detector, Level, Mark, SwingExtreme
from tradingbot.scoring import ERAS, TOLERANCE, Era, Score, Tolerance, match_marks, score
from tradingbot.turning_points import Kind, TurningPoint, TurningPointFinder

HOUR = Timeframe.H1.seconds


class HourBuilder:
    """Builds hourly candles from the candles of a shorter (or the hourly) timeframe.

    `push` answers the hourly candles the pushed candle completes: none, the
    hour the candle ends, the previous hour when this candle is the first of a
    later hour, or both. The last candle of a series completes its hour too.
    Pushed hourly candles complete themselves, one per push.
    """

    def __init__(self, timeframe: Timeframe) -> None:
        self._size = timeframe.seconds
        self._current: Candle | None = None

    def push(self, candle: Candle, *, last: bool = False) -> list[Candle]:
        start = period_start(candle.time, Timeframe.H1)
        completed: list[Candle] = []
        if self._current is not None and self._current.time != start:
            completed.append(self._current)
            self._current = None
        self._current = merge(self._current, candle, start)
        if last or candle.time + self._size == start + HOUR:
            completed.append(self._current)
            self._current = None
        return completed


def build_hourly(candles: Sequence[Candle], timeframe: Timeframe) -> list[Candle]:
    """The hourly candles a replay of `candles` (of `timeframe`) builds, oldest first."""
    hours = HourBuilder(timeframe)
    built: list[Candle] = []
    for i, candle in enumerate(candles):
        built.extend(hours.push(candle, last=i == len(candles) - 1))
    return built


@dataclass(frozen=True)
class Step:
    candle: Candle
    mark: Mark | None
    """The mark the detector placed on this candle, if any."""
    confirmed: tuple[TurningPoint, ...]
    """The turning points confirmed by the hours this candle completed: new levels from now on."""
    pending_from: int | None
    """Start time of the earliest hourly candle that can still become a turning point;
    None until the first hour has completed."""
    completed: tuple[Candle, ...]
    """The hourly candles this candle completed: itself for an hourly detector."""


def replay(candles: Iterable[Candle], detector: Detector) -> Iterator[Step]:
    """One step per candle of the detector's timeframe, oldest first.

    Candles must be in time order and start on a period of that timeframe.
    """
    seen: list[Candle] = []
    levels: list[TurningPoint] = []
    finder = TurningPointFinder()
    hours = HourBuilder(detector.timeframe)
    size = detector.timeframe.seconds
    iterator = iter(candles)
    following = next(iterator, None)
    while following is not None:
        candle, following = following, next(iterator, None)
        if seen and candle.time <= seen[-1].time:
            raise ValueError(
                f"candles must be in time order; {candle.time} follows {seen[-1].time}"
            )
        if candle.time % size:
            raise ValueError(f"{candle.time} does not start a {detector.timeframe.value} candle")
        seen.append(candle)
        completed = hours.push(candle, last=following is None)
        confirmed = [point for hour in completed for point in finder.push(hour)]
        levels.extend(confirmed)
        kind = detector.mark(seen, levels)
        mark = Mark(kind, candle.time, candle.close) if kind is not None else None
        yield Step(candle, mark, tuple(confirmed), finder.pending_from, tuple(completed))


@dataclass(frozen=True)
class Replayed:
    """Everything a replay produced, before scoring."""

    detector: str
    timeframe: Timeframe
    candles: list[Candle]
    """The candles the detector read, oldest first."""
    hourly: list[Candle]
    """The hourly candles the turning-point finder read: `candles` for an hourly detector."""
    completed_at: list[int]
    """Per hourly candle, the start time of the candle (of the detector's timeframe) that
    completed it; the hourly candle's own time for an hourly detector."""
    pending_index: list[int]
    """Per hourly candle, the index in `hourly` of the earliest hourly candle that could
    still become a turning point once it had completed. It never moves backwards."""
    turning_points: list[TurningPoint]
    levels: list[Level]
    swing_extremes: list[SwingExtreme]
    marks: list[Mark]


def replay_all(candles: Sequence[Candle], detector: Detector) -> Replayed:
    """Replay the whole series through the detector and keep what it produced."""
    hourly: list[Candle] = []
    completed_at: list[int] = []
    pending_index: list[int] = []
    index: dict[int, int] = {}
    marks: list[Mark] = []
    points: list[TurningPoint] = []
    for step in replay(candles, detector):
        if step.mark is not None:
            marks.append(step.mark)
        points.extend(step.confirmed)
        for hour in step.completed:
            index[hour.time] = len(hourly)
            hourly.append(hour)
            completed_at.append(step.candle.time)
        if step.completed:
            assert step.pending_from is not None  # the finder has seen an hour
            pending_index.extend([index[step.pending_from]] * len(step.completed))
    return Replayed(
        detector.name,
        detector.timeframe,
        list(candles),
        hourly,
        completed_at,
        pending_index,
        points,
        detector.levels(points),
        detector.swing_extremes(),
        marks,
    )


@dataclass(frozen=True, slots=True)
class MarkOutcome:
    kind: Kind
    time: int
    price: float
    scored: bool
    """Whether the mark falls in the scored period. An unscored mark is neither a hit
    nor a false mark, and the fields below say nothing about it."""
    hit: bool
    turning_point: int | None
    """Time of the turning point this mark is the hit of."""
    timing: int | None
    give_up: float | None
    settled_at: int
    """Time of the first candle from which the outcome can no longer change; the mark's
    own time for an unscored mark."""


@dataclass(frozen=True)
class ReplayResult:
    detector: str
    timeframe: Timeframe
    scored_from: int | None
    """Start of the scored period; None when the whole series was scored."""
    candles: list[Candle]
    """Every candle the detector read, oldest first: the record of the run."""
    turning_points: list[TurningPoint]
    """Every turning point of the series, in and before the scored period."""
    levels: list[Level]
    """The levels the detector read, with the candles that saw them; what the chart draws."""
    swing_extremes: list[SwingExtreme]
    """The swing extremes the detector read, with the candles that read them; drawn likewise."""
    marks: list[MarkOutcome]
    """Every mark the detector placed, with its outcome where it was scored."""
    score: Score
    """The score over the scored period."""

    @property
    def scored_candles(self) -> list[Candle]:
        """The candles from `scored_from` on: the series the score counts."""
        if self.scored_from is None:
            return self.candles
        return self.candles[bisect_left(self.candles, self.scored_from, key=lambda c: c.time) :]


def settled_index(mark_index: int, pending_index: Sequence[int], tolerance: Tolerance) -> int:
    """The hourly candle from which a mark's outcome is certain.

    Two things can still change it before then: a mark placed later that is
    nearer to a turning point inside this mark's tolerance (possible until two
    tolerances after the mark), and a turning point still to be confirmed
    inside the tolerance (possible until the earliest candle that can still
    become a turning point lies beyond it). `pending_index` holds, per hourly
    candle, the index of that candle; it never moves backwards. If the series
    ends first, the outcome is settled by its last hour.
    """
    last = len(pending_index) - 1
    tolerance_end = mark_index + tolerance.candles
    competitors_placed = mark_index + 2 * tolerance.candles
    tolerance_settled = bisect_right(pending_index, tolerance_end)
    return min(max(competitors_placed, tolerance_settled), last)


def unscored(mark: Mark) -> MarkOutcome:
    """The outcome of a mark before the scored period: none."""
    return MarkOutcome(mark.kind, mark.time, mark.price, False, False, None, None, None, mark.time)


def score_replayed(
    replayed: Replayed,
    tolerance: Tolerance = TOLERANCE,
    score_from: int | None = None,
    eras: Sequence[Era] = ERAS,
) -> ReplayResult:
    """Score a replay's marks against its turning points.

    With `score_from`, a whole hour, only the candles, marks and turning points
    from that time on are scored, among themselves as a series of their own:
    a mark before it is unscored, a turning point before it takes no hit. The
    detector saw everything before it, so its state carried over, and the
    result still records every candle and every mark. The scoring period and
    the out-of-sample check both use this.
    """
    hourly = replayed.hourly
    completed_at = replayed.completed_at
    pending_index = replayed.pending_index
    marks, points = replayed.marks, replayed.turning_points
    before: list[Mark] = []
    if score_from is not None:
        if score_from % HOUR:
            raise ValueError(f"score_from must start an hour; {score_from} does not")
        first = bisect_left(hourly, score_from, key=lambda c: c.time)
        hourly = hourly[first:]
        completed_at = completed_at[first:]
        before = [m for m in marks if m.time < score_from]
        marks = [m for m in marks if m.time >= score_from]
        points = [p for p in points if p.time >= score_from]
        # A candle before `score_from` that can still become a turning point
        # counts as the first scored candle: nothing earlier exists in this series.
        pending_index = [max(i - first, 0) for i in pending_index[first:]]
    hour_index = {candle.time: i for i, candle in enumerate(hourly)}
    outcome = match_marks(hourly, marks, points, tolerance)
    hits = {hit.mark.time: hit for hit in outcome.hits}
    outcomes = [unscored(mark) for mark in before]
    for mark in marks:
        hit = hits.get(mark.time)
        mark_hour = hour_index[period_start(mark.time, Timeframe.H1)]
        settled = settled_index(mark_hour, pending_index, tolerance)
        outcomes.append(
            MarkOutcome(
                mark.kind,
                mark.time,
                mark.price,
                scored=True,
                hit=hit is not None,
                turning_point=hit.turning_point.time if hit else None,
                timing=hit.timing if hit else None,
                give_up=hit.give_up if hit else None,
                settled_at=completed_at[settled],
            )
        )
    return ReplayResult(
        replayed.detector,
        replayed.timeframe,
        score_from,
        replayed.candles,
        replayed.turning_points,
        replayed.levels,
        replayed.swing_extremes,
        outcomes,
        score(outcome, eras),
    )


def run(
    candles: Sequence[Candle],
    detector: Detector,
    tolerance: Tolerance = TOLERANCE,
    score_from: int | None = None,
    eras: Sequence[Era] = ERAS,
) -> ReplayResult:
    """Replay the whole series through the detector and score its marks; see `score_replayed`."""
    return score_replayed(replay_all(candles, detector), tolerance, score_from, eras)
