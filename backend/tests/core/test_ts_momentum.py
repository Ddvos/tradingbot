from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from tradingbot.core.ports.market_data import OHLCV_SCHEMA
from tradingbot.core.strategies.ts_momentum import TSMomentumStrategy


def frame(closes: list[float]) -> pl.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(len(closes))],
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [100.0] * len(closes),
        },
        schema=OHLCV_SCHEMA,
    )


def test_warmup_is_flat_then_sign_of_trailing_return() -> None:
    strategy = TSMomentumStrategy(lookback=3)
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 99.0]

    signals = strategy.signals(frame(closes)).to_list()

    # bar 3: 103 > 100 -> long; bar 4: 104 > 101 -> long; bar 5: 99 < 102 -> short
    assert signals == ["flat", "flat", "flat", "long", "long", "short"]


def test_exactly_zero_trailing_return_stands_aside() -> None:
    strategy = TSMomentumStrategy(lookback=2)
    closes = [100.0, 90.0, 100.0]

    assert strategy.signals(frame(closes)).to_list() == ["flat", "flat", "flat"]


def test_lookback_must_be_positive() -> None:
    with pytest.raises(ValueError, match="lookback"):
        TSMomentumStrategy(lookback=0)
