"""The out-of-sample boundary: development code never reads candles past it."""

from tradingbot.candles import Candle, Timeframe, iso
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY, development_end, read_development
from tradingbot.store import CandleStore

H = 3600


def flat(time: int) -> Candle:
    return Candle(time, 100.0, 100.0, 100.0, 100.0, 1.0, 1)


def store_around_the_boundary() -> CandleStore:
    store = CandleStore(":memory:")
    store.upsert(flat(OUT_OF_SAMPLE_BOUNDARY + offset * H) for offset in range(-3, 3))
    return store


def test_the_boundary_is_2025_01_01_utc() -> None:
    # Moved from 2024-10-19 by ADR-0009 (slice 10), so the third era is the whole of 2022
    # to 2024; nothing from here on grades anything.
    assert OUT_OF_SAMPLE_BOUNDARY == 1_735_689_600
    assert iso(OUT_OF_SAMPLE_BOUNDARY) == "2025-01-01T00:00:00Z"


def test_the_development_period_ends_with_the_last_quarter_of_2024() -> None:
    quarter = 900
    store = CandleStore(":memory:", Timeframe.M15)
    store.upsert(flat(OUT_OF_SAMPLE_BOUNDARY + offset * quarter) for offset in range(-2, 2))

    candles = read_development(store)

    assert iso(candles[-1].time) == "2024-12-31T23:45:00Z"
    assert iso(development_end(None)) == "2024-12-31T23:59:59Z"


def test_development_reads_stop_before_the_boundary() -> None:
    candles = read_development(store_around_the_boundary())

    assert [c.time for c in candles] == [
        OUT_OF_SAMPLE_BOUNDARY - 3 * H,
        OUT_OF_SAMPLE_BOUNDARY - 2 * H,
        OUT_OF_SAMPLE_BOUNDARY - H,
    ]


def test_an_end_past_the_boundary_is_clamped_to_it() -> None:
    candles = read_development(store_around_the_boundary(), end=OUT_OF_SAMPLE_BOUNDARY + 10 * H)

    assert candles[-1].time == OUT_OF_SAMPLE_BOUNDARY - H


def test_a_window_entirely_past_the_boundary_is_empty() -> None:
    assert read_development(store_around_the_boundary(), start=OUT_OF_SAMPLE_BOUNDARY) == []


def test_a_window_before_the_boundary_is_honoured() -> None:
    candles = read_development(
        store_around_the_boundary(),
        start=OUT_OF_SAMPLE_BOUNDARY - 2 * H,
        end=OUT_OF_SAMPLE_BOUNDARY - 2 * H,
    )

    assert [c.time for c in candles] == [OUT_OF_SAMPLE_BOUNDARY - 2 * H]


def test_the_clamp_holds_for_fifteen_minute_candles_too() -> None:
    quarter = 900
    store = CandleStore(":memory:", Timeframe.M15)
    store.upsert(flat(OUT_OF_SAMPLE_BOUNDARY + offset * quarter) for offset in range(-3, 3))

    candles = read_development(store, end=OUT_OF_SAMPLE_BOUNDARY + 10 * quarter)

    assert [c.time for c in candles] == [
        OUT_OF_SAMPLE_BOUNDARY - 3 * quarter,
        OUT_OF_SAMPLE_BOUNDARY - 2 * quarter,
        OUT_OF_SAMPLE_BOUNDARY - quarter,
    ]
