"""Response schemas for the models feature (Pydantic at the boundary)."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel

from tradingbot.core.ports.storage import ModelRecord


class ModelSummary(BaseModel):
    id: UUID
    name: str
    artifact_path: str
    auc: float
    ic: float
    trained_at: datetime
    created_at: datetime

    @classmethod
    def from_record(cls, record: ModelRecord) -> Self:
        return cls(
            id=record.id,
            name=record.name,
            artifact_path=record.artifact_path,
            auc=record.auc,
            ic=record.ic,
            trained_at=record.trained_at,
            created_at=record.created_at,
        )
