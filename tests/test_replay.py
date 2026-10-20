"""Replay: candles go to the detector one at a time, so nothing later is ever visible."""

from collections.abc import Sequence

import pytest

from tests.walks import quarter_walk, random_walk
from tradingbot.candles import Candle, Timeframe, period_start, resample
from tradingbot.detectors import (
    LEVEL_LIFETIME,
    DetectorThree,
    DetectorTwo,
    FloorDetector,
    Level,
    Mark,
    SwingExtreme,
)
from tradingbot.replay import ReplayResult, replay, replay_all, run
from tradingbot.scoring import match_marks
from tradingbot.turning_points import Kind, TurningPoint, find_turning_points

H = 3600
Q = 900  # a quarter of an hour
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


class Spy:
    """A detector that records exactly what replay shows it and marks every candle a top."""

    name = "spy"

    def __init__(self, timeframe: Timeframe = Timeframe.H1) -> None:
        self.timeframe = timeframe
        self.candles_seen: list[tuple[Candle, ...]] = []
        self.levels_seen: list[tuple[TurningPoint, ...]] = []

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        self.candles_seen.append(tuple(candles))
        self.levels_seen.append(tuple(levels))
        return Kind.TOP

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]:
        return []

    def swing_extremes(self) -> list[SwingExtreme]:
        return []


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


def test_a_mark_in_a_steady_rise_is_settled_two_tolerances_later() -> None:
    # Every hour makes a new high, so the earliest candle that can still become a
    # turning point moves on every step; only later competing marks remain to wait for.
    staircase = [
        Candle(T0 + h * H, 100 + h, 100.5 + h, 99.5 + h, 100.2 + h, 1.0, 1) for h in range(100)
    ]

    result = run(staircase, Spy())

    assert result.marks[0].settled_at == T0 + 48 * H
    assert result.marks[10].settled_at == T0 + 58 * H


def test_a_mark_in_a_flat_market_is_settled_only_by_the_last_candle() -> None:
    # Nothing ever makes a new extreme, so the very first candle can still become a
    # turning point until the series ends.
    flat = [Candle(T0 + h * H, 100.0, 100.0, 100.0, 100.0, 1.0, 1) for h in range(100)]

    result = run(flat, Spy())

    assert result.marks[0].settled_at == T0 + 99 * H


def test_scoring_from_a_time_scores_the_marks_and_turning_points_from_then_on() -> None:
    candles = random_walk(hours=2000, seed=9)
    boundary = T0 + 1500 * H
    spy = Spy()

    result = run(candles, spy, score_from=boundary)

    assert result.scored_from == boundary
    assert result.candles == candles, "the whole run is recorded"
    assert [c.time for c in result.scored_candles] == [
        c.time for c in candles if c.time >= boundary
    ]
    assert [m.time for m in result.marks] == [c.time for c in candles], "every mark is recorded"
    assert [m.time for m in result.marks if m.scored] == [
        c.time for c in candles if c.time >= boundary
    ]
    assert result.turning_points == find_turning_points(candles)
    assert result.score.marks == 500
    assert result.score.turning_points == len(
        [p for p in find_turning_points(candles) if p.time >= boundary]
    )
    assert result.score.turning_points > 3


def test_a_mark_before_the_scored_time_is_unscored() -> None:
    candles = random_walk(hours=2000, seed=9)
    boundary = T0 + 1500 * H

    result = run(candles, Spy(), score_from=boundary)

    before = [m for m in result.marks if m.time < boundary]
    assert len(before) == 1500
    assert all(
        (m.scored, m.hit, m.turning_point, m.timing, m.give_up, m.settled_at)
        == (False, False, None, None, None, m.time)
        for m in before
    )
    assert all(m.scored for m in result.marks if m.time >= boundary)


