"""The out-of-sample boundary and the development period.

Development data is every stored candle, fifteen-minute or hourly, that starts
before the boundary. Every development entry point (the API, the batch replay,
the re-scoring, the hourly check) reads candles through `read_development`,
which clamps the window to the boundary in code, so no command can read past
it by accident. Out-of-sample runs go through a separate, explicit command that
logs each use (slice 3, #12).
"""

from __future__ import annotations

from tradingbot.candles import Candle
from tradingbot.store import CandleStore

OUT_OF_SAMPLE_BOUNDARY = 1_729_296_000
"""2024-10-19T00:00:00Z, fixed in slice 2 (#11). Candles from this hour on are
out of sample; the development period ends with the hour before it."""


def development_end(end: int | None) -> int:
    """`end` clamped to the last second of the development period, so a candle of any
    stored timeframe is read only when it starts before the boundary."""
    last = OUT_OF_SAMPLE_BOUNDARY - 1
    return last if end is None else min(end, last)


def read_development(
    store: CandleStore, start: int | None = None, end: int | None = None
) -> list[Candle]:
    """The store's candles in the development period, oldest first, never past the boundary."""
    return store.read(start, development_end(end))
