"""StructureTrendStrategy: confirmed-structure trend signals (H4).

The zigzag sequences are hand-crafted for k = 2; swing bars and their
confirmation bars are worked out in the comments so the expected signal
transitions are exact, not approximate. The make_ohlcv fixture derives
high/low as close ±1%, so the ordering of swing values follows the closes.
"""

from collections.abc import Callable

import polars as pl
import pytest

from tradingbot.core.signals.signal import Signal
from tradingbot.core.strategies.structure_trend import StructureTrendStrategy

type OhlcvFactory = Callable[[list[float]], pl.DataFrame]

# Rising zigzag: swing lows at bars 2 (8), 7 (10), 12 (13), 16 (10) and
# swing highs at bars 5 (12), 10 (15), 14 (16). With k = 2 the second
# rising low confirms at bar 9 and the second rising high at bar 12 ->
# LONG from bar 12. The dip to 10 (bar 16, confirmed at 18) breaks the
# rising lows while highs still rise -> mixed structure -> carry the long.
UPTREND = [
    10.0, 9.0, 8.0, 9.0, 10.0, 12.0, 11.0, 10.0, 11.0, 13.0,
    15.0, 14.0, 13.0, 14.0, 16.0, 11.0, 10.0, 11.0, 17.0,
]  # fmt: skip

# Mirror image (20 - close): lower highs confirm at bar 9, lower lows at
# bar 12 -> SHORT from bar 12.
DOWNTREND = [20.0 - close for close in UPTREND[:15]]


def signal_values(closes: list[float], make_ohlcv: OhlcvFactory) -> list[str]:
    return StructureTrendStrategy(k=2).signals(make_ohlcv(closes)).to_list()


def test_long_from_second_rising_high_and_low_carried_through_mixed(
    make_ohlcv: OhlcvFactory,
) -> None:
    signals = signal_values(UPTREND, make_ohlcv)

    assert signals == [Signal.FLAT.value] * 12 + [Signal.LONG.value] * 7


def test_short_from_confirmed_downtrend(make_ohlcv: OhlcvFactory) -> None:
    signals = signal_values(DOWNTREND, make_ohlcv)

    assert signals == [Signal.FLAT.value] * 12 + [Signal.SHORT.value] * 3


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError, match="k must be >= 1"):
        StructureTrendStrategy(k=0)
