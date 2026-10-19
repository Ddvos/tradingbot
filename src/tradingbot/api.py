"""The read-only HTTP API the dashboard reads candles from.

`GET /candles?timeframe=1h|4h|1d&from=...&to=...` answers candles from the
SQLite store. `from` and `to` are Unix seconds or ISO 8601 and are widened to
whole periods, so a 4-hour or daily candle is always built from every hour it
covers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tradingbot.candles import Candle, Timeframe, resample
from tradingbot.store import CandleStore


class CandlesOut(BaseModel):
    timeframe: str
    candles: list[Candle]


def parse_time(value: str) -> int:
    """Unix seconds from either Unix seconds or an ISO 8601 date-time (UTC if naive)."""
    if value.isdigit():
        return int(value)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"{value!r} is neither Unix seconds nor ISO 8601"
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def create_app(db_path: str | Path) -> FastAPI:
    app = FastAPI(title="TradingBot candles")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
    )

    @app.get("/candles")
    def candles(
        timeframe: Timeframe,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
    ) -> CandlesOut:
        size = timeframe.seconds
        start = end = None
        if from_ is not None:
            start = parse_time(from_)
            start -= start % size
        if to is not None:
            end = parse_time(to)
            end += size - 1 - end % size
        with CandleStore(db_path) as store:
            hourly = store.read(start, end)
        return CandlesOut(timeframe=timeframe.value, candles=resample(hourly, timeframe))

    return app
