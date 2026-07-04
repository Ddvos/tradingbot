"""End-to-end walk-forward on synthetic data: structure and discipline checks.

Random-walk data has no edge, so metric *values* are meaningless here — the
tests assert the mechanics: fold counts, a gap-free stitched curve, and the
holdout clamp.
"""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from tradingbot.adapters.parquet.store import ParquetStore
from tradingbot.application.run_walkforward import run_walk_forward
from tradingbot.core.models.walk_forward import WalkForwardConfig

type RandomOhlcvFactory = Callable[[int], pl.DataFrame]

SMALL = WalkForwardConfig(
    train_bars=400, test_bars=200, purge_bars=6, embargo_bars=24, min_test_bars=100
)
FAR_FUTURE = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.fixture
def data_dir(tmp_path: Path, make_random_ohlcv: RandomOhlcvFactory) -> Path:
    # 1261 bars -> 1200 dataset rows (55 warmup + 6 unlabeled tail dropped)
    ParquetStore(tmp_path).upsert("PF_XBTUSD", "1h", make_random_ohlcv(1261))
    return tmp_path


def test_full_run_structure(data_dir: Path) -> None:
    report = run_walk_forward(
        data_dir,
        "PF_XBTUSD",
        "1h",
        config=SMALL,
        threshold=0.3,
        holdout_start=FAR_FUTURE,
    )

    # 1200 dataset rows host 3 full test windows + one truncated (170 rows)
    assert len(report.folds) == 4
    assert report.dataset_rows == 1200

    # the stitched OOS curve covers every test bar exactly once, in order
    expected_rows = sum(f.fold.test_end - f.fold.test_start for f in report.folds)
    assert report.equity_curve.height == expected_rows
    deltas = report.equity_curve.get_column("timestamp").diff().drop_nulls()
    assert (deltas == timedelta(hours=1)).all()
    assert report.equity_curve[0, "timestamp"] == report.folds[0].test_start

    # metrics exist and are sane for a no-edge random walk
    assert math.isfinite(report.oos_sharpe)
    assert report.oos_final_equity > 0
    assert report.baseline_final_equity > 0
    assert -1.0 <= report.oos_max_drawdown <= 0.0
    assert math.isnan(report.deflated_sharpe) or 0.0 <= report.deflated_sharpe <= 1.0
    assert "this_run" in report.trial_sharpes_annualized


def test_holdout_clamp_excludes_data_after_the_boundary(data_dir: Path) -> None:
    boundary = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(hours=1000)

    report = run_walk_forward(data_dir, "PF_XBTUSD", "1h", config=SMALL, holdout_start=boundary)

    assert report.data_end < boundary
    # 1000 dev bars -> 939 dataset rows -> two full folds + one 109-row tail
    assert len(report.folds) == 3


def test_no_data_before_holdout_raises(data_dir: Path) -> None:
    with pytest.raises(ValueError, match="before holdout start"):
        run_walk_forward(
            data_dir,
            "PF_XBTUSD",
            "1h",
            config=SMALL,
            holdout_start=datetime(2020, 1, 1, tzinfo=UTC),
        )
