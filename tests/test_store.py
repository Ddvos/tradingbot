"""The SQLite candle store: hourly candles in, hourly candles out, no duplicates."""

from tradingbot.candles import Candle
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


def test_read_can_be_limited_to_a_time_window() -> None:
    store = CandleStore(":memory:")
    store.upsert(three_hours())

    window = store.read(start=T0 + H, end=T0 + H)

    assert window == [Candle(T0 + H, 105.0, 120.0, 100.0, 115.0, 2.0, 20)]


def test_an_empty_store_has_no_time_range() -> None:
    store = CandleStore(":memory:")

    assert store.time_range() is None
    assert store.read() == []
