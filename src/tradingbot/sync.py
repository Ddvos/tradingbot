"""Keeping the store up to date: import the archive, catch up from the endpoint.

Both work on the store's own timeframe, fifteen-minute or hourly, and both
are safe to re-run: the same period is never stored twice, and the period
that is still forming is never stored at all. Three impossible hourly prints
are skipped at import, by a hand list of their hours (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from tradingbot.candles import Candle, Timeframe, period_start
from tradingbot.kraken import REST_REACH, read_archive
from tradingbot.store import CandleStore

DROPPED_HOURS = frozenset({1_383_807_600, 1_384_056_000, 1_384_236_000})
"""Start times of the three hourly prints dropped by ADR-0005: 2013-11-07 07:00
(high 3,484), 2013-11-10 04:00 (high and close 4,000) and 2013-11-12 06:00
(high 4,000), UTC. Neither these hours nor any fifteen-minute candle inside
them is stored. A scan of the eleven years against neighbouring closes found
nothing else, so there is no general rule."""

CandleSource = Callable[[int | None], list[Candle]]
"""Answers the candles from `since` (inclusive) on; `None` means all it has."""


def is_dropped(time: int) -> bool:
    """Whether a candle starting at `time` falls in one of the dropped hours."""
    return period_start(time, Timeframe.H1) in DROPPED_HOURS


def without_dropped(candles: Iterable[Candle]) -> Iterator[Candle]:
    return (c for c in candles if not is_dropped(c.time))


@dataclass(frozen=True)
class ImportResult:
    stored: int
    """Candles that were new to the store."""
    time_range: tuple[int, int]
    """Start time of the oldest and the newest candle in the store afterwards."""


def import_archive(path: Path, store: CandleStore) -> ImportResult:
    """Store every candle of the archive file but the dropped prints; re-importing adds nothing."""
    stored = store.upsert(without_dropped(read_archive(path)))
    time_range = store.time_range()
    if time_range is None:
        raise ValueError(f"{path} holds no candles")
    return ImportResult(stored, time_range)


@dataclass(frozen=True)
class CatchUpResult:
    stored: int
    """Candles that were new to the store."""
    unreachable: tuple[int, int] | None
    """First and last period between the store's newest candle and the oldest one the
    endpoint still had, when the endpoint's reach could not bridge them. Periods the
    endpoint could reach but had no candle for are quiet periods, not unreachable."""


def catch_up(store: CandleStore, source: CandleSource, *, now: int) -> CatchUpResult:
    """Append the completed candles newer than the store's newest one.

    A candle is complete once its period has ended at `now`; the still-forming
    period is never stored, so re-running is safe at any moment.
    """
    size = store.timeframe.seconds
    time_range = store.time_range()
    since = time_range[1] + size if time_range is not None else None
    fetched = sorted(source(since), key=lambda c: c.time)
    completed = [c for c in fetched if c.time + size <= now]
    stored = store.upsert(completed)
    unreachable: tuple[int, int] | None = None
    truncated = len(fetched) >= REST_REACH
    if since is not None and truncated and fetched[0].time > since:
        unreachable = (since, fetched[0].time - size)
    return CatchUpResult(stored, unreachable)
