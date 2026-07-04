"""Round-trip tests for the Postgres repositories, run on SQLite in-memory.

SQLite exercises the SQLAlchemy mapping (types, ordering, upsert) without a
server; the Postgres dialect itself is covered by running the Alembic
migration against a real database. SQLite stores Numeric as float, hence the
SAWarning filter — values with ≤8 decimals still round-trip exactly.
"""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tests.fakes import (
    make_config_record,
    make_model_record,
    make_run_record,
    make_trade_record,
)
from tradingbot.adapters.postgres.engine import create_session_factory
from tradingbot.adapters.postgres.repositories import (
    PostgresBacktestRunRepository,
    PostgresModelRegistry,
    PostgresStrategyConfigRepository,
    PostgresTradeRepository,
)
from tradingbot.adapters.postgres.tables import Base
from tradingbot.core.ports.storage import BacktestRunId

pytestmark = pytest.mark.filterwarnings("ignore::sqlalchemy.exc.SAWarning")


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


class TestBacktestRunRepository:
    def test_roundtrip(self, session_factory: sessionmaker[Session]) -> None:
        repo = PostgresBacktestRunRepository(session_factory)
        record = make_run_record()

        repo.add(record)
        loaded = repo.get(record.id)

        assert loaded == record
        assert loaded is not None
        assert loaded.created_at.tzinfo is not None

    def test_get_missing_returns_none(self, session_factory: sessionmaker[Session]) -> None:
        repo = PostgresBacktestRunRepository(session_factory)
        assert repo.get(BacktestRunId(uuid4())) is None

    def test_list_runs_newest_first(self, session_factory: sessionmaker[Session]) -> None:
        repo = PostgresBacktestRunRepository(session_factory)
        older = make_run_record(strategy="older", created_offset_hours=0)
        newer = make_run_record(strategy="newer", created_offset_hours=5)
        repo.add(older)
        repo.add(newer)

        runs = repo.list_runs()

        assert [run.strategy for run in runs] == ["newer", "older"]


class TestTradeRepository:
    def test_roundtrip_and_ordering(self, session_factory: sessionmaker[Session]) -> None:
        repo = PostgresTradeRepository(session_factory)
        earlier = make_trade_record(exit_offset_hours=0)
        later = make_trade_record(exit_offset_hours=3)
        repo.add(earlier)
        repo.add(later)

        trades = repo.list_trades()

        assert trades == [later, earlier]


class TestModelRegistry:
    def test_register_upserts_on_name(self, session_factory: sessionmaker[Session]) -> None:
        registry = PostgresModelRegistry(session_factory)
        first = make_model_record(name="xgb_v1")
        retrained = make_model_record(name="xgb_v1", created_offset_hours=2)

        registry.register(first)
        registry.register(retrained)

        assert registry.list_models() == [retrained]
        assert registry.get_by_name("xgb_v1") == retrained

    def test_get_by_name_missing_returns_none(self, session_factory: sessionmaker[Session]) -> None:
        registry = PostgresModelRegistry(session_factory)
        assert registry.get_by_name("nope") is None


class TestStrategyConfigRepository:
    def test_roundtrip(self, session_factory: sessionmaker[Session]) -> None:
        repo = PostgresStrategyConfigRepository(session_factory)
        record = make_config_record()

        repo.add(record)

        assert repo.get_by_name(record.name) == record
        assert repo.list_configs() == [record]
