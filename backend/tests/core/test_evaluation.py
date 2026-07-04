import math
from decimal import Decimal

from tradingbot.core.models.evaluation import (
    bootstrap_sharpe_ci,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    profit_factor,
    win_rate,
)


def steady_positive_returns(n: int = 500) -> list[float]:
    """Deterministic returns with a clearly positive mean and mild noise."""
    return [0.001 + 0.0005 * math.sin(i) for i in range(n)]


def test_psr_high_for_clearly_positive_returns() -> None:
    assert probabilistic_sharpe_ratio(steady_positive_returns()) > 0.99


def test_psr_near_half_for_zero_mean_returns() -> None:
    zero_mean = [0.001 * math.sin(i) for i in range(500)]
    assert abs(probabilistic_sharpe_ratio(zero_mean) - 0.5) < 0.1


def test_psr_degenerate_inputs_are_nan() -> None:
    assert math.isnan(probabilistic_sharpe_ratio([0.01, 0.02]))  # too short
    assert math.isnan(probabilistic_sharpe_ratio([0.01] * 100))  # zero variance


def test_expected_max_sharpe_grows_with_trials_and_spread() -> None:
    assert expected_max_sharpe([0.5]) == 0.0  # one trial: no selection bias
    # 0.125 is exact in binary, so identical trials give exactly zero spread
    assert expected_max_sharpe([0.125, 0.125, 0.125]) == 0.0  # no spread: no luck to reward
    narrow = expected_max_sharpe([0.0, 0.1, -0.1])
    wide = expected_max_sharpe([0.0, 1.0, -1.0])
    assert 0.0 < narrow < wide
    assert expected_max_sharpe([0.0, 0.1, -0.1] * 4) > narrow  # more trials, higher bar


def test_deflated_sharpe_is_bounded_by_psr() -> None:
    returns = steady_positive_returns()
    trials = [0.02, -0.01, 0.005]
    assert deflated_sharpe_ratio(returns, trials) <= probabilistic_sharpe_ratio(returns)


def test_bootstrap_ci_brackets_the_sample_sharpe() -> None:
    returns = steady_positive_returns()
    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
    sample_sharpe = mean / std * math.sqrt(8760)

    low, high = bootstrap_sharpe_ci(returns, 8760, seed=7)
    assert low < sample_sharpe < high


def test_bootstrap_ci_nan_when_shorter_than_a_block() -> None:
    low, high = bootstrap_sharpe_ci([0.01] * 10, 8760, block_bars=24)
    assert math.isnan(low)
    assert math.isnan(high)


def test_win_rate_and_profit_factor() -> None:
    pnls = [Decimal(30), Decimal(-10), Decimal(-20), Decimal(60)]
    assert win_rate(pnls) == 0.5
    assert profit_factor(pnls) == 3.0

    assert math.isnan(win_rate([]))
    assert math.isnan(profit_factor([]))
    assert profit_factor([Decimal(5)]) == float("inf")
