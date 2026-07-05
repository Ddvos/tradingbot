"""Response/request schemas for the live feature (Pydantic at the boundary)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel

from tradingbot.core.ports.executor import Side
from tradingbot.core.ports.storage import PositionRecord, TradeRecord

type SideValue = Literal["buy", "sell"]


def _side_value(side: Side) -> SideValue:
    return "buy" if side is Side.BUY else "sell"


class OpenPosition(BaseModel):
    strategy: str
    symbol: str
    side: SideValue
    quantity: Decimal
    entry_price: Decimal
    entry_time: datetime
    stop: Decimal | None
    take_profit: Decimal | None
    bars_held: int

    @classmethod
    def from_record(cls, record: PositionRecord) -> Self:
        return cls(
            strategy=record.strategy,
            symbol=record.symbol,
            side=_side_value(record.side),
            quantity=record.quantity,
            entry_price=record.entry_price,
            entry_time=record.entry_time,
            stop=record.stop,
            take_profit=record.take_profit,
            bars_held=record.bars_held,
        )


class LiveStatus(BaseModel):
    state: Literal["running", "paused", "idle"]
    """idle = nothing promoted; the bot ticks but does not trade."""

    promoted_strategy: str | None
    last_tick_at: datetime | None
    last_bar_time: datetime | None
    cash: Decimal | None
    """None until the bot's first tick initializes the paper account."""
    equity: Decimal | None
    initial_capital: Decimal | None
    position: OpenPosition | None


class PaperTrade(BaseModel):
    id: UUID
    strategy: str
    symbol: str
    side: SideValue
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    fees: Decimal
    exit_reason: str

    @classmethod
    def from_record(cls, record: TradeRecord) -> Self:
        return cls(
            id=record.id,
            strategy=record.strategy,
            symbol=record.symbol,
            side=_side_value(record.side),
            quantity=record.quantity,
            entry_price=record.entry_price,
            exit_price=record.exit_price,
            entry_time=record.entry_time,
            exit_time=record.exit_time,
            pnl=record.pnl,
            fees=record.fees,
            exit_reason=record.exit_reason,
        )


class PromoteRequest(BaseModel):
    name: str
    """Name of a saved strategy config (see /strategies)."""
