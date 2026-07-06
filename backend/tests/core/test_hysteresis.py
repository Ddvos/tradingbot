import pytest

from tradingbot.core.signals.hysteresis import hysteresis_signals
from tradingbot.core.signals.signal import Signal

LONG = Signal.LONG.value
FLAT = Signal.FLAT.value


def test_stays_long_between_the_bars_but_does_not_enter_there() -> None:
    # 0.20 keeps an open position alive (>= exit 0.18) yet is not enough to
    # open one (< enter 0.27) — the stickiness that suppresses churn.
    probabilities = [0.10, 0.30, 0.20, 0.15, 0.20, 0.30, 0.05]

    signals = hysteresis_signals(probabilities, enter_at=0.27, exit_at=0.18)

    assert signals == [FLAT, LONG, LONG, FLAT, FLAT, LONG, FLAT]


def test_boundary_values_count_as_inside() -> None:
    signals = hysteresis_signals([0.27, 0.18, 0.1799], enter_at=0.27, exit_at=0.18)

    assert signals == [LONG, LONG, FLAT]


def test_exit_bar_must_be_below_entry_bar() -> None:
    with pytest.raises(ValueError, match="must be below"):
        hysteresis_signals([0.5], enter_at=0.2, exit_at=0.2)
