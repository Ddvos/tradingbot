"""Scoring marks against turning points: hits, misses, false marks, timing and give-up."""

from tradingbot.candles import Candle
from tradingbot.detectors import Mark
from tradingbot.scoring import Hit, Score, match_marks, score
from tradingbot.turning_points import Kind, TurningPoint

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def at(hour: int) -> int:
    return T0 + hour * H


def flat_series(hours: int) -> list[Candle]:
    """Hourly candles whose prices do not matter: marks and turning points carry their own."""
    return [Candle(at(hour), 100.0, 100.0, 100.0, 100.0, 1.0, 1) for hour in range(hours)]


def top(hour: int, price: float) -> TurningPoint:
    return TurningPoint(Kind.TOP, at(hour), price, confirmed_at=at(hour + 5))


def bottom(hour: int, price: float) -> TurningPoint:
    return TurningPoint(Kind.BOTTOM, at(hour), price, confirmed_at=at(hour + 5))


def test_a_late_mark_near_a_top_is_a_hit_with_positive_timing() -> None:
    point = top(10, 100.0)
    mark = Mark(Kind.TOP, at(13), price=99.0)

    outcome = match_marks(flat_series(100), [mark], [point])

    assert outcome.hits == [Hit(mark, point, timing=3, give_up=1.0)]
    assert outcome.false_marks == []
    assert outcome.misses == []


def test_an_early_mark_near_a_bottom_is_a_hit_with_negative_timing() -> None:
    point = bottom(30, 50.0)
    mark = Mark(Kind.BOTTOM, at(28), price=50.5)

    outcome = match_marks(flat_series(100), [mark], [point])

    assert outcome.hits == [Hit(mark, point, timing=-2, give_up=1.0)]


def test_a_turning_point_without_a_mark_is_a_miss() -> None:
    point = bottom(50, 50.0)

    outcome = match_marks(flat_series(100), [], [point])

    assert outcome.misses == [point]
    assert outcome.hits == []


def test_of_two_marks_near_one_turning_point_only_the_nearest_is_a_hit() -> None:
    point = top(10, 100.0)
    nearer = Mark(Kind.TOP, at(13), price=99.0)
    further = Mark(Kind.TOP, at(6), price=98.5)

    outcome = match_marks(flat_series(100), [further, nearer], [point])

    assert [hit.mark for hit in outcome.hits] == [nearer]
    assert outcome.false_marks == [further]


def test_a_mark_is_false_when_too_far_in_candles_price_or_kind() -> None:
    point = top(30, 100.0)
    too_late = Mark(Kind.TOP, at(55), price=100.0)
    too_far_in_price = Mark(Kind.TOP, at(31), price=97.0)
    wrong_kind = Mark(Kind.BOTTOM, at(30), price=100.0)

    outcome = match_marks(flat_series(100), [too_late, too_far_in_price, wrong_kind], [point])

    assert outcome.hits == []
    assert outcome.false_marks == [wrong_kind, too_far_in_price, too_late]  # oldest first
    assert outcome.misses == [point]


def test_a_mark_at_the_edge_of_the_tolerance_is_still_a_hit() -> None:
    point = bottom(30, 100.0)
    mark = Mark(Kind.BOTTOM, at(54), price=102.0)

    outcome = match_marks(flat_series(100), [mark], [point])

    assert outcome.hits == [Hit(mark, point, timing=24, give_up=2.0)]


def test_the_score_sums_up_the_outcome() -> None:
    points = [top(10, 100.0), bottom(30, 50.0), top(60, 100.0)]
    marks = [
        Mark(Kind.TOP, at(13), price=99.0),  # hit, 3 late, give-up 1%
        Mark(Kind.BOTTOM, at(28), price=51.0),  # hit, 2 early, give-up 2%
        Mark(Kind.TOP, at(40), price=90.0),  # false: 10% below the top at 60
        Mark(Kind.BOTTOM, at(45), price=60.0),  # false: 20% above the bottom at 30
    ]

    result = score(match_marks(flat_series(100), marks, points))

    assert result == Score(
        turning_points=3,
        marks=4,
        hits=2,
        false_marks=2,
        hit_rate=2 / 3,
        false_mark_rate=0.5,
        median_timing=0.5,
        median_give_up=1.5,
    )


def test_a_score_without_hits_has_no_timing_or_give_up() -> None:
    result = score(match_marks(flat_series(10), [], []))

    assert result == Score(
        0, 0, 0, 0, hit_rate=0.0, false_mark_rate=0.0, median_timing=None, median_give_up=None
    )
