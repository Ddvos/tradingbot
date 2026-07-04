"""HTTP routes for the models feature."""

from typing import Annotated

from fastapi import APIRouter, Depends

from tradingbot.api.deps import get_repositories
from tradingbot.api.features.models import handlers
from tradingbot.api.features.models.schemas import ModelSummary
from tradingbot.application.persistence import Repositories

router = APIRouter(prefix="/models", tags=["models"])

_ReposDep = Annotated[Repositories, Depends(get_repositories)]


@router.get("")
def list_models(repos: _ReposDep) -> list[ModelSummary]:
    return handlers.list_models(repos.models)


@router.get("/{name}")
def get_model(name: str, repos: _ReposDep) -> ModelSummary:
    return handlers.get_model(repos.models, name)