def test_the_detector_still_sees_every_candle_before_the_scored_time() -> None:
    candles = random_walk(hours=2000, seed=9)
    boundary = T0 + 1500 * H
    spy = Spy()

    run(candles, spy, score_from=boundary)

    assert spy.candles_seen[0] == (candles[0],)
    assert spy.candles_seen[-1] == tuple(candles)
    assert len(spy.levels_seen[-1]) == len(find_turning_points(candles))


def test_marks_scored_from_a_time_are_settled_by_a_kept_candle() -> None:
    candles = random_walk(hours=2000, seed=10)
    boundary = T0 + 1500 * H

    result = run(candles, FloorDetector(), score_from=boundary)

    scored = [m for m in result.marks if m.scored]
    kept = {c.time for c in result.scored_candles}
    assert scored, "the floor should place marks past the boundary"
    for outcome in scored:
        assert outcome.settled_at in kept
        assert outcome.settled_at >= outcome.time


def test_a_run_carries_the_levels_the_detector_read_with_their_spans() -> None:
    candles = random_walk(hours=2000, seed=12)

    result = run(candles, DetectorTwo())

    assert result.levels, "the series should hold turning points"
    assert result.levels == [
        Level(p.kind, p.price, p.time, p.confirmed_at, p.time + LEVEL_LIFETIME)
        for p in result.turning_points
    ]
    assert run(candles, FloorDetector()).levels == []
    assert run(candles, Spy()).levels == []


def test_a_run_carries_every_swing_extreme_the_detector_read_with_its_span() -> None:
    quarters = quarter_walk(hours=600, seed=24)
    by_time = {c.time: c for c in quarters}

    result = run(quarters, DetectorThree())

    extremes = result.swing_extremes
    assert len(extremes) > 100, "the walk should set many extremes"
    assert extremes == sorted(extremes, key=lambda e: e.active_from)
    for extreme in extremes:
        candle = by_time[extreme.time]
        assert extreme.price == (candle.high if extreme.kind is Kind.TOP else candle.low)
        assert extreme.active_from >= extreme.time
        assert extreme.active_until is None or extreme.active_until >= extreme.active_from
    for kind in Kind:
        of_kind = [e for e in extremes if e.kind is kind]
        assert [e.active_until for e in of_kind[:-1]] == [
            quarters[quarters.index(by_time[e.active_from]) - 1].time for e in of_kind[1:]
        ], "each extreme stands until the candle before the next one is read"
        assert of_kind[-1].active_until is None
    assert run(quarters, Spy(Timeframe.M15)).swing_extremes == []
    assert run(random_walk(hours=600, seed=24), FloorDetector()).swing_extremes == []


def test_scoring_from_a_time_records_every_swing_extreme_the_detector_read() -> None:
    quarters = quarter_walk(hours=600, seed=25)
    boundary = T0 + 400 * H

    whole = run(quarters, DetectorThree())
    scored = run(quarters, DetectorThree(), score_from=boundary)

    assert scored.swing_extremes == whole.swing_extremes
    assert scored.swing_extremes[0].active_from < boundary


def test_scoring_from_a_time_records_every_level_the_detector_read() -> None:
    candles = random_walk(hours=2000, seed=12)
    boundary = T0 + 1500 * H

    whole = run(candles, DetectorTwo())
    scored = run(candles, DetectorTwo(), score_from=boundary)

    assert scored.levels == whole.levels
    assert scored.score != whole.score


def test_scoring_from_before_the_first_candle_changes_nothing() -> None:
    candles = random_walk(hours=500, seed=11)

    scored = run(candles, FloorDetector(), score_from=T0 - H)
    whole = run(candles, FloorDetector())

    assert (scored.marks, scored.score, scored.candles) == (whole.marks, whole.score, whole.candles)
    assert (scored.scored_from, whole.scored_from) == (T0 - H, None)


def test_each_hourly_step_completes_its_own_candle_as_the_hourly_candle() -> None:
    candles = random_walk(hours=5, seed=3)

    steps = list(replay(candles, Spy()))

    assert [step.completed for step in steps] == [(c,) for c in candles]


