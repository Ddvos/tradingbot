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
    SINGLETON_ROW_ID,
    BacktestRunRow,
    BotCommandsRow,
    ModelRow,
    PaperAccountRow,
    PositionRow,
    StrategyConfigRow,
    TradeRow,
)
from tradingbot.core.ports.executor import Side
from tradingbot.core.ports.storage import (
    BacktestRunId,
    BacktestRunRecord,
    BotCommandsRecord,
    ModelId,
    ModelRecord,
    PaperAccountRecord,
    PositionId,
    PositionRecord,
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


def _position_record(row: PositionRow) -> PositionRecord:
    return PositionRecord(
        id=PositionId(row.id),
        strategy=row.strategy,
        symbol=row.symbol,
        side=Side(row.side),
        quantity=row.quantity,
        entry_price=row.entry_price,
        entry_fee=row.entry_fee,
        entry_time=_as_utc(row.entry_time),
        stop=row.stop,
        take_profit=row.take_profit,
        bars_held=row.bars_held,
        updated_at=_as_utc(row.updated_at),
    )


class PostgresPositionRepository:
    """Implements the PositionRepository port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_open(self, symbol: str) -> PositionRecord | None:
        statement = select(PositionRow).where(PositionRow.symbol == symbol)
        with self._session_factory() as session:
            row = session.scalar(statement)
            return _position_record(row) if row is not None else None

    def save(self, position: PositionRecord) -> None:
        row = PositionRow(
            id=position.id,
            strategy=position.strategy,
            symbol=position.symbol,
            side=position.side.value,
            quantity=position.quantity,
            entry_price=position.entry_price,
            entry_fee=position.entry_fee,
            entry_time=position.entry_time,
            stop=position.stop,
            take_profit=position.take_profit,
            bars_held=position.bars_held,
            updated_at=position.updated_at,
        )
        with self._session_factory() as session, session.begin():
            session.merge(row)

    def delete(self, position_id: PositionId) -> None:
        with self._session_factory() as session, session.begin():
            row = session.get(PositionRow, position_id)
            if row is not None:
                session.delete(row)


class PostgresBotCommandRepository:
    """Implements the BotCommandRepository port.

    Targeted single-column updates: the API process writes flags while the
    bot process reads them — never rewriting the whole row avoids one write
    clobbering the other.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self) -> BotCommandsRecord | None:
        with self._session_factory() as session:
            row = session.get(BotCommandsRow, SINGLETON_ROW_ID)
            if row is None:
                return None
            return BotCommandsRecord(
                is_paused=row.is_paused,
                promoted_strategy=row.promoted_strategy,
                updated_at=_as_utc(row.updated_at),
            )

    def set_paused(self, paused: bool) -> None:
        with self._session_factory() as session, session.begin():
            row = self._row(session)
            row.is_paused = paused
            row.updated_at = datetime.now(UTC)

    def set_promoted(self, strategy: str | None) -> None:
        with self._session_factory() as session, session.begin():
            row = self._row(session)
            row.promoted_strategy = strategy
            row.updated_at = datetime.now(UTC)

    def _row(self, session: Session) -> BotCommandsRow:
        row = session.get(BotCommandsRow, SINGLETON_ROW_ID)
        if row is None:
            row = BotCommandsRow(
                id=SINGLETON_ROW_ID,
                is_paused=False,
                promoted_strategy=None,
                updated_at=datetime.now(UTC),
            )
            session.add(row)
        return row


class PostgresPaperAccountRepository:
    """Implements the PaperAccountRepository port."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self) -> PaperAccountRecord | None:
        with self._session_factory() as session:
            row = session.get(PaperAccountRow, SINGLETON_ROW_ID)
            if row is None:
                return None
            return PaperAccountRecord(
                cash=row.cash,
                equity=row.equity,
                initial_capital=row.initial_capital,
                last_tick_at=_as_utc(row.last_tick_at) if row.last_tick_at is not None else None,
                last_bar_time=(
                    _as_utc(row.last_bar_time) if row.last_bar_time is not None else None
                ),
                updated_at=_as_utc(row.updated_at),
            )

    def save(self, account: PaperAccountRecord) -> None:
        row = PaperAccountRow(
            id=SINGLETON_ROW_ID,
            cash=account.cash,
            equity=account.equity,
            initial_capital=account.initial_capital,
            last_tick_at=account.last_tick_at,
            last_bar_time=account.last_bar_time,
            updated_at=account.updated_at,
        )
        with self._session_factory() as session, session.begin():
            session.merge(row)


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
