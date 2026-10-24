"""The public Kraken Futures endpoints the paper loop reads (slice 11, ADR-0009).

Two routes, both public and read-only: the ticker of the perpetual, for the
price Kraken Futures marks it at, and the funding history, one relative rate
per hour for the past year, for the rate really charged in an hour. No key
and no order route: nothing here can trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

PERPETUAL_SYMBOL = "PF_XBTUSD"
"""The USD-margined Bitcoin perpetual of ADR-0008, where the orders will go."""


@dataclass(frozen=True, slots=True)
class MarkPrice:
    """The perpetual's mark price at one moment."""

    price: float
    """The price Kraken Futures marks the perpetual at, for margining."""
    time: int
    """The server's time of the answer, Unix seconds."""


def parse_time(value: str) -> int:
    """Unix seconds from the API's ISO 8601 date-times, like 2026-10-24T17:07:27.733Z."""
    return int(datetime.fromisoformat(value).timestamp())


class KrakenFutures:
    """The public Kraken Futures REST API."""

    BASE_URL = "https://futures.kraken.com/derivatives/api"
    """The public REST API; the ticker is under v3, the funding history under v4."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=30.0)

    def _get(self, path: str, **params: str) -> dict:
        response = self._http.get(f"{self.BASE_URL}/{path}", params=params)
        response.raise_for_status()
        body = response.json()
        if body.get("result") != "success":
            raise RuntimeError(f"Kraken Futures error: {body.get('error', body)}")
        return body

    def mark_price(self) -> MarkPrice:
        """The perpetual's mark price now."""
        body = self._get(f"v3/tickers/{PERPETUAL_SYMBOL}")
        return MarkPrice(float(body["ticker"]["markPrice"]), parse_time(body["serverTime"]))

    def funding_rates(self) -> dict[int, float]:
        """The relative funding rate of every hour Kraken Futures publishes, about a year of
        them, by the start of the hour it covers, charged at that hour's close: the share of
        the position's value a long pays, negative when longs were paid. The rate stamped
        with the current hour is the ticker's current rate. An hour with no entry was not
        published."""
        body = self._get("v4/historicalfundingrates", symbol=PERPETUAL_SYMBOL)
        return {
            parse_time(rate["timestamp"]): float(rate["relativeFundingRate"])
            for rate in body["rates"]
        }
