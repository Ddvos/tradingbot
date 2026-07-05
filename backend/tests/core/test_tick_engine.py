"""TickEngine behavior + the parity guarantee against BacktestEngine.

The parity test is the load-bearing one: identical bars and signals through
both engines must produce identical trades and equity when consecutive
opens equal the prior close (the tick engine fills signal changes at the
last close, the backtest at the next open — equal by construction here).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import polars as pl

from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.core.backtest.engine import BacktestEngine, ExitReason, TradeRules
from tradingbot.core.features.indicators import atr
from tradingbot.core.live.tick_engine import Bar, TickEngine, TickState
from tradingbot.core.ports.market_data import OHLCV_SCHEMA
from tradingbot.core.signals.signal import Signal, direction

FEE = Decimal("0.0005")
SLIPPAGE = Decimal("0.001")
CAPITAL = Decimal(10_000)
SYMBOL = "PF_XBTUSD"


@dataclass(frozen=True)
class ScriptedStrategy:
    values: list[str]

    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        return pl.Series("signal", self.values[: ohlcv.height])


def chained_ohlcv(n: int, seed: int = 7) -> pl.DataFrame:
    """Random walk where every bar opens exactly at the previous close."""
    rng = np.random.default_rng(seed)
    closes = 100.0 + np.cumsum(rng.normal(0.0, 1.5, n))
    opens = np.concatenate(([closes[0]], closes[:-1]))
    spread = rng.uniform(0.5, 2.5, n)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=i) for i in range(n)],
            "open": opens,
            "high": np.maximum(opens, closes) + spread,
            "low": np.minimum(opens, closes) - spread,
            "close": closes,
            "volume": [100.0] * n,
        },
        schema=OHLCV_SCHEMA,
    )


def run_tick_engine(
    ohlcv: pl.DataFrame, signal_values: list[str], rules: TradeRules
) -> tuple[TickState, list[Decimal], list[ExitReason]]:
    executor = SimulatedExecutor(fee_rate=FEE, slippage_rate=SLIPPAGE)
    engine = TickEngine(executor, rules, set_market=executor.set_market)
    atr_values: list[float | None] = (
        ohlcv.select(atr(rules.atr_period).alias("atr")).get_column("atr").to_list()
    )

    state = TickState(cash=CAPITAL, position=None)
    pnls: list[Decimal] = []
    reasons: list[ExitReason] = []
    for index, (ts, _open, high, low, close, _volume) in enumerate(ohlcv.iter_rows()):
        bar = Bar(
            timestamp=ts,
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
        )
        outcome = engine.process_bar(
            state, bar, direction(signal_values[index]), atr_values[index], SYMBOL
        )
        state = outcome.state
        pnls.extend(trade.pnl for trade in outcome.trades)
        reasons.extend(trade.reason for trade in outcome.trades)
    return state, pnls, reasons


def test_parity_with_backtest_engine() -> None:
    """Same bars, same signals, same rules -> identical trades and cash."""
    n = 300
    ohlcv = chained_ohlcv(n)
    # long stretches with flat gaps exercises entries, signal exits, stops,
    # take-profits, and time exits; the flat tail avoids the one designed
    # difference (the backtest drops the last bar's signal, the tick engine
    # executes it at tick time)
    signal_values = [
        Signal.LONG.value if (i % 25) < 15 else Signal.FLAT.value for i in range(n - 10)
    ] + [Signal.FLAT.value] * 10
    rules = TradeRules()  # 1% risk, 1.5 ATR stop, 3.0 ATR TP, 6-bar time exit

    executor = SimulatedExecutor(fee_rate=FEE, slippage_rate=SLIPPAGE)
    backtest = BacktestEngine(
        executor, ScriptedStrategy(signal_values), CAPITAL, rules, set_market=executor.set_market
    )
    expected = backtest.run(ohlcv, SYMBOL)

    state, pnls, reasons = run_tick_engine(ohlcv, signal_values, rules)

    assert state.position is None
    assert reasons == [trade.reason for trade in expected.trades]
    assert pnls == [trade.pnl for trade in expected.trades]
    assert state.cash == expected.final_equity
    # sanity: the scenario actually exercised every exit path
    assert len(pnls) > 5
    assert {ExitReason.SIGNAL, ExitReason.TIME} <= set(reasons)


def make_bar(high: float, low: float, close: float, hour: int = 0) -> Bar:
    return Bar(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
    )


def make_engine(rules: TradeRules) -> TickEngine:
    executor = SimulatedExecutor(fee_rate=Decimal(0), slippage_rate=Decimal(0))
    return TickEngine(executor, rules, set_market=executor.set_market)


def test_entry_places_barriers_and_survives_ticks() -> None:
    rules = TradeRules()
    engine = make_engine(rules)
    state = TickState(cash=CAPITAL, position=None)

    # a calm bar so neither barrier of the fresh position can fire next tick
    outcome = engine.process_bar(
        state, make_bar(101, 99, 100), target=1, atr_value=2.0, symbol=SYMBOL
    )

    position = outcome.state.position
    assert position is not None
    assert position.quantity > 0
    assert position.bars_held == 0
    assert position.stop == Decimal(100) - Decimal("1.5") * Decimal(2)
    assert position.take_profit == Decimal(100) + Decimal("3.0") * Decimal(2)

    second = engine.process_bar(
        outcome.state, make_bar(100.5, 99.5, 100, hour=1), target=1, atr_value=2.0, symbol=SYMBOL
    )
    held = second.state.position
    assert held is not None
    assert held.bars_held == 1
    funding = abs(held.quantity) * Decimal(100) * rules.funding_rate_per_bar
    assert second.state.cash == outcome.state.cash - funding


def test_stop_wins_when_bar_hits_both_barriers() -> None:
    engine = make_engine(TradeRules())
    state = TickState(cash=CAPITAL, position=None)
    opened = engine.process_bar(
        state, make_bar(101, 99, 100), target=1, atr_value=2.0, symbol=SYMBOL
    )

    # stop at 97, TP at 106: this bar sweeps both
    swept = engine.process_bar(
        opened.state, make_bar(110, 90, 100, hour=1), target=1, atr_value=2.0, symbol=SYMBOL
    )

    assert [t.reason for t in swept.trades] == [ExitReason.STOP_LOSS]
    assert swept.trades[0].exit_price == Decimal(97)


def test_time_exit_then_reentry_matches_engine_semantics() -> None:
    rules = TradeRules(max_bars_held=2)
    engine = make_engine(rules)
    state = TickState(cash=CAPITAL, position=None)
    state = engine.process_bar(state, make_bar(101, 99, 100), 1, 2.0, SYMBOL).state
    state = engine.process_bar(state, make_bar(101, 99, 100, hour=1), 1, 2.0, SYMBOL).state

    third = engine.process_bar(state, make_bar(101, 99, 100, hour=2), 1, 2.0, SYMBOL)

    # bars_held reached 2 -> TIME exit at the close; the still-long signal
    # re-enters immediately (exactly what the backtest does at the next open)
    assert [t.reason for t in third.trades] == [ExitReason.TIME]
    reentered = third.state.position
    assert reentered is not None
    assert reentered.bars_held == 0


def test_no_entry_without_valid_atr() -> None:
    engine = make_engine(TradeRules())
    state = TickState(cash=CAPITAL, position=None)

    outcome = engine.process_bar(
        state, make_bar(101, 99, 100), target=1, atr_value=None, symbol=SYMBOL
    )

    assert outcome.state.position is None
    assert outcome.state.cash == CAPITAL
    assert outcome.trades == []
