"""Pytest configuration root for the tradingbot backend.

Shared fixtures are added here as slices introduce them (see ROADMAP.md).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from tradingbot.core.ports.market_data import OHLCV_SCHEMA


@pytest.fixture
def make_ohlcv() -> Callable[[list[float]], pl.DataFrame]:
    """Factory for valid hourly OHLCV frames from a list of closes."""

    def _make(closes: list[float]) -> pl.DataFrame:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        return pl.DataFrame(
            {
                "timestamp": [start + timedelta(hours=i) for i in range(len(closes))],
                "open": closes,
                "high": [c * 1.01 for c in closes],
                "low": [c * 0.99 for c in closes],
                "close": closes,
                "volume": [100.0] * len(closes),
            },
            schema=OHLCV_SCHEMA,
        )

    return _make
