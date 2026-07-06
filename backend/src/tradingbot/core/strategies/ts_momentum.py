"""Time-series momentum: hold the sign of the trailing N-bar return.

Hypothesis (HYPOTHESES.md → H5): an asset's own trailing return predicts
its next return (Moskowitz, Ooi & Pedersen 2012). Long when the trailing
return is positive, short when negative — symmetric, as in the literature.
Designed for daily bars, where a multi-week holding horizon dwarfs
round-trip costs; the lookback is fixed a priori, not searched.
"""

from dataclasses import dataclass

import polars as pl

from tradingbot.core.signals.signal import Signal


@dataclass(frozen=True)
class TSMomentumStrategy:
    lookback: int = 90

    def __post_init__(self) -> None:
        if self.lookback < 1:
            raise ValueError(f"lookback must be >= 1, got {self.lookback}")

    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        past = pl.col("close").shift(self.lookback)
        return ohlcv.select(
            pl.when(past.is_null())  # warmup: no trailing return yet
            .then(pl.lit(Signal.FLAT.value))
            .when(pl.col("close") > past)
            .then(pl.lit(Signal.LONG.value))
            .when(pl.col("close") < past)
            .then(pl.lit(Signal.SHORT.value))
            .otherwise(pl.lit(Signal.FLAT.value))  # exactly-zero return: stand aside
            .alias("signal")
        ).get_column("signal")
