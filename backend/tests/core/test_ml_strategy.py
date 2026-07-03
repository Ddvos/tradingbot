from collections.abc import Callable

import polars as pl

from tradingbot.core.models.artifact import ModelArtifact
from tradingbot.core.models.dataset import build_dataset
from tradingbot.core.models.train import train_model
from tradingbot.core.signals.signal import Signal
from tradingbot.core.strategies.ml_strategy import MLStrategy

type RandomOhlcvFactory = Callable[[int], pl.DataFrame]


def make_artifact(make_random_ohlcv: RandomOhlcvFactory) -> ModelArtifact:
    """Artifact trained on the real feature set over a random walk."""
    ohlcv = make_random_ohlcv(300)
    return train_model(build_dataset(ohlcv), n_estimators=10)


def test_one_signal_per_bar(make_random_ohlcv: RandomOhlcvFactory) -> None:
    artifact = make_artifact(make_random_ohlcv)
    ohlcv = make_random_ohlcv(300)

    signals = MLStrategy(artifact).signals(ohlcv)

    assert len(signals) == ohlcv.height
    assert set(signals.to_list()) <= {Signal.LONG.value, Signal.FLAT.value}


def test_warmup_rows_are_flat_even_at_zero_threshold(
    make_random_ohlcv: RandomOhlcvFactory,
) -> None:
    artifact = make_artifact(make_random_ohlcv)
    ohlcv = make_random_ohlcv(300)

    signals = MLStrategy(artifact, threshold=0.0).signals(ohlcv).to_list()

    assert signals[:20] == [Signal.FLAT.value] * 20  # features incomplete -> no prediction
    assert signals[-1] == Signal.LONG.value  # complete features + threshold 0 -> long


def test_impossible_threshold_stays_flat(make_random_ohlcv: RandomOhlcvFactory) -> None:
    artifact = make_artifact(make_random_ohlcv)
    ohlcv = make_random_ohlcv(300)

    signals = MLStrategy(artifact, threshold=1.1).signals(ohlcv)

    assert signals.to_list() == [Signal.FLAT.value] * ohlcv.height
