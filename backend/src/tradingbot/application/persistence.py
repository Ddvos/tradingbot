"""Use-case wiring: build the storage-port implementations from configuration.

The API and the CLI scripts call this factory instead of importing adapters
directly (see CLAUDE.md → import rules). Tests build the same `Repositories`
bundle from in-memory fakes.
"""

from dataclasses import dataclass

from tradingbot.adapters.postgres.engine import create_db_engine, create_session_factory
from tradingbot.adapters.postgres.repositories import (
    PostgresBacktestRunRepository,
    PostgresModelRegistry,
    PostgresStrategyConfigRepository,
    PostgresTradeRepository,
)
from tradingbot.core.ports.storage import (
    BacktestRunRepository,
    ModelRegistry,
    StrategyConfigRepository,
    TradeRepository,
)


@dataclass(frozen=True)
class Repositories:
    backtest_runs: BacktestRunRepository
    trades: TradeRepository
    models: ModelRegistry
    strategy_configs: StrategyConfigRepository


def build_postgres_repositories(database_url: str) -> Repositories:
    session_factory = create_session_factory(create_db_engine(database_url))
    return Repositories(
        backtest_runs=PostgresBacktestRunRepository(session_factory),
        trades=PostgresTradeRepository(session_factory),
        models=PostgresModelRegistry(session_factory),
        strategy_configs=PostgresStrategyConfigRepository(session_factory),
    )
