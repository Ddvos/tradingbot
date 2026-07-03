import pytest

from tradingbot.core.signals.signal import Signal, direction


def test_direction_mapping() -> None:
    assert direction(Signal.LONG) == 1
    assert direction(Signal.FLAT) == 0
    assert direction(Signal.SHORT) == -1
    assert direction("long") == 1


def test_direction_rejects_unknown_signal() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        direction("hodl")
