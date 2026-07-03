from collections.abc import Callable

import polars as pl
import pytest

from tradingbot.core.signals.signal import Signal
from tradingbot.core.strategies.ma_cross import MACrossStrategy

type OhlcvFactory = Callable[[list[float]], pl.DataFrame]


def test_fast_must_be_below_slow() -> None:
    with pytest.raises(ValueError, match="must be <"):
        MACrossStrategy(fast=50, slow=20)


def test_long_when_fast_above_slow(make_ohlcv: OhlcvFactory) -> None:
    # steadily rising: fast MA sits above slow MA once both exist
    signals = MACrossStrategy(fast=2, slow=3).signals(make_ohlcv([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert signals.to_list()[-1] == Signal.LONG.value


def test_flat_when_fast_below_slow(make_ohlcv: OhlcvFactory) -> None:
    signals = MACrossStrategy(fast=2, slow=3).signals(make_ohlcv([5.0, 4.0, 3.0, 2.0, 1.0]))
    assert signals.to_list()[-1] == Signal.FLAT.value


def test_warmup_rows_are_flat(make_ohlcv: OhlcvFactory) -> None:
    signals = MACrossStrategy(fast=2, slow=3).signals(make_ohlcv([1.0, 2.0, 3.0, 4.0]))
    assert signals.to_list()[:2] == [Signal.FLAT.value, Signal.FLAT.value]


def test_one_signal_per_bar(make_ohlcv: OhlcvFactory) -> None:
    ohlcv = make_ohlcv([1.0, 2.0, 3.0])
    assert len(MACrossStrategy(fast=2, slow=3).signals(ohlcv)) == ohlcv.height
