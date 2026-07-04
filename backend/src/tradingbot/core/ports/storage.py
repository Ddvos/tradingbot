"""Storage ports: persistence contracts for runs, trades, models, and configs.

Justified now per ADR-001: each Protocol has two implementations — the
Postgres adapter (adapters/postgres/) and an in-memory fake (tests/fakes.py).
Records are frozen dataclasses (internal data, no Pydantic); money is Decimal;
all datetimes are UTC-aware.

Open-position state is deliberately absent: its consumer is the live runner,
so it arrives with Slice 5 (no speculative API design).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import NewType, Protocol
from uuid import UUID

from tradingbot.core.ports.executor import Side

BacktestRunId = NewType("BacktestRunId", UUID)
TradeId = NewType("TradeId", UUID)
ModelId = NewType("ModelId", UUID)
StrategyConfigId = NewType("StrategyConfigId", UUID)

type ParamValue = str | int | float | bool
"""Strategy/run parameters are flat key-value maps (JSON column in Postgres)."""


@dataclass(frozen=True)
class BacktestRunRecord:
    """Metadata of one backtest run. The equity curve itself stays in Parquet
    (see CLAUDE.md → Storage); `equity_curve_path` points at it."""

    id: BacktestRunId
    strategy: str
    symbol: str
    timeframe: str
    data_start: datetime
    """Timestamp of the first bar in the backtest window."""
    data_end: datetime
    """Timestamp of the last bar in the backtest window."""
    initial_capital: Decimal
    final_equity: Decimal
    sharpe: float
    max_drawdown: float
    n_trades: int
    params: dict[str, ParamValue]
    equity_curve_path: str
    created_at: datetime


@dataclass(frozen=True)
class TradeRecord:
    """One closed round-trip, written by the live/paper runner (Slice 5)."""

    id: TradeId
    strategy: str
    symbol: str
    side: Side
    """Entry side: BUY = long round-trip, SELL = short."""
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    fees: Decimal
    exit_reason: str


@dataclass(frozen=True)
class ModelRecord:
    """Registry entry for a trained model. The artifact itself is a .joblib
    on disk (adapters/filesystem/); this row is the queryable metadata."""

    id: ModelId
    name: str
    artifact_path: str
    auc: float
    ic: float
    trained_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class StrategyConfigRecord:
    id: StrategyConfigId
    name: str
    params: dict[str, ParamValue]
    created_at: datetime


class BacktestRunRepository(Protocol):
    """Port with two implementations: Postgres (live) and in-memory (tests)."""

    def add(self, run: BacktestRunRecord) -> None: ...

    def get(self, run_id: BacktestRunId) -> BacktestRunRecord | None: ...

    def list_runs(self) -> list[BacktestRunRecord]:
        """All runs, newest first."""
        ...


class TradeRepository(Protocol):
    """Port with two implementations: Postgres (live) and in-memory (tests)."""

    def add(self, trade: TradeRecord) -> None: ...

    def list_trades(self) -> list[TradeRecord]:
        """All closed trades, most recent exit first."""
        ...


class ModelRegistry(Protocol):
    """Port with two implementations: Postgres (live) and in-memory (tests)."""

    def register(self, record: ModelRecord) -> None:
        """Insert, or replace the existing entry with the same name —
        retraining under the same name overwrites the .joblib too."""
        ...

    def get_by_name(self, name: str) -> ModelRecord | None: ...

    def list_models(self) -> list[ModelRecord]:
        """All registered models, newest first."""
        ...


class StrategyConfigRepository(Protocol):
    """Port with two implementations: Postgres (live) and in-memory (tests)."""

    def add(self, config: StrategyConfigRecord) -> None: ...

    def get_by_name(self, name: str) -> StrategyConfigRecord | None: ...

    def list_configs(self) -> list[StrategyConfigRecord]:
        """All configs, newest first."""
        ...
