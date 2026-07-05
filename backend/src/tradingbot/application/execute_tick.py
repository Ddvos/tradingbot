"""Use case: one paper-trading tick (Slice 5).

Live Kraken data (closed bars only) + SimulatedExecutor (paper fills) +
the promoted strategy, one closed bar at a time through the TickEngine,
persisted through the storage ports. The runner (live/runner.py) schedules
this hourly.

Idempotent by design: a tick that finds no new closed bar is a no-op, so
scheduler double-fires and restarts are safe. If the bot was down, every
missed closed bar is replayed in order — barrier exits happen at the
prices a backtest over those bars would have used.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

from tradingbot.adapters.filesystem.model_store import ModelStore
from tradingbot.application.persistence import Repositories
from tradingbot.application.run_backtest import HOLD_RULES
from tradingbot.core.backtest.engine import TradeRules
from tradingbot.core.features.indicators import atr
from tradingbot.core.live.tick_engine import (
    Bar,
    ClosedTrade,
    TickEngine,
    TickPosition,
    TickState,
)
from tradingbot.core.ports.executor import OrderExecutor, Side
from tradingbot.core.ports.market_data import TIMEFRAME_SECONDS, MarketDataProvider, Timeframe
from tradingbot.core.ports.storage import (
    PaperAccountRecord,
    ParamValue,
    PositionId,
    PositionRecord,
    PositionRepository,
    StrategyConfigRecord,
    TradeId,
    TradeRecord,
)
from tradingbot.core.signals.signal import direction
from tradingbot.core.strategies.base import Strategy
from tradingbot.core.strategies.hold import HoldStrategy
from tradingbot.core.strategies.ma_cross import MACrossStrategy
from tradingbot.core.strategies.ml_strategy import ML_TRADE_RULES, MLStrategy

WARMUP_BARS = 2000
"""Bars fetched ahead of the newest one so rolling/ewm features are fully
converged. MLStrategy recomputes its features on whatever frame it gets;
the slowest state is Wilder's ATR/EMA (alpha 1/14), whose remaining warmup
error after 2000 hourly bars is far below any price quantum."""

type TickStatus = Literal["paused", "idle", "no_new_bar", "executed"]


@dataclass(frozen=True)
class TickReport:
    """What one tick did — the runner logs this."""

    status: TickStatus
    bar_time: datetime | None = None
    """Open time of the newest closed bar seen this tick."""
    n_trades: int = 0
    equity: Decimal | None = None


def _int_param(params: dict[str, ParamValue], key: str, default: int) -> int:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Strategy param {key!r} must be an int, got {value!r}")
    return value


def _float_param(params: dict[str, ParamValue], key: str, default: float) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"Strategy param {key!r} must be a number, got {value!r}")
    return float(value)


def _str_param(params: dict[str, ParamValue], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Strategy param {key!r} must be a string, got {value!r}")
    return value


def build_strategy(config: StrategyConfigRecord, models_dir: Path) -> tuple[Strategy, TradeRules]:
    """Instantiate the promoted strategy plus the trade rules that match its
    hypothesis — the same pairings every backtest and walk-forward used."""
    kind = config.params.get("kind")
    if kind == "hold":
        return HoldStrategy(), HOLD_RULES
    if kind == "ma_cross":
        strategy = MACrossStrategy(
            fast=_int_param(config.params, "fast", 20),
            slow=_int_param(config.params, "slow", 50),
        )
        return strategy, HOLD_RULES  # trend exits: signal flips only (finding #2)
    if kind == "ml":
        artifact = ModelStore(models_dir).load(_str_param(config.params, "model"))
        threshold = _float_param(config.params, "threshold", 0.6)
        return MLStrategy(artifact, threshold), ML_TRADE_RULES
    raise ValueError(f"Strategy config {config.name!r} has unknown kind {kind!r}")


def execute_tick(
    provider: MarketDataProvider,
    executor: OrderExecutor,
    repos: Repositories,
    *,
    symbol: str,
    timeframe: Timeframe = "1h",
    models_dir: Path,
    initial_capital: Decimal = Decimal(10_000),
    warmup_bars: int = WARMUP_BARS,
    set_market: Callable[[datetime, Decimal], None] | None = None,
    now: Callable[[], datetime] | None = None,
) -> TickReport:
    """Fetch → signal → risk → execute → persist, for every new closed bar."""
    clock = now if now is not None else (lambda: datetime.now(UTC))

    commands = repos.bot_commands.get()
    if commands is not None and commands.is_paused:
        return TickReport("paused")
    promoted = commands.promoted_strategy if commands is not None else None
    if promoted is None:
        return TickReport("idle")
    config = repos.strategy_configs.get_by_name(promoted)
    if config is None:
        raise ValueError(f"Promoted strategy {promoted!r} has no saved config")
    strategy, rules = build_strategy(config, models_dir)

    tick_time = clock()
    since = tick_time - timedelta(seconds=warmup_bars * TIMEFRAME_SECONDS[timeframe])
    ohlcv = provider.fetch_ohlcv(symbol, timeframe, since)
    if ohlcv.is_empty():
        raise ValueError(f"No closed {symbol} {timeframe} bars since {since}")

    account = repos.paper_account.get()
    if account is None:
        account = PaperAccountRecord(
            cash=initial_capital,
            equity=initial_capital,
            initial_capital=initial_capital,
            last_tick_at=None,
            last_bar_time=None,
            updated_at=tick_time,
        )

    newest: datetime = ohlcv[-1, "timestamp"]
    if account.last_bar_time is not None and newest <= account.last_bar_time:
        return TickReport("no_new_bar", bar_time=newest)

    # Everything after the last processed bar; on the very first tick only
    # the newest bar — never trade through the warmup history.
    if account.last_bar_time is None:
        first_row = ohlcv.height - 1
    else:
        timestamps = ohlcv.get_column("timestamp")
        first_row = int(timestamps.search_sorted(account.last_bar_time, side="right"))

    targets = [direction(value) for value in strategy.signals(ohlcv)]
    atr_values: list[float | None] = (
        ohlcv.select(atr(rules.atr_period).alias("atr")).get_column("atr").to_list()
    )
    engine = TickEngine(executor, rules, set_market=set_market)

    existing = repos.positions.get_open(symbol)
    state = TickState(cash=account.cash, position=_to_tick_position(existing))
    closed: list[ClosedTrade] = []
    equity = account.equity

    for offset, (ts, _open, high, low, close, _volume) in enumerate(
        ohlcv.slice(first_row).iter_rows()
    ):
        row = first_row + offset
        bar = Bar(
            timestamp=ts,
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
        )
        outcome = engine.process_bar(state, bar, targets[row], atr_values[row], symbol)
        state = outcome.state
        equity = outcome.equity
        closed.extend(outcome.trades)

    for trade in closed:
        repos.trades.add(_to_trade_record(trade, config.name, symbol))
    _persist_position(repos.positions, existing, state.position, config.name, symbol, tick_time)
    repos.paper_account.save(
        PaperAccountRecord(
            cash=state.cash,
            equity=equity,
            initial_capital=account.initial_capital,
            last_tick_at=tick_time,
            last_bar_time=newest,
            updated_at=tick_time,
        )
    )
    return TickReport("executed", bar_time=newest, n_trades=len(closed), equity=equity)


def _to_tick_position(record: PositionRecord | None) -> TickPosition | None:
    if record is None:
        return None
    sign = Decimal(1) if record.side is Side.BUY else Decimal(-1)
    return TickPosition(
        quantity=sign * record.quantity,
        entry_price=record.entry_price,
        entry_fee=record.entry_fee,
        entry_time=record.entry_time,
        stop=record.stop,
        take_profit=record.take_profit,
        bars_held=record.bars_held,
    )


def _to_trade_record(trade: ClosedTrade, strategy: str, symbol: str) -> TradeRecord:
    return TradeRecord(
        id=TradeId(uuid4()),
        strategy=strategy,
        symbol=symbol,
        side=Side.BUY if trade.quantity > 0 else Side.SELL,
        quantity=abs(trade.quantity),
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        pnl=trade.pnl,
        fees=trade.fees,
        exit_reason=trade.reason.value,
    )


def _persist_position(
    positions: PositionRepository,
    existing: PositionRecord | None,
    current: TickPosition | None,
    strategy: str,
    symbol: str,
    now: datetime,
) -> None:
    """Mirror the in-memory position to storage: update the same row while
    the entry is unchanged, otherwise replace (or clear) it."""
    if current is None:
        if existing is not None:
            positions.delete(existing.id)
        return
    same_entry = existing is not None and existing.entry_time == current.entry_time
    if existing is not None and not same_entry:
        positions.delete(existing.id)
    positions.save(
        PositionRecord(
            id=existing.id if existing is not None and same_entry else PositionId(uuid4()),
            strategy=strategy,
            symbol=symbol,
            side=Side.BUY if current.quantity > 0 else Side.SELL,
            quantity=abs(current.quantity),
            entry_price=current.entry_price,
            entry_fee=current.entry_fee,
            entry_time=current.entry_time,
            stop=current.stop,
            take_profit=current.take_profit,
            bars_held=current.bars_held,
            updated_at=now,
        )
    )
