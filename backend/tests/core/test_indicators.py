from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from tradingbot.core.features.indicators import (
    atr,
    bollinger_width,
    ema,
    ma_slope,
    macd_histogram,
    obv,
    pct_return,
    rsi,
    sma,
    volume_vs_ma,
)
from tradingbot.core.features.temporal import day_of_week, hour_of_day
from tradingbot.core.ports.market_data import OHLCV_SCHEMA

type OhlcvFactory = Callable[[list[float]], pl.DataFrame]


def series(df: pl.DataFrame, expr: pl.Expr) -> list[float | None]:
    return df.select(expr.alias("x")).get_column("x").to_list()


def test_sma_known_values(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv([1.0, 2.0, 3.0, 4.0]), sma(2))
    assert values == [None, 1.5, 2.5, 3.5]


def test_ema_of_constant_series_is_constant(make_ohlcv: OhlcvFactory) -> None:
    assert series(make_ohlcv([5.0, 5.0, 5.0]), ema(2)) == [5.0, 5.0, 5.0]


def test_pct_return_known_values(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv([100.0, 110.0]), pct_return(1))
    assert values[0] is None
    assert values[1] == pytest.approx(0.1)


def test_ma_slope_positive_for_rising_prices(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv([1.0, 2.0, 3.0, 4.0, 5.0]), ma_slope(2, 1))
    assert values[-1] is not None
    assert values[-1] > 0


def test_atr_equals_bar_range_for_constant_range_bars() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    close = [100.0, 100.0, 100.0, 100.0]
    df = pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=i) for i in range(4)],
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [10.0] * 4,
        },
        schema=OHLCV_SCHEMA,
    )
    values = series(df, atr(14))
    assert values == pytest.approx([2.0, 2.0, 2.0, 2.0])


def test_rsi_is_100_for_only_gains(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv([1.0, 2.0, 3.0, 4.0]), rsi(2))
    assert values[-1] == pytest.approx(100.0)


def test_rsi_is_neutral_without_movement(make_ohlcv: OhlcvFactory) -> None:
    assert series(make_ohlcv([5.0, 5.0, 5.0]), rsi(2)) == [50.0, 50.0, 50.0]


def test_macd_histogram_is_zero_for_constant_series(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv([5.0] * 10), macd_histogram(3, 5, 2))
    assert values == pytest.approx([0.0] * 10)


def test_bollinger_width_is_zero_for_constant_series(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv([5.0, 5.0, 5.0]), bollinger_width(2))
    assert values[1:] == pytest.approx([0.0, 0.0])


def test_volume_vs_ma_is_one_for_constant_volume(make_ohlcv: OhlcvFactory) -> None:
    values = series(make_ohlcv([1.0, 2.0, 3.0]), volume_vs_ma(2))
    assert values[1:] == pytest.approx([1.0, 1.0])


def test_obv_accumulates_signed_volume(make_ohlcv: OhlcvFactory) -> None:
    # closes 1 -> 2 (up: +100), 2 -> 1 (down: -100), 1 -> 1 (unchanged: 0)
    values = series(make_ohlcv([1.0, 2.0, 1.0, 1.0]), obv())
    assert values == pytest.approx([0.0, 100.0, 0.0, 0.0])


def test_temporal_features(make_ohlcv: OhlcvFactory) -> None:
    df = make_ohlcv([1.0, 2.0])  # starts Monday 2024-01-01 00:00 UTC
    assert series(df, hour_of_day()) == [0, 1]
    assert series(df, day_of_week()) == [1, 1]
