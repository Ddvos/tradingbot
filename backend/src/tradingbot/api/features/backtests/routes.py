"""HTTP routes for the backtests feature."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from tradingbot.api.deps import get_ohlcv_dir, get_repositories
from tradingbot.api.features.backtests import handlers
from tradingbot.api.features.backtests.schemas import (
    BacktestRunSummary,
    CandlesResponse,
    EquityCurveResponse,
    TradesResponse,
)
from tradingbot.application.persistence import Repositories
from tradingbot.core.ports.storage import BacktestRunId

router = APIRouter(prefix="/backtests", tags=["backtests"])

_ReposDep = Annotated[Repositories, Depends(get_repositories)]
_OhlcvDep = Annotated[Path, Depends(get_ohlcv_dir)]


@router.get("")
def list_backtests(repos: _ReposDep) -> list[BacktestRunSummary]:
    return handlers.list_backtests(repos.backtest_runs)


@router.get("/{run_id}")
def get_backtest(run_id: UUID, repos: _ReposDep) -> BacktestRunSummary:
    return handlers.get_backtest(repos.backtest_runs, BacktestRunId(run_id))


@router.get("/{run_id}/equity")
def get_equity_curve(run_id: UUID, repos: _ReposDep) -> EquityCurveResponse:
    return handlers.get_equity_curve(repos.backtest_runs, BacktestRunId(run_id))


@router.get("/{run_id}/trades")
def get_trades(run_id: UUID, repos: _ReposDep) -> TradesResponse:
    return handlers.get_trades(repos.backtest_runs, BacktestRunId(run_id))


@router.get("/{run_id}/candles")
def get_candles(run_id: UUID, repos: _ReposDep, ohlcv_dir: _OhlcvDep) -> CandlesResponse:
    return handlers.get_candles(repos.backtest_runs, BacktestRunId(run_id), ohlcv_dir)
