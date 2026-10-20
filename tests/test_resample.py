"""Resampling hourly candles into 4-hour and daily candles, UTC-aligned."""

from tradingbot.candles import Candle, Timeframe, resample

H = 3600
DAY_START = 1_704_067_200  # 2024-01-01T00:00:00Z


def hourly_series_with_missing_hour() -> list[Candle]:
    """Eight hours of 2024-01-01 with 02:00 missing (no trades that hour)."""
    rows = [
        (0, 100.0, 110.0, 95.0, 105.0, 1.0, 10),
        (1, 105.0, 120.0, 100.0, 115.0, 2.0, 20),
        # 02:00 has no candle
        (3, 115.0, 118.0, 90.0, 92.0, 3.0, 30),
        (4, 92.0, 100.0, 91.0, 99.0, 4.0, 40),
        (5, 99.0, 101.0, 98.0, 100.0, 5.0, 50),
        (6, 100.0, 130.0, 99.0, 125.0, 6.0, 60),
        (7, 125.0, 126.0, 120.0, 121.0, 7.0, 70),
    ]
    return [
        Candle(DAY_START + hour * H, o, h, lo, c, volume, trades)
        for hour, o, h, lo, c, volume, trades in rows
    ]


def test_four_hour_candles_span_a_missing_hour() -> None:
    candles = resample(hourly_series_with_missing_hour(), Timeframe.H4)

    assert candles == [
        Candle(DAY_START, 100.0, 120.0, 90.0, 92.0, 6.0, 60),
        Candle(DAY_START + 4 * H, 92.0, 130.0, 91.0, 121.0, 22.0, 220),
    ]


def test_daily_candle_covers_the_whole_day() -> None:
    candles = resample(hourly_series_with_missing_hour(), Timeframe.D1)

    assert candles == [Candle(DAY_START, 100.0, 130.0, 90.0, 121.0, 28.0, 280)]


Q = 900  # a quarter of an hour
HOUR_START = DAY_START + 9 * H  # 2024-01-01T09:00:00Z


def fifteen_minute_hour_with_missing_quarter() -> list[Candle]:
    """09:00, 09:15 and 09:45 of 2024-01-01; 09:30 had no trades."""
    rows = [
        (0, 100.0, 104.0, 99.0, 103.0, 1.0, 10),
        (1, 103.0, 108.0, 102.0, 107.0, 2.0, 20),
        # 09:30 has no candle
        (3, 107.0, 107.5, 101.0, 102.0, 4.0, 40),
    ]
    return [
        Candle(HOUR_START + quarter * Q, o, h, lo, c, volume, trades)
        for quarter, o, h, lo, c, volume, trades in rows
    ]


def test_four_fifteen_minute_candles_make_one_hourly_candle() -> None:
    quarters = [
        Candle(HOUR_START, 100.0, 104.0, 99.0, 103.0, 1.0, 10),
        Candle(HOUR_START + Q, 103.0, 108.0, 102.0, 107.0, 2.0, 20),
        Candle(HOUR_START + 2 * Q, 107.0, 110.0, 105.0, 106.0, 3.0, 30),
        Candle(HOUR_START + 3 * Q, 106.0, 107.5, 101.0, 102.0, 4.0, 40),
    ]

    assert resample(quarters, Timeframe.H1) == [
        Candle(HOUR_START, 100.0, 110.0, 99.0, 102.0, 10.0, 100)
    ]


def test_an_hourly_candle_spans_a_missing_quarter() -> None:
    hourly = resample(fifteen_minute_hour_with_missing_quarter(), Timeframe.H1)

    assert hourly == [Candle(HOUR_START, 100.0, 108.0, 99.0, 102.0, 7.0, 70)]


def test_the_fifteen_minute_timeframe_is_nine_hundred_seconds() -> None:
    assert Timeframe.M15.value == "15m"
    assert Timeframe.M15.seconds == 900
    assert Timeframe.M15.label == "15-minute"
    assert Timeframe.H1.label == "hourly"
