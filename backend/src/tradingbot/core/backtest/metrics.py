"""Performance metrics on equity curves. Pure functions, float math.

Metrics are analysis, not money, so float is fine here (see CLAUDE.md → Type
discipline). Crypto trades 24/7, hence 8760 hourly periods per year.
"""

import math

import polars as pl

PERIODS_PER_YEAR_1H = 24 * 365

MIN_RETURNS_FOR_SHARPE = 2


def sharpe_ratio(equity: pl.Series, periods_per_year: int) -> float:
    """Annualized Sharpe (risk-free rate 0) from per-period equity returns.

    Returns 0.0 for fewer than 3 equity points or zero-variance returns —
    there is no meaningful risk-adjusted number in either case.
    """
    returns = equity.pct_change().drop_nulls()
    if len(returns) < MIN_RETURNS_FOR_SHARPE:
        return 0.0
    mean = returns.mean()
    std = returns.std()
    if not isinstance(mean, float) or not isinstance(std, float) or std == 0.0:
        return 0.0
    return mean / std * math.sqrt(periods_per_year)


def max_drawdown(equity: pl.Series) -> float:
    """Largest peak-to-trough decline as a negative fraction (e.g. -0.55 = -55%)."""
    drawdowns = equity / equity.cum_max() - 1
    worst = drawdowns.min()
    return worst if isinstance(worst, float) else 0.0
