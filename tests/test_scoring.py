"""Scoring marks against turning points: hits, misses, false marks, timing and give-up."""

from tradingbot.candles import Candle
from tradingbot.detectors import Mark
from tradingbot.scoring import (
    ERAS,
    SCORING_START,
    Era,
    EraScore,
    Hit,
    Outcome,
    Score,
    describe_score,
    match_marks,
    score,
)
from tradingbot.turning_points import Kind, TurningPoint

H = 3600
Q = 900
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
        false_marks_per_hit=1.0,
        median_timing=0.5,
        median_give_up=1.5,
    )


def test_a_score_without_hits_has_no_timing_or_give_up() -> None:
    result = score(match_marks(flat_series(10), [], []))

    assert result == Score(
        0,
        0,
        0,
        0,
        hit_rate=0.0,
        false_mark_rate=0.0,
        false_marks_per_hit=0.0,
        median_timing=None,
        median_give_up=None,
    )


def test_false_marks_per_hit_is_the_false_marks_divided_by_the_hits() -> None:
    point = top(10, 100.0)
    marks = [
        Mark(Kind.TOP, at(13), price=99.0),  # hit
        Mark(Kind.TOP, at(40), price=90.0),  # false
        Mark(Kind.TOP, at(60), price=90.0),  # false
        Mark(Kind.BOTTOM, at(70), price=90.0),  # false
    ]

    result = score(match_marks(flat_series(100), marks, [point]))

    assert (result.hits, result.false_marks, result.false_marks_per_hit) == (1, 3, 3.0)


def test_false_marks_per_hit_is_zero_without_hits_and_without_false_marks() -> None:
    only_false = score(match_marks(flat_series(100), [Mark(Kind.TOP, at(40), price=90.0)], []))
    only_hit = score(
        match_marks(flat_series(100), [Mark(Kind.TOP, at(13), price=99.0)], [top(10, 100.0)])
    )

    assert (only_false.hits, only_false.false_marks, only_false.false_marks_per_hit) == (0, 1, 0.0)
    assert (only_hit.hits, only_hit.false_marks, only_hit.false_marks_per_hit) == (1, 0, 0.0)


def series_with_a_top_whose_candle_closes_five_percent_below_it() -> list[Candle]:
    """Flat at 100 but for hour 10, whose high is 100 and whose close is 95."""
    candles = flat_series(100)
    candles[10] = Candle(at(10), 100.0, 100.0, 94.0, 95.0, 1.0, 1)
    return candles


def test_under_tolerance_b_a_mark_at_the_extreme_candles_close_is_a_hit() -> None:
    point = top(10, 100.0)
    at_the_close = Mark(Kind.TOP, at(12), price=95.0)

    outcome = match_marks(
        series_with_a_top_whose_candle_closes_five_percent_below_it(), [at_the_close], [point]
    )

    assert outcome.hits == [Hit(at_the_close, point, timing=2, give_up=5.0)]


def test_under_tolerance_b_a_mark_further_out_than_the_extreme_candles_close_is_false() -> None:
    point = top(10, 100.0)
    further = Mark(Kind.TOP, at(12), price=94.9)

    outcome = match_marks(
        series_with_a_top_whose_candle_closes_five_percent_below_it(), [further], [point]
    )

    assert outcome.hits == []
    assert outcome.false_marks == [further]
    assert outcome.misses == [point]


def test_under_tolerance_b_two_percent_still_holds_when_the_extreme_candle_closes_nearer() -> None:
    # The bottom's own candle closes 0.5% above its low; a mark 1.9% above is still a hit.
    candles = flat_series(100)
    candles[30] = Candle(at(30), 100.0, 100.0, 50.0, 50.25, 1.0, 1)
    point = bottom(30, 50.0)
    within_two_percent = Mark(Kind.BOTTOM, at(33), price=50.95)
    beyond = Mark(Kind.BOTTOM, at(34), price=51.05)

    outcome = match_marks(candles, [within_two_percent, beyond], [point])

    assert [hit.mark for hit in outcome.hits] == [within_two_percent]
    assert outcome.false_marks == [beyond]


