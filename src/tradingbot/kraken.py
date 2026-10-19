"""Kraken spot data sources for the hourly XBTUSD candles.

Two sources feed the store:

* the downloadable OHLCVT archive, a header-less CSV per pair and interval
  (`timestamp,open,high,low,close,volume,trades`, Unix seconds UTC), which
  holds the history back to 2013 and is downloaded by hand;
* the public REST OHLC endpoint, which returns at most the latest 720 hourly
  candles, the last of them still forming.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from tradingbot.candles import Candle
from tradingbot.store import CandleStore

HOUR = 3600

HourlySource = Callable[[int | None], list[Candle]]
"""Answers the hourly candles from `since` (inclusive) onward; `None` means all it has."""


@dataclass(frozen=True)
class ImportResult:
    stored: int
    """Hours that were new to the store."""
    time_range: tuple[int, int]
    """Start time of the oldest and the newest candle in the store afterwards."""


def read_archive(path: Path) -> Iterator[Candle]:
    """Yield the hourly candles of one OHLCVT archive file."""
    with path.open(newline="") as file:
        for row in csv.reader(file):
            if not row:
                continue
            time, open_, high, low, close, volume, trades = row
            yield Candle(
                int(time),
                float(open_),
                float(high),
                float(low),
                float(close),
                float(volume),
                int(trades),
            )


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
    endpoint still had, when the endpoint's 720-candle reach could not bridge them."""


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
    if since is not None and fetched and fetched[0].time > since:
        unreachable = (since, fetched[0].time - HOUR)
    return CatchUpResult(stored, unreachable)


class KrakenSpot:
    """The public Kraken spot REST API as an `HourlySource`."""

    BASE_URL = "https://api.kraken.com"

    def __init__(self, pair: str = "XBTUSD", http: httpx.Client | None = None) -> None:
        self._pair = pair
        self._http = http or httpx.Client(timeout=30.0)

    def hourly_candles(self, since: int | None) -> list[Candle]:
        """The latest hourly candles, at most 720, the last one still forming."""
        params: dict[str, str] = {"pair": self._pair, "interval": "60"}
        if since is not None:
            params["since"] = str(since)
        response = self._http.get(f"{self.BASE_URL}/0/public/OHLC", params=params)
        response.raise_for_status()
        body = response.json()
        if body.get("error"):
            raise RuntimeError(f"Kraken OHLC error: {', '.join(body['error'])}")
        result = body["result"]
        rows = next(rows for key, rows in result.items() if key != "last")
        return [
            Candle(int(time), float(o), float(h), float(lo), float(c), float(volume), int(trades))
            for time, o, h, lo, c, _vwap, volume, trades in rows
        ]
