"""Structure trend-following: trade the confirmed swing structure (H4).

Hypothesis (HYPOTHESES.md → H4): trend *is* market structure. Higher highs
plus higher lows is an uptrend → long; lower highs plus lower lows is a
downtrend → short; while the two swing series disagree, the previous trend
is carried — the position flips only when the opposite structure fully
confirms. Pure price action: no indicators anywhere in the signal.

Swings come from core.features.structure and are confirmed k bars after
they form, so every signal is causal; the engine then fills at the next
bar's open like any other strategy. Exits are the signal itself — the
run_backtest wiring pairs this strategy with HOLD_RULES (no stop, no
take-profit, no time exit), per H1's lesson that exits must match the
signal's holding horizon.
"""

from dataclasses import dataclass

import polars as pl

from tradingbot.core.features.structure import higher_high, higher_low
from tradingbot.core.signals.signal import Signal


@dataclass(frozen=True)
class StructureTrendStrategy:
    k: int = 3
    """Fractal half-width (bars each side of a swing). Fixed a priori in
    HYPOTHESES.md → H4; not a tuning knob."""

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"k must be >= 1, got {self.k}")

    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        rising_highs = higher_high(self.k)
        rising_lows = higher_low(self.k)
        return ohlcv.select(
            pl.when(rising_highs.eq(1.0) & rising_lows.eq(1.0))
            .then(pl.lit(Signal.LONG.value))
            .when(rising_highs.eq(0.0) & rising_lows.eq(0.0))
            .then(pl.lit(Signal.SHORT.value))
            .otherwise(pl.lit(None, dtype=pl.String))  # mixed -> carry the trend
            .forward_fill()
            .fill_null(pl.lit(Signal.FLAT.value))  # before the first full structure
            .alias("signal")
        ).get_column("signal")
