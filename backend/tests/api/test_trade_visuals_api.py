"""Trades + candles endpoints (backtests and walkforward) against tmp artifacts."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from tests.api.test_walkforward_api import write_run
from tests.fakes import make_fake_repositories, make_run_record
from tradingbot.api.app import create_app
from tradingbot.application.persistence import Repositories
from tradingbot.application.run_backtest import trades_frame, trades_path_for
from tradingbot.config.settings import Settings
from tradingbot.core.backtest.engine import ExitReason, Trade
from tradingbot.core.ports.executor import Fill, OrderId, Side
from tradingbot.core.ports.market_data import OHLCV_SCHEMA

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def repos() -> Repositories:
    return make_fake_repositories()


@pytest.fixture
def client(repos: Repositories, tmp_path: Path) -> TestClient:
    settings = Settings(walkforward_dir=tmp_path / "walkforward", ohlcv_dir=tmp_path / "ohlcv")
    return TestClient(create_app(repositories=repos, settings=settings))


def write_ohlcv(base: Path, symbol: str, n: int) -> None:
    closes = [100.0 + i for i in range(n)]
    frame = pl.DataFrame(
        {
            "timestamp": [_T0 + timedelta(hours=i) for i in range(n)],
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [10.0] * n,
        },
        schema=OHLCV_SCHEMA,
    )
    target = base / symbol / "1h.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(target)


def make_trade(*, stop: Decimal | None) -> Trade:
    def fill(side: Side, price: str, hours: int) -> Fill:
        return Fill(
            OrderId("o"),
            "PF_XBTUSD",
            side,
            Decimal(1),
            Decimal(price),
            Decimal(1),
            _T0 + timedelta(hours=hours),
        )

    return Trade(
        entry_fill=fill(Side.BUY, "101", 1),
        exit_fill=fill(Side.SELL, "104", 4),
        reason=ExitReason.TAKE_PROFIT,
        pnl=Decimal(1),
        stop=stop,
        take_profit=Decimal("104"),
    )


def test_backtest_trades_endpoint(client: TestClient, repos: Repositories, tmp_path: Path) -> None:
    equity_path = tmp_path / "equity.parquet"
    trades_frame([make_trade(stop=None)]).write_parquet(trades_path_for(equity_path))
    record = make_run_record(equity_curve_path=str(equity_path))
    repos.backtest_runs.add(record)

    body = client.get(f"/backtests/{record.id}/trades").json()

    assert body["run_id"] == str(record.id)
    (trade,) = body["trades"]
    assert trade["side"] == "long"
    assert trade["stop_price"] is None
    assert trade["take_profit_price"] == 104.0
    assert trade["reason"] == "take_profit"


def test_backtest_trades_404_when_log_missing(
    client: TestClient, repos: Repositories, tmp_path: Path
) -> None:
    record = make_run_record(equity_curve_path=str(tmp_path / "equity.parquet"))
    repos.backtest_runs.add(record)

    response = client.get(f"/backtests/{record.id}/trades")

    assert response.status_code == 404
    assert "re-run the backtest" in response.json()["detail"]


def test_backtest_candles_clamped_to_run_window(
    client: TestClient, repos: Repositories, tmp_path: Path
) -> None:
    write_ohlcv(tmp_path / "ohlcv", "PF_XBTUSD", 100)
    # make_run_record spans _T0 .. _T0 + 30 days, wider than the 100 bars
    record = make_run_record(equity_curve_path=str(tmp_path / "equity.parquet"))
    repos.backtest_runs.add(record)

    body = client.get(f"/backtests/{record.id}/candles").json()

    assert len(body["candles"]) == 100
    first = body["candles"][0]
    assert first["time"] == int(_T0.timestamp())
    assert first["high"] == 101.0


def test_walkforward_trades_and_candles(client: TestClient, tmp_path: Path) -> None:
    run = "1h_xgb_v1_hysteresis_20260101_000000"
    write_run(tmp_path / "walkforward", "PF_XBTUSD", run, equity=[10000.0, 10100.0])
    trades_frame([make_trade(stop=Decimal("99"))]).write_parquet(
        tmp_path / "walkforward" / "PF_XBTUSD" / run / "trades.parquet"
    )
    write_ohlcv(tmp_path / "ohlcv", "PF_XBTUSD", 10)

    trades = client.get(f"/walkforward/PF_XBTUSD/{run}/trades").json()["trades"]
    assert trades[0]["stop_price"] == 99.0

    candles = client.get(f"/walkforward/PF_XBTUSD/{run}/candles").json()["candles"]
    # clamped to the equity curve's window: bars at _T0 and _T0 + 1h
    assert len(candles) == 2


def test_walkforward_trades_404_for_pre_trade_log_runs(client: TestClient, tmp_path: Path) -> None:
    run = "1h_xgb_v1_20260101_000000"
    write_run(tmp_path / "walkforward", "PF_XBTUSD", run, equity=[10000.0, 10100.0])

    response = client.get(f"/walkforward/PF_XBTUSD/{run}/trades")

    assert response.status_code == 404
    assert "re-run the walk-forward" in response.json()["detail"]
