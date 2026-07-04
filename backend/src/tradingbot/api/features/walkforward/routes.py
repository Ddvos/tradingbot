"""HTTP routes for the walkforward feature."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from tradingbot.api.deps import get_walkforward_dir
from tradingbot.api.features.walkforward import handlers
from tradingbot.api.features.walkforward.schemas import (
    WalkForwardEquityResponse,
    WalkForwardRunDetail,
    WalkForwardRunSummary,
)

router = APIRouter(prefix="/walkforward", tags=["walkforward"])

_DirDep = Annotated[Path, Depends(get_walkforward_dir)]


@router.get("")
def list_walkforward_runs(base_dir: _DirDep) -> list[WalkForwardRunSummary]:
    return handlers.list_runs(base_dir)


@router.get("/{symbol}/{run}")
def get_walkforward_run(symbol: str, run: str, base_dir: _DirDep) -> WalkForwardRunDetail:
    return handlers.get_run(base_dir, symbol, run)


@router.get("/{symbol}/{run}/equity")
def get_walkforward_equity(symbol: str, run: str, base_dir: _DirDep) -> WalkForwardEquityResponse:
    return handlers.get_equity(base_dir, symbol, run)