def test_a_fifteen_minute_mark_is_scored_by_the_hour_it_falls_in() -> None:
    point = top(10, 100.0)
    at_quarter_past = Mark(Kind.TOP, at(13) + Q, price=99.0)
    at_quarter_to = Mark(Kind.TOP, at(13) + 3 * Q, price=99.5)

    outcome = match_marks(flat_series(100), [at_quarter_to, at_quarter_past], [point])

    # Both lie in hour 13, three hourly candles late; the earlier one takes the hit.
    assert outcome.hits == [Hit(at_quarter_past, point, timing=3, give_up=1.0)]
    assert outcome.false_marks == [at_quarter_to]


def test_the_scoring_period_starts_in_2016_and_has_three_eras() -> None:
    assert SCORING_START == 1_451_606_400  # 2016-01-01T00:00:00Z
    assert ERAS == (
        Era("2016-2018", 1_451_606_400, 1_546_300_800),
        Era("2019-2021", 1_546_300_800, 1_640_995_200),
        Era("2022-2024", 1_640_995_200, 1_735_689_600),
    )
    assert ERAS[0].start == SCORING_START


def in_era(era: Era, hours: int) -> int:
    return era.start + hours * H


def test_the_score_is_split_per_era() -> None:
    first, second, third = ERAS
    candles = [
        Candle(t, 100.0, 100.0, 100.0, 100.0, 1.0, 1) for t in range(first.start, third.end, H)
    ]
    hit_in_first = TurningPoint(Kind.TOP, in_era(first, 10), 100.0, in_era(first, 15))
    missed_in_first = TurningPoint(Kind.BOTTOM, in_era(first, 100), 100.0, in_era(first, 105))
    hit_in_third = TurningPoint(Kind.TOP, in_era(third, 10), 100.0, in_era(third, 15))
    marks = [
        Mark(Kind.TOP, in_era(first, 12), 99.0),  # hit, 2 late, give-up 1%
        Mark(Kind.BOTTOM, in_era(second, 50), 100.0),  # false, in the second era
        Mark(Kind.TOP, in_era(third, 9), 99.5),  # hit, 1 early, give-up 0.5%
        Mark(Kind.TOP, in_era(third, 500), 100.0),  # false, in the third era
    ]

    result = score(match_marks(candles, marks, [hit_in_first, missed_in_first, hit_in_third]), ERAS)

    assert (result.turning_points, result.marks, result.hits, result.false_marks) == (3, 4, 2, 2)
    assert result.median_timing == 0.5
    assert [e.era.name for e in result.eras] == ["2016-2018", "2019-2021", "2022-2024"]
    assert result.eras[0] == EraScore(
        first,
        Score(
            turning_points=2,
            marks=1,
            hits=1,
            false_marks=0,
            hit_rate=0.5,
            false_mark_rate=0.0,
            false_marks_per_hit=0.0,
            median_timing=2,
            median_give_up=1.0,
        ),
    )
    assert result.eras[1].score == Score(
        0,
        1,
        0,
        1,
        hit_rate=0.0,
        false_mark_rate=1.0,
        false_marks_per_hit=0.0,
        median_timing=None,
        median_give_up=None,
    )
    assert result.eras[2].score == Score(
        1,
        2,
        1,
        1,
        hit_rate=1.0,
        false_mark_rate=0.5,
        false_marks_per_hit=1.0,
        median_timing=-1,
        median_give_up=0.5,
    )


def test_a_hit_across_an_era_boundary_counts_in_its_turning_points_era() -> None:
    first, second, _ = ERAS
    candles = [
        Candle(t, 100.0, 100.0, 100.0, 100.0, 1.0, 1) for t in range(first.start, second.end, H)
    ]
    point = TurningPoint(Kind.TOP, in_era(second, 1), 100.0, in_era(second, 5))
    mark = Mark(Kind.TOP, in_era(second, -2), 99.0)  # the last day of 2018

    result = score(match_marks(candles, [mark], [point]), ERAS)

    assert (result.eras[0].score.hits, result.eras[0].score.marks) == (0, 0)
    assert (result.eras[1].score.hits, result.eras[1].score.marks) == (1, 1)


