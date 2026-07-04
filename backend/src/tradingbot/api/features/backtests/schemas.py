"""Response schemas for the backtests feature (Pydantic at the boundary)."""

from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel

from tradingbot.core.ports.storage import BacktestRunRecord, ParamValue


class BacktestRunSummary(BaseModel):
    id: UUID
    strategy: str
    symbol: str
    timeframe: str
    data_start: datetime
    data_end: datetime
    initial_capital: Decimal
    final_equity: Decimal
    sharpe: float
    max_drawdown: float
    n_trades: int
    params: dict[str, ParamValue]
    created_at: datetime

    @classmethod
    def from_record(cls, record: BacktestRunRecord) -> Self:
        return cls(
            id=record.id,
            strategy=record.strategy,
            symbol=record.symbol,
            timeframe=record.timeframe,
            data_start=record.data_start,
            data_end=record.data_end,
            initial_capital=record.initial_capital,
            final_equity=record.final_equity,
            sharpe=record.sharpe,
            max_drawdown=record.max_drawdown,
            n_trades=record.n_trades,
            params=dict(record.params),
            created_at=record.created_at,
        )


class EquityPoint(BaseModel):
    time: int
    """Unix seconds (UTC) — the time format lightweight-charts expects."""

    value: float


class EquityCurveResponse(BaseModel):
    run_id: UUID
    points: list[EquityPoint]
