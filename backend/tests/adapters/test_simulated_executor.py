from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.core.ports.executor import OrderRequest, Side

BAR_TIME = datetime(2024, 1, 1, tzinfo=UTC)


def make_executor() -> SimulatedExecutor:
    executor = SimulatedExecutor(fee_rate=Decimal("0.0005"), slippage_rate=Decimal("0.001"))
    executor.set_market(BAR_TIME, Decimal(50000))
    return executor


def test_buy_fills_above_market_with_fee() -> None:
    fill = make_executor().execute(OrderRequest("PF_XBTUSD", Side.BUY, Decimal("0.5")))

    assert fill.price == Decimal("50050.00")
    assert fill.fee == Decimal("0.5") * Decimal("50050.00") * Decimal("0.0005")
    assert fill.quantity == Decimal("0.5")
    assert fill.timestamp == BAR_TIME


def test_sell_fills_below_market() -> None:
    fill = make_executor().execute(OrderRequest("PF_XBTUSD", Side.SELL, Decimal("0.5")))

    assert fill.price == Decimal("49950.00")


def test_execute_without_market_price_raises() -> None:
    executor = SimulatedExecutor(fee_rate=Decimal("0.0005"), slippage_rate=Decimal("0.001"))
    with pytest.raises(RuntimeError, match="set_market"):
        executor.execute(OrderRequest("PF_XBTUSD", Side.BUY, Decimal(1)))
