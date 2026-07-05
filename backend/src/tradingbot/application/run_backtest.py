"""Use cases: run a strategy backtest from local Parquet data.

Wires ParquetStore + SimulatedExecutor + BacktestEngine. Cost defaults are
deliberately pessimistic (taker fee, upper-bound slippage; see CLAUDE.md →
Trading constraints).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from tradingbot.adapters.parquet.store import ParquetStore
from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.application.holdout import clamp_to_development
from tradingbot.core.backtest.engine import BacktestEngine, BacktestResult, TradeRules
from tradingbot.core.backtest.metrics import PERIODS_PER_YEAR_1H, max_drawdown, sharpe_ratio
from tradingbot.core.ports.market_data import Timeframe
from tradingbot.core.ports.storage import BacktestRunId, BacktestRunRecord, ParamValue
from tradingbot.core.strategies.base import Strategy
from tradingbot.core.strategies.hold import HoldStrategy
from tradingbot.core.strategies.ma_cross import MACrossStrategy

TAKER_FEE_RATE = Decimal("0.0005")
SLIPPAGE_RATE = Decimal("0.001")

HOLD_RULES = TradeRules(risk_pct=None, stop_atr=None, take_profit_atr=None, max_bars_held=None)


@dataclass(frozen=True)
class BacktestReport:
    result: BacktestResult
    sharpe: float
    max_drawdown: float
    num_bars: int


def run_strategy(
    strategy: Strategy,
    rules: TradeRules,
    data_dir: Path,
    symbol: str,
    timeframe: Timeframe,
    initial_capital: Decimal,
    fee_rate: Decimal = TAKER_FEE_RATE,
    slippage_rate: Decimal = SLIPPAGE_RATE,
) -> BacktestReport:
    # Development data only — exploratory backtests must never observe the
    # holdout, not even at aggregate level (HOLDOUT.md, rule 4).
    ohlcv = clamp_to_development(ParquetStore(data_dir).read(symbol, timeframe))

    executor = SimulatedExecutor(fee_rate=fee_rate, slippage_rate=slippage_rate)
    engine = BacktestEngine(
        executor, strategy, initial_capital, rules, set_market=executor.set_market
    )
    result = engine.run(ohlcv, symbol)

    equity = result.equity_curve.get_column("equity")
    return BacktestReport(
        result=result,
        sharpe=sharpe_ratio(equity, PERIODS_PER_YEAR_1H),
        max_drawdown=max_drawdown(equity),
        num_bars=len(ohlcv),
    )


def to_run_record(
    report: BacktestReport,
    strategy: str,
    symbol: str,
    timeframe: Timeframe,
    params: dict[str, ParamValue],
    equity_curve_path: Path,
) -> BacktestRunRecord:
    """Turn a finished report into the persistable metadata record.

    The equity curve itself stays in Parquet (CLAUDE.md → Storage); the
    record only points at it.
    """
    timestamps = report.result.equity_curve.get_column("timestamp")
    data_start: datetime = timestamps[0]
    data_end: datetime = timestamps[-1]
    return BacktestRunRecord(
        id=BacktestRunId(uuid4()),
        strategy=strategy,
        symbol=symbol,
        timeframe=timeframe,
        data_start=data_start,
        data_end=data_end,
        initial_capital=report.result.initial_capital,
        final_equity=report.result.final_equity,
        sharpe=report.sharpe,
        max_drawdown=report.max_drawdown,
        n_trades=len(report.result.trades),
        params=params,
        equity_curve_path=str(equity_curve_path),
        created_at=datetime.now(UTC),
    )


def run_buy_and_hold(
    data_dir: Path,
    symbol: str,
    timeframe: Timeframe,
    initial_capital: Decimal,
) -> BacktestReport:
    """All-in long on the first bar, no exits; pays funding like any perp position."""
    return run_strategy(HoldStrategy(), HOLD_RULES, data_dir, symbol, timeframe, initial_capital)


def run_ma_cross(
    data_dir: Path,
    symbol: str,
    timeframe: Timeframe,
    initial_capital: Decimal,
    fast: int = 20,
    slow: int = 50,
) -> BacktestReport:
    """MA-cross with the full v1 risk rules (1% risk, ATR stop/TP, 6-bar time exit).

    Empirical warning (2 Jul 2026): these rules are calibrated for a 6-bar ML
    horizon; forcing them onto a slow trend signal churns ~4300 round trips
    whose costs compound to -100%. Kept as the honest record of that mismatch.
    """
    strategy = MACrossStrategy(fast=fast, slow=slow)
    return run_strategy(strategy, TradeRules(), data_dir, symbol, timeframe, initial_capital)


def run_ma_cross_trend(
    data_dir: Path,
    symbol: str,
    timeframe: Timeframe,
    initial_capital: Decimal,
    fast: int = 20,
    slow: int = 50,
) -> BacktestReport:
    """MA-cross with exits matched to its hypothesis: signal flips only.

    All-in sizing, no barriers — the trend thesis says stay in until the
    trend ends, so the only exit is the fast MA crossing back under.
    """
    strategy = MACrossStrategy(fast=fast, slow=slow)
    return run_strategy(strategy, HOLD_RULES, data_dir, symbol, timeframe, initial_capital)
