from collections.abc import Callable

import polars as pl
from polars.testing import assert_frame_equal

from tradingbot.core.models.dataset import FEATURE_COLUMNS, build_dataset

type RandomOhlcvFactory = Callable[[int], pl.DataFrame]


def test_dataset_has_features_and_label(make_random_ohlcv: RandomOhlcvFactory) -> None:
    dataset = build_dataset(make_random_ohlcv(200))

    assert dataset.columns == ["timestamp", *FEATURE_COLUMNS, "label"]
    assert dataset.null_count().sum_horizontal().item() == 0
    assert dataset.get_column("label").is_in([0, 1]).all()


def test_warmup_and_unlabeled_tail_are_dropped(make_random_ohlcv: RandomOhlcvFactory) -> None:
    ohlcv = make_random_ohlcv(200)
    dataset = build_dataset(ohlcv, horizon=6)

    # slowest feature (ma_slope_50_6) needs 56 bars; the last 6 bars are unlabelable
    assert dataset.height == 200 - 55 - 6
    assert dataset[0, "timestamp"] == ohlcv[55, "timestamp"]


def test_no_lookahead_truncating_future_does_not_change_the_past(
    make_random_ohlcv: RandomOhlcvFactory,
) -> None:
    """The flagship leakage check: rows must be identical with or without
    the future data that follows them."""
    ohlcv = make_random_ohlcv(300)
    full = build_dataset(ohlcv)
    partial = build_dataset(ohlcv.head(250))

    assert_frame_equal(partial, full.head(partial.height))
