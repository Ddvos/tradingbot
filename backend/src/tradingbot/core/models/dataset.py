"""Build the ML dataset: causal features + triple-barrier labels, aligned.

The no-lookahead guarantee has two halves:
- every feature at row i is computed from rows 0..i only (causal indicators);
- the label at row i is the outcome of rows i+1..i+horizon — that is the
  prediction target, not leakage.

v1 features are 1h-only (13 of them); the multi-timeframe set (4H trend,
15M momentum) from CLAUDE.md arrives in a later slice. Scale-dependent
indicators (ATR, MACD) are normalized by price so the model does not learn
the era of the price level. The market-structure set (features/structure.py)
was evaluated under H3 and left out per its parsimony verdict — see
HYPOTHESES.md before re-adding it.
"""

import polars as pl

from tradingbot.core.features.indicators import (
    atr,
    bollinger_width,
    ma_slope,
    macd_histogram,
    obv,
    pct_return,
    rsi,
    volume_vs_ma,
)
from tradingbot.core.features.temporal import day_of_week, hour_of_day
from tradingbot.core.models.labeling import triple_barrier_labels
from tradingbot.core.ports.market_data import validate_ohlcv


def feature_expressions() -> dict[str, pl.Expr]:
    return {
        "ret_1": pct_return(1),
        "ret_6": pct_return(6),
        "ret_24": pct_return(24),
        "ma_slope_20_3": ma_slope(20, 3),
        "ma_slope_50_6": ma_slope(50, 6),
        "rsi_14": rsi(14),
        "macd_hist_rel": macd_histogram() / pl.col("close"),
        "atr_pct": atr(14) / pl.col("close"),
        "bb_width_20": bollinger_width(20),
        "vol_vs_ma_20": volume_vs_ma(20),
        "obv_slope_6": (obv() - obv().shift(6)) / pl.col("volume").rolling_sum(6),
        "hour": hour_of_day(),
        "dow": day_of_week(),
    }


FEATURE_COLUMNS: list[str] = list(feature_expressions().keys())


def build_dataset(
    ohlcv: pl.DataFrame,
    *,
    upper_atr: float = 2.0,
    lower_atr: float = 1.5,
    horizon: int = 6,
) -> pl.DataFrame:
    """Return timestamp + features + label, with warmup and unlabeled tail dropped."""
    validate_ohlcv(ohlcv)
    labels = triple_barrier_labels(ohlcv, upper_atr=upper_atr, lower_atr=lower_atr, horizon=horizon)
    return (
        ohlcv.with_columns(**feature_expressions())
        .with_columns(labels)
        .select("timestamp", *FEATURE_COLUMNS, "label")
        .drop_nulls()
    )
