"""Detector one: a mark in a zone on the first failed higher high or lower low (#12)."""

from tradingbot.candles import Candle
from tradingbot.detectors import (
    DETECTORS,
    DetectorOne,
    Mark,
    higher_highs,
    lower_lows,
    near_level,
)
from tradingbot.turning_points import Kind, TurningPoint


def test_a_price_within_one_percent_of_a_level_is_in_its_zone() -> None:
    assert near_level(100.5, [100.0])
    assert near_level(99.5, [100.0])
    assert near_level(101.0, [100.0])  # exactly 1% above: still inside
    assert near_level(99.0, [100.0])  # exactly 1% below: still inside


def test_a_price_more_than_one_percent_from_every_level_is_outside_every_zone() -> None:
    assert not near_level(101.1, [100.0])
    assert not near_level(98.9, [100.0])
    assert not near_level(100.0, [])


def test_the_zone_is_measured_as_a_fraction_of_the_level() -> None:
    assert near_level(1010.0, [1000.0])
    assert not near_level(1010.1, [1000.0])


def test_any_level_can_put_a_price_in_a_zone() -> None:
    levels = [50.0, 100.0, 200.0]  # sorted ascending, as the detector keeps them
    assert near_level(199.0, levels)
    assert near_level(50.4, levels)
    assert not near_level(150.0, levels)


H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def candle(hour: int, high: float, low: float, close: float) -> Candle:
    return Candle(T0 + hour * H, close, high, low, close, 1.0, 1)


def test_a_run_of_higher_highs_counts_the_candles_whose_high_beat_the_candle_before() -> None:
    candles = [
        candle(0, high=100.0, low=90.0, close=95.0),
        candle(1, high=101.0, low=90.0, close=95.0),  # higher high
        candle(2, high=102.0, low=90.0, close=95.0),  # higher high
        candle(3, high=102.0, low=90.0, close=95.0),  # equal high: the run is broken
        candle(4, high=103.0, low=90.0, close=95.0),  # higher high: a new run of one
    ]

    assert higher_highs(candles, ending_at=0) == 0  # the first candle has nothing to beat
    assert higher_highs(candles, ending_at=1) == 1
    assert higher_highs(candles, ending_at=2) == 2
    assert higher_highs(candles, ending_at=3) == 0
    assert higher_highs(candles, ending_at=4) == 1


def test_a_run_of_lower_lows_is_the_mirror_image() -> None:
    candles = [
        candle(0, high=110.0, low=100.0, close=105.0),
        candle(1, high=110.0, low=99.0, close=105.0),  # lower low
        candle(2, high=110.0, low=98.0, close=105.0),  # lower low
        candle(3, high=110.0, low=97.0, close=105.0),  # lower low
        candle(4, high=110.0, low=97.5, close=105.0),  # not a lower low
    ]

    assert lower_lows(candles, ending_at=3) == 3
    assert lower_lows(candles, ending_at=4) == 0


def level(kind: Kind, price: float) -> TurningPoint:
    """A turning point confirmed long before the test series starts."""
    return TurningPoint(kind, T0 - 100 * H, price, T0 - 50 * H)


def marks_of(
    detector: DetectorOne, candles: list[Candle], levels: list[TurningPoint]
) -> list[Mark]:
    """Hand the detector the candles one at a time, as replay does, and collect its marks."""
    marks: list[Mark] = []
    for i, latest in enumerate(candles):
        kind = detector.mark(candles[: i + 1], levels)
        if kind is not None:
            marks.append(Mark(kind, latest.time, latest.close))
    return marks


RISE_THEN_FAIL = [
    candle(0, high=95.0, low=90.0, close=94.0),
    candle(1, high=96.0, low=91.0, close=95.0),  # higher high
    candle(2, high=97.0, low=92.0, close=96.0),  # higher high
    candle(3, high=98.0, low=93.0, close=97.0),  # higher high: a run of three
    candle(4, high=97.6, low=93.0, close=96.0),  # the first failed higher high
    candle(5, high=97.0, low=92.0, close=95.0),  # a lower high again, but no run before it
]


def test_a_top_is_marked_on_the_first_failed_higher_high_in_a_zone() -> None:
    marks = marks_of(DetectorOne(), RISE_THEN_FAIL, [level(Kind.TOP, 98.5)])

    assert marks == [Mark(Kind.TOP, T0 + 4 * H, 96.0)]


FALL_THEN_FAIL = [
    candle(0, high=110.0, low=105.0, close=106.0),
    candle(1, high=109.0, low=104.0, close=105.0),  # lower low
    candle(2, high=108.0, low=103.0, close=104.0),  # lower low
    candle(3, high=107.0, low=102.0, close=103.0),  # lower low: a run of three
    candle(4, high=107.0, low=102.4, close=104.0),  # the first failed lower low
    candle(5, high=108.0, low=103.0, close=105.0),  # a higher low again, but no run before it
]


