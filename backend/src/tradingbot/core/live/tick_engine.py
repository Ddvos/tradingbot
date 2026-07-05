"""One closed bar at a time — the live counterpart of BacktestEngine.

Execution model, mirroring the backtest bar for bar:

- The tick fires moments after bar B closes. Barriers (stop/TP, stop wins
  ties) are resolved against B's high/low, funding is charged on open
  notional at B's close, and the time exit counts B as one more bar held —
  exactly what BacktestEngine does when it processes bar B.
- The fresh signal (computed from bars up to and including B) is executed
  at tick time. The backtest fills that signal at bar B+1's open; at tick
  time that open is an instant away, so the last close stands in for it —
  the gap between the two is well inside the slippage assumption.
- A position that survives the tick is returned in the new state; the
  caller persists it, which is what makes restarts safe.

Parity with BacktestEngine is not asserted by construction alone — it is
tested: the same bars and signals through both engines produce identical
trades and equity when consecutive opens equal the prior close
(tests/core/test_tick_engine.py).
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from tradingbot.core.backtest.engine import (
    ExitReason,
    TradeRules,
    barrier_prices,
    check_barriers,
    entry_quantity,
    rules_require_atr,
)
from tradingbot.core.ports.executor import Fill, OrderExecutor, OrderRequest, Side


@dataclass(frozen=True)
class TickPosition:
    """The open position between ticks — persistable, no engine internals."""

    quantity: Decimal
    """Signed: > 0 long, < 0 short."""
    entry_price: Decimal
    entry_fee: Decimal
    entry_time: datetime
    stop: Decimal | None
    take_profit: Decimal | None
    bars_held: int
    """Closed bars processed since entry."""


@dataclass(frozen=True)
class TickState:
    """Everything that must survive between ticks (and restarts)."""

    cash: Decimal
    position: TickPosition | None


@dataclass(frozen=True)
class ClosedTrade:
    """One closed round-trip. pnl = price P&L minus both fees; funding is
    charged to cash per bar, not attributed to trades (engine convention)."""

    quantity: Decimal
    """Signed entry quantity: > 0 was long, < 0 was short."""
    entry_price: Decimal
    entry_time: datetime
    exit_price: Decimal
    exit_time: datetime
    reason: ExitReason
    pnl: Decimal
    fees: Decimal


@dataclass(frozen=True)
class Bar:
    """The just-closed bar, prices already Decimal."""

    timestamp: datetime
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True)
class TickOutcome:
    state: TickState
    trades: list[ClosedTrade]
    fills: list[Fill]
    equity: Decimal
    """Mark-to-market at the just-closed bar's close."""


class TickEngine:
    """Stateless processor: state in, one bar + one signal, state out.

    All persistence stays with the caller; the executor is the port that
    makes paper (SimulatedExecutor) and live (KrakenExecutor, Slice 7) run
    this same code.
    """

    def __init__(
        self,
        executor: OrderExecutor,
        rules: TradeRules | None = None,
        set_market: Callable[[datetime, Decimal], None] | None = None,
    ) -> None:
        self._executor = executor
        self._rules = rules if rules is not None else TradeRules()
        self._set_market = set_market

    def process_bar(
        self,
        state: TickState,
        bar: Bar,
        target: int,
        atr_value: float | None,
        symbol: str,
    ) -> TickOutcome:
        """Process the just-closed bar, then reconcile to the fresh signal.

        `target` is the direction (+1/0/-1) of the signal computed on data
        up to and including `bar`; `atr_value` is the ATR at `bar`, the
        latest value a live bot can know — the same bar the backtest uses
        for an entry at the next open.
        """
        cash = state.cash
        position = state.position
        trades: list[ClosedTrade] = []
        fills: list[Fill] = []

        def execute(side: Side, quantity: Decimal, reference_price: Decimal) -> Fill:
            nonlocal cash
            if self._set_market is not None:
                self._set_market(bar.timestamp, reference_price)
            fill = self._executor.execute(OrderRequest(symbol, side, quantity))
            delta = fill.quantity if fill.side is Side.BUY else -fill.quantity
            cash -= delta * fill.price + fill.fee
            fills.append(fill)
            return fill

        def close(
            open_position: TickPosition, reference_price: Decimal, reason: ExitReason
        ) -> None:
            side = Side.SELL if open_position.quantity > 0 else Side.BUY
            fill = execute(side, abs(open_position.quantity), reference_price)
            sign = Decimal(1) if open_position.quantity > 0 else Decimal(-1)
            price_move = sign * (fill.price - open_position.entry_price)
            pnl = price_move * abs(open_position.quantity) - open_position.entry_fee - fill.fee
            trades.append(
                ClosedTrade(
                    quantity=open_position.quantity,
                    entry_price=open_position.entry_price,
                    entry_time=open_position.entry_time,
                    exit_price=fill.price,
                    exit_time=fill.timestamp,
                    reason=reason,
                    pnl=pnl,
                    fees=open_position.entry_fee + fill.fee,
                )
            )

        # 1. The just-closed bar acts on the existing position: barriers
        #    intrabar, then funding + time exit at the close — the same
        #    order as BacktestEngine.
        if position is not None:
            hit = check_barriers(
                position.quantity, position.stop, position.take_profit, bar.high, bar.low
            )
            if hit is not None:
                reason, reference_price = hit
                close(position, reference_price, reason)
                position = None
            else:
                position = replace(position, bars_held=position.bars_held + 1)
                cash -= abs(position.quantity) * bar.close * self._rules.funding_rate_per_bar
                max_bars = self._rules.max_bars_held
                if max_bars is not None and position.bars_held >= max_bars:
                    close(position, bar.close, ExitReason.TIME)
                    position = None

        # 2. Reconcile to the fresh signal at tick time (~ the next open).
        current = 0 if position is None else (1 if position.quantity > 0 else -1)
        if target != current:
            if position is not None:
                close(position, bar.close, ExitReason.SIGNAL)
                position = None
            if target != 0:
                # cash already reflects any close this tick — the same
                # balance the backtest would size from at the next open
                position = self._open(execute, cash, target, bar, atr_value)

        equity = cash if position is None else cash + position.quantity * bar.close
        return TickOutcome(
            state=TickState(cash=cash, position=position),
            trades=trades,
            fills=fills,
            equity=equity,
        )

    def _open(
        self,
        execute: Callable[[Side, Decimal, Decimal], Fill],
        balance: Decimal,
        target: int,
        bar: Bar,
        atr_value: float | None,
    ) -> TickPosition | None:
        rules = self._rules
        entry_atr: Decimal | None = None
        if rules_require_atr(rules):
            if atr_value is None or atr_value <= 0:
                return None  # cannot size or place barriers without a valid ATR yet
            entry_atr = Decimal(str(atr_value))

        quantity = entry_quantity(rules, balance, bar.close, entry_atr)
        if quantity <= 0:
            return None

        side = Side.BUY if target > 0 else Side.SELL
        fill = execute(side, quantity, bar.close)
        sign = Decimal(target)
        stop, take_profit = barrier_prices(rules, fill.price, sign, entry_atr)
        return TickPosition(
            quantity=sign * fill.quantity,
            entry_price=fill.price,
            entry_fee=fill.fee,
            entry_time=fill.timestamp,
            stop=stop,
            take_profit=take_profit,
            bars_held=0,
        )
