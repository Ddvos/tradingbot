"""Signal-driven backtest engine with ATR-based exits.

Execution model, chosen to avoid lookahead and stay pessimistic:

- The signal computed at bar i's close is executed at bar i+1's open.
- Stop-loss / take-profit are checked intrabar against high/low; if both could
  fire in the same bar, the stop fires (pessimistic).
- A time exit closes the position at the close of its Nth bar.
- Funding is charged on open notional at every bar close, in both directions
  (pessimistic: never assume funding is collected). Flat placeholder rate
  until real funding data arrives in Slice 3.
- A position still open at the end of the data stays open, marked to market;
  only closed round-trips appear in `trades`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

import polars as pl

from tradingbot.core.features.indicators import atr
from tradingbot.core.ports.executor import Fill, OrderExecutor, OrderRequest, Side
from tradingbot.core.ports.market_data import validate_ohlcv
from tradingbot.core.risk.sizing import all_in_size, position_size
from tradingbot.core.signals.signal import direction
from tradingbot.core.strategies.base import Strategy


class ExitReason(StrEnum):
    SIGNAL = "signal"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TIME = "time"


@dataclass(frozen=True)
class TradeRules:
    """Trade mechanics applied around any strategy. None disables a rule.

    Calibrated for 1h bars. risk_pct sizing derives quantity from the stop
    distance, so risk_pct requires stop_atr; risk_pct=None means all-in
    sizing (buy-and-hold). The default funding rate approximates 0.005% per
    4h funding interval (~11%/year), deliberately pessimistic.
    """

    atr_period: int = 14
    risk_pct: Decimal | None = Decimal("0.01")
    stop_atr: Decimal | None = Decimal("1.5")
    take_profit_atr: Decimal | None = Decimal("3.0")
    max_bars_held: int | None = 6
    funding_rate_per_bar: Decimal = Decimal("0.0000125")

    def __post_init__(self) -> None:
        if self.risk_pct is not None and self.stop_atr is None:
            raise ValueError("risk_pct sizing requires stop_atr — the stop defines the risk")
        if self.atr_period < 1:
            raise ValueError(f"atr_period must be >= 1, got {self.atr_period}")


@dataclass(frozen=True)
class Trade:
    """One closed round-trip. pnl = price P&L minus both fees; funding is
    charged to cash per bar, not attributed to trades."""

    entry_fill: Fill
    exit_fill: Fill
    reason: ExitReason
    pnl: Decimal


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pl.DataFrame
    """Columns: timestamp (Datetime ms UTC), equity (Float64) — mark-to-market at close."""
    fills: list[Fill]
    trades: list[Trade]
    initial_capital: Decimal
    final_equity: Decimal


@dataclass
class _OpenPosition:
    quantity: Decimal  # signed: > 0 long, < 0 short
    entry_fill: Fill
    entry_index: int
    stop: Decimal | None
    take_profit: Decimal | None


class BacktestEngine:
    """Stateful runner: walks bars chronologically, reconciles position to signal."""

    def __init__(
        self,
        executor: OrderExecutor,
        strategy: Strategy,
        initial_capital: Decimal,
        rules: TradeRules | None = None,
        set_market: Callable[[datetime, Decimal], None] | None = None,
    ) -> None:
        self._executor = executor
        self._strategy = strategy
        self._initial_capital = initial_capital
        self._rules = rules if rules is not None else TradeRules()
        self._set_market = set_market
        self._cash = initial_capital
        self._position: _OpenPosition | None = None
        self._fills: list[Fill] = []
        self._trades: list[Trade] = []

    def run(self, ohlcv: pl.DataFrame, symbol: str) -> BacktestResult:
        validate_ohlcv(ohlcv)
        if ohlcv.is_empty():
            raise ValueError("Cannot backtest an empty OHLCV frame")
        signals = self._strategy.signals(ohlcv)
        if len(signals) != ohlcv.height:
            raise ValueError(f"Strategy produced {len(signals)} signals for {ohlcv.height} bars")
        targets = [direction(s) for s in signals]
        atr_values: list[float | None] = (
            ohlcv.select(atr(self._rules.atr_period).alias("atr")).get_column("atr").to_list()
        )

        self._cash = self._initial_capital
        self._position = None
        self._fills = []
        self._trades = []
        equities: list[float] = []
        pending_target = 0
        last_close = Decimal(0)

        for index, (ts, open_, high, low, close, _volume) in enumerate(ohlcv.iter_rows()):
            open_p = Decimal(str(open_))
            high_p = Decimal(str(high))
            low_p = Decimal(str(low))
            close_p = Decimal(str(close))

            if pending_target != self._direction():
                if self._position is not None:
                    self._close_position(symbol, ts, open_p, ExitReason.SIGNAL)
                if pending_target != 0:
                    entry_atr = atr_values[index - 1] if index > 0 else None
                    self._open_position(pending_target, symbol, ts, open_p, entry_atr, index)

            self._check_barriers(symbol, ts, high_p, low_p)

            if self._position is not None:
                notional = abs(self._position.quantity) * close_p
                self._cash -= notional * self._rules.funding_rate_per_bar
                bars_held = index - self._position.entry_index + 1
                if self._rules.max_bars_held is not None and bars_held >= self._rules.max_bars_held:
                    self._close_position(symbol, ts, close_p, ExitReason.TIME)

            pending_target = targets[index]
            last_close = close_p
            equities.append(float(self._equity(close_p)))

        equity_curve = pl.DataFrame(
            {"timestamp": ohlcv.get_column("timestamp"), "equity": equities}
        )
        return BacktestResult(
            equity_curve=equity_curve,
            fills=self._fills,
            trades=self._trades,
            initial_capital=self._initial_capital,
            final_equity=self._equity(last_close),
        )

    def _direction(self) -> int:
        if self._position is None:
            return 0
        return 1 if self._position.quantity > 0 else -1

    def _equity(self, price: Decimal) -> Decimal:
        if self._position is None:
            return self._cash
        return self._cash + self._position.quantity * price

    def _execute(
        self, symbol: str, side: Side, quantity: Decimal, ts: datetime, reference_price: Decimal
    ) -> Fill:
        if self._set_market is not None:
            self._set_market(ts, reference_price)
        fill = self._executor.execute(OrderRequest(symbol, side, quantity))
        delta = fill.quantity if fill.side is Side.BUY else -fill.quantity
        self._cash -= delta * fill.price + fill.fee
        self._fills.append(fill)
        return fill

    def _open_position(
        self,
        target: int,
        symbol: str,
        ts: datetime,
        price: Decimal,
        entry_atr: float | None,
        index: int,
    ) -> None:
        rules = self._rules
        needs_atr = (
            rules.risk_pct is not None
            or rules.stop_atr is not None
            or rules.take_profit_atr is not None
        )
        entry_atr_dec: Decimal | None = None
        if needs_atr:
            if entry_atr is None or entry_atr <= 0:
                return  # cannot size or place barriers without a valid ATR yet
            entry_atr_dec = Decimal(str(entry_atr))

        if rules.risk_pct is not None and rules.stop_atr is not None and entry_atr_dec is not None:
            quantity = position_size(
                self._cash, price, entry_atr_dec, rules.risk_pct, rules.stop_atr
            )
        else:
            quantity = all_in_size(self._cash, price)
        if quantity <= 0:
            return

        side = Side.BUY if target > 0 else Side.SELL
        fill = self._execute(symbol, side, quantity, ts, price)
        sign = Decimal(target)
        stop = None
        take_profit = None
        if rules.stop_atr is not None and entry_atr_dec is not None:
            stop = fill.price - sign * rules.stop_atr * entry_atr_dec
        if rules.take_profit_atr is not None and entry_atr_dec is not None:
            take_profit = fill.price + sign * rules.take_profit_atr * entry_atr_dec
        self._position = _OpenPosition(sign * fill.quantity, fill, index, stop, take_profit)

    def _close_position(
        self, symbol: str, ts: datetime, reference_price: Decimal, reason: ExitReason
    ) -> None:
        position = self._position
        if position is None:
            return
        side = Side.SELL if position.quantity > 0 else Side.BUY
        fill = self._execute(symbol, side, abs(position.quantity), ts, reference_price)
        sign = Decimal(1) if position.quantity > 0 else Decimal(-1)
        price_move = sign * (fill.price - position.entry_fill.price)
        pnl = price_move * abs(position.quantity) - position.entry_fill.fee - fill.fee
        self._trades.append(Trade(position.entry_fill, fill, reason, pnl))
        self._position = None

    def _check_barriers(self, symbol: str, ts: datetime, high_p: Decimal, low_p: Decimal) -> None:
        position = self._position
        if position is None:
            return
        if position.quantity > 0:
            if position.stop is not None and low_p <= position.stop:
                self._close_position(symbol, ts, position.stop, ExitReason.STOP_LOSS)
            elif position.take_profit is not None and high_p >= position.take_profit:
                self._close_position(symbol, ts, position.take_profit, ExitReason.TAKE_PROFIT)
        elif position.stop is not None and high_p >= position.stop:
            self._close_position(symbol, ts, position.stop, ExitReason.STOP_LOSS)
        elif position.take_profit is not None and low_p <= position.take_profit:
            self._close_position(symbol, ts, position.take_profit, ExitReason.TAKE_PROFIT)
