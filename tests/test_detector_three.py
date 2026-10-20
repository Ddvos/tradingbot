"""Detector three: the swing rule on fifteen-minute candles (#20), family two's first iteration.

Every series is hand-built. A turning point is handed to the detector from the
fifteen-minute candle that completes its confirming hour on, as the replay does
(ADR-0006); a turning point confirmed before the series is known from the first
candle, so the series' own lows and highs make the swing.
"""

from bisect import bisect_left
from collections.abc import Callable

from tests.walks import quarter_walk
from tradingbot.candles import Candle
from tradingbot.detectors import DETECTORS, DetectorThree, Mark, SwingExtreme
from tradingbot.replay import replay_all, run
from tradingbot.turning_points import Kind, TurningPoint

Q = 900
H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def candle(quarter: int, high: float, low: float, close: float) -> Candle:
    return Candle(T0 + quarter * Q, close, high, low, close, 1.0, 1)


Known = Callable[[list[TurningPoint], Candle], list[TurningPoint]]


def known_on(points: list[TurningPoint], latest: Candle) -> list[TurningPoint]:
    """The turning points known on `latest`: those confirmed by an hour it completes or an
    earlier one, as the replay hands them over."""
    return [p for p in points if p.confirmed_at + H <= latest.time + Q]


def leaked_on(points: list[TurningPoint], latest: Candle) -> list[TurningPoint]:
    """The turning points a leaky replay would hand over: known from the first candle of
    the confirming hour, before that hour has completed."""
    return [p for p in points if p.confirmed_at <= latest.time]


def marks_of(
    detector: DetectorThree,
    candles: list[Candle],
    points: list[TurningPoint],
    known: Known = known_on,
) -> list[Mark]:
    """Hand the detector the candles one at a time, as replay does, and collect its marks."""
    marks: list[Mark] = []
    for i, latest in enumerate(candles):
        kind = detector.mark(candles[: i + 1], known(points, latest))
        if kind is not None:
            marks.append(Mark(kind, latest.time, latest.close))
    return marks


TOP_BEFORE = TurningPoint(Kind.TOP, T0 - 2 * H, 120.0, confirmed_at=T0 - H)
"""A top confirmed before the series: the swing low is the series' lowest low so far."""

RISE = [
    candle(0, high=101.0, low=100.0, close=100.5),  # the swing low, 100, holds the first extreme
    candle(1, high=104.0, low=101.0, close=103.0),  # a new extreme
    candle(2, high=103.0, low=101.0, close=102.0),  # short of it, but the swing is 4%
    candle(3, high=107.9, low=102.0, close=107.0),  # a new extreme, 7.9% above the swing low
    candle(4, high=107.0, low=104.0, close=106.0),  # short of it, the swing still under 8%
    candle(5, high=108.0, low=105.0, close=107.5),  # a new extreme, exactly 8% above the swing low
    candle(6, high=107.5, low=106.0, close=107.0),  # the first candle short of it: a top mark
    candle(7, high=107.8, low=106.0, close=107.5),  # short of it again, but the mark disarmed
    candle(8, high=109.0, low=107.0, close=108.5),  # a new extreme arms again
    candle(9, high=108.0, low=106.0, close=107.0),  # short of it: a top mark
    candle(10, high=108.5, low=105.0, close=106.0),  # disarmed
]
FIRST_TOP = Mark(Kind.TOP, T0 + 6 * Q, 107.0)
SECOND_TOP = Mark(Kind.TOP, T0 + 9 * Q, 107.0)


def test_no_mark_while_the_swing_is_under_the_reversal_size() -> None:
    assert marks_of(DetectorThree(), RISE[:5], [TOP_BEFORE]) == []


def test_the_first_candle_short_of_a_new_extreme_is_marked_and_the_next_one_is_not() -> None:
    assert marks_of(DetectorThree(), RISE[:8], [TOP_BEFORE]) == [FIRST_TOP]


