"""Live feature endpoints against the in-memory fakes."""

import pytest
from fastapi.testclient import TestClient

from tests.fakes import (
    make_config_record,
    make_fake_repositories,
    make_paper_account_record,
    make_position_record,
    make_trade_record,
)
from tradingbot.api.app import create_app
from tradingbot.application.persistence import Repositories
from tradingbot.config.settings import Settings


@pytest.fixture
def repos() -> Repositories:
    return make_fake_repositories()


@pytest.fixture
def client(repos: Repositories) -> TestClient:
    return TestClient(create_app(repositories=repos, settings=Settings()))


def test_promote_then_status_running(client: TestClient, repos: Repositories) -> None:
    repos.strategy_configs.add(make_config_record(name="hold"))

    promoted = client.post("/live/promote", json={"name": "hold"}).json()

    assert promoted["state"] == "running"
    assert promoted["promoted_strategy"] == "hold"
    assert client.get("/live/status").json()["state"] == "running"


def test_promote_unknown_config_is_404(client: TestClient) -> None:
    response = client.post("/live/promote", json={"name": "ghost"})

    assert response.status_code == 404
    assert "ghost" in response.json()["detail"]


def test_pause_resume_roundtrip(client: TestClient, repos: Repositories) -> None:
    repos.strategy_configs.add(make_config_record(name="hold"))
    client.post("/live/promote", json={"name": "hold"})

    assert client.post("/live/pause").json()["state"] == "paused"
    assert client.post("/live/resume").json()["state"] == "running"


def test_demote_goes_idle_and_keeps_account_visible(
    client: TestClient, repos: Repositories
) -> None:
    repos.strategy_configs.add(make_config_record(name="hold"))
    client.post("/live/promote", json={"name": "hold"})
    repos.paper_account.save(make_paper_account_record())

    status = client.post("/live/demote").json()

    assert status["state"] == "idle"
    assert status["promoted_strategy"] is None
    assert status["cash"] is not None


def test_status_includes_account_and_open_position(client: TestClient, repos: Repositories) -> None:
    repos.paper_account.save(make_paper_account_record())
    repos.positions.save(make_position_record(bars_held=2))

    status = client.get("/live/status").json()

    assert float(status["equity"]) == 10_000.0
    assert status["position"]["side"] == "buy"
    assert status["position"]["bars_held"] == 2
    assert float(status["position"]["entry_price"]) == 50_000.0


def test_paper_trades_listing_newest_first(client: TestClient, repos: Repositories) -> None:
    repos.trades.add(make_trade_record(exit_offset_hours=0))
    repos.trades.add(make_trade_record(exit_offset_hours=3))

    trades = client.get("/live/trades").json()

    assert len(trades) == 2
    assert trades[0]["exit_time"] > trades[1]["exit_time"]
    assert trades[0]["exit_reason"] == "take_profit"
