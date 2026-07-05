"""Walkforward API against a fake run-artifact directory on disk."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.fakes import make_fake_repositories
from tradingbot.api.app import create_app
from tradingbot.api.features.walkforward import handlers
from tradingbot.config.settings import Settings

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def write_run(base: Path, symbol: str, run: str, *, equity: list[float]) -> None:
    """A minimal but schema-faithful run folder: 2 folds, of which fold 0 has
    zero trades (NaN win rate) and fold 1 an infinite profit factor."""
    run_dir = base / symbol / run
    run_dir.mkdir(parents=True)
    stamps = [_T0, _T0 + timedelta(days=90)]
    pl.DataFrame(
        {
            "fold": [0, 1],
            "test_start": pl.Series(stamps, dtype=pl.Datetime("ms", "UTC")),
            "test_end": pl.Series(
                [s + timedelta(days=89) for s in stamps], dtype=pl.Datetime("ms", "UTC")
            ),
            "n_test": [2160, 2160],
            "auc": [0.66, 0.67],
            "ic": [0.21, 0.23],
            "sharpe": [0.0, -4.0],
            "max_drawdown": [0.0, -0.02],
            "n_trades": [0, 3],
            "win_rate": [float("nan"), 0.33],
            "profit_factor": [float("nan"), float("inf")],
        }
    ).write_parquet(run_dir / "folds.parquet")
    pl.DataFrame(
        {
            "timestamp": pl.Series(
                [_T0 + timedelta(hours=i) for i in range(len(equity))],
                dtype=pl.Datetime("ms", "UTC"),
            ),
            "equity": equity,
        }
    ).write_parquet(run_dir / "equity.parquet")
    (run_dir / "report.md").write_text(f"# Walk-forward report — {run}\n")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(walkforward_dir=tmp_path)
    return TestClient(create_app(repositories=make_fake_repositories(), settings=settings))


def test_list_runs_empty_when_dir_missing(client: TestClient) -> None:
    # tmp_path exists but holds no runs; a missing dir behaves the same
    assert client.get("/walkforward").json() == []


def test_list_runs_newest_first_with_parsed_names(client: TestClient, tmp_path: Path) -> None:
    write_run(tmp_path, "PF_XBTUSD", "1h_xgb_v1_20260101_000000", equity=[10000.0, 10100.0])
    write_run(tmp_path, "PF_XBTUSD", "1h_xgb_v2_20260201_000000", equity=[10000.0, 9900.0])
    (tmp_path / "PF_XBTUSD" / "scratch").mkdir()  # no artifacts — must be skipped

    listed = client.get("/walkforward").json()

    assert [run["name"] for run in listed] == ["xgb_v2", "xgb_v1"]
    first = listed[0]
    assert first["symbol"] == "PF_XBTUSD"
    assert first["timeframe"] == "1h"
    assert first["run"] == "1h_xgb_v2_20260201_000000"
    assert first["n_folds"] == 2
    assert first["created_at"].startswith("2026-02-01")
    assert first["initial_equity"] == 10000.0
    assert first["final_equity"] == 9900.0
    assert first["oos_max_drawdown"] == pytest.approx(-0.01)


def test_run_detail_maps_non_finite_metrics_to_null(client: TestClient, tmp_path: Path) -> None:
    write_run(tmp_path, "PF_XBTUSD", "1h_xgb_v2_20260201_000000", equity=[10000.0, 9900.0])

    response = client.get("/walkforward/PF_XBTUSD/1h_xgb_v2_20260201_000000")

    assert response.status_code == 200
    body = response.json()
    assert body["report"].startswith("# Walk-forward report")
    assert body["summary"]["name"] == "xgb_v2"
    zero_trade_fold, traded_fold = body["folds"]
    assert zero_trade_fold["win_rate"] is None
    assert zero_trade_fold["profit_factor"] is None
    assert traded_fold["profit_factor"] is None  # inf is not JSON either
    assert traded_fold["win_rate"] == pytest.approx(0.33)
    assert traded_fold["auc"] == pytest.approx(0.67)


def test_run_detail_404(client: TestClient) -> None:
    assert client.get("/walkforward/PF_XBTUSD/1h_missing_20260101_000000").status_code == 404


def test_equity_curve(client: TestClient, tmp_path: Path) -> None:
    write_run(tmp_path, "PF_XBTUSD", "1h_xgb_v2_20260201_000000", equity=[10000.0, 10050.0])

    body = client.get("/walkforward/PF_XBTUSD/1h_xgb_v2_20260201_000000/equity").json()

    assert body["run"] == "1h_xgb_v2_20260201_000000"
    assert body["points"] == [
        {"time": int(_T0.timestamp()), "value": 10000.0},
        {"time": int(_T0.timestamp()) + 3600, "value": 10050.0},
    ]


def test_traversal_segments_are_404(tmp_path: Path) -> None:
    with pytest.raises(HTTPException) as excinfo:
        handlers.get_run(tmp_path, "..", "1h_xgb_v1_20260101_000000")
    assert excinfo.value.status_code == 404
