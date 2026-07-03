"""The Strategy contract: OHLCV in, one signal per bar out."""

from typing import Protocol

import polars as pl


class Strategy(Protocol):
    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        """Return one Signal value (see core.signals) per input row.

        Must be causal: the signal at row i may only use rows 0..i. The
        backtest engine executes the signal of bar i at the open of bar i+1,
        exactly as a live bot deciding after each closed candle would.
        """
        ...
