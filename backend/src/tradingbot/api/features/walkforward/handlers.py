"""Walkforward feature: read run artifacts straight from disk.

scripts/walkforward.py writes each run as a folder
{base}/{symbol}/{timeframe}_{name}_{stamp}/ holding folds.parquet,
equity.parquet, and report.md. There is no database row — the filesystem is
the registry — so the handlers scan it, and derive the summary metrics from
the stitched OOS equity curve with the same core functions the report used
(identical numbers, no summary file to keep in sync).
"""

import math
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from fastapi import HTTPException

from tradingbot.api.features.walkforward.schemas import (
    Candle,
    EquityPoint,
    FoldMetrics,
    WalkForwardCandlesResponse,
    WalkForwardEquityResponse,
    WalkForwardRunDetail,
    WalkForwardRunSummary,
    WalkForwardTrade,
    WalkForwardTradesResponse,
)
from tradingbot.core.backtest.metrics import max_drawdown, sharpe_ratio
from tradingbot.core.ports.market_data import TIMEFRAME_SECONDS, Timeframe

SECONDS_PER_YEAR = 365 * 24 * 3600
ARTIFACTS = ("folds.parquet", "equity.parquet", "report.md")
MIN_RUN_TOKENS = 4
"""timeframe + at least one name token + date + time"""


def list_runs(base_dir: Path) -> list[WalkForwardRunSummary]:
    """Every complete run under base_dir, newest first. Folders that do not
    parse as a run (scratch dirs, partial writes) are skipped, not errors."""
    if not base_dir.is_dir():
        return []
    summaries = [
        summary
        for symbol_dir in sorted(base_dir.iterdir())
        if symbol_dir.is_dir()
        for run_dir in sorted(symbol_dir.iterdir())
        if (summary := _summarize(run_dir, symbol_dir.name)) is not None
    ]
    return sorted(summaries, key=lambda summary: summary.created_at, reverse=True)


def get_run(base_dir: Path, symbol: str, run: str) -> WalkForwardRunDetail:
    run_dir = _run_dir_or_404(base_dir, symbol, run)
    summary = _summarize(run_dir, symbol)
    if summary is None:
        raise HTTPException(
            status_code=404, detail=f"{symbol}/{run} is not a complete walk-forward run"
        )
    folds = pl.read_parquet(run_dir / "folds.parquet")
    fold_metrics = [
        FoldMetrics(
            fold=row["fold"],
            test_start=row["test_start"],
            test_end=row["test_end"],
            auc=_finite(row["auc"]),
            ic=_finite(row["ic"]),
            sharpe=_finite(row["sharpe"]),
            max_drawdown=_finite(row["max_drawdown"]),
            n_trades=row["n_trades"],
            win_rate=_finite(row["win_rate"]),
            profit_factor=_finite(row["profit_factor"]),
        )
        for row in folds.iter_rows(named=True)
    ]
    report = (run_dir / "report.md").read_text()
    return WalkForwardRunDetail(summary=summary, folds=fold_metrics, report=report)


def get_equity(base_dir: Path, symbol: str, run: str) -> WalkForwardEquityResponse:
    run_dir = _run_dir_or_404(base_dir, symbol, run)
    curve = pl.read_parquet(run_dir / "equity.parquet")
    times: list[int] = curve.get_column("timestamp").dt.epoch(time_unit="s").to_list()
    values: list[float] = curve.get_column("equity").to_list()
    points = [
        EquityPoint(time=time, value=value) for time, value in zip(times, values, strict=True)
    ]
    return WalkForwardEquityResponse(symbol=symbol, run=run, points=points)


def get_trades(base_dir: Path, symbol: str, run: str) -> WalkForwardTradesResponse:
    run_dir = _run_dir_or_404(base_dir, symbol, run)
    path = run_dir / "trades.parquet"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"{symbol}/{run} has no trade log — runs from before 6 Jul 2026"
            " predate trade persistence; re-run the walk-forward to generate one",
        )
    frame = pl.read_parquet(path)
    trades = [WalkForwardTrade.model_validate(row) for row in frame.iter_rows(named=True)]
    return WalkForwardTradesResponse(symbol=symbol, run=run, trades=trades)


