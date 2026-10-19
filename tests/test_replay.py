"""Replay: candles go to the detector one at a time, so nothing later is ever visible."""

from collections.abc import Sequence

import pytest

from tradingbot.candles import Candle
from tradingbot.detectors import FloorDetector, Mark
from tradingbot.replay import ReplayResult, replay, run
from tradingbot.scoring import match_marks
from tradingbot.turning_points import Kind, TurningPoint, find_turning_points

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def random_walk(hours: int, seed: int) -> list[Candle]:
    import random

    rng = random.Random(seed)
    candles: list[Candle] = []
    close = 1000.0
    for hour in range(hours):
        open_ = close
        close = open_ * (1 + rng.uniform(-0.03, 0.03))
        high = max(open_, close) * (1 + rng.uniform(0, 0.01))
        low = min(open_, close) * (1 - rng.uniform(0, 0.01))
        candles.append(Candle(T0 + hour * H, open_, high, low, close, 1.0, 1))
    return candles


class Spy:
    """A detector that records exactly what replay shows it and marks every candle a top."""

    name = "spy"

    def __init__(self) -> None:
        self.candles_seen: list[tuple[Candle, ...]] = []
        self.levels_seen: list[tuple[TurningPoint, ...]] = []

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        self.candles_seen.append(tuple(candles))
        self.levels_seen.append(tuple(levels))
        return Kind.TOP


def test_each_step_places_the_mark_on_the_latest_candle_at_its_close() -> None:
    candles = random_walk(hours=5, seed=3)

    steps = list(replay(candles, Spy()))

    assert [step.candle for step in steps] == candles
    assert [step.mark for step in steps] == [Mark(Kind.TOP, c.time, c.close) for c in candles]


def test_the_detector_only_ever_sees_the_candles_so_far() -> None:
    candles = random_walk(hours=50, seed=4)
    spy = Spy()

    list(replay(candles, spy))

    assert spy.candles_seen == [tuple(candles[: i + 1]) for i in range(len(candles))]


def test_levels_at_a_step_never_include_a_turning_point_confirmed_later() -> None:
    candles = random_walk(hours=400, seed=5)
    spy = Spy()

    steps = list(replay(candles, spy))

    assert any(step.confirmed for step in steps), "the series should hold turning points"
    for step, levels in zip(steps, spy.levels_seen, strict=True):
        assert all(level.confirmed_at <= step.candle.time for level in levels)
    assert list(spy.levels_seen[-1]) == find_turning_points(candles)


def test_turning_points_are_reported_on_the_step_that_confirms_them() -> None:
    candles = random_walk(hours=400, seed=5)

    steps = list(replay(candles, FloorDetector()))

    confirmed = [(step.candle.time, point) for step in steps for point in step.confirmed]
    assert all(time == point.confirmed_at for time, point in confirmed)
    assert [point for _, point in confirmed] == find_turning_points(candles)


def test_candles_out_of_time_order_are_refused() -> None:
    candles = random_walk(hours=3, seed=6)

    with pytest.raises(ValueError, match="time order"):
        list(replay(reversed(candles), FloorDetector()))


def test_a_run_scores_the_floor_identically_every_time() -> None:
    candles = random_walk(hours=2000, seed=7)

    first = run(candles, FloorDetector())
    second = run(candles, FloorDetector())

    assert isinstance(first, ReplayResult)
    assert first.detector == "floor"
    assert first.score.turning_points > 5
    assert first.score.marks > first.score.hits > 0
    assert first == second


def test_a_mark_outcome_is_settled_once_no_later_candle_can_change_it() -> None:
    candles = random_walk(hours=2000, seed=8)
    result = run(candles, FloorDetector())
    index = {c.time: i for i, c in enumerate(candles)}
    marks = [Mark(m.kind, m.time, m.price) for m in result.marks]

    assert result.marks, "the floor should place marks"
    for outcome in result.marks:
        assert outcome.settled_at >= outcome.time
        if outcome.turning_point is not None:
            point = next(p for p in result.turning_points if p.time == outcome.turning_point)
            assert outcome.settled_at >= point.confirmed_at
        for last in (index[outcome.settled_at], len(candles) - 1):
            until = candles[last].time
            partial = match_marks(
                candles[: last + 1],
                [m for m in marks if m.time <= until],
                [p for p in result.turning_points if p.confirmed_at <= until],
            )
            hit = next((h for h in partial.hits if h.mark.time == outcome.time), None)
            assert (hit is not None) == outcome.hit
            assert (hit.turning_point.time if hit else None) == outcome.turning_point
