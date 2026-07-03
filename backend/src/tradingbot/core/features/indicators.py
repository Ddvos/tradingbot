"""Technical indicators as Polars expressions over the OHLCV schema.

Each function returns a pl.Expr computed from the standard OHLCV column names,
so features compose into a single with_columns call:

    df.with_columns(rsi(14).alias("rsi_14"), atr(14).alias("atr_14"))

All expressions are causal: row i uses only rows 0..i. That property is what
keeps backtests free of lookahead — never break it.
"""

import polars as pl


def sma(period: int) -> pl.Expr:
    """Simple moving average of the close. Null during the warmup rows."""
    return pl.col("close").rolling_mean(window_size=period)


def ema(period: int) -> pl.Expr:
    """Exponential moving average of the close (span parameterization)."""
    return pl.col("close").ewm_mean(span=period, adjust=False)


def pct_return(period: int = 1) -> pl.Expr:
    """Close-to-close return over `period` bars."""
    return pl.col("close").pct_change(n=period)


def ma_slope(period: int, lag: int) -> pl.Expr:
    """Relative change of the SMA over `lag` bars — trend direction and strength."""
    mean = sma(period)
    return mean / mean.shift(lag) - 1


def atr(period: int = 14) -> pl.Expr:
    """Wilder's Average True Range — the volatility unit for stops and sizing.

    True range = max(high-low, |high-prev close|, |low-prev close|); on the
    first row only high-low is available. Smoothed with Wilder's EMA
    (alpha = 1/period), so it is never null.
    """
    prev_close = pl.col("close").shift(1)
    true_range = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    return true_range.ewm_mean(alpha=1 / period, adjust=False)


def rsi(period: int = 14) -> pl.Expr:
    """Wilder's RSI in [0, 100]; 50 when there has been no movement at all."""
    delta = pl.col("close").diff()
    gain = delta.clip(lower_bound=0).fill_null(0.0)
    loss = (-delta).clip(lower_bound=0).fill_null(0.0)
    avg_gain = gain.ewm_mean(alpha=1 / period, adjust=False)
    avg_loss = loss.ewm_mean(alpha=1 / period, adjust=False)
    total = avg_gain + avg_loss
    return pl.when(total > 0).then(100 * avg_gain / total).otherwise(50.0)


def macd_histogram(fast: int = 12, slow: int = 26, signal: int = 9) -> pl.Expr:
    """MACD line minus its signal line — momentum acceleration."""
    macd_line = ema(fast) - ema(slow)
    signal_line = macd_line.ewm_mean(span=signal, adjust=False)
    return macd_line - signal_line


def bollinger_width(period: int = 20, num_std: float = 2.0) -> pl.Expr:
    """Band width relative to the middle band — a volatility regime gauge."""
    middle = sma(period)
    std = pl.col("close").rolling_std(window_size=period)
    return 2 * num_std * std / middle


def volume_vs_ma(period: int = 20) -> pl.Expr:
    """Current volume relative to its moving average (1.0 = typical)."""
    return pl.col("volume") / pl.col("volume").rolling_mean(window_size=period)


def obv() -> pl.Expr:
    """On-balance volume: cumulative volume signed by the close-to-close direction."""
    return (pl.col("volume") * pl.col("close").diff().sign().fill_null(0.0)).cum_sum()