def get_candles(
    base_dir: Path, ohlcv_dir: Path, symbol: str, run: str
) -> WalkForwardCandlesResponse:
    """Price history spanning the run's stitched OOS window, for trade charts."""
    run_dir = _run_dir_or_404(base_dir, symbol, run)
    parsed = _parse_run_name(run_dir.name)
    if parsed is None:
        raise HTTPException(status_code=404, detail=f"{symbol}/{run} is not a walk-forward run")
    timeframe = parsed[0]
    path = ohlcv_dir / symbol / f"{timeframe}.parquet"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No OHLCV data at {path}")
    window = pl.read_parquet(run_dir / "equity.parquet").get_column("timestamp")
    ohlcv = pl.read_parquet(path).filter(pl.col("timestamp").is_between(window.min(), window.max()))
    times: list[int] = ohlcv.get_column("timestamp").dt.epoch(time_unit="s").to_list()
    opens: list[float] = ohlcv.get_column("open").to_list()
    highs: list[float] = ohlcv.get_column("high").to_list()
    lows: list[float] = ohlcv.get_column("low").to_list()
    closes: list[float] = ohlcv.get_column("close").to_list()
    candles = [
        Candle(time=t, open=o, high=h, low=lo, close=c)
        for t, o, h, lo, c in zip(times, opens, highs, lows, closes, strict=True)
    ]
    return WalkForwardCandlesResponse(symbol=symbol, run=run, candles=candles)


def _summarize(run_dir: Path, symbol: str) -> WalkForwardRunSummary | None:
    parsed = _parse_run_name(run_dir.name)
    if parsed is None or not all((run_dir / artifact).is_file() for artifact in ARTIFACTS):
        return None
    timeframe, name, created_at = parsed
    folds = pl.read_parquet(run_dir / "folds.parquet")
    equity = pl.read_parquet(run_dir / "equity.parquet").get_column("equity")
    if folds.is_empty() or equity.is_empty():
        return None
    periods_per_year = SECONDS_PER_YEAR // TIMEFRAME_SECONDS[timeframe]
    test_starts: list[datetime] = folds.get_column("test_start").to_list()
    test_ends: list[datetime] = folds.get_column("test_end").to_list()
    return WalkForwardRunSummary(
        symbol=symbol,
        run=run_dir.name,
        timeframe=timeframe,
        name=name,
        created_at=created_at,
        n_folds=folds.height,
        test_start=min(test_starts),
        test_end=max(test_ends),
        oos_sharpe=sharpe_ratio(equity, periods_per_year),
        oos_max_drawdown=max_drawdown(equity),
        initial_equity=float(equity[0]),
        final_equity=float(equity[-1]),
    )


def _parse_run_name(run: str) -> tuple[Timeframe, str, datetime] | None:
    """Split {timeframe}_{name}_{YYYYMMDD}_{HHMMSS}; name may contain underscores."""
    tokens = run.split("_")
    if len(tokens) < MIN_RUN_TOKENS:
        return None
    timeframe = _timeframe_of(tokens[0])
    name = "_".join(tokens[1:-2])
    if timeframe is None or not name:
        return None
    try:
        created_at = datetime.strptime(f"{tokens[-2]}_{tokens[-1]}", "%Y%m%d_%H%M%S").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None
    return timeframe, name, created_at


def _timeframe_of(token: str) -> Timeframe | None:
    for timeframe in TIMEFRAME_SECONDS:
        if timeframe == token:
            return timeframe
    return None


def _run_dir_or_404(base_dir: Path, symbol: str, run: str) -> Path:
    run_dir = base_dir / symbol / run
    # Path params can smuggle traversal segments ("..", absolute paths);
    # anything that rewrites the joined path is treated as not found.
    if (Path(symbol).name, Path(run).name) != (symbol, run) or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"No walk-forward run {symbol}/{run}")
    return run_dir


def _finite(value: float) -> float | None:
    """JSON has no NaN/inf — zero-trade folds produce both. Null instead."""
    return value if math.isfinite(value) else None
