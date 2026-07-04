"""Response schemas for the strategies feature (Pydantic at the boundary)."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel

from tradingbot.core.ports.storage import ParamValue, StrategyConfigRecord


class StrategyConfigSummary(BaseModel):
    id: UUID
    name: str
    params: dict[str, ParamValue]
    created_at: datetime

    @classmethod
    def from_record(cls, record: StrategyConfigRecord) -> Self:
        return cls(
            id=record.id,
            name=record.name,
            params=dict(record.params),
            created_at=record.created_at,
        )
