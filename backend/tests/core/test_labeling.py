from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from tradingbot.core.models.labeling import triple_barrier_labels
from tradingbot.core.ports.market_data import OHLCV_SCHEMA


def frame(bars: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    """Build an OHLCV frame from (open, high, low, close) tuples."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=i) for i in range(len(bars))],
            "open": [b[0] for b in bars],
            "high": [b[1] for b in bars],
            "low": [b[2] for b in bars],
            "close": [b[3] for b in bars],
            "volume": [100.0] * len(bars),
        },
        schema=OHLCV_SCHEMA,
    )


# All bars below have range 2 (high = close+1, low = close-1) so ATR = 2:
# from entry close 100, upper barrier = 104, lower barrier = 97.
BASE = (100.0, 101.0, 99.0, 100.0)


def test_upper_barrier_first_labels_one() -> None:
    labels = triple_barrier_labels(frame([BASE, (100, 105, 99, 100)] + [BASE] * 6))
    assert labels[0] == 1


def test_lower_barrier_first_labels_zero() -> None:
    labels = triple_barrier_labels(frame([BASE, (100, 101, 96, 100)] + [BASE] * 6))
    assert labels[0] == 0


def test_same_bar_tie_goes_to_lower_barrier() -> None:
    labels = triple_barrier_labels(frame([BASE, (100, 105, 96, 100)] + [BASE] * 6))
    assert labels[0] == 0


def test_no_touch_within_horizon_labels_zero() -> None:
    labels = triple_barrier_labels(frame([BASE] * 8))
    assert labels[0] == 0


def test_upper_touch_after_horizon_does_not_count() -> None:
    # the spike sits at bar 7; horizon from bar 0 covers bars 1..6
    labels = triple_barrier_labels(frame([BASE] * 7 + [(100, 105, 99, 100)] + [BASE] * 5))
    assert labels[0] == 0


def test_unlabelable_tail_is_null() -> None:
    labels = triple_barrier_labels(frame([BASE] * 10), horizon=6)
    assert labels.to_list()[-6:] == [None] * 6
    assert labels.to_list()[:4] == [0, 0, 0, 0]


def test_invalid_horizon_raises() -> None:
    with pytest.raises(ValueError, match="horizon"):
        triple_barrier_labels(frame([BASE] * 8), horizon=0)
