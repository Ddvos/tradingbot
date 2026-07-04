"""HTTP routes for the backtests feature."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from tradingbot.api.deps import get_repositories
from tradingbot.api.features.backtests import handlers
from tradingbot.api.features.backtests.schemas import BacktestRunSummary, EquityCurveResponse
from tradingbot.application.persistence import Repositories
from tradingbot.core.ports.storage import BacktestRunId

router = APIRouter(prefix="/backtests", tags=["backtests"])

_ReposDep = Annotated[Repositories, Depends(get_repositories)]


@router.get("")
def list_backtests(repos: _ReposDep) -> list[BacktestRunSummary]:
    return handlers.list_backtests(repos.backtest_runs)


@router.get("/{run_id}")
def get_backtest(run_id: UUID, repos: _ReposDep) -> BacktestRunSummary:
    return handlers.get_backtest(repos.backtest_runs, BacktestRunId(run_id))


@router.get("/{run_id}/equity")
def get_equity_curve(run_id: UUID, repos: _ReposDep) -> EquityCurveResponse:
    return handlers.get_equity_curve(repos.backtest_runs, BacktestRunId(run_id))
