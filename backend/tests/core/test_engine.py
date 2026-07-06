from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.core.backtest.engine import BacktestEngine, ExitReason, TradeRules
from tradingbot.core.ports.market_data import OHLCV_SCHEMA

NO_RULES = TradeRules(
    risk_pct=None,
    stop_atr=None,
    take_profit_atr=None,
    max_bars_held=None,
    funding_rate_per_bar=Decimal(0),
)
# Bars below have a range of 2 on the first bar, so ATR at entry time is 2:
# stop distance = 1.5 * 2 = 3, take-profit distance = 3.0 * 2 = 6.
BARRIER_RULES = TradeRules(
    risk_pct=Decimal("0.01"),
    stop_atr=Decimal("1.5"),
    take_profit_atr=Decimal("3.0"),
    max_bars_held=None,
    funding_rate_per_bar=Decimal(0),
)


@dataclass(frozen=True)
class StubStrategy:
    values: tuple[str, ...]

    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        return pl.Series("signal", list(self.values))


def frame(bars: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    """Build an OHLCV frame from (open, high, low, close) tuples."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=i) for i in range(len(bars))],
            "open": [b[0] for b in bars],
            "high": [b[1] for b in bars],
            "low": [b[2] for b in bars],
            "close": [b[3] for b in bars],
            "volume": [100.0] * len(bars),
        },
        schema=OHLCV_SCHEMA,
    )


def make_engine(
    signals: list[str], rules: TradeRules, capital: Decimal = Decimal(10000)
) -> BacktestEngine:
    executor = SimulatedExecutor(fee_rate=Decimal(0), slippage_rate=Decimal(0))
    strategy = StubStrategy(tuple(signals))
    return BacktestEngine(executor, strategy, capital, rules, set_market=executor.set_market)


def test_signal_executes_at_next_bar_open() -> None:
    bars = frame([(100, 101, 99, 100), (102, 103, 101, 102), (104, 105, 103, 104)])
    result = make_engine(["long", "long", "long"], NO_RULES).run(bars, "X")

    assert len(result.fills) == 1
    assert result.fills[0].price == Decimal(102)  # bar 1's open, not bar 0's close
    assert result.fills[0].timestamp == datetime(2024, 1, 1, 1, tzinfo=UTC)


def test_flat_signal_closes_at_next_open() -> None:
    bars = frame([(100, 101, 99, 100), (102, 103, 101, 102), (104, 105, 103, 104)])
    result = make_engine(["long", "flat", "flat"], NO_RULES).run(bars, "X")

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.reason is ExitReason.SIGNAL
    assert trade.exit_fill.price == Decimal(104)
    assert trade.pnl == (Decimal(104) - Decimal(102)) * trade.entry_fill.quantity


def test_stop_loss_exits_intrabar_and_risks_one_percent() -> None:
    # entry at open 100, stop at 97; bar 1's low of 96 pierces it
    bars = frame([(100, 101, 99, 100), (100, 101, 96, 98)])
    result = make_engine(["long", "long"], BARRIER_RULES).run(bars, "X")

    trade = result.trades[0]
    assert trade.reason is ExitReason.STOP_LOSS
    assert trade.exit_fill.price == Decimal(97)
    # qty = (10000 * 1%) / 3 = 33.33333333 -> losing 3 loses ~1% of the account
    assert trade.entry_fill.quantity == Decimal("33.33333333")
    assert trade.pnl == Decimal("-99.99999999")


def test_take_profit_exits_intrabar() -> None:
    # entry at open 100, take-profit at 106; bar 1's high of 107 reaches it
    bars = frame([(100, 101, 99, 100), (100, 107, 99.5, 105)])
    result = make_engine(["long", "long"], BARRIER_RULES).run(bars, "X")

    trade = result.trades[0]
    assert trade.reason is ExitReason.TAKE_PROFIT
    assert trade.exit_fill.price == Decimal(106)
    assert trade.pnl == Decimal("199.99999998")


def test_trade_records_the_barrier_levels_it_ran_with() -> None:
    # entry 100 with ATR 2: stop 100 - 1.5*2 = 97, take-profit 100 + 3*2 = 106
    bars = frame([(100, 101, 99, 100), (100, 101, 96, 98)])
    result = make_engine(["long", "long"], BARRIER_RULES).run(bars, "X")

    trade = result.trades[0]
    assert trade.stop == Decimal("97.0")
    assert trade.take_profit == Decimal("106.0")


def test_trade_barriers_are_none_without_barrier_rules() -> None:
    bars = frame([(100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100)])
    result = make_engine(["long", "flat", "flat"], NO_RULES).run(bars, "X")

    trade = result.trades[0]
    assert trade.stop is None
    assert trade.take_profit is None


def test_stop_wins_when_both_barriers_hit_in_one_bar() -> None:
    bars = frame([(100, 101, 99, 100), (100, 107, 96, 100)])
    result = make_engine(["long", "long"], BARRIER_RULES).run(bars, "X")

    assert result.trades[0].reason is ExitReason.STOP_LOSS


def test_time_exit_after_max_bars() -> None:
    rules = replace(BARRIER_RULES, max_bars_held=2)
    bars = frame(
        [
            (100, 101, 99, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
        ]
    )
    result = make_engine(["long"] * 4, rules).run(bars, "X")

    trade = result.trades[0]
    assert trade.reason is ExitReason.TIME
    # entered at bar 1's open, closed at bar 2's close = held exactly 2 bars
    assert trade.exit_fill.timestamp == datetime(2024, 1, 1, 2, tzinfo=UTC)
    assert trade.exit_fill.price == Decimal(100)


def test_funding_is_charged_on_open_notional_every_close() -> None:
    rules = replace(NO_RULES, funding_rate_per_bar=Decimal("0.001"))
    bars = frame([(100, 100.5, 99.5, 100)] * 3)
    result = make_engine(["long"] * 3, rules).run(bars, "X")

    # all-in at open 100: qty 99.5, cash residue 50; funding 9.95 per bar for 2 bars
    assert result.final_equity == Decimal("9980.10")


def test_short_position_profits_when_price_falls() -> None:
    bars = frame([(100, 101, 99, 100), (100, 101, 89, 95), (95, 96, 89, 90)])
    result = make_engine(["short", "short", "short"], NO_RULES).run(bars, "X")

    # sold 99.5 at 100 (cash 19950), marked at 90: 19950 - 99.5 * 90
    assert result.final_equity == Decimal("10995.00")


def test_short_stop_loss_sits_above_entry() -> None:
    # short entry at open 100, stop at 103; bar 1's high of 104 pierces it
    bars = frame([(100, 101, 99, 100), (100, 104, 99, 102)])
    result = make_engine(["short", "short"], BARRIER_RULES).run(bars, "X")

    trade = result.trades[0]
    assert trade.reason is ExitReason.STOP_LOSS
    assert trade.exit_fill.price == Decimal(103)
    assert trade.pnl == Decimal("-99.99999999")


def test_reenters_after_stop_while_signal_stays_long() -> None:
    bars = frame(
        [
            (100, 101, 99, 100),
            (100, 101, 96, 98),  # stop at 97 hit
            (98, 99, 97.5, 98),  # signal still long -> re-entry at this open
            (98, 99, 97.5, 98),
        ]
    )
    result = make_engine(["long"] * 4, BARRIER_RULES).run(bars, "X")

    assert len(result.trades) == 1  # only the stopped-out round-trip closed
    assert len(result.fills) == 3  # entry, stop exit, re-entry


def test_mismatched_signal_count_raises() -> None:
    bars = frame([(100, 101, 99, 100), (100, 101, 99, 100)])
    with pytest.raises(ValueError, match="signals"):
        make_engine(["long"], NO_RULES).run(bars, "X")


def test_empty_frame_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        make_engine([], NO_RULES).run(pl.DataFrame(schema=OHLCV_SCHEMA), "X")
