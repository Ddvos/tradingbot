"""Market-structure features: swing points, HH/HL structure, swing levels.

A swing high is a fractal: a bar whose high strictly exceeds the highs of the
k bars on each side (swing low mirrored on lows). The right-hand side makes
the raw definition non-causal — the swing at bar t is only CONFIRMED at
t + k, once the k bars after it have closed. Every public expression here
therefore works on confirmed swings only: the swing value is shifted k bars
forward before it is forward-filled, so row i sees exactly the swings whose
confirmation bar is <= i. That lag is load-bearing (see HYPOTHESES.md → H3):
without it a backtest knows a top is "in" while a live bot cannot.

Like indicators.py, every expression is causal (row i uses rows 0..i only)
and composes into a single with_columns call.

Status: evaluated under H3 (walk-forward run 1h_xgb_v2_20260704_221613) with
a null result — pooled OOS IC +0.004 over the 13-feature set, inside the
pre-registered parsimony band — so these features are deliberately NOT in
feature_expressions(). Re-adding them requires a new pre-registered
iteration in HYPOTHESES.md.
"""

import polars as pl


def _swing_high_marker(k: int) -> pl.Expr:
    """True at swing-high bars. Reads k bars ahead — never use unshifted."""
    left = pl.col("high").shift(1).rolling_max(window_size=k)
    right = pl.col("high").shift(-k).rolling_max(window_size=k)
    return (pl.col("high") > left) & (pl.col("high") > right)


def _swing_low_marker(k: int) -> pl.Expr:
    """True at swing-low bars. Reads k bars ahead — never use unshifted."""
    left = pl.col("low").shift(1).rolling_min(window_size=k)
    right = pl.col("low").shift(-k).rolling_min(window_size=k)
    return (pl.col("low") < left) & (pl.col("low") < right)


def _confirmed_sparse(marker: pl.Expr, value: pl.Expr, k: int) -> pl.Expr:
    """`value` at the swing bar, placed on its confirmation bar; null elsewhere."""
    return pl.when(marker).then(value).otherwise(None).shift(k)


def _sparse_swing_high(k: int) -> pl.Expr:
    return _confirmed_sparse(_swing_high_marker(k), pl.col("high"), k)


def _sparse_swing_low(k: int) -> pl.Expr:
    return _confirmed_sparse(_swing_low_marker(k), pl.col("low"), k)


def last_swing_high(k: int = 3) -> pl.Expr:
    """Price of the most recent confirmed swing high; null before the first."""
    return _sparse_swing_high(k).forward_fill()


def last_swing_low(k: int = 3) -> pl.Expr:
    """Price of the most recent confirmed swing low; null before the first."""
    return _sparse_swing_low(k).forward_fill()


def _higher_than_previous(sparse: pl.Expr) -> pl.Expr:
    """1.0 when the latest confirmed swing sits above the one before it.

    `last.shift(1)` on a confirmation bar still holds the previous swing's
    value, so comparing there — and forward-filling that comparison — tracks
    the last two swing events, not the last two rows.
    """
    last = sparse.forward_fill()
    previous = pl.when(sparse.is_not_null()).then(last.shift(1)).otherwise(None).forward_fill()
    return (last > previous).cast(pl.Float64)


def higher_high(k: int = 3) -> pl.Expr:
    """1.0 while the market makes higher highs; null before two swing highs."""
    return _higher_than_previous(_sparse_swing_high(k))


def higher_low(k: int = 3) -> pl.Expr:
    """1.0 while the market makes higher lows; null before two swing lows."""
    return _higher_than_previous(_sparse_swing_low(k))


def _bars_since_confirmed(sparse: pl.Expr, k: int) -> pl.Expr:
    """Bars elapsed since the swing bar itself (confirmation bar minus k)."""
    index = pl.int_range(pl.len())
    confirmed_at = pl.when(sparse.is_not_null()).then(index).otherwise(None).forward_fill()
    return (index - confirmed_at + k).cast(pl.Float64)


def bars_since_swing_high(k: int = 3) -> pl.Expr:
    """Age of the most recent confirmed swing high, in bars."""
    return _bars_since_confirmed(_sparse_swing_high(k), k)


def bars_since_swing_low(k: int = 3) -> pl.Expr:
    """Age of the most recent confirmed swing low, in bars."""
    return _bars_since_confirmed(_sparse_swing_low(k), k)


def range_position(k: int = 3) -> pl.Expr:
    """Close inside the confirmed swing range: 0 at the low, 1 at the high.

    Deliberately unclamped — values outside [0, 1] are breakouts, which is
    signal. The levels come from different bars, so an inverted range
    (swing low above swing high, after a strong one-way move) is possible
    and also informative; only an exactly zero-width range yields null.
    """
    high_level = last_swing_high(k)
    low_level = last_swing_low(k)
    width = high_level - low_level
    position = (pl.col("close") - low_level) / width
    return pl.when(width != 0).then(position).otherwise(None)