def test_a_new_extreme_arms_again() -> None:
    assert marks_of(DetectorThree(), RISE, [TOP_BEFORE]) == [FIRST_TOP, SECOND_TOP]


NEW_SWING_LOW = RISE + [
    candle(11, high=106.0, low=95.0, close=96.0),  # a new swing low: the extreme restarts at 106
    candle(12, high=105.0, low=96.0, close=100.0),  # short of 106, which is 11.6% above 95: a mark
]


def test_a_new_swing_low_re_arms_and_restarts_the_extreme_at_its_candle() -> None:
    assert marks_of(DetectorThree(), NEW_SWING_LOW, [TOP_BEFORE]) == [
        FIRST_TOP,
        SECOND_TOP,
        Mark(Kind.TOP, T0 + 12 * Q, 100.0),
    ]


BOTTOM_BEFORE = TurningPoint(Kind.BOTTOM, T0 - 2 * H, 80.0, confirmed_at=T0 - H)


def test_before_a_top_is_confirmed_there_is_no_swing_low_and_no_top_mark() -> None:
    assert marks_of(DetectorThree(), NEW_SWING_LOW, []) == []
    # A confirmed bottom starts the bottom side only, and the rise never falls 8%.
    assert marks_of(DetectorThree(), RISE, [BOTTOM_BEFORE]) == []


RESET = [
    candle(0, high=91.0, low=90.0, close=90.5),  # hour 0: the swing low, 90
    candle(1, high=93.0, low=91.0, close=92.0),
    candle(2, high=95.0, low=92.0, close=94.0),
    candle(3, high=97.0, low=94.0, close=96.0),
    candle(4, high=99.0, low=96.0, close=98.0),  # hour 1
    candle(5, high=100.0, low=97.0, close=99.0),  # the extreme, 100, 11% above the swing low
    candle(6, high=99.5, low=98.0, close=99.0),  # short of it: a top mark
    candle(7, high=99.0, low=97.0, close=98.0),
    candle(8, high=98.0, low=93.0, close=94.0),  # hour 2 falls 8% from 100: hour 1 holds a top
    candle(9, high=95.0, low=92.0, close=93.0),  # the hour's low, 92
    candle(10, high=94.0, low=92.5, close=93.0),
    candle(11, high=94.5, low=93.0, close=94.0),  # completes hour 2: the top is known
    # From here the swing low is 92, the lowest low since hour 1, and the extreme is 95 (09).
    candle(12, high=95.0, low=94.0, close=94.5),  # equals the extreme: not short of it
    candle(13, high=99.5, low=95.0, close=99.0),  # a new extreme, 8.2% above 92
    candle(14, high=99.0, low=97.0, close=98.0),  # short of it: a top mark
]
TOP_AT_HOUR_ONE = TurningPoint(Kind.TOP, T0 + H, 100.0, confirmed_at=T0 + 2 * H)
"""Confirmed by hour 2, so known from the candle that completes it, 02:45."""


def test_a_confirmed_top_resets_the_swing_low_to_the_lowest_low_since_its_hour() -> None:
    # Without the reset the side stays disarmed since 01:30 and 99.5 is short of 100; with
    # the swing low counted from the confirming candle instead (93) the swing is 7%.
    assert marks_of(DetectorThree(), RESET, [TOP_BEFORE, TOP_AT_HOUR_ONE]) == [
        Mark(Kind.TOP, T0 + 6 * Q, 99.0),
        Mark(Kind.TOP, T0 + 14 * Q, 98.0),
    ]


def mirror(candles: list[Candle]) -> list[Candle]:
    """The series reflected around 100: every high becomes a low as far below as it was above."""
    return [
        Candle(c.time, 200 - c.close, 200 - c.low, 200 - c.high, 200 - c.close, c.volume, c.trades)
        for c in candles
    ]


