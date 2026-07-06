"""Backtests feature: port → response schema, plus the Parquet curve read.

Run metadata lives in Postgres; the equity curve itself is the Parquet file
the backtest script wrote (CLAUDE.md → Storage). The handler joins the two.
"""

from pathlib import Path

import polars as pl
from fastapi import HTTPException

from tradingbot.api.features.backtests.schemas import (
    BacktestRunSummary,
    BacktestTrade,
    Candle,
    CandlesResponse,
    EquityCurveResponse,
    EquityPoint,
    TradesResponse,
)
from tradingbot.application.run_backtest import trades_path_for
from tradingbot.core.ports.storage import BacktestRunId, BacktestRunRecord, BacktestRunRepository


def list_backtests(runs: BacktestRunRepository) -> list[BacktestRunSummary]:
    return [BacktestRunSummary.from_record(record) for record in runs.list_runs()]


def get_backtest(runs: BacktestRunRepository, run_id: BacktestRunId) -> BacktestRunSummary:
    return BacktestRunSummary.from_record(_get_or_404(runs, run_id))


def get_equity_curve(runs: BacktestRunRepository, run_id: BacktestRunId) -> EquityCurveResponse:
    record = _get_or_404(runs, run_id)
    path = Path(record.equity_curve_path)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Equity curve file missing: {path} — re-run the backtest with --save",
        )
    curve = pl.read_parquet(path)
    times: list[int] = curve.get_column("timestamp").dt.epoch(time_unit="s").to_list()
    values: list[float] = curve.get_column("equity").to_list()
    points = [
        EquityPoint(time=time, value=value) for time, value in zip(times, values, strict=True)
    ]
    return EquityCurveResponse(run_id=record.id, points=points)


def get_trades(runs: BacktestRunRepository, run_id: BacktestRunId) -> TradesResponse:
    record = _get_or_404(runs, run_id)
    path = trades_path_for(Path(record.equity_curve_path))
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Trade log missing: {path} — re-run the backtest to generate it",
        )
    frame = pl.read_parquet(path)
    trades = [BacktestTrade.model_validate(row) for row in frame.iter_rows(named=True)]
    return TradesResponse(run_id=record.id, trades=trades)


def get_candles(
    runs: BacktestRunRepository, run_id: BacktestRunId, ohlcv_dir: Path
) -> CandlesResponse:
    """The run's price history, for drawing trades on a candlestick chart."""
    record = _get_or_404(runs, run_id)
    path = ohlcv_dir / record.symbol / f"{record.timeframe}.parquet"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No OHLCV data at {path}")
    frame = pl.read_parquet(path).filter(
        pl.col("timestamp").is_between(record.data_start, record.data_end)
    )
    return CandlesResponse(run_id=record.id, candles=_candles(frame))


def _candles(ohlcv: pl.DataFrame) -> list[Candle]:
    times: list[int] = ohlcv.get_column("timestamp").dt.epoch(time_unit="s").to_list()
    opens: list[float] = ohlcv.get_column("open").to_list()
    highs: list[float] = ohlcv.get_column("high").to_list()
    lows: list[float] = ohlcv.get_column("low").to_list()
    closes: list[float] = ohlcv.get_column("close").to_list()
    return [
        Candle(time=t, open=o, high=h, low=lo, close=c)
        for t, o, h, lo, c in zip(times, opens, highs, lows, closes, strict=True)
    ]


def _get_or_404(runs: BacktestRunRepository, run_id: BacktestRunId) -> BacktestRunRecord:
    record = runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No backtest run with id {run_id}")
    return record
