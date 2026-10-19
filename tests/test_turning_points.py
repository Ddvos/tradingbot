"""Turning points in hindsight: the extremes before a move of the reversal size the other way."""

from tradingbot.candles import Candle
from tradingbot.turning_points import Kind, TurningPoint, find_turning_points

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def candle(hour: int, high: float, low: float, close: float) -> Candle:
    return Candle(T0 + hour * H, close, high, low, close, 1.0, 1)


def hand_built_series() -> list[Candle]:
    """Sixteen hours with 02:00 missing: a bottom at 03:00, a top at 08:00, a bottom at 12:00.

    The rise from 90 (03:00) first reaches 8% at 06:00 (high 98), the fall from 100
    (08:00) first reaches 8% at 11:00 (low 91), the rise from 90 (12:00) first
    reaches 8% at 14:00 (high 98). The high of 101 at 15:00 is never confirmed.
    """
    return [
        candle(0, high=96.0, low=94.0, close=95.0),
        candle(1, high=95.0, low=92.0, close=93.0),
        # 02:00 has no candle
        candle(3, high=93.0, low=90.0, close=91.0),
        candle(4, high=94.0, low=91.0, close=93.0),
        candle(5, high=96.0, low=92.0, close=95.0),
        candle(6, high=98.0, low=94.0, close=97.0),
        candle(7, high=99.0, low=96.0, close=98.0),
        candle(8, high=100.0, low=97.0, close=99.0),
        candle(9, high=99.0, low=95.0, close=96.0),
        candle(10, high=97.0, low=93.0, close=94.0),
        candle(11, high=95.0, low=91.0, close=92.0),
        candle(12, high=93.0, low=90.0, close=91.0),
        candle(13, high=95.0, low=91.0, close=94.0),
        candle(14, high=98.0, low=93.0, close=97.0),
        candle(15, high=101.0, low=96.0, close=100.0),
    ]


def test_turning_points_are_the_extremes_before_an_eight_percent_reversal() -> None:
    points = find_turning_points(hand_built_series())

    assert points == [
        TurningPoint(Kind.BOTTOM, time=T0 + 3 * H, price=90.0, confirmed_at=T0 + 6 * H),
        TurningPoint(Kind.TOP, time=T0 + 8 * H, price=100.0, confirmed_at=T0 + 11 * H),
        TurningPoint(Kind.BOTTOM, time=T0 + 12 * H, price=90.0, confirmed_at=T0 + 14 * H),
    ]


def test_a_candle_never_confirms_its_own_extreme() -> None:
    wide = candle(0, high=100.0, low=90.0, close=95.0)

    assert find_turning_points([wide]) == []


def test_an_empty_series_has_no_turning_points() -> None:
    assert find_turning_points([]) == []


def random_walk(hours: int, seed: int) -> list[Candle]:
    """A seeded hourly random walk with hourly moves of up to 3%."""
    import random

    rng = random.Random(seed)
    candles: list[Candle] = []
    close = 1000.0
    for hour in range(hours):
        open_ = close
        close = open_ * (1 + rng.uniform(-0.03, 0.03))
        high = max(open_, close) * (1 + rng.uniform(0, 0.01))
        low = min(open_, close) * (1 - rng.uniform(0, 0.01))
        candles.append(Candle(T0 + hour * H, open_, high, low, close, 1.0, 1))
    return candles


def test_turning_points_alternate_and_neighbours_differ_by_the_reversal_size() -> None:
    candles = random_walk(hours=5000, seed=1)

    points = find_turning_points(candles)

    assert len(points) > 10
    for earlier, later in zip(points, points[1:], strict=False):
        assert earlier.kind != later.kind
        assert earlier.time < later.time
        assert earlier.confirmed_at <= later.confirmed_at
        if earlier.kind is Kind.TOP:
            assert later.price <= earlier.price * (1 - 0.08)
        else:
            assert later.price >= earlier.price * (1 + 0.08)


def test_the_turning_points_of_a_prefix_are_those_confirmed_by_its_last_candle() -> None:
    candles = random_walk(hours=400, seed=2)
    all_points = find_turning_points(candles)

    for length in range(1, len(candles) + 1):
        prefix = candles[:length]
        until = prefix[-1].time

        assert find_turning_points(prefix) == [p for p in all_points if p.confirmed_at <= until]
