"""In-memory implementations of the storage ports, plus record factories.

These fakes are the second implementation that justifies the ports
(ROADMAP.md → ADR-001). They are typed like production code: assigning them
to port-typed fields (e.g. `Repositories`) makes basedpyright verify the
structural conformance.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

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


class InMemoryBacktestRunRepository:
    def __init__(self) -> None:
        self._runs: dict[BacktestRunId, BacktestRunRecord] = {}

    def add(self, run: BacktestRunRecord) -> None:
        self._runs[run.id] = run

    def get(self, run_id: BacktestRunId) -> BacktestRunRecord | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[BacktestRunRecord]:
        return sorted(self._runs.values(), key=lambda run: run.created_at, reverse=True)


class InMemoryTradeRepository:
    def __init__(self) -> None:
        self._trades: dict[TradeId, TradeRecord] = {}

    def add(self, trade: TradeRecord) -> None:
        self._trades[trade.id] = trade

    def list_trades(self) -> list[TradeRecord]:
        return sorted(self._trades.values(), key=lambda trade: trade.exit_time, reverse=True)


class InMemoryModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelRecord] = {}

    def register(self, record: ModelRecord) -> None:
        self._models[record.name] = record

    def get_by_name(self, name: str) -> ModelRecord | None:
        return self._models.get(name)

    def list_models(self) -> list[ModelRecord]:
        return sorted(self._models.values(), key=lambda model: model.created_at, reverse=True)


class InMemoryStrategyConfigRepository:
    def __init__(self) -> None:
        self._configs: dict[str, StrategyConfigRecord] = {}

    def add(self, config: StrategyConfigRecord) -> None:
        self._configs[config.name] = config

    def get_by_name(self, name: str) -> StrategyConfigRecord | None:
        return self._configs.get(name)

    def list_configs(self) -> list[StrategyConfigRecord]:
        return sorted(self._configs.values(), key=lambda config: config.created_at, reverse=True)


_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def make_run_record(
    strategy: str = "buy_and_hold",
    created_offset_hours: int = 0,
    equity_curve_path: str = "/tmp/equity.parquet",  # noqa: S108 — test fixture value, never opened
) -> BacktestRunRecord:
    return BacktestRunRecord(
        id=BacktestRunId(uuid4()),
        strategy=strategy,
        symbol="PF_XBTUSD",
        timeframe="1h",
        data_start=_T0,
        data_end=_T0 + timedelta(days=30),
        initial_capital=Decimal("10000.00"),
        final_equity=Decimal("11234.50"),
        sharpe=0.42,
        max_drawdown=-0.31,
        n_trades=17,
        params={"fast": 20, "slow": 50},
        equity_curve_path=equity_curve_path,
        created_at=_T0 + timedelta(hours=created_offset_hours),
    )


def make_trade_record(exit_offset_hours: int = 0) -> TradeRecord:
    return TradeRecord(
        id=TradeId(uuid4()),
        strategy="ml_v1",
        symbol="PF_XBTUSD",
        side=Side.BUY,
        quantity=Decimal("0.25"),
        entry_price=Decimal("50000.00"),
        exit_price=Decimal("51000.00"),
        entry_time=_T0,
        exit_time=_T0 + timedelta(hours=6 + exit_offset_hours),
        pnl=Decimal("245.75"),
        fees=Decimal("12.50"),
        exit_reason="take_profit",
    )


def make_model_record(name: str = "xgb_v1", created_offset_hours: int = 0) -> ModelRecord:
    return ModelRecord(
        id=ModelId(uuid4()),
        name=name,
        artifact_path=f"data/models/{name}.joblib",
        auc=0.656,
        ic=0.208,
        trained_at=_T0,
        created_at=_T0 + timedelta(hours=created_offset_hours),
    )


def make_config_record(
    name: str = "ma_cross_20_50", created_offset_hours: int = 0
) -> StrategyConfigRecord:
    return StrategyConfigRecord(
        id=StrategyConfigId(uuid4()),
        name=name,
        params={"fast": 20, "slow": 50},
        created_at=_T0 + timedelta(hours=created_offset_hours),
    )
