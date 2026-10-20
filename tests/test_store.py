"""The SQLite candle store: hourly candles in, hourly candles out, no duplicates."""

from pathlib import Path

import pytest

from tradingbot.candles import Candle, Timeframe
from tradingbot.store import CandleStore

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def three_hours() -> list[Candle]:
    return [
        Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.0, 10),
        Candle(T0 + H, 105.0, 120.0, 100.0, 115.0, 2.0, 20),
        Candle(T0 + 2 * H, 115.0, 118.0, 90.0, 92.0, 3.0, 30),
    ]


def test_stored_candles_are_read_back_in_time_order() -> None:
    store = CandleStore(":memory:")

    stored = store.upsert(reversed(three_hours()))

    assert stored == 3
    assert store.read() == three_hours()
    assert store.time_range() == (T0, T0 + 2 * H)


def test_storing_the_same_candles_again_adds_no_rows() -> None:
    store = CandleStore(":memory:")
    store.upsert(three_hours())

    stored_again = store.upsert(three_hours())

    assert stored_again == 0
    assert store.count() == 3


def test_read_can_be_limited_to_a_time_range() -> None:
    store = CandleStore(":memory:")
    store.upsert(three_hours())

    in_range = store.read(start=T0 + H, end=T0 + H)

    assert in_range == [Candle(T0 + H, 105.0, 120.0, 100.0, 115.0, 2.0, 20)]


def test_an_empty_store_has_no_time_range() -> None:
    store = CandleStore(":memory:")

    assert store.time_range() is None
    assert store.read() == []


Q = 900


def test_a_fifteen_minute_store_keeps_its_own_table_next_to_the_hourly_one(
    tmp_path: Path,
) -> None:
    db = tmp_path / "candles.sqlite"
    quarters = [
        Candle(T0, 100.0, 104.0, 99.0, 103.0, 1.0, 10),
        Candle(T0 + Q, 103.0, 108.0, 102.0, 107.0, 2.0, 20),
    ]
    with CandleStore(db, Timeframe.M15) as fifteen, CandleStore(db, Timeframe.H1) as hourly:
        assert fifteen.timeframe is Timeframe.M15
        assert fifteen.upsert(quarters) == 2
        hourly.upsert(three_hours())

        assert fifteen.read() == quarters
        assert fifteen.time_range() == (T0, T0 + Q)
        assert hourly.read() == three_hours()
        assert hourly.count() == 3


def test_a_store_defaults_to_hourly_candles() -> None:
    assert CandleStore(":memory:").timeframe is Timeframe.H1


def test_only_fifteen_minute_and_hourly_candles_are_stored() -> None:
    with pytest.raises(ValueError, match="4h"):
        CandleStore(":memory:", Timeframe.H4)
