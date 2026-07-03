"""MA-cross baseline: long while the fast SMA is above the slow SMA.

Hypothesis: medium-term trend persistence in BTC — when the recent average
price sits above the longer-term average, the move is more likely to continue
than to revert. Long/flat only: shorting a perpetual carries funding costs
this simple rule earns nothing to pay for.
"""

from dataclasses import dataclass

import polars as pl

from tradingbot.core.features.indicators import sma
from tradingbot.core.signals.signal import Signal


@dataclass(frozen=True)
class MACrossStrategy:
    fast: int = 20
    slow: int = 50

    def __post_init__(self) -> None:
        if self.fast >= self.slow:
            raise ValueError(f"fast period ({self.fast}) must be < slow period ({self.slow})")

    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        is_long = (sma(self.fast) > sma(self.slow)).fill_null(value=False)  # warmup -> flat
        return ohlcv.select(
            pl.when(is_long)
            .then(pl.lit(Signal.LONG.value))
            .otherwise(pl.lit(Signal.FLAT.value))
            .alias("signal")
        ).get_column("signal")
