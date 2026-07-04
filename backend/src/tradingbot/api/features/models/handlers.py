"""Models feature: registry port → response schemas."""

from fastapi import HTTPException

from tradingbot.api.features.models.schemas import ModelSummary
from tradingbot.core.ports.storage import ModelRegistry


def list_models(registry: ModelRegistry) -> list[ModelSummary]:
    return [ModelSummary.from_record(record) for record in registry.list_models()]


def get_model(registry: ModelRegistry, name: str) -> ModelSummary:
    record = registry.get_by_name(name)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No registered model named {name!r}")
    return ModelSummary.from_record(record)
