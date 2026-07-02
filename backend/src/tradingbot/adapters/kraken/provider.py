"""Kraken Futures market data via the public charts API.

Endpoint: GET /api/charts/v1/trade/{symbol}/{timeframe}?from=..&to=..
Returns at most 2000 candles per call with a more_candles flag, so we paginate
by advancing `from` past the last received candle. Prices arrive as strings;
Pydantic validates and coerces at this system boundary.

Note: PF_XBTUSD 1h history starts 2022-03-23 — the API returns an empty list
for anything earlier (verified 2 Jul 2026).
"""

from datetime import UTC, datetime

import httpx
import polars as pl
from pydantic import BaseModel

from tradingbot.core.ports.market_data import (
    OHLCV_SCHEMA,
    TIMEFRAME_SECONDS,
    Timeframe,
    validate_ohlcv,
)

BASE_URL = "https://futures.kraken.com/api/charts/v1"


class _Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class _ChartsResponse(BaseModel):
    candles: list[_Candle]
    more_candles: bool


class KrakenProvider:
    """Implements the MarketDataProvider port against Kraken Futures."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=30.0)

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, since: datetime) -> pl.DataFrame:
        candles: list[_Candle] = []
        start = int(since.timestamp())
        end = int(datetime.now(UTC).timestamp())
        while start < end:
            page = self._fetch_page(symbol, timeframe, start, end)
            candles.extend(page.candles)
            if not page.more_candles or not page.candles:
                break
            start = page.candles[-1].time // 1000 + TIMEFRAME_SECONDS[timeframe]

        df = (
            pl.DataFrame(
                {
                    "timestamp": [c.time for c in candles],
                    "open": [c.open for c in candles],
                    "high": [c.high for c in candles],
                    "low": [c.low for c in candles],
                    "close": [c.close for c in candles],
                    "volume": [c.volume for c in candles],
                },
                schema={**dict(OHLCV_SCHEMA), "timestamp": pl.Int64()},
            )
            .with_columns(pl.col("timestamp").cast(pl.Datetime("ms", "UTC")))
            .unique(subset="timestamp", keep="last")
            .sort("timestamp")
        )
        validate_ohlcv(df)
        return df

    def _fetch_page(
        self, symbol: str, timeframe: Timeframe, start: int, end: int
    ) -> _ChartsResponse:
        response = self._client.get(
            f"/trade/{symbol}/{timeframe}", params={"from": start, "to": end}
        )
        response.raise_for_status()
        return _ChartsResponse.model_validate_json(response.content)
