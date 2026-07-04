"""HTTP routes for the strategies feature."""

from typing import Annotated

from fastapi import APIRouter, Depends

from tradingbot.api.deps import get_repositories
from tradingbot.api.features.strategies import handlers
from tradingbot.api.features.strategies.schemas import StrategyConfigSummary
from tradingbot.application.persistence import Repositories

router = APIRouter(prefix="/strategies", tags=["strategies"])

_ReposDep = Annotated[Repositories, Depends(get_repositories)]


@router.get("")
def list_strategy_configs(repos: _ReposDep) -> list[StrategyConfigSummary]:
    return handlers.list_strategy_configs(repos.strategy_configs)