def test_bottoms_are_the_mirror_image() -> None:
    # 92 is exactly 8% below the swing high of 100; 94 is 10.5% below the new swing high, 105.
    assert marks_of(DetectorThree(), mirror(NEW_SWING_LOW), [BOTTOM_BEFORE]) == [
        Mark(Kind.BOTTOM, T0 + 6 * Q, 93.0),
        Mark(Kind.BOTTOM, T0 + 9 * Q, 93.0),
        Mark(Kind.BOTTOM, T0 + 12 * Q, 100.0),
    ]
    assert marks_of(DetectorThree(), mirror(NEW_SWING_LOW), [TOP_BEFORE]) == [
        Mark(Kind.TOP, T0 + 12 * Q, 100.0)  # the last two candles rise 12.8%, from 91 to 105
    ]


BOTH_KNOWN = [TOP_BEFORE, BOTTOM_BEFORE]

UP_SWING_LARGER = [
    candle(0, high=100.0, low=100.0, close=100.0),  # the swing low and the swing high, 100
    candle(1, high=112.0, low=90.0, close=101.0),  # a new swing low and a new swing high: both arm
    candle(2, high=105.0, low=95.0, close=100.0),  # short of both: 90 to 112 is 24%, 112 to 90 20%
    candle(3, high=104.0, low=96.0, close=101.0),  # the bottom side kept its arming
]

DOWN_SWING_LARGER = [
    candle(0, high=130.0, low=110.0, close=120.0),  # the swing high, 130, and the swing low, 110
    candle(1, high=120.0, low=100.0, close=110.0),  # a new swing low restarts the extreme at 120
    candle(2, high=115.0, low=105.0, close=110.0),  # short of both: 100 to 120 20%, 130 to 100 23%
    candle(3, high=118.0, low=104.0, close=112.0),  # the top side kept its arming
]


def test_when_one_candle_qualifies_for_both_the_larger_swing_in_percent_wins() -> None:
    assert marks_of(DetectorThree(), UP_SWING_LARGER, BOTH_KNOWN) == [
        Mark(Kind.TOP, T0 + 2 * Q, 100.0),
        Mark(Kind.BOTTOM, T0 + 3 * Q, 101.0),
    ]
    assert marks_of(DetectorThree(), DOWN_SWING_LARGER, BOTH_KNOWN) == [
        Mark(Kind.BOTTOM, T0 + 2 * Q, 110.0),
        Mark(Kind.TOP, T0 + 3 * Q, 112.0),
    ]


EQUAL_SWINGS = [
    candle(0, high=125.0, low=110.0, close=120.0),  # the swing high, 125
    candle(1, high=120.0, low=100.0, close=110.0),  # the swing low, 100, with the extreme at 120
    candle(2, high=115.0, low=105.0, close=110.0),  # short of both, and both swings are 20%
    candle(3, high=118.0, low=104.0, close=110.0),  # still short of both, still equal
    candle(4, high=121.0, low=106.0, close=118.0),  # a new extreme on the top side only
]


def test_equal_swings_give_no_mark_and_disarm_nothing() -> None:
    assert marks_of(DetectorThree(), EQUAL_SWINGS[:4], BOTH_KNOWN) == []
    # The bottom side is still armed, and the candle is short of its extreme alone.
    assert marks_of(DetectorThree(), EQUAL_SWINGS, BOTH_KNOWN) == [
        Mark(Kind.BOTTOM, T0 + 4 * Q, 118.0)
    ]


LATE_TOP = RESET[:8] + [
    candle(8, high=98.0, low=92.0, close=93.0),  # hour 2's low, 8% below 100: hour 1 holds a top
    candle(9, high=99.5, low=93.0, close=99.0),  # 8.2% above 92
    candle(10, high=99.0, low=95.0, close=97.0),  # short of 99.5
    candle(11, high=98.0, low=96.0, close=97.0),  # completes hour 2: the top is known; short too
]


