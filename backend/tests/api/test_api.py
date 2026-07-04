"""API happy paths (plus 404s) against the in-memory fakes."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import polars as pl
import pytest
from fastapi.testclient import TestClient

from tests.fakes import (
    InMemoryBacktestRunRepository,
    InMemoryModelRegistry,
    InMemoryStrategyConfigRepository,
    InMemoryTradeRepository,
    make_config_record,
    make_model_record,
    make_run_record,
)
from tradingbot.api.app import create_app
from tradingbot.application.persistence import Repositories
from tradingbot.config.settings import Settings


@pytest.fixture
def repos() -> Repositories:
    return Repositories(
        backtest_runs=InMemoryBacktestRunRepository(),
        trades=InMemoryTradeRepository(),
        models=InMemoryModelRegistry(),
        strategy_configs=InMemoryStrategyConfigRepository(),
    )


@pytest.fixture
def client(repos: Repositories) -> TestClient:
    return TestClient(create_app(repositories=repos, settings=Settings()))


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_backtests_empty(client: TestClient) -> None:
    response = client.get("/backtests")
    assert response.status_code == 200
    assert response.json() == []


def test_backtest_list_and_detail(client: TestClient, repos: Repositories) -> None:
    record = make_run_record(strategy="ma_cross")
    repos.backtest_runs.add(record)

    listed = client.get("/backtests").json()
    assert len(listed) == 1
    assert listed[0]["strategy"] == "ma_cross"
    assert listed[0]["n_trades"] == record.n_trades
    assert float(listed[0]["final_equity"]) == float(record.final_equity)

    detail = client.get(f"/backtests/{record.id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == str(record.id)


def test_backtest_detail_404(client: TestClient) -> None:
    assert client.get(f"/backtests/{uuid4()}").status_code == 404


def test_equity_curve(client: TestClient, repos: Repositories, tmp_path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    curve = pl.DataFrame(
        {
            "timestamp": pl.Series(
                [start + timedelta(hours=i) for i in range(3)],
                dtype=pl.Datetime("ms", "UTC"),
            ),
            "equity": [10000.0, 10100.0, 10050.0],
        }
    )
    curve_path = tmp_path / "equity.parquet"
    curve.write_parquet(curve_path)
    record = make_run_record(equity_curve_path=str(curve_path))
    repos.backtest_runs.add(record)

    response = client.get(f"/backtests/{record.id}/equity")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == str(record.id)
    assert body["points"][0] == {"time": int(start.timestamp()), "value": 10000.0}
    assert len(body["points"]) == 3


def test_equity_curve_missing_file_404(client: TestClient, repos: Repositories) -> None:
    record = make_run_record(equity_curve_path="/nonexistent/equity.parquet")
    repos.backtest_runs.add(record)
    assert client.get(f"/backtests/{record.id}/equity").status_code == 404


def test_models_list_and_detail(client: TestClient, repos: Repositories) -> None:
    repos.models.register(make_model_record(name="xgb_v1"))

    listed = client.get("/models").json()
    assert [model["name"] for model in listed] == ["xgb_v1"]

    detail = client.get("/models/xgb_v1")
    assert detail.status_code == 200
    assert detail.json()["auc"] == pytest.approx(0.656)

    assert client.get("/models/missing").status_code == 404


def test_strategies_list(client: TestClient, repos: Repositories) -> None:
    repos.strategy_configs.add(make_config_record(name="ma_cross_20_50"))
    listed = client.get("/strategies").json()
    assert [config["name"] for config in listed] == ["ma_cross_20_50"]
    assert listed[0]["params"] == {"fast": 20, "slow": 50}


def test_live_status_stub(client: TestClient) -> None:
    response = client.get("/live/status")
    assert response.status_code == 200
    assert response.json()["state"] == "offline"
