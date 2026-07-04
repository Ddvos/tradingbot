"""Postgres implementations of the storage ports (SQLAlchemy 2.0, sync).

Sync on purpose: the callers are CLI scripts, FastAPI handlers (which run
sync functions in a threadpool), and later the 1h-tick live runner — nothing
here needs an event loop.

Datetimes are stored as UTC; `_as_utc` re-attaches tzinfo on read because
SQLite (used in the repository tests) drops it. Postgres `timestamptz`
round-trips aware datetimes unchanged.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tradingbot.adapters.postgres.tables import (
    BacktestRunRow,
    ModelRow,
    StrategyConfigRow,
    TradeRow,
)
from tradingbot.core.ports.executor import Side
from tradingbot.core.ports.storage import (
    BacktestRunId,
    BacktestRunRecord,
    ModelId,
    ModelRecord,
    StrategyConfigId,
    StrategyConfigRecord,
    TradeId,
    TradeRecord,
)


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _run_record(row: BacktestRunRow) -> BacktestRunRecord:
    return BacktestRunRecord(
        id=BacktestRunId(row.id),
        strategy=row.strategy,
        symbol=row.symbol,
        timeframe=row.timeframe,
        data_start=_as_utc(row.data_start),
        data_end=_as_utc(row.data_end),
        initial_capital=row.initial_capital,
        final_equity=row.final_equity,
        sharpe=row.sharpe,
        max_drawdown=row.max_drawdown,
        n_trades=row.n_trades,
        params=row.params,
        equity_curve_path=row.equity_curve_path,
        created_at=_as_utc(row.created_at),
    )


def _trade_record(row: TradeRow) -> TradeRecord:
    return TradeRecord(
        id=TradeId(row.id),
        strategy=row.strategy,
        symbol=row.symbol,
        side=Side(row.side),
        quantity=row.quantity,
        entry_price=row.entry_price,
        exit_price=row.exit_price,
        entry_time=_as_utc(row.entry_time),
        exit_time=_as_utc(row.exit_time),
        pnl=row.pnl,
        fees=row.fees,
        exit_reason=row.exit_reason,
    )


def _model_record(row: ModelRow) -> ModelRecord:
    return ModelRecord(
        id=ModelId(row.id),
        name=row.name,
        artifact_path=row.artifact_path,
        auc=row.auc,
        ic=row.ic,
        trained_at=_as_utc(row.trained_at),
        created_at=_as_utc(row.created_at),
    )


def _config_record(row: StrategyConfigRow) -> StrategyConfigRecord:
    return StrategyConfigRecord(
        id=StrategyConfigId(row.id),
        name=row.name,
        params=row.params,
        created_at=_as_utc(row.created_at),
    )


class PostgresBacktestRunRepository:
    """Implements the BacktestRunRepository port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, run: BacktestRunRecord) -> None:
        row = BacktestRunRow(
            id=run.id,
            strategy=run.strategy,
            symbol=run.symbol,
            timeframe=run.timeframe,
            data_start=run.data_start,
            data_end=run.data_end,
            initial_capital=run.initial_capital,
            final_equity=run.final_equity,
            sharpe=run.sharpe,
            max_drawdown=run.max_drawdown,
            n_trades=run.n_trades,
            params=dict(run.params),
            equity_curve_path=run.equity_curve_path,
            created_at=run.created_at,
        )
        with self._session_factory() as session, session.begin():
            session.add(row)

    def get(self, run_id: BacktestRunId) -> BacktestRunRecord | None:
        with self._session_factory() as session:
            row = session.get(BacktestRunRow, run_id)
            return _run_record(row) if row is not None else None

    def list_runs(self) -> list[BacktestRunRecord]:
        statement = select(BacktestRunRow).order_by(BacktestRunRow.created_at.desc())
        with self._session_factory() as session:
            return [_run_record(row) for row in session.scalars(statement)]


class PostgresTradeRepository:
    """Implements the TradeRepository port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, trade: TradeRecord) -> None:
        row = TradeRow(
            id=trade.id,
            strategy=trade.strategy,
            symbol=trade.symbol,
            side=trade.side.value,
            quantity=trade.quantity,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            pnl=trade.pnl,
            fees=trade.fees,
            exit_reason=trade.exit_reason,
        )
        with self._session_factory() as session, session.begin():
            session.add(row)

    def list_trades(self) -> list[TradeRecord]:
        statement = select(TradeRow).order_by(TradeRow.exit_time.desc())
        with self._session_factory() as session:
            return [_trade_record(row) for row in session.scalars(statement)]


class PostgresModelRegistry:
    """Implements the ModelRegistry port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def register(self, record: ModelRecord) -> None:
        row = ModelRow(
            id=record.id,
            name=record.name,
            artifact_path=record.artifact_path,
            auc=record.auc,
            ic=record.ic,
            trained_at=record.trained_at,
            created_at=record.created_at,
        )
        with self._session_factory() as session, session.begin():
            existing = session.scalar(select(ModelRow).where(ModelRow.name == record.name))
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(row)

    def get_by_name(self, name: str) -> ModelRecord | None:
        statement = select(ModelRow).where(ModelRow.name == name)
        with self._session_factory() as session:
            row = session.scalar(statement)
            return _model_record(row) if row is not None else None

    def list_models(self) -> list[ModelRecord]:
        statement = select(ModelRow).order_by(ModelRow.created_at.desc())
        with self._session_factory() as session:
            return [_model_record(row) for row in session.scalars(statement)]


class PostgresStrategyConfigRepository:
    """Implements the StrategyConfigRepository port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, config: StrategyConfigRecord) -> None:
        row = StrategyConfigRow(
            id=config.id,
            name=config.name,
            params=dict(config.params),
            created_at=config.created_at,
        )
        with self._session_factory() as session, session.begin():
            session.add(row)

    def get_by_name(self, name: str) -> StrategyConfigRecord | None:
        statement = select(StrategyConfigRow).where(StrategyConfigRow.name == name)
        with self._session_factory() as session:
            row = session.scalar(statement)
            return _config_record(row) if row is not None else None

    def list_configs(self) -> list[StrategyConfigRecord]:
        statement = select(StrategyConfigRow).order_by(StrategyConfigRow.created_at.desc())
        with self._session_factory() as session:
            return [_config_record(row) for row in session.scalars(statement)]
