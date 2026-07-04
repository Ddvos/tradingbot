"""SQLAlchemy 2.0 table definitions behind the storage ports.

Column types are dialect-generic (sa.Uuid, sa.JSON, sa.Numeric) so the same
metadata runs on Postgres (production, via Alembic) and SQLite in-memory
(repository tests). Money columns are Numeric → Decimal, never Float.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tradingbot.core.ports.storage import ParamValue


class Base(DeclarativeBase):
    pass


class BacktestRunRow(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    strategy: Mapped[str] = mapped_column(sa.String(64))
    symbol: Mapped[str] = mapped_column(sa.String(32))
    timeframe: Mapped[str] = mapped_column(sa.String(8))
    data_start: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    data_end: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    initial_capital: Mapped[Decimal] = mapped_column(sa.Numeric(24, 8))
    final_equity: Mapped[Decimal] = mapped_column(sa.Numeric(24, 8))
    sharpe: Mapped[float]
    max_drawdown: Mapped[float]
    n_trades: Mapped[int]
    params: Mapped[dict[str, ParamValue]] = mapped_column(sa.JSON)
    equity_curve_path: Mapped[str] = mapped_column(sa.String(512))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class TradeRow(Base):
    __tablename__ = "trades"

    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    strategy: Mapped[str] = mapped_column(sa.String(64))
    symbol: Mapped[str] = mapped_column(sa.String(32))
    side: Mapped[str] = mapped_column(sa.String(4))
    quantity: Mapped[Decimal] = mapped_column(sa.Numeric(24, 8))
    entry_price: Mapped[Decimal] = mapped_column(sa.Numeric(24, 8))
    exit_price: Mapped[Decimal] = mapped_column(sa.Numeric(24, 8))
    entry_time: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    exit_time: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    pnl: Mapped[Decimal] = mapped_column(sa.Numeric(24, 8))
    fees: Mapped[Decimal] = mapped_column(sa.Numeric(24, 8))
    exit_reason: Mapped[str] = mapped_column(sa.String(32))


class ModelRow(Base):
    __tablename__ = "model_registry"

    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(128), unique=True)
    artifact_path: Mapped[str] = mapped_column(sa.String(512))
    auc: Mapped[float]
    ic: Mapped[float]
    trained_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class StrategyConfigRow(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(128), unique=True)
    params: Mapped[dict[str, ParamValue]] = mapped_column(sa.JSON)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