def test_a_turning_point_is_read_from_the_candle_that_completes_its_hour_not_before() -> None:
    # Handed the top on hour 2's first candle, the detector would know the swing low of 92
    # and the extreme of 99.5 a candle early and mark 02:30; handed it on 02:45, as the
    # replay does, it recomputes the same swing then and marks 02:45.
    assert marks_of(DetectorThree(), LATE_TOP, [TOP_AT_HOUR_ONE], known=leaked_on) == [
        Mark(Kind.TOP, T0 + 10 * Q, 97.0)
    ]
    assert marks_of(DetectorThree(), LATE_TOP, [TOP_AT_HOUR_ONE]) == [
        Mark(Kind.TOP, T0 + 11 * Q, 97.0)
    ]
    assert [(m.kind, m.time) for m in run(LATE_TOP, DetectorThree()).marks] == [
        (Kind.BOTTOM, T0 + 9 * Q),  # 92 is 8% below the swing high of 100, known since 01:45
        (Kind.TOP, T0 + 11 * Q),
    ]


def extremes_of(candles: list[Candle], points: list[TurningPoint]) -> list[SwingExtreme]:
    detector = DetectorThree()
    marks_of(detector, candles, points)
    return detector.swing_extremes()


def test_every_swing_extreme_is_recorded_with_the_candles_that_read_it() -> None:
    assert extremes_of(RISE[:8], [TOP_BEFORE]) == [
        SwingExtreme(Kind.TOP, 101.0, time=T0, active_from=T0, active_until=T0),
        SwingExtreme(Kind.TOP, 104.0, T0 + Q, active_from=T0 + Q, active_until=T0 + 2 * Q),
        SwingExtreme(Kind.TOP, 107.9, T0 + 3 * Q, active_from=T0 + 3 * Q, active_until=T0 + 4 * Q),
        SwingExtreme(Kind.TOP, 108.0, T0 + 5 * Q, active_from=T0 + 5 * Q, active_until=None),
    ]


def test_a_confirmed_top_makes_the_detector_read_an_extreme_set_on_an_earlier_candle() -> None:
    # On 02:45 the swing low moves to 02:15's low, so the extreme is 02:15's high, 95, read
    # from 02:45 until 03:00, whose high equals it; 03:15 then sets a new one.
    extremes = extremes_of(RESET, [TOP_BEFORE, TOP_AT_HOUR_ONE])

    assert extremes[5:] == [
        SwingExtreme(Kind.TOP, 100.0, T0 + 5 * Q, active_from=T0 + 5 * Q, active_until=T0 + 10 * Q),
        SwingExtreme(Kind.TOP, 95.0, T0 + 9 * Q, active_from=T0 + 11 * Q, active_until=T0 + 12 * Q),
        SwingExtreme(Kind.TOP, 99.5, T0 + 13 * Q, active_from=T0 + 13 * Q, active_until=None),
    ]
    assert [e.price for e in extremes[:5]] == [91.0, 93.0, 95.0, 97.0, 99.0]


def test_detector_three_reads_fifteen_minute_candles_and_no_levels() -> None:
    detector = DETECTORS["three"]()

    assert isinstance(detector, DetectorThree)
    assert detector.timeframe.value == "15m"
    assert detector.levels([TOP_BEFORE]) == []
    assert detector.swing_extremes() == []


