"""HTTP routes for the walkforward feature."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from tradingbot.api.deps import get_ohlcv_dir, get_walkforward_dir
from tradingbot.api.features.walkforward import handlers
from tradingbot.api.features.walkforward.schemas import (
    WalkForwardCandlesResponse,
    WalkForwardEquityResponse,
    WalkForwardRunDetail,
    WalkForwardRunSummary,
    WalkForwardTradesResponse,
)

router = APIRouter(prefix="/walkforward", tags=["walkforward"])

_DirDep = Annotated[Path, Depends(get_walkforward_dir)]
_OhlcvDep = Annotated[Path, Depends(get_ohlcv_dir)]


@router.get("")
def list_walkforward_runs(base_dir: _DirDep) -> list[WalkForwardRunSummary]:
    return handlers.list_runs(base_dir)


@router.get("/{symbol}/{run}")
def get_walkforward_run(symbol: str, run: str, base_dir: _DirDep) -> WalkForwardRunDetail:
    return handlers.get_run(base_dir, symbol, run)


@router.get("/{symbol}/{run}/equity")
def get_walkforward_equity(symbol: str, run: str, base_dir: _DirDep) -> WalkForwardEquityResponse:
    return handlers.get_equity(base_dir, symbol, run)


@router.get("/{symbol}/{run}/trades")
def get_walkforward_trades(symbol: str, run: str, base_dir: _DirDep) -> WalkForwardTradesResponse:
    return handlers.get_trades(base_dir, symbol, run)


@router.get("/{symbol}/{run}/candles")
def get_walkforward_candles(
    symbol: str, run: str, base_dir: _DirDep, ohlcv_dir: _OhlcvDep
) -> WalkForwardCandlesResponse:
    return handlers.get_candles(base_dir, ohlcv_dir, symbol, run)
