"""Kraken spot data sources for the hourly XBTUSD candles.

* The downloadable OHLCVT archive: one header-less CSV per pair and timeframe
  (`timestamp,open,high,low,close,volume,trades`, Unix seconds UTC), which
  holds the history back to 2013 and is downloaded by hand.
* The public REST OHLC endpoint, which answers at most the latest 720 hourly
  candles, the last of them still forming.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import httpx

from tradingbot.candles import Candle

PAIR = "XBTUSD"
REST_REACH = 720
"""The most hourly candles the REST endpoint ever answers; older ones it cannot reach."""


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


class KrakenSpot:
    """The public Kraken spot REST API."""

    BASE_URL = "https://api.kraken.com"

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=30.0)

    def hourly_candles(self, since: int | None) -> list[Candle]:
        """The hourly candles from `since` (inclusive) on, at most `REST_REACH` of
        them plus the still-forming one; `None` asks for everything it has."""
        params: dict[str, str] = {"pair": PAIR, "interval": "60"}
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
