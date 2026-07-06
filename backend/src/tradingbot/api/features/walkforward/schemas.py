"""Response schemas for the walkforward feature (Pydantic at the boundary).

Per-fold metrics can be NaN or inf (a fold with zero trades has no win rate;
one loss and no wins gives profit factor 0, one win and no losses gives inf).
JSON cannot carry those, so the handlers map every non-finite float to null —
hence the `float | None` fields here.
"""

from datetime import datetime

from pydantic import BaseModel


class WalkForwardRunSummary(BaseModel):
    symbol: str
    run: str
    """Run folder name: {timeframe}_{name}_{stamp} — the API identifier."""

    timeframe: str
    name: str
    created_at: datetime
    n_folds: int
    test_start: datetime
    test_end: datetime
    oos_sharpe: float
    oos_max_drawdown: float
    initial_equity: float
    final_equity: float


class FoldMetrics(BaseModel):
    fold: int
    test_start: datetime
    test_end: datetime
    auc: float | None
    ic: float | None
    sharpe: float | None
    max_drawdown: float | None
    n_trades: int
    win_rate: float | None
    profit_factor: float | None


class WalkForwardRunDetail(BaseModel):
    summary: WalkForwardRunSummary
    folds: list[FoldMetrics]
    report: str
    """The report.md content — the authoritative verdict text."""


class EquityPoint(BaseModel):
    time: int
    """Unix seconds (UTC) — the time format lightweight-charts expects."""

    value: float


class WalkForwardEquityResponse(BaseModel):
    symbol: str
    run: str
    points: list[EquityPoint]


class WalkForwardTrade(BaseModel):
    """One closed OOS round-trip from the run's trades.parquet. stop/take-profit
    are null where the mapping's rules disabled them (hysteresis: always)."""

    entry_time: datetime
    exit_time: datetime
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    stop_price: float | None
    take_profit_price: float | None
    pnl: float
    fees: float
    reason: str


class WalkForwardTradesResponse(BaseModel):
    symbol: str
    run: str
    trades: list[WalkForwardTrade]


class Candle(BaseModel):
    time: int
    """Unix seconds (UTC) — the time format lightweight-charts expects."""

    open: float
    high: float
    low: float
    close: float


class WalkForwardCandlesResponse(BaseModel):
    symbol: str
    run: str
    candles: list[Candle]
