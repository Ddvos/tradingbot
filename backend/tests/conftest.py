"""Pytest configuration root for the tradingbot backend.

Shared fixtures are added here as slices introduce them (see ROADMAP.md).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from tradingbot.core.models.artifact import ModelArtifact
from tradingbot.core.models.train import train_model
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


@pytest.fixture
def make_random_ohlcv() -> Callable[[int], pl.DataFrame]:
    """Factory for a deterministic random-walk OHLCV frame (seeded), for ML tests."""

    def _make(n: int) -> pl.DataFrame:
        rng = np.random.default_rng(seed=42)
        closes = 100.0 + np.cumsum(rng.normal(0.0, 0.5, n))
        spread = rng.uniform(0.2, 1.0, n)
        start = datetime(2024, 1, 1, tzinfo=UTC)
        return pl.DataFrame(
            {
                "timestamp": [start + timedelta(hours=i) for i in range(n)],
                "open": closes,
                "high": closes + spread,
                "low": closes - spread,
                "close": closes,
                "volume": rng.uniform(50.0, 150.0, n),
            },
            schema=OHLCV_SCHEMA,
        )

    return _make


@pytest.fixture(scope="session")
def ml_artifact() -> ModelArtifact:
    """A small trained artifact (f1 determines the label, f2 is noise)."""
    n = 400
    start = datetime(2024, 1, 1, tzinfo=UTC)
    f1 = [float((i % 10) - 5) for i in range(n)]
    dataset = pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=i) for i in range(n)],
            "f1": f1,
            "f2": [((i * 7) % 13) / 13 for i in range(n)],
            "label": pl.Series([1 if v > 0 else 0 for v in f1], dtype=pl.Int8),
        }
    )
    return train_model(dataset, feature_columns=["f1", "f2"], n_estimators=10)
