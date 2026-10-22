"""Strategies: the flip, the reference that acts on every mark (ADR-0008)."""

from tradingbot.candles import Candle
from tradingbot.strategies import STRATEGIES, Flip, MarkWithExtreme, Position
from tradingbot.turning_points import Kind

Q = 900
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def candle(quarter: int) -> Candle:
    return Candle(T0 + quarter * Q, 100.0, 101.0, 99.0, 100.0, 1.0, 1)


def mark(kind: Kind, quarter: int) -> MarkWithExtreme:
    return MarkWithExtreme(kind, T0 + quarter * Q, 100.0, extreme=105.0)


def test_the_flip_goes_long_on_a_bottom_mark_when_flat() -> None:
    candles = [candle(0), candle(1)]
    marks = [mark(Kind.BOTTOM, 1)]

    assert Flip().desired(candles, marks, [], Position.FLAT) is Position.LONG


def test_a_second_bottom_mark_while_long_does_nothing() -> None:
    candles = [candle(0), candle(1), candle(2)]
    marks = [mark(Kind.BOTTOM, 1), mark(Kind.BOTTOM, 2)]

    assert Flip().desired(candles, marks, [], Position.LONG) is Position.LONG


def test_the_flip_goes_flat_on_a_top_mark_when_long() -> None:
    candles = [candle(0), candle(1), candle(2)]
    marks = [mark(Kind.BOTTOM, 1), mark(Kind.TOP, 2)]

    assert Flip().desired(candles, marks, [], Position.LONG) is Position.FLAT


def test_a_top_mark_while_flat_does_nothing_and_so_does_a_candle_without_a_mark() -> None:
    flip = Flip()

    assert flip.desired([candle(0)], [mark(Kind.TOP, 0)], [], Position.FLAT) is Position.FLAT
    assert flip.desired([candle(0)], [], [], Position.FLAT) is Position.FLAT
    # The bottom mark on candle 1 is history by candle 2: a mark is acted on at its own
    # candle's close only, never again.
    assert (
        flip.desired([candle(0), candle(1), candle(2)], [mark(Kind.BOTTOM, 1)], [], Position.FLAT)
        is Position.FLAT
    )
    assert (
        flip.desired([candle(0), candle(1), candle(2)], [mark(Kind.TOP, 1)], [], Position.LONG)
        is Position.LONG
    )


def test_the_flip_is_known_by_name() -> None:
    assert list(STRATEGIES) == ["flip"]
    assert STRATEGIES["flip"]().name == "flip"
