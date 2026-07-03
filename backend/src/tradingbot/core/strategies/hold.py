"""Always-long: buy-and-hold expressed as a strategy, the baseline to beat."""

import polars as pl

from tradingbot.core.signals.signal import Signal


class HoldStrategy:
    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        return pl.Series("signal", [Signal.LONG.value] * ohlcv.height)
