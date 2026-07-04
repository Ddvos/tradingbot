import pytest

from tradingbot.core.models.walk_forward import WalkForwardConfig, walk_forward_folds

SMALL = WalkForwardConfig(
    train_bars=400, test_bars=200, purge_bars=6, embargo_bars=24, min_test_bars=100
)


def test_folds_roll_forward_with_purge_and_embargo_gap() -> None:
    folds = walk_forward_folds(1_100, SMALL)

    assert len(folds) == 3
    for k, fold in enumerate(folds):
        assert fold.train_start == k * SMALL.test_bars
        assert fold.train_end - fold.train_start == SMALL.train_bars
        assert fold.test_start - fold.train_end == SMALL.purge_bars + SMALL.embargo_bars
    # test windows are contiguous: together they form one OOS period
    assert folds[1].test_start == folds[0].test_end
    assert folds[2].test_start == folds[1].test_end


def test_truncated_final_fold_kept_only_above_minimum() -> None:
    # fourth fold would get 1130 - 1030 = 100 test rows: exactly at the minimum
    assert len(walk_forward_folds(1_130, SMALL)) == 4
    # 99 rows: below the minimum, dropped
    assert len(walk_forward_folds(1_129, SMALL)) == 3


def test_too_few_rows_for_one_fold_raises() -> None:
    with pytest.raises(ValueError, match="cannot host a single fold"):
        walk_forward_folds(500, SMALL)


def test_invalid_config_raises() -> None:
    with pytest.raises(ValueError, match="train_bars"):
        WalkForwardConfig(train_bars=0)
    with pytest.raises(ValueError, match="min_test_bars"):
        WalkForwardConfig(test_bars=100, min_test_bars=200)
