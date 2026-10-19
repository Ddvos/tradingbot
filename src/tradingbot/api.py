"""The read-only HTTP API the dashboard reads from.

`GET /candles?timeframe=1h|4h|1d&from=...&to=...` answers candles from the
SQLite store. `from` and `to` are Unix seconds or ISO 8601 and are widened to
whole periods, so a 4-hour or daily candle is always built from every hour it
covers. `GET /turning-points` answers the hindsight turning points of the same
window, on the candle of the requested timeframe that holds the hourly extreme.
`GET /replay?detector=...` replays the hourly candles through a detector and
answers its marks, their outcomes and the score.

Every route reads through the development window, so nothing past the
out-of-sample boundary is ever served.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tradingbot.candles import Candle, Timeframe, resample
from tradingbot.detectors import DETECTORS
from tradingbot.development import read_development
from tradingbot.replay import MarkOutcome, ReplayResult, run
from tradingbot.scoring import Score
from tradingbot.store import CandleStore
from tradingbot.turning_points import TurningPoint, find_turning_points


class CandlesOut(BaseModel):
    timeframe: str
    candles: list[Candle]


class TurningPointsOut(BaseModel):
    timeframe: str
    turning_points: list[TurningPoint]


class ReplayOut(BaseModel):
    detector: str
    candles: list[Candle]
    turning_points: list[TurningPoint]
    marks: list[MarkOutcome]
    score: Score

    @classmethod
    def of(cls, result: ReplayResult) -> ReplayOut:
        return cls(
            detector=result.detector,
            candles=result.candles,
            turning_points=result.turning_points,
            marks=result.marks,
            score=result.score,
        )


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


def whole_periods(
    timeframe: Timeframe, from_: str | None, to: str | None
) -> tuple[int | None, int | None]:
    """The requested window widened to whole periods of the timeframe."""
    size = timeframe.seconds
    start = end = None
    if from_ is not None:
        start = parse_time(from_)
        start -= start % size
    if to is not None:
        end = parse_time(to)
        end += size - 1 - end % size
    return start, end


def on_timeframe(point: TurningPoint, timeframe: Timeframe) -> TurningPoint:
    """The turning point placed on the candle of `timeframe` that holds its hour."""
    size = timeframe.seconds
    return replace(
        point,
        time=point.time - point.time % size,
        confirmed_at=point.confirmed_at - point.confirmed_at % size,
    )


def create_app(db_path: str | Path) -> FastAPI:
    app = FastAPI(title="TradingBot candles")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
    )

    def read(timeframe: Timeframe, from_: str | None, to: str | None) -> list[Candle]:
        start, end = whole_periods(timeframe, from_, to)
        with CandleStore(db_path) as store:
            return read_development(store, start, end)

    @app.get("/candles")
    def candles(
        timeframe: Timeframe,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
    ) -> CandlesOut:
        hourly = read(timeframe, from_, to)
        return CandlesOut(timeframe=timeframe.value, candles=resample(hourly, timeframe))

    @app.get("/turning-points")
    def turning_points(
        timeframe: Timeframe,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
    ) -> TurningPointsOut:
        hourly = read(timeframe, from_, to)
        points = [on_timeframe(p, timeframe) for p in find_turning_points(hourly)]
        return TurningPointsOut(timeframe=timeframe.value, turning_points=points)

    @app.get("/replay")
    def replay(
        detector: str,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
    ) -> ReplayOut:
        build = DETECTORS.get(detector)
        if build is None:
            known = ", ".join(DETECTORS)
            raise HTTPException(404, f"unknown detector {detector!r}; known detectors: {known}")
        hourly = read(Timeframe.H1, from_, to)
        return ReplayOut.of(run(hourly, build()))

    return app
