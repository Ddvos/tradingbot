"""Strategies and what they read.

A strategy is a set of explicit, readable rules that turn marks and market
data into a desired position, long or flat (ADR-0008). The backtest asks it
at the close of every candle of the detector's timeframe, from the first
candle of the scoring period on, and hands it the candles so far, the marks
so far each with the swing extreme it was measured against, the turning
points confirmed so far, and its own position. A strategy reads price, marks,
swing extremes and turning points only: no indicators (ADR-0003), and never a
mark's outcome, which is hindsight.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from tradingbot.candles import Candle
from tradingbot.turning_points import Kind, TurningPoint


class Position(Enum):
    """The bot's exposure in this trading phase: long or flat (ADR-0008)."""

    LONG = "long"
    FLAT = "flat"


@dataclass(frozen=True, slots=True)
class MarkWithExtreme:
    """A mark as a strategy reads it: the detector's claim and the swing extreme it was
    measured against."""

    kind: Kind
    time: int
    """Start time of the candle the mark was placed on."""
    price: float
    """That candle's close."""
    extreme: float | None
    """The swing extreme the detector read on that candle, on the mark's side: the price
    the mark was measured against. None for a detector that tracks no swing."""


class Strategy(Protocol):
    """What the backtest asks of a strategy.

    At the close of every candle, `desired`: `candles` are the candles so far,
    oldest first, the latest one last; `marks` the marks placed so far, the
    one on the latest candle last when there is one; `turning_points` the
    turning points confirmed so far; `position` the account's position at
    this close. The answer is the position the strategy wants from here on;
    a change becomes a market order filled at the next candle's open.
    """

    name: str

    def desired(
        self,
        candles: Sequence[Candle],
        marks: Sequence[MarkWithExtreme],
        turning_points: Sequence[TurningPoint],
        position: Position,
    ) -> Position: ...


class Flip:
    """The reference strategy, never a candidate (ADR-0008): flat at the start, long on
    a bottom mark when flat, flat on a top mark when long; a mark of the kind the
    position already answers does nothing; nothing else. No parameter at all."""

    name = "flip"

    def desired(
        self,
        candles: Sequence[Candle],
        marks: Sequence[MarkWithExtreme],
        turning_points: Sequence[TurningPoint],
        position: Position,
    ) -> Position:
        if not marks or marks[-1].time != candles[-1].time:
            return position
        latest = marks[-1]
        if latest.kind is Kind.BOTTOM and position is Position.FLAT:
            return Position.LONG
        if latest.kind is Kind.TOP and position is Position.LONG:
            return Position.FLAT
        return position


STRATEGIES: dict[str, Callable[[], Strategy]] = {Flip.name: Flip}
"""Every strategy by name; each entry builds a fresh instance."""