def test_a_bottom_is_marked_on_the_first_failed_lower_low_in_a_zone() -> None:
    marks = marks_of(DetectorOne(), FALL_THEN_FAIL, [level(Kind.BOTTOM, 101.5)])

    assert marks == [Mark(Kind.BOTTOM, T0 + 4 * H, 104.0)]


def test_no_mark_outside_a_zone() -> None:
    far_away = [level(Kind.TOP, 120.0), level(Kind.BOTTOM, 80.0)]

    assert marks_of(DetectorOne(), RISE_THEN_FAIL, far_away) == []
    assert marks_of(DetectorOne(), FALL_THEN_FAIL, far_away) == []
    assert marks_of(DetectorOne(), RISE_THEN_FAIL, []) == []


def test_a_level_of_either_kind_serves_tops_and_bottoms_alike() -> None:
    assert marks_of(DetectorOne(), RISE_THEN_FAIL, [level(Kind.BOTTOM, 98.5)]) == [
        Mark(Kind.TOP, T0 + 4 * H, 96.0)
    ]
    assert marks_of(DetectorOne(), FALL_THEN_FAIL, [level(Kind.TOP, 101.5)]) == [
        Mark(Kind.BOTTOM, T0 + 4 * H, 104.0)
    ]


def test_a_run_of_two_higher_highs_is_not_enough() -> None:
    short_run = [
        candle(0, high=95.0, low=90.0, close=94.0),
        candle(1, high=96.0, low=91.0, close=95.0),  # higher high
        candle(2, high=96.0, low=92.0, close=96.0),  # equal high breaks the run
        candle(3, high=97.0, low=93.0, close=97.0),  # higher high
        candle(4, high=98.0, low=93.0, close=97.0),  # higher high: a run of two
        candle(5, high=97.6, low=93.0, close=96.0),  # a failed higher high, but too soon
    ]

    assert marks_of(DetectorOne(), short_run, [level(Kind.TOP, 98.5)]) == []


def test_a_level_counts_from_the_candle_that_confirms_it() -> None:
    detector = DetectorOne()
    confirmed_late = TurningPoint(Kind.TOP, T0 - 100 * H, 98.5, confirmed_at=T0 + 4 * H)

    before = [detector.mark(RISE_THEN_FAIL[: i + 1], []) for i in range(4)]
    on_confirmation = detector.mark(RISE_THEN_FAIL[:5], [confirmed_late])

    assert before == [None, None, None, None]
    assert on_confirmation is Kind.TOP


def test_the_decision_on_a_candle_never_depends_on_later_candles() -> None:
    levels = [level(Kind.TOP, 98.5), level(Kind.BOTTOM, 101.5)]
    series = RISE_THEN_FAIL + [
        candle(h + 6, c.high, c.low, c.close) for h, c in enumerate(FALL_THEN_FAIL)
    ]
    whole = marks_of(DetectorOne(), series, levels)

    for i in range(len(series)):
        assert marks_of(DetectorOne(), series[: i + 1], levels) == [
            m for m in whole if m.time <= series[i].time
        ]


def test_when_a_candle_fails_both_runs_the_longer_run_wins_and_a_tie_means_no_mark() -> None:
    # Expanding ranges: every candle beats the previous high and the previous low,
    # then an inside candle fails both at once, with both its high and low in a zone.
    expanding = [
        candle(0, high=100.0, low=99.0, close=99.5),
        candle(1, high=101.0, low=98.0, close=99.5),  # higher high and lower low
        candle(2, high=102.0, low=97.0, close=99.5),  # both again
        candle(3, high=103.0, low=96.0, close=99.5),  # both again: two runs of three
        candle(4, high=102.5, low=96.5, close=99.5),  # inside candle: fails both
    ]
    levels = [level(Kind.TOP, 103.0), level(Kind.BOTTOM, 96.0)]
    assert marks_of(DetectorOne(), expanding, levels) == []

    # The same, but the lows started falling one candle earlier: the longer run wins.
    longer_fall = [candle(0, high=100.5, low=99.5, close=100.0)] + [
        candle(h + 1, c.high, c.low, c.close) for h, c in enumerate(expanding)
    ]
    assert marks_of(DetectorOne(), longer_fall, levels) == [Mark(Kind.BOTTOM, T0 + 5 * H, 99.5)]


def test_detector_one_is_registered_under_its_name() -> None:
    assert isinstance(DETECTORS["one"](), DetectorOne)
