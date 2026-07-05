"""Use case: the honest walk-forward evaluation of the ML strategy (Slice 3).

Per fold (see core.models.walk_forward): train a fresh XGBoost on the
rolling train window with the exact fixed hyperparameters of train.py,
predict the out-of-sample test window, and backtest those predictions
through the real engine with the same pessimistic costs as every other
backtest. The per-fold test curves are stitched into one continuous
out-of-sample equity curve; on it we compute the full metric suite,
including the deflated Sharpe and a block-bootstrap CI.

Holdout discipline: everything here runs on data strictly before the
evaluation window end (H2_EVAL_END, so H2 iterations stay comparable),
which clamp_to_development additionally caps at HOLDOUT_START. The holdout
protocol lives in HOLDOUT.md at the repo root.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.metrics import roc_auc_score

from tradingbot.adapters.parquet.store import ParquetStore
from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.application.holdout import H2_EVAL_END, clamp_to_development
from tradingbot.application.run_backtest import HOLD_RULES, SLIPPAGE_RATE, TAKER_FEE_RATE
from tradingbot.core.backtest.engine import BacktestEngine, BacktestResult, TradeRules
from tradingbot.core.backtest.metrics import max_drawdown, sharpe_ratio
from tradingbot.core.models.dataset import FEATURE_COLUMNS, build_dataset
from tradingbot.core.models.evaluation import (
    bootstrap_sharpe_ci,
    deflated_sharpe_ratio,
    information_coefficient,
    probabilistic_sharpe_ratio,
    profit_factor,
    win_rate,
)
from tradingbot.core.models.train import fit_classifier
from tradingbot.core.models.walk_forward import Fold, WalkForwardConfig, walk_forward_folds
from tradingbot.core.ports.market_data import TIMEFRAME_SECONDS, Timeframe
from tradingbot.core.signals.signal import Signal
from tradingbot.core.strategies.hold import HoldStrategy
from tradingbot.core.strategies.ml_strategy import ML_TRADE_RULES

TRIAL_SHARPES_ANNUALIZED: dict[str, float] = {
    "buy_and_hold": 0.21,
    "ma_cross_20_50_trend_exits": -0.59,
    "ml_xgb_v1_threshold_0.6": -1.66,
    "ml_xgb_v2_structure_features_threshold_0.6": -2.12,
}
"""Every strategy candidate evaluated against the development data so far,
with its annualized Sharpe (ROADMAP.md → The honest numbers). This is the
false-discovery record that sets the deflated-Sharpe bar: append every new
candidate BEFORE looking at its results. The ma-cross run under v1 exit
rules (-10.1) is deliberately absent — it is the same hypothesis as the
trend-exit variant under mismatched exit mechanics (ROADMAP finding #2),
a diagnostic, not an independent candidate."""

SECONDS_PER_YEAR = 365 * 24 * 3600


@dataclass(frozen=True)
class _PrecomputedStrategy:
    """Feeds externally computed signals through the Strategy port.

    The walk-forward predicts a test window with features built on full
    history (exactly what a live bot would see); recomputing them inside
    MLStrategy from a short window slice would lose warmup bars instead.
    """

    precomputed: pl.Series

    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        if len(self.precomputed) != ohlcv.height:
            raise ValueError(f"{len(self.precomputed)} precomputed signals for {ohlcv.height} bars")
        return self.precomputed


@dataclass(frozen=True)
class FoldResult:
    """Out-of-sample metrics of one fold's freshly trained model."""

    fold: Fold
    test_start: datetime
    test_end: datetime
    auc: float
    ic: float
    sharpe: float
    max_drawdown: float
    n_trades: int
    win_rate: float
    profit_factor: float


@dataclass(frozen=True)
class WalkForwardReport:
    """Everything the report artifact needs, computed once."""

    symbol: str
    timeframe: Timeframe
    config: WalkForwardConfig
    threshold: float
    initial_capital: Decimal
    eval_end: datetime
    """End of the evaluation window this run was clamped to (H2_EVAL_END by
    default; never past HOLDOUT_START)."""
    data_start: datetime
    data_end: datetime
    dataset_rows: int
    folds: list[FoldResult]
    equity_curve: pl.DataFrame
    """Stitched out-of-sample curve: timestamp + equity, all test windows."""
    oos_sharpe: float
    oos_max_drawdown: float
    oos_final_equity: float
    oos_ic: float
    """Pooled over every (prediction, label) pair of every test window."""
    oos_auc: float
    probabilistic_sharpe: float
    deflated_sharpe: float
    sharpe_ci: tuple[float, float]
    n_trades: int
    win_rate: float
    profit_factor: float
    baseline_sharpe: float
    """Buy-and-hold over exactly the same test windows and costs."""
    baseline_max_drawdown: float
    baseline_final_equity: float
    trial_sharpes_annualized: dict[str, float]


def _periods_per_year(timeframe: Timeframe) -> int:
    return SECONDS_PER_YEAR // TIMEFRAME_SECONDS[timeframe]


def _run_engine(
    ohlcv: pl.DataFrame,
    strategy: HoldStrategy | _PrecomputedStrategy,
    rules: TradeRules,
    symbol: str,
    initial_capital: Decimal,
    fee_rate: Decimal,
    slippage_rate: Decimal,
) -> BacktestResult:
    executor = SimulatedExecutor(fee_rate=fee_rate, slippage_rate=slippage_rate)
    engine = BacktestEngine(
        executor, strategy, initial_capital, rules, set_market=executor.set_market
    )
    return engine.run(ohlcv, symbol)


def _stitch(curves: list[pl.DataFrame], initial_capital: Decimal) -> pl.DataFrame:
    """Chain per-fold curves into one: each fold restarts the engine at fresh
    capital, so rescale every curve to continue from the previous end value."""
    scaled: list[pl.DataFrame] = []
    running = float(initial_capital)
    for curve in curves:
        first: float = curve[0, "equity"]
        scaled.append(curve.with_columns(pl.col("equity") / first * running))
        running = scaled[-1][-1, "equity"]
    return pl.concat(scaled)


def run_walk_forward(
    data_dir: Path,
    symbol: str,
    timeframe: Timeframe,
    *,
    config: WalkForwardConfig | None = None,
    threshold: float = 0.6,
    initial_capital: Decimal = Decimal(10_000),
    eval_end: datetime = H2_EVAL_END,
    fee_rate: Decimal = TAKER_FEE_RATE,
    slippage_rate: Decimal = SLIPPAGE_RATE,
) -> WalkForwardReport:
    """Full purged walk-forward evaluation on the development data."""
    config = config if config is not None else WalkForwardConfig()
    ohlcv = ParquetStore(data_dir).read(symbol, timeframe)
    dev = clamp_to_development(ohlcv, end=eval_end)

    dataset = build_dataset(dev)
    folds = walk_forward_folds(dataset.height, config)
    warmup = ML_TRADE_RULES.atr_period + 1  # bars the engine needs before its ATR is defined
    dev_timestamps = dev.get_column("timestamp")

    fold_results: list[FoldResult] = []
    fold_curves: list[pl.DataFrame] = []
    baseline_curves: list[pl.DataFrame] = []
    pooled_probabilities: list[float] = []
    pooled_labels: list[float] = []
    pooled_pnls: list[Decimal] = []

    for fold in folds:
        train = dataset.slice(fold.train_start, fold.train_end - fold.train_start)
        test = dataset.slice(fold.test_start, fold.test_end - fold.test_start)
        model = fit_classifier(
            train.select(FEATURE_COLUMNS).to_numpy(),
            train.get_column("label").to_numpy(),
        )
        probabilities: list[float] = model.predict_proba(test.select(FEATURE_COLUMNS).to_numpy())[
            :, 1
        ].tolist()
        labels: list[float] = test.get_column("label").to_list()

        # Dataset rows map 1:1 onto dev bars (build_dataset only trims the
        # frame's edges), so the test window plus an ATR warmup prefix can be
        # cut straight from the OHLCV. The prefix signals are forced flat and
        # its bars are dropped from the fold curve below.
        start_row = int(dev_timestamps.search_sorted(test[0, "timestamp"]))
        engine_slice = dev.slice(start_row - warmup, warmup + test.height)
        if engine_slice[warmup, "timestamp"] != test[0, "timestamp"]:
            raise ValueError(f"Fold {fold.index}: dataset rows do not align with OHLCV bars")

        signal_values = [Signal.FLAT.value] * warmup + [
            Signal.LONG.value if p >= threshold else Signal.FLAT.value for p in probabilities
        ]
        result = _run_engine(
            engine_slice,
            _PrecomputedStrategy(pl.Series("signal", signal_values)),
            ML_TRADE_RULES,
            symbol,
            initial_capital,
            fee_rate,
            slippage_rate,
        )
        curve = result.equity_curve.slice(warmup)
        baseline = _run_engine(
            dev.slice(start_row, test.height),
            HoldStrategy(),
            HOLD_RULES,
            symbol,
            initial_capital,
            fee_rate,
            slippage_rate,
        )

        pnls = [trade.pnl for trade in result.trades]
        equity = curve.get_column("equity")
        fold_results.append(
            FoldResult(
                fold=fold,
                test_start=test[0, "timestamp"],
                test_end=test[-1, "timestamp"],
                auc=(
                    float(roc_auc_score(labels, probabilities))
                    if len(set(labels)) > 1
                    else float("nan")
                ),
                ic=information_coefficient(probabilities, labels),
                sharpe=sharpe_ratio(equity, _periods_per_year(timeframe)),
                max_drawdown=max_drawdown(equity),
                n_trades=len(result.trades),
                win_rate=win_rate(pnls),
                profit_factor=profit_factor(pnls),
            )
        )
        fold_curves.append(curve)
        baseline_curves.append(baseline.equity_curve)
        pooled_probabilities.extend(probabilities)
        pooled_labels.extend(labels)
        pooled_pnls.extend(pnls)

    oos_curve = _stitch(fold_curves, initial_capital)
    baseline_curve = _stitch(baseline_curves, initial_capital)
    periods = _periods_per_year(timeframe)
    equity_values = oos_curve.get_column("equity").to_numpy()
    returns: list[float] = (np.diff(equity_values) / equity_values[:-1]).tolist()

    oos_sharpe = sharpe_ratio(oos_curve.get_column("equity"), periods)
    trial_sharpes_annualized = {**TRIAL_SHARPES_ANNUALIZED, "this_run": oos_sharpe}
    per_period = 1.0 / math.sqrt(periods)
    trial_sharpes = [s * per_period for s in trial_sharpes_annualized.values()]

    return WalkForwardReport(
        symbol=symbol,
        timeframe=timeframe,
        config=config,
        threshold=threshold,
        initial_capital=initial_capital,
        eval_end=eval_end,
        data_start=dev[0, "timestamp"],
        data_end=dev[-1, "timestamp"],
        dataset_rows=dataset.height,
        folds=fold_results,
        equity_curve=oos_curve,
        oos_sharpe=oos_sharpe,
        oos_max_drawdown=max_drawdown(oos_curve.get_column("equity")),
        oos_final_equity=float(oos_curve[-1, "equity"]),
        oos_ic=information_coefficient(pooled_probabilities, pooled_labels),
        oos_auc=(
            float(roc_auc_score(pooled_labels, pooled_probabilities))
            if len(set(pooled_labels)) > 1
            else float("nan")
        ),
        probabilistic_sharpe=probabilistic_sharpe_ratio(returns),
        deflated_sharpe=deflated_sharpe_ratio(returns, trial_sharpes),
        sharpe_ci=bootstrap_sharpe_ci(returns, periods),
        n_trades=len(pooled_pnls),
        win_rate=win_rate(pooled_pnls),
        profit_factor=profit_factor(pooled_pnls),
        baseline_sharpe=sharpe_ratio(baseline_curve.get_column("equity"), periods),
        baseline_max_drawdown=max_drawdown(baseline_curve.get_column("equity")),
        baseline_final_equity=float(baseline_curve[-1, "equity"]),
        trial_sharpes_annualized=trial_sharpes_annualized,
    )
