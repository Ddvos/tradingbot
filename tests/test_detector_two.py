"""Detector two: detector one's rule with levels that expire after 30 days (#16)."""

from tradingbot.candles import Candle
from tradingbot.detectors import (
    DETECTORS,
    LEVEL_LIFETIME,
    DetectorOne,
    DetectorTwo,
    FloorDetector,
    Level,
    Mark,
)
from tradingbot.turning_points import Kind, TurningPoint

H = 3600
DAY = 24 * H
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def candle(hour: int, high: float, low: float, close: float) -> Candle:
    return Candle(T0 + hour * H, close, high, low, close, 1.0, 1)


def point(kind: Kind, price: float, time: int, confirmed_at: int) -> TurningPoint:
    return TurningPoint(kind, time, price, confirmed_at)


def marks_of(
    detector: DetectorOne | DetectorTwo, candles: list[Candle], levels: list[TurningPoint]
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
FAILS_AT = T0 + 4 * H
TOP_MARK = Mark(Kind.TOP, FAILS_AT, 96.0)

FALL_THEN_FAIL = [
    candle(0, high=110.0, low=105.0, close=106.0),
    candle(1, high=109.0, low=104.0, close=105.0),  # lower low
    candle(2, high=108.0, low=103.0, close=104.0),  # lower low
    candle(3, high=107.0, low=102.0, close=103.0),  # lower low: a run of three
    candle(4, high=107.0, low=102.4, close=104.0),  # the first failed lower low
    candle(5, high=108.0, low=103.0, close=105.0),  # a higher low again, but no run before it
]


def test_a_level_is_seen_until_thirty_days_after_its_turning_points_candle() -> None:
    # The turning point's candle started exactly 30 days before the failing candle.
    born = FAILS_AT - LEVEL_LIFETIME
    level = point(Kind.TOP, 98.5, time=born, confirmed_at=born + H)

    assert marks_of(DetectorTwo(), RISE_THEN_FAIL, [level]) == [TOP_MARK]


def test_a_level_is_no_longer_seen_one_hour_after_its_thirty_days() -> None:
    born = FAILS_AT - LEVEL_LIFETIME - H
    level = point(Kind.TOP, 98.5, time=born, confirmed_at=born + H)

    assert marks_of(DetectorTwo(), RISE_THEN_FAIL, [level]) == []
    # Detector one, whose levels never expire, still sees it.
    assert marks_of(DetectorOne(), RISE_THEN_FAIL, [level]) == [TOP_MARK]


def test_age_is_calendar_time_from_the_extreme_not_from_the_confirmation() -> None:
    # Confirmed only 10 days before the failing candle, but the extreme is 31 days old.
    born = FAILS_AT - 31 * DAY
    level = point(Kind.TOP, 98.5, time=born, confirmed_at=FAILS_AT - 10 * DAY)

    assert marks_of(DetectorTwo(), RISE_THEN_FAIL, [level]) == []


def test_a_level_counts_from_the_candle_that_confirms_it() -> None:
    detector = DetectorTwo()
    confirmed_late = point(Kind.TOP, 98.5, time=T0 - DAY, confirmed_at=FAILS_AT)

    before = [detector.mark(RISE_THEN_FAIL[: i + 1], []) for i in range(4)]
    on_confirmation = detector.mark(RISE_THEN_FAIL[:5], [confirmed_late])

    assert before == [None, None, None, None]
    assert on_confirmation is Kind.TOP


def test_a_mark_does_not_use_up_a_level() -> None:
    # The same rise fails twice in the zone of one level, inside its 30 days: two marks.
    twice = RISE_THEN_FAIL + [
        candle(h + 6, c.high, c.low, c.close) for h, c in enumerate(RISE_THEN_FAIL)
    ]
    level = point(Kind.TOP, 98.5, time=T0 - DAY, confirmed_at=T0 - DAY + H)

    assert marks_of(DetectorTwo(), twice, [level]) == [
        TOP_MARK,
        Mark(Kind.TOP, T0 + 10 * H, 96.0),
    ]


def test_an_expired_level_stays_expired_when_newer_levels_arrive() -> None:
    expired = point(Kind.TOP, 98.5, time=T0 - 31 * DAY, confirmed_at=T0 - 31 * DAY + H)
    far_away = point(Kind.BOTTOM, 150.0, time=T0 - DAY, confirmed_at=T0 - DAY + H)

    assert marks_of(DetectorTwo(), RISE_THEN_FAIL, [expired, far_away]) == []


def test_within_its_thirty_days_a_level_works_exactly_as_in_detector_one() -> None:
    top = point(Kind.TOP, 98.5, time=T0 - DAY, confirmed_at=T0 - DAY + H)
    bottom = point(Kind.BOTTOM, 101.5, time=T0 - DAY, confirmed_at=T0 - DAY + H)

    for series in (RISE_THEN_FAIL, FALL_THEN_FAIL):
        assert marks_of(DetectorTwo(), series, [top, bottom]) == marks_of(
            DetectorOne(), series, [top, bottom]
        )
    assert marks_of(DetectorTwo(), FALL_THEN_FAIL, [bottom]) == [Mark(Kind.BOTTOM, FAILS_AT, 104.0)]
    assert marks_of(DetectorTwo(), RISE_THEN_FAIL, [bottom]) == []  # 101.5 is outside the zone


def test_the_decision_on_a_candle_never_depends_on_later_candles() -> None:
    levels = [
        point(Kind.TOP, 98.5, time=T0 - DAY, confirmed_at=T0 - DAY + H),
        point(Kind.BOTTOM, 101.5, time=T0 - DAY, confirmed_at=T0 - DAY + H),
    ]
    series = RISE_THEN_FAIL + [
        candle(h + 6, c.high, c.low, c.close) for h, c in enumerate(FALL_THEN_FAIL)
    ]
    whole = marks_of(DetectorTwo(), series, levels)

    assert len(whole) == 2
    for i in range(len(series)):
        assert marks_of(DetectorTwo(), series[: i + 1], levels) == [
            m for m in whole if m.time <= series[i].time
        ]


def test_the_levels_a_detector_reads_carry_the_span_of_candles_that_see_them() -> None:
    points = [
        point(Kind.TOP, 98.5, time=T0, confirmed_at=T0 + 5 * H),
        point(Kind.BOTTOM, 90.0, time=T0 + 10 * H, confirmed_at=T0 + 20 * H),
    ]

    assert DetectorTwo().levels(points) == [
        Level(Kind.TOP, 98.5, T0, active_from=T0 + 5 * H, active_until=T0 + LEVEL_LIFETIME),
        Level(
            Kind.BOTTOM,
            90.0,
            T0 + 10 * H,
            active_from=T0 + 20 * H,
            active_until=T0 + 10 * H + LEVEL_LIFETIME,
        ),
    ]
    assert DetectorOne().levels(points) == [
        Level(Kind.TOP, 98.5, T0, active_from=T0 + 5 * H, active_until=None),
        Level(Kind.BOTTOM, 90.0, T0 + 10 * H, active_from=T0 + 20 * H, active_until=None),
    ]
    assert FloorDetector().levels(points) == []


def test_the_lifetime_is_thirty_days_of_calendar_time() -> None:
    assert LEVEL_LIFETIME == 30 * DAY


def test_detector_two_is_registered_under_its_name() -> None:
    assert isinstance(DETECTORS["two"](), DetectorTwo)
