"""Use case: run a buy-and-hold backtest from local Parquet data.

Wires ParquetStore + SimulatedExecutor + BacktestEngine — the Slice 0 walking
skeleton. Cost defaults are deliberately pessimistic (taker fee, upper-bound
slippage; see CLAUDE.md → Trading constraints).
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tradingbot.adapters.parquet.store import ParquetStore
from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.core.backtest.engine import BacktestEngine, BacktestResult
from tradingbot.core.backtest.metrics import PERIODS_PER_YEAR_1H, max_drawdown, sharpe_ratio
from tradingbot.core.ports.market_data import Timeframe

TAKER_FEE_RATE = Decimal("0.0005")
SLIPPAGE_RATE = Decimal("0.001")


@dataclass(frozen=True)
class BacktestReport:
    result: BacktestResult
    sharpe: float
    max_drawdown: float
    num_bars: int


def run_buy_and_hold(
    data_dir: Path,
    symbol: str,
    timeframe: Timeframe,
    initial_capital: Decimal,
    fee_rate: Decimal = TAKER_FEE_RATE,
    slippage_rate: Decimal = SLIPPAGE_RATE,
) -> BacktestReport:
    store = ParquetStore(data_dir)
    ohlcv = store.read(symbol, timeframe)

    executor = SimulatedExecutor(fee_rate=fee_rate, slippage_rate=slippage_rate)
    engine = BacktestEngine(executor, initial_capital, on_bar=executor.set_market)
    result = engine.run(ohlcv, symbol)

    equity = result.equity_curve.get_column("equity")
    return BacktestReport(
        result=result,
        sharpe=sharpe_ratio(equity, PERIODS_PER_YEAR_1H),
        max_drawdown=max_drawdown(equity),
        num_bars=len(ohlcv),
    )
