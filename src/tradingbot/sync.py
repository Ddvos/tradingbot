"""Keeping the store up to date: import the archive, catch up from the endpoint.

Both are safe to re-run: the same hour is never stored twice, and the hour
that is still forming is never stored at all.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tradingbot.candles import Candle, Timeframe
from tradingbot.kraken import REST_REACH, read_archive
from tradingbot.store import CandleStore

HOUR = Timeframe.H1.seconds

HourlySource = Callable[[int | None], list[Candle]]
"""Answers the hourly candles from `since` (inclusive) on; `None` means all it has."""


@dataclass(frozen=True)
class ImportResult:
    stored: int
    """Hours that were new to the store."""
    time_range: tuple[int, int]
    """Start time of the oldest and the newest candle in the store afterwards."""


def import_archive(path: Path, store: CandleStore) -> ImportResult:
    """Store every candle of the archive file; re-importing adds nothing."""
    stored = store.upsert(read_archive(path))
    time_range = store.time_range()
    if time_range is None:
        raise ValueError(f"{path} holds no candles")
    return ImportResult(stored, time_range)


@dataclass(frozen=True)
class CatchUpResult:
    stored: int
    """Hours that were new to the store."""
    unreachable: tuple[int, int] | None
    """First and last hour between the store's newest candle and the oldest one the
    endpoint still had, when the endpoint's reach could not bridge them. Hours the
    endpoint could reach but had no candle for are quiet hours, not unreachable."""


def catch_up(store: CandleStore, source: HourlySource, *, now: int) -> CatchUpResult:
    """Append the completed hourly candles newer than the store's newest one.

    A candle is complete once its hour has ended at `now`; the still-forming
    hour is never stored, so re-running is safe at any moment.
    """
    time_range = store.time_range()
    since = time_range[1] + HOUR if time_range is not None else None
    fetched = sorted(source(since), key=lambda c: c.time)
    completed = [c for c in fetched if c.time + HOUR <= now]
    stored = store.upsert(completed)
    unreachable: tuple[int, int] | None = None
    truncated = len(fetched) >= REST_REACH
    if since is not None and truncated and fetched[0].time > since:
        unreachable = (since, fetched[0].time - HOUR)
    return CatchUpResult(stored, unreachable)
