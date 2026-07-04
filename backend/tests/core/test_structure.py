"""The make_ohlcv fixture derives high = close * 1.01 and low = close * 0.99,
so a close of 110 puts a swing-high candidate at 111.1. The two hand-crafted
sequences below have exactly two swing highs (peak bars 3 and 9, k = 3), each
confirmed 3 bars later — the confirmation lag is the property under test."""

from collections.abc import Callable

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from tradingbot.core.features.structure import (
    bars_since_swing_high,
    bars_since_swing_low,
    higher_high,
    higher_low,
    last_swing_high,
    last_swing_low,
    range_position,
)

type OhlcvFactory = Callable[[list[float]], pl.DataFrame]
type RandomOhlcvFactory = Callable[[int], pl.DataFrame]

RISING_PEAKS = [100.0, 101.0, 102.0, 110.0, 105.0, 103.0, 101.0, 104.0, 108.0, 115.0]
FALLING_PEAKS = [100.0, 101.0, 102.0, 115.0, 105.0, 103.0, 101.0, 104.0, 108.0, 110.0]
TAIL = [108.0, 104.0, 101.0, 100.0]


def series(df: pl.DataFrame, expr: pl.Expr) -> list[float | None]:
    return df.select(expr.alias("x")).get_column("x").to_list()


def test_swing_high_confirms_k_bars_after_the_peak(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv(RISING_PEAKS + TAIL), last_swing_high(3))

    assert values[:6] == [None] * 6  # peak at bar 3 is not knowable before bar 6
    assert values[6] == pytest.approx(110.0 * 1.01)
    assert values[11] == pytest.approx(110.0 * 1.01)  # second peak (bar 9) not confirmed yet
    assert values[12] == pytest.approx(115.0 * 1.01)


def test_swing_low_confirms_k_bars_after_the_trough(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv(RISING_PEAKS + TAIL), last_swing_low(3))

    assert values[:9] == [None] * 9  # trough at bar 6 confirms at bar 9
    assert values[9] == pytest.approx(101.0 * 0.99)
    assert values[13] == pytest.approx(101.0 * 0.99)  # final decline never confirms a new low


def test_higher_high_needs_two_confirmed_swings(make_ohlcv: OhlcvFactory) -> None:
    rising = series(make_ohlcv(RISING_PEAKS + TAIL), higher_high(3))
    falling = series(make_ohlcv(FALLING_PEAKS + TAIL), higher_high(3))

    assert rising[:12] == [None] * 12  # one swing high alone says nothing about structure
    assert rising[12:] == [1.0, 1.0]  # 115 above 110: making higher highs
    assert falling[12:] == [0.0, 0.0]  # 110 below 115: structure broken


def test_higher_low_stays_null_with_a_single_swing_low(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv(RISING_PEAKS + TAIL), higher_low(3))

    assert values == [None] * 14


def test_bars_since_swing_high_counts_from_the_peak_bar(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv(RISING_PEAKS + TAIL), bars_since_swing_high(3))

    assert values[5] is None
    assert values[6] == 3.0  # confirmation bar: the peak itself is 3 bars back
    assert values[11] == 8.0
    assert values[12] == 3.0  # resets to the newly confirmed peak at bar 9


def test_bars_since_swing_low_counts_from_the_trough_bar(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv(RISING_PEAKS + TAIL), bars_since_swing_low(3))

    assert values[8] is None
    assert values[9] == 3.0
    assert values[13] == 7.0


def test_range_position_places_close_between_the_swing_levels(
    make_ohlcv: OhlcvFactory,
) -> None:
    values = series(make_ohlcv(RISING_PEAKS + TAIL), range_position(3))

    assert values[8] is None  # no confirmed swing low yet
    low, high = 101.0 * 0.99, 115.0 * 1.01
    assert values[12] == pytest.approx((101.0 - low) / (high - low))


def test_no_lookahead_truncating_future_does_not_change_the_past(
    make_random_ohlcv: RandomOhlcvFactory,
) -> None:
    """The flagship leakage check, as in test_dataset: a confirmed swing may
    never appear earlier than its confirmation bar allows."""
    expressions = {
        "sh": last_swing_high(3),
        "sl": last_swing_low(3),
        "hh": higher_high(3),
        "hl": higher_low(3),
        "range_pos": range_position(3),
        "since_sh": bars_since_swing_high(3),
        "since_sl": bars_since_swing_low(3),
    }
    ohlcv = make_random_ohlcv(300)
    full = ohlcv.with_columns(**expressions).select(expressions.keys())
    partial = ohlcv.head(250).with_columns(**expressions).select(expressions.keys())

    assert_frame_equal(partial, full.head(250))
