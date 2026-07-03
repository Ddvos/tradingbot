"""Triple-barrier labeling (López de Prado).

For each bar i, three barriers are placed from entry = close[i], using the
ATR known at bar i (causal):

- upper:  entry + upper_atr * ATR(i)   — the profit target
- lower:  entry - lower_atr * ATR(i)   — the stop
- time:   `horizon` bars

The label is binary: 1 if the upper barrier is touched (via the bar highs)
before the lower barrier within the horizon, else 0. Ties inside one bar go
to the lower barrier — the same stop-wins pessimism as the backtest engine.
The last `horizon` bars cannot be labeled and get null; drop them downstream.

Entry is close[i] while the engine actually enters at open[i+1]; on 1h bars
the gap is well inside the slippage assumption. Barriers mirror TradeRules
except the 2.0x target (per the ML spec) vs the engine's 3.0x default —
align TradeRules.take_profit_atr with the label when backtesting MLStrategy.
"""

import polars as pl

from tradingbot.core.features.indicators import atr
from tradingbot.core.ports.market_data import validate_ohlcv


def triple_barrier_labels(
    ohlcv: pl.DataFrame,
    *,
    upper_atr: float = 2.0,
    lower_atr: float = 1.5,
    horizon: int = 6,
    atr_period: int = 14,
) -> pl.Series:
    """One label per input row: 1 (target first), 0 (stop first / expired), null (tail)."""
    validate_ohlcv(ohlcv)
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    closes: list[float] = ohlcv.get_column("close").to_list()
    highs: list[float] = ohlcv.get_column("high").to_list()
    lows: list[float] = ohlcv.get_column("low").to_list()
    atrs: list[float] = ohlcv.select(atr(atr_period).alias("atr")).get_column("atr").to_list()

    labels: list[int | None] = []
    last_labelable = len(closes) - horizon
    for i in range(len(closes)):
        if i >= last_labelable:
            labels.append(None)
            continue
        upper = closes[i] + upper_atr * atrs[i]
        lower = closes[i] - lower_atr * atrs[i]
        label = 0
        for j in range(i + 1, i + 1 + horizon):
            if lows[j] <= lower:
                break  # stop first (or same-bar tie): stays 0
            if highs[j] >= upper:
                label = 1
                break
        labels.append(label)
    return pl.Series("label", labels, dtype=pl.Int8)
