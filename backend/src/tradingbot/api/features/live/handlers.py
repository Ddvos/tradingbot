"""Live feature: bot state, paper account, and commands over the storage ports.

The API never talks to the bot process — it writes command flags the bot
reads on its next tick (poll) and renders the state the bot last persisted.
"""

from fastapi import HTTPException

from tradingbot.api.features.live.schemas import LiveStatus, OpenPosition, PaperTrade
from tradingbot.application.persistence import Repositories


def get_status(repos: Repositories, symbol: str) -> LiveStatus:
    commands = repos.bot_commands.get()
    is_paused = commands.is_paused if commands is not None else False
    promoted = commands.promoted_strategy if commands is not None else None
    account = repos.paper_account.get()
    position = repos.positions.get_open(symbol)

    if is_paused:
        state = "paused"
    elif promoted is not None:
        state = "running"
    else:
        state = "idle"
    return LiveStatus(
        state=state,
        promoted_strategy=promoted,
        last_tick_at=account.last_tick_at if account is not None else None,
        last_bar_time=account.last_bar_time if account is not None else None,
        cash=account.cash if account is not None else None,
        equity=account.equity if account is not None else None,
        initial_capital=account.initial_capital if account is not None else None,
        position=OpenPosition.from_record(position) if position is not None else None,
    )


def list_trades(repos: Repositories) -> list[PaperTrade]:
    return [PaperTrade.from_record(record) for record in repos.trades.list_trades()]


def set_paused(repos: Repositories, symbol: str, paused: bool) -> LiveStatus:
    repos.bot_commands.set_paused(paused)
    return get_status(repos, symbol)


def promote(repos: Repositories, symbol: str, name: str) -> LiveStatus:
    if repos.strategy_configs.get_by_name(name) is None:
        raise HTTPException(
            status_code=404,
            detail=f"No strategy config named {name!r} — save it first (see /strategies)",
        )
    repos.bot_commands.set_promoted(name)
    return get_status(repos, symbol)


def demote(repos: Repositories, symbol: str) -> LiveStatus:
    repos.bot_commands.set_promoted(None)
    return get_status(repos, symbol)
