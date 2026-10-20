"""The read-only HTTP API the dashboard reads from.

`GET /candles?timeframe=15m|1h|4h|1d&from=...&to=...` answers candles from the
SQLite store: fifteen-minute and hourly ones from their own tables, 4-hour and
daily ones resampled from the hourly table. `from` and `to` are Unix seconds or
ISO 8601 and are widened to whole periods, so a resampled candle is always
built from every hour it covers. `GET /turning-points?timeframe=...` answers
the hindsight turning points of the whole development period, always found on
the hourly candles, placed on the candle of the requested timeframe that holds
the extreme. `GET /replay?detector=...` replays the development period through
a detector, on the candles of the detector's timeframe, and answers every
candle it read, the levels and the swing extremes it read, every mark with its
outcome where the scoring period scored it, and the score over the scoring
period, per era.

Every route reads through `read_development`, so nothing past the
out-of-sample boundary is ever served.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tradingbot.candles import Candle, Timeframe, period_start, resample
from tradingbot.detectors import DETECTORS, Level, SwingExtreme
from tradingbot.development import read_development
from tradingbot.replay import MarkOutcome, ReplayResult, run
from tradingbot.scoring import SCORING_START, Score
from tradingbot.store import STORED_TIMEFRAMES, CandleStore
from tradingbot.turning_points import Kind, TurningPoint, find_turning_points


class CandlesOut(BaseModel):
    timeframe: str
    candles: list[Candle]


class TurningPointsOut(BaseModel):
    timeframe: str
    turning_points: list[TurningPoint]


class ReplayOut(BaseModel):
    detector: str
    timeframe: str
    """The timeframe of `candles`: what the detector read."""
    scored_from: int | None
    """Start of the scored period; marks before it are unscored."""
    candles: list[Candle]
    turning_points: list[TurningPoint]
    levels: list[Level]
    swing_extremes: list[SwingExtreme]
    marks: list[MarkOutcome]
    score: Score

    @classmethod
    def of(cls, result: ReplayResult) -> ReplayOut:
        return cls(
            detector=result.detector,
            timeframe=result.timeframe.value,
            scored_from=result.scored_from,
            candles=result.candles,
            turning_points=result.turning_points,
            levels=result.levels,
            swing_extremes=result.swing_extremes,
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
    return replace(
        point,
        time=period_start(point.time, timeframe),
        confirmed_at=period_start(point.confirmed_at, timeframe),
    )


def on_fifteen_minutes(point: TurningPoint, by_time: dict[int, Candle]) -> TurningPoint:
    """The turning point placed on the fifteen-minute candle of its hour that holds the
    extreme, or on the start of the hour when no stored candle of the hour holds it."""
    for i in range(4):
        candle = by_time.get(point.time + i * Timeframe.M15.seconds)
        if candle is None:
            continue
        extreme = candle.high if point.kind is Kind.TOP else candle.low
        if extreme == point.price:
            return replace(point, time=candle.time)
    return point


def create_app(db_path: str | Path) -> FastAPI:
    app = FastAPI(title="TradingBot candles")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
    )

    def read(
        timeframe: Timeframe = Timeframe.H1, start: int | None = None, end: int | None = None
    ) -> list[Candle]:
        with CandleStore(db_path, timeframe) as store:
            return read_development(store, start, end)

    @app.get("/candles")
    def candles(
        timeframe: Timeframe,
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
    ) -> CandlesOut:
        start, end = whole_periods(timeframe, from_, to)
        if timeframe in STORED_TIMEFRAMES:
            result = read(timeframe, start, end)
        else:
            result = resample(read(Timeframe.H1, start, end), timeframe)
        return CandlesOut(timeframe=timeframe.value, candles=result)

    @app.get("/turning-points")
    def turning_points(timeframe: Timeframe) -> TurningPointsOut:
        points = find_turning_points(read())
        if timeframe is Timeframe.M15:
            by_time = {c.time: c for c in read(Timeframe.M15)}
            placed = [on_fifteen_minutes(p, by_time) for p in points]
        else:
            placed = [on_timeframe(p, timeframe) for p in points]
        return TurningPointsOut(timeframe=timeframe.value, turning_points=placed)

    @app.get("/replay")
    def replay(detector: str) -> ReplayOut:
        build = DETECTORS.get(detector)
        if build is None:
            known = ", ".join(DETECTORS)
            raise HTTPException(404, f"unknown detector {detector!r}; known detectors: {known}")
        instance = build()
        return ReplayOut.of(run(read(instance.timeframe), instance, score_from=SCORING_START))

    return app
