"""Minimal backtest engine: buy-and-hold (Slice 0).

The engine only sees the OrderExecutor port, so the same fill semantics apply
in backtest and (later) live. The on_bar hook lets the application layer feed
each bar's close to a SimulatedExecutor without core importing adapters.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

import polars as pl

from tradingbot.core.ports.executor import Fill, OrderExecutor, OrderRequest, Side
from tradingbot.core.ports.market_data import validate_ohlcv

QUANTITY_QUANTUM = Decimal("0.00000001")

# Fraction of capital committed on entry; the rest stays as cash so the fill
# (slippage + fee, unknown until execution) can never overdraw the account.
ENTRY_CAPITAL_FRACTION = Decimal("0.995")


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pl.DataFrame
    """Columns: timestamp (Datetime ms UTC), equity (Float64) — mark-to-market at close."""
    fills: list[Fill]
    initial_capital: Decimal
    final_equity: Decimal


class BacktestEngine:
    """Stateful runner: walks bars chronologically, executes, marks to market."""

    def __init__(
        self,
        executor: OrderExecutor,
        initial_capital: Decimal,
        on_bar: Callable[[datetime, Decimal], None] | None = None,
    ) -> None:
        self._executor = executor
        self._initial_capital = initial_capital
        self._on_bar = on_bar

    def run(self, ohlcv: pl.DataFrame, symbol: str) -> BacktestResult:
        """Buy on the first close, hold, mark to market on every close."""
        validate_ohlcv(ohlcv)
        if ohlcv.is_empty():
            raise ValueError("Cannot backtest an empty OHLCV frame")

        cash = self._initial_capital
        position = Decimal(0)
        fills: list[Fill] = []
        equities: list[float] = []

        for timestamp, close in ohlcv.select("timestamp", "close").iter_rows():
            close_price = Decimal(str(close))
            if self._on_bar is not None:
                self._on_bar(timestamp, close_price)

            if not fills:
                quantity = (cash * ENTRY_CAPITAL_FRACTION / close_price).quantize(
                    QUANTITY_QUANTUM, rounding=ROUND_DOWN
                )
                fill = self._executor.execute(OrderRequest(symbol, Side.BUY, quantity))
                cash -= fill.quantity * fill.price + fill.fee
                position += fill.quantity
                fills.append(fill)

            equities.append(float(cash + position * close_price))

        final_equity = cash + position * Decimal(str(ohlcv.get_column("close").last()))
        equity_curve = pl.DataFrame(
            {"timestamp": ohlcv.get_column("timestamp"), "equity": equities}
        )
        return BacktestResult(
            equity_curve=equity_curve,
            fills=fills,
            initial_capital=self._initial_capital,
            final_equity=final_equity,
        )
