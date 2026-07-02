import math
import statistics

import polars as pl
import pytest

from tradingbot.core.backtest.metrics import PERIODS_PER_YEAR_1H, max_drawdown, sharpe_ratio


def test_sharpe_matches_manual_computation() -> None:
    equity = pl.Series([100.0, 101.0, 103.02])
    returns = [101.0 / 100.0 - 1, 103.02 / 101.0 - 1]
    expected = statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(PERIODS_PER_YEAR_1H)

    assert sharpe_ratio(equity, PERIODS_PER_YEAR_1H) == pytest.approx(expected)


def test_sharpe_of_constant_equity_is_zero() -> None:
    assert sharpe_ratio(pl.Series([100.0, 100.0, 100.0]), PERIODS_PER_YEAR_1H) == 0.0


def test_sharpe_of_single_point_is_zero() -> None:
    assert sharpe_ratio(pl.Series([100.0]), PERIODS_PER_YEAR_1H) == 0.0


def test_max_drawdown_peak_to_trough() -> None:
    equity = pl.Series([100.0, 120.0, 90.0, 130.0])

    assert max_drawdown(equity) == pytest.approx(90.0 / 120.0 - 1)


def test_max_drawdown_monotonic_rise_is_zero() -> None:
    assert max_drawdown(pl.Series([100.0, 110.0, 120.0])) == 0.0
