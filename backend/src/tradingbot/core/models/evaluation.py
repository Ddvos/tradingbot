"""The honest evaluation suite (Slice 3).

Signal quality: `information_coefficient`. Strategy quality on returns:
`probabilistic_sharpe_ratio`, `deflated_sharpe_ratio` (Bailey & López de
Prado, "The Deflated Sharpe Ratio", 2014) and `bootstrap_sharpe_ci`. Trade
quality: `win_rate`, `profit_factor`. Plain Sharpe and max drawdown live in
`core.backtest.metrics` and are reused, not duplicated.

Convention: every function taking `returns` expects **per-period** simple
returns (e.g. hourly), and Sharpe ratios passed between these functions are
per-period too — annualization happens only at the reporting edge.
"""

import math
from collections.abc import Sequence
from decimal import Decimal
from statistics import NormalDist
from typing import cast

import numpy as np
from scipy.stats import spearmanr

_NORMAL = NormalDist()
_EULER_GAMMA = float(np.euler_gamma)

MIN_RETURNS_FOR_PSR = 3
MIN_TRIALS_FOR_SELECTION_BIAS = 2


def information_coefficient(predictions: Sequence[float], outcomes: Sequence[float]) -> float:
    """Spearman rank correlation between predictions and realized outcomes.

    The core question of any signal: do higher predictions actually come with
    better outcomes? Returns nan when either side is constant — that nan is
    itself the sanity signal (a model predicting one value has no IC).
    """
    # cast: scipy's SignificanceResult is opaque to the type checker (scipy 1.18 ships
    # partial annotations); at runtime it is a (statistic, pvalue) named tuple.
    result = cast("tuple[float, float]", spearmanr(predictions, outcomes))
    return float(result[0])


def probabilistic_sharpe_ratio(returns: Sequence[float], benchmark_sharpe: float = 0.0) -> float:
    """P(true Sharpe > benchmark) given the observed returns.

    Adjusts the observed Sharpe for sample length, skewness, and fat tails —
    a lucky short track record with ugly higher moments scores low even if
    its point-estimate Sharpe looks good. `benchmark_sharpe` is per-period.
    Returns nan when the inputs cannot support the estimate (too few
    returns, zero variance, or a degenerate moment combination).
    """
    values = np.asarray(returns, dtype=np.float64)
    n = values.size
    if n < MIN_RETURNS_FOR_PSR:
        return float("nan")
    std = float(values.std(ddof=1))
    if std == 0.0:
        return float("nan")
    sharpe = float(values.mean()) / std

    centered = values - values.mean()
    m2 = float(np.mean(centered**2))
    skew = float(np.mean(centered**3)) / (m2 * math.sqrt(m2))
    kurtosis = float(np.mean(centered**4)) / (m2 * m2)  # Pearson: normal = 3

    variance_term = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    if variance_term <= 0.0:
        return float("nan")
    z = (sharpe - benchmark_sharpe) * math.sqrt(n - 1) / math.sqrt(variance_term)
    return _NORMAL.cdf(z)


def expected_max_sharpe(trial_sharpes: Sequence[float]) -> float:
    """Expected best per-period Sharpe among N zero-skill trials.

    The false-discovery bar: having run N strategy trials against the same
    data, the best of them shows this Sharpe by pure luck. Uses the
    variance across the actual trials. With fewer than two trials there is
    no selection pressure to correct for — returns 0.0.
    """
    n = len(trial_sharpes)
    if n < MIN_TRIALS_FOR_SELECTION_BIAS:
        return 0.0
    std = float(np.asarray(trial_sharpes, dtype=np.float64).std(ddof=1))
    high = _NORMAL.inv_cdf(1.0 - 1.0 / n)
    low = _NORMAL.inv_cdf(1.0 - 1.0 / (n * math.e))
    return std * ((1.0 - _EULER_GAMMA) * high + _EULER_GAMMA * low)


def deflated_sharpe_ratio(returns: Sequence[float], trial_sharpes: Sequence[float]) -> float:
    """P(true Sharpe > 0) after correcting for multiple trials.

    The probabilistic Sharpe ratio, but benchmarked against the Sharpe the
    best of `trial_sharpes` would show by luck alone. `trial_sharpes` must
    list every strategy trial evaluated against this data (including this
    one), as per-period Sharpes.
    """
    return probabilistic_sharpe_ratio(returns, expected_max_sharpe(trial_sharpes))


def bootstrap_sharpe_ci(
    returns: Sequence[float],
    periods_per_year: int,
    *,
    block_bars: int = 24,
    n_resamples: int = 2_000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Confidence interval for the annualized Sharpe via moving-block bootstrap.

    Blocks (default one day of hourly bars) preserve the serial correlation
    that an iid bootstrap would destroy — resampling autocorrelated returns
    bar-by-bar understates the variance of the Sharpe estimate. Seeded for
    reproducible reports. Returns (nan, nan) when the series is shorter
    than one block.
    """
    values = np.asarray(returns, dtype=np.float64)
    n = values.size
    if n < block_bars + 1:
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block_bars)
    offsets = np.arange(block_bars)
    annualizer = math.sqrt(periods_per_year)
    sharpes = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        starts = rng.integers(0, n - block_bars + 1, size=n_blocks)
        sample = values[(starts[:, None] + offsets).ravel()[:n]]
        std = float(sample.std(ddof=1))
        sharpes[i] = float(sample.mean()) / std * annualizer if std > 0.0 else 0.0

    alpha = 1.0 - confidence
    lower, upper = np.quantile(sharpes, [alpha / 2.0, 1.0 - alpha / 2.0])
    return (float(lower), float(upper))


def win_rate(pnls: Sequence[Decimal]) -> float:
    """Fraction of trades with positive P&L; nan when there are no trades."""
    if not pnls:
        return float("nan")
    return sum(1 for pnl in pnls if pnl > 0) / len(pnls)


def profit_factor(pnls: Sequence[Decimal]) -> float:
    """Gross profit / gross loss; nan without trades, inf without losers."""
    if not pnls:
        return float("nan")
    gross_profit = float(sum(pnl for pnl in pnls if pnl > 0))
    gross_loss = -float(sum(pnl for pnl in pnls if pnl <= 0))
    if gross_loss == 0.0:
        return float("inf")
    return gross_profit / gross_loss
