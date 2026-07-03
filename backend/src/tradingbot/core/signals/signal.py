"""Discrete trading signals: what the strategy wants the position to be."""

from enum import StrEnum


class Signal(StrEnum):
    LONG = "long"
    FLAT = "flat"
    SHORT = "short"


_DIRECTIONS = {Signal.LONG: 1, Signal.FLAT: 0, Signal.SHORT: -1}


def direction(signal: str) -> int:
    """Map a signal value to a position direction: +1 long, 0 flat, -1 short.

    Raises ValueError for anything that is not a valid Signal value.
    """
    return _DIRECTIONS[Signal(signal)]
