from collections.abc import Callable
from decimal import Decimal

import polars as pl
import pytest

from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.core.backtest.engine import BacktestEngine
from tradingbot.core.ports.market_data import OHLCV_SCHEMA

type OhlcvFactory = Callable[[list[float]], pl.DataFrame]


def make_engine(fee_rate: Decimal, slippage_rate: Decimal, capital: Decimal) -> BacktestEngine:
    executor = SimulatedExecutor(fee_rate=fee_rate, slippage_rate=slippage_rate)
    return BacktestEngine(executor, capital, on_bar=executor.set_market)


def test_buy_and_hold_without_costs(make_ohlcv: OhlcvFactory) -> None:
    engine = make_engine(Decimal(0), Decimal(0), capital=Decimal(1000))

    result = engine.run(make_ohlcv([100.0, 110.0, 120.0]), "PF_XBTUSD")

    # Entry commits 99.5% of capital: qty = 995 / 100 = 9.95, cash residue 5.
    assert len(result.fills) == 1
    assert result.fills[0].quantity == Decimal("9.95")
    equity = result.equity_curve.get_column("equity").to_list()
    assert equity == pytest.approx([1000.0, 5 + 9.95 * 110, 5 + 9.95 * 120])
    assert result.final_equity == Decimal("1199.00")


def test_costs_reduce_equity(make_ohlcv: OhlcvFactory) -> None:
    frame = make_ohlcv([100.0, 110.0])
    free = make_engine(Decimal(0), Decimal(0), capital=Decimal(1000)).run(frame, "PF_XBTUSD")
    costly = make_engine(Decimal("0.0005"), Decimal("0.001"), capital=Decimal(1000)).run(
        frame, "PF_XBTUSD"
    )

    assert costly.fills[0].price == Decimal("100.10")
    assert costly.fills[0].fee > 0
    assert costly.final_equity < free.final_equity


def test_empty_frame_raises() -> None:
    engine = make_engine(Decimal(0), Decimal(0), capital=Decimal(1000))
    with pytest.raises(ValueError, match="empty"):
        engine.run(pl.DataFrame(schema=OHLCV_SCHEMA), "PF_XBTUSD")


def test_unsorted_frame_raises(make_ohlcv: OhlcvFactory) -> None:
    engine = make_engine(Decimal(0), Decimal(0), capital=Decimal(1000))
    with pytest.raises(ValueError, match="strictly increasing"):
        engine.run(make_ohlcv([100.0, 110.0]).reverse(), "PF_XBTUSD")