def test_a_fifteen_minute_replay_builds_the_hourly_candles_as_hours_complete() -> None:
    # Hour 00 has all four quarters, hour 01 lacks its last quarter, hour 02 has one
    # candle and ends the series.
    rows = [
        (0, 100.0, 104.0, 99.0, 103.0),
        (1, 103.0, 108.0, 102.0, 107.0),
        (2, 107.0, 110.0, 105.0, 106.0),
        (3, 106.0, 107.5, 101.0, 102.0),
        (4, 102.0, 103.0, 98.0, 99.0),
        (5, 99.0, 100.0, 97.0, 98.0),
        (6, 98.0, 101.0, 96.0, 100.0),
        # 01:45 has no candle
        (8, 100.0, 102.0, 99.0, 101.0),
    ]
    quarters = [Candle(T0 + q * Q, o, h, lo, c, 1.0, 1) for q, o, h, lo, c in rows]

    steps = list(replay(quarters, Spy(Timeframe.M15)))

    assert [step.candle for step in steps] == quarters
    assert [step.completed for step in steps] == [
        (),
        (),
        (),
        (Candle(T0, 100.0, 110.0, 99.0, 102.0, 4.0, 4),),
        (),
        (),
        (),
        (
            Candle(T0 + H, 102.0, 103.0, 96.0, 100.0, 3.0, 3),
            Candle(T0 + 2 * H, 100.0, 102.0, 99.0, 101.0, 1.0, 1),
        ),
    ]


def test_the_hourly_candles_built_in_a_fifteen_minute_replay_equal_the_resampled_ones() -> None:
    quarters = quarter_walk(hours=300, seed=21)

    replayed = replay_all(quarters, Spy(Timeframe.M15))

    assert replayed.hourly == resample(quarters, Timeframe.H1)
    assert replayed.candles == quarters
    assert replayed.timeframe is Timeframe.M15
    assert len(replayed.completed_at) == len(replayed.hourly)
    for hour, completed_at in zip(replayed.hourly, replayed.completed_at, strict=True):
        assert period_start(completed_at, Timeframe.H1) >= hour.time
    assert replayed.turning_points == find_turning_points(replayed.hourly)


def test_a_turning_point_confirmed_by_the_hour_a_candle_completes_is_seen_on_that_candle() -> None:
    quarters = quarter_walk(hours=400, seed=22)
    spy = Spy(Timeframe.M15)

    steps = list(replay(quarters, spy))

    points = find_turning_points(resample(quarters, Timeframe.H1))
    assert points, "the series should hold turning points"
    assert list(spy.levels_seen[-1]) == points
    completed: set[int] = set()
    for step, levels in zip(steps, spy.levels_seen, strict=True):
        completed.update(hour.time for hour in step.completed)
        assert list(levels) == [p for p in points if p.confirmed_at in completed]
    # Somewhere a turning point is confirmed by the last quarter of its hour, which is
    # the step that completes the hour, so it was not visible one candle earlier.
    assert any(
        step.confirmed and step.candle.time + Q == step.completed[-1].time + H for step in steps
    )


def test_a_fifteen_minute_mark_is_scored_by_its_hour_and_settled_by_a_fifteen_minute_candle() -> (
    None
):
    quarters = quarter_walk(hours=600, seed=23)

    result = run(quarters, Spy(Timeframe.M15))

    assert result.timeframe is Timeframe.M15
    assert result.candles == quarters
    assert [m.time for m in result.marks] == [c.time for c in quarters]
    assert result.score.hits > 0
    times = {c.time for c in quarters}
    point_by_time = {p.time: p for p in result.turning_points}
    for outcome in result.marks:
        assert outcome.settled_at in times
        assert outcome.settled_at >= outcome.time
        if outcome.turning_point is not None:
            point = point_by_time[outcome.turning_point]
            assert outcome.timing == (period_start(outcome.time, Timeframe.H1) - point.time) // H
            assert outcome.give_up is not None
            assert abs(outcome.give_up) == abs(outcome.price - point.price) / point.price * 100
