"""Simulated order execution for backtests: fill at the current bar close.

Costs are applied pessimistically: slippage moves the fill price against the
order, and the fee is taken on the slipped notional.
"""

from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from tradingbot.core.ports.executor import Fill, OrderId, OrderRequest, Side

PRICE_QUANTUM = Decimal("0.01")


class SimulatedExecutor:
    """Implements the OrderExecutor port against a market price fed per bar.

    The backtest engine calls set_market on every bar (wired via its on_bar
    hook), so fills always happen at the close the strategy just observed.
    """

    def __init__(self, fee_rate: Decimal, slippage_rate: Decimal) -> None:
        self._fee_rate = fee_rate
        self._slippage_rate = slippage_rate
        self._market_time: datetime | None = None
        self._market_price: Decimal | None = None
        self._fill_count = 0

    def set_market(self, timestamp: datetime, price: Decimal) -> None:
        self._market_time = timestamp
        self._market_price = price

    def execute(self, order: OrderRequest) -> Fill:
        if self._market_price is None or self._market_time is None:
            raise RuntimeError("SimulatedExecutor has no market price — call set_market first")
        slip = 1 if order.side is Side.BUY else -1
        fill_price = (self._market_price * (1 + slip * self._slippage_rate)).quantize(
            PRICE_QUANTUM, rounding=ROUND_HALF_EVEN
        )
        fee = order.quantity * fill_price * self._fee_rate
        self._fill_count += 1
        return Fill(
            order_id=OrderId(f"sim-{self._fill_count}"),
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            fee=fee,
            timestamp=self._market_time,
        )