def test_describe_score_prints_the_false_marks_per_hit_after_the_false_mark_rate() -> None:
    whole = Score(
        3,
        4,
        2,
        2,
        hit_rate=2 / 3,
        false_mark_rate=0.5,
        false_marks_per_hit=1.0,
        median_timing=0.5,
        median_give_up=1.5,
    )

    lines = describe_score(whole)

    assert [label for label, _ in lines] == [
        "turning points",
        "marks",
        "hits",
        "false marks",
        "false marks/hit",
        "median timing",
        "median give-up",
    ]
    assert lines[3:5] == [
        ("false marks", "2  (false-mark rate 50.0%)"),
        ("false marks/hit", "1.0 per hit"),
    ]


def test_describe_score_rounds_the_false_marks_per_hit_to_one_decimal() -> None:
    # The recorded run of detector three (#20): 4,698 false marks against 719 hits.
    recorded = Score(
        798,
        5417,
        719,
        4698,
        hit_rate=719 / 798,
        false_mark_rate=4698 / 5417,
        false_marks_per_hit=4698 / 719,
        median_timing=0.0,
        median_give_up=1.31,
    )

    assert ("false marks/hit", "6.5 per hit") in describe_score(recorded)


def test_describe_score_says_n_a_for_a_period_with_marks_but_no_hits() -> None:
    only_false = score(match_marks(flat_series(100), [Mark(Kind.TOP, at(40), price=90.0)], []))
    nothing = score(match_marks(flat_series(100), [], []))

    assert ("false marks/hit", "n/a (no hits)") in describe_score(only_false)
    assert ("false marks/hit", "0.0 per hit") in describe_score(nothing)


def test_describe_score_prints_one_line_per_era() -> None:
    whole = Score(
        3,
        4,
        2,
        2,
        hit_rate=2 / 3,
        false_mark_rate=0.5,
        false_marks_per_hit=1.0,
        median_timing=0.5,
        median_give_up=1.5,
    )
    era = Score(
        2,
        1,
        1,
        0,
        hit_rate=0.5,
        false_mark_rate=0.0,
        false_marks_per_hit=0.0,
        median_timing=2.0,
        median_give_up=1.0,
    )
    scored = Score(
        *(getattr(whole, f) for f in ("turning_points", "marks", "hits", "false_marks")),
        hit_rate=whole.hit_rate,
        false_mark_rate=whole.false_mark_rate,
        false_marks_per_hit=whole.false_marks_per_hit,
        median_timing=whole.median_timing,
        median_give_up=whole.median_give_up,
        eras=(EraScore(ERAS[0], era),),
    )

    lines = describe_score(scored)

    assert lines[:7] == describe_score(whole)
    assert lines[7] == (
        "2016-2018",
        "2 turning points, 1 marks, 1 hits (hit rate 50.0%), 0 false marks (false-mark rate 0.0%), "
        "0.0 per hit, median timing +2.0 candles (late), median give-up 1.00%",
    )


def test_an_era_line_says_n_a_for_marks_but_no_hits() -> None:
    first = ERAS[0]
    candles = [
        Candle(t, 100.0, 100.0, 100.0, 100.0, 1.0, 1) for t in range(first.start, first.end, H)
    ]

    lines = describe_score(
        score(match_marks(candles, [Mark(Kind.TOP, in_era(first, 5), 100.0)], []), ERAS)
    )

    assert lines[7][0] == "2016-2018"
    assert "1 false marks (false-mark rate 100.0%), n/a (no hits), median timing" in lines[7][1]


def test_a_score_without_eras_has_none() -> None:
    assert score(Outcome([], [], [])).eras == ()
