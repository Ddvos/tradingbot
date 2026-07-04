"""Backtests feature: port → response schema, plus the Parquet curve read.

Run metadata lives in Postgres; the equity curve itself is the Parquet file
the backtest script wrote (CLAUDE.md → Storage). The handler joins the two.
"""

from pathlib import Path

import polars as pl
from fastapi import HTTPException

from tradingbot.api.features.backtests.schemas import (
    BacktestRunSummary,
    EquityCurveResponse,
    EquityPoint,
)
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


def _get_or_404(runs: BacktestRunRepository, run_id: BacktestRunId) -> BacktestRunRecord:
    record = runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No backtest run with id {run_id}")
    return record
