"""Order execution port: the contract between strategy code and an exchange.

Money crosses this boundary, so quantities, prices, and fees are Decimal —
never float. See CLAUDE.md → Type discipline.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import NewType, Protocol

OrderId = NewType("OrderId", str)


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class OrderRequest:
    """A market order. Limit orders arrive in a later slice."""

    symbol: str
    side: Side
    quantity: Decimal


@dataclass(frozen=True)
class Fill:
    order_id: OrderId
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    """Actual fill price, slippage included."""
    fee: Decimal
    """Absolute fee in quote currency (USD)."""
    timestamp: datetime


class OrderExecutor(Protocol):
    """Port with two implementations: KrakenExecutor (live), SimulatedExecutor (backtest)."""

    def execute(self, order: OrderRequest) -> Fill:
        """Execute a market order and return the resulting fill."""
        ...