def test_a_replay_hands_detector_three_the_turning_points_as_their_hours_complete() -> None:
    # Hour 1's high of 100 is a top once hour 2 falls to 92, and hour 0's low of 90 a bottom
    # once hour 1 rises to 100; the replay confirms them on 01:45 and 02:45, and hour 2's
    # low becomes a bottom on the last candle, which completes hour 3. No top is known
    # before 02:45, so the 01:30 mark of the hand-fed series is not placed.
    result = run(RESET, DetectorThree())

    assert [(p.kind, p.time, p.price) for p in result.turning_points] == [
        (Kind.BOTTOM, T0, 90.0),
        (Kind.TOP, T0 + H, 100.0),
        (Kind.BOTTOM, T0 + 2 * H, 92.0),
    ]
    assert [(m.kind, m.time, m.price) for m in result.marks] == [
        (Kind.BOTTOM, T0 + 10 * Q, 93.0),  # 92 is 8% below 100, the swing high since 00:00
        (Kind.TOP, T0 + 14 * Q, 98.0),
    ]
    assert result.score.hits == 2
    assert result.swing_extremes == [
        SwingExtreme(
            Kind.BOTTOM, 97.0, T0 + 5 * Q, active_from=T0 + 7 * Q, active_until=T0 + 7 * Q
        ),
        SwingExtreme(
            Kind.BOTTOM, 93.0, T0 + 8 * Q, active_from=T0 + 8 * Q, active_until=T0 + 8 * Q
        ),
        SwingExtreme(
            Kind.BOTTOM, 92.0, T0 + 9 * Q, active_from=T0 + 9 * Q, active_until=T0 + 13 * Q
        ),
        SwingExtreme(Kind.TOP, 95.0, T0 + 9 * Q, active_from=T0 + 11 * Q, active_until=T0 + 12 * Q),
        SwingExtreme(Kind.TOP, 99.5, T0 + 13 * Q, active_from=T0 + 13 * Q, active_until=None),
        SwingExtreme(Kind.BOTTOM, 95.0, T0 + 13 * Q, active_from=T0 + 14 * Q, active_until=None),
    ]


def hindsight_walk(quarters: list[Candle], points: list[TurningPoint]) -> list[tuple[Kind, int]]:
    """The swing rule as `fifteen_pullback2.py` measured it at depth 0, the script recorded
    on #20, ported without the scoring-period filter: the kind and time of every event.

    The script records both sides on one candle where the detector's tie rule
    keeps one, so a series the port is compared on must hold no such candle.
    """
    times = [c.time for c in quarters]
    known = sorted(points, key=lambda p: p.confirmed_at)
    next_known = 0
    up: tuple[float, float] | None = None  # swing low, highest high since it
    down: tuple[float, float] | None = None  # swing high, lowest low since it
    armed_up = armed_down = False
    events: list[tuple[Kind, int]] = []
    for j, c in enumerate(quarters):
        while next_known < len(known) and known[next_known].confirmed_at + H <= c.time + Q:
            p = known[next_known]
            next_known += 1
            seg = quarters[bisect_left(times, p.time) : j + 1]
            if p.kind is Kind.TOP:
                k = min(range(len(seg)), key=lambda i: seg[i].low)
                up = (seg[k].low, max(x.high for x in seg[k:]))
                armed_up = True
            else:
                k = max(range(len(seg)), key=lambda i: seg[i].high)
                down = (seg[k].high, min(x.low for x in seg[k:]))
                armed_down = True
        if up is not None:
            if c.low < up[0]:
                up, armed_up = (c.low, c.high), True
            elif c.high > up[1]:
                up, armed_up = (up[0], c.high), True
        if down is not None:
            if c.high > down[0]:
                down, armed_down = (c.high, c.low), True
            elif c.low < down[1]:
                down, armed_down = (down[0], c.low), True
        if up is not None and armed_up and c.high < up[1] and up[1] >= up[0] * 1.08:
            events.append((Kind.TOP, c.time))
            armed_up = False
        if down is not None and armed_down and c.low > down[1] and down[1] <= down[0] * 0.92:
            events.append((Kind.BOTTOM, c.time))
            armed_down = False
    return events


def test_the_marks_are_the_events_of_the_pre_registered_hindsight_walk() -> None:
    quarters = quarter_walk(hours=4000, seed=26)

    replayed = replay_all(quarters, DetectorThree())

    events = hindsight_walk(quarters, replayed.turning_points)
    assert len(events) > 200, "the walk should hold many swings"
    assert len({time for _, time in events}) == len(events), "no candle qualifies for both"
    assert [(m.kind, m.time) for m in replayed.marks] == events
