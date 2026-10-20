"""The out-of-sample boundary: development code never reads candles past it."""

from tradingbot.candles import Candle, Timeframe
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY, read_development
from tradingbot.store import CandleStore

H = 3600


def flat(time: int) -> Candle:
    return Candle(time, 100.0, 100.0, 100.0, 100.0, 1.0, 1)


def store_around_the_boundary() -> CandleStore:
    store = CandleStore(":memory:")
    store.upsert(flat(OUT_OF_SAMPLE_BOUNDARY + offset * H) for offset in range(-3, 3))
    return store


def test_the_boundary_is_2024_10_19_utc() -> None:
    assert OUT_OF_SAMPLE_BOUNDARY == 1_729_296_000


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
