"""HTTP routes for the live feature: status, paper trades, and commands.

Commands flow through DB flags (two-process design, ROADMAP.md Slice 5):
POST here, the bot picks it up on its next poll/tick.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from tradingbot.api.deps import get_paper_symbol, get_repositories
from tradingbot.api.features.live import handlers
from tradingbot.api.features.live.schemas import LiveStatus, PaperTrade, PromoteRequest
from tradingbot.application.persistence import Repositories

router = APIRouter(prefix="/live", tags=["live"])

_ReposDep = Annotated[Repositories, Depends(get_repositories)]
_SymbolDep = Annotated[str, Depends(get_paper_symbol)]


@router.get("/status")
def get_live_status(repos: _ReposDep, symbol: _SymbolDep) -> LiveStatus:
    return handlers.get_status(repos, symbol)


@router.get("/trades")
def list_paper_trades(repos: _ReposDep) -> list[PaperTrade]:
    return handlers.list_trades(repos)


@router.post("/pause")
def pause(repos: _ReposDep, symbol: _SymbolDep) -> LiveStatus:
    return handlers.set_paused(repos, symbol, paused=True)


@router.post("/resume")
def resume(repos: _ReposDep, symbol: _SymbolDep) -> LiveStatus:
    return handlers.set_paused(repos, symbol, paused=False)


@router.post("/promote")
def promote(repos: _ReposDep, symbol: _SymbolDep, request: PromoteRequest) -> LiveStatus:
    return handlers.promote(repos, symbol, request.name)


@router.post("/demote")
def demote(repos: _ReposDep, symbol: _SymbolDep) -> LiveStatus:
    return handlers.demote(repos, symbol)
