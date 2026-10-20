"""Seeded random walks the replay tests share: hourly, and fifteen-minute with a gap."""

import random

from tradingbot.candles import Candle

H = 3600
Q = 900  # a quarter of an hour
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def random_walk(hours: int, seed: int) -> list[Candle]:
    """A seeded hourly random walk with hourly moves of up to 3%."""
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


def quarter_walk(hours: int, seed: int) -> list[Candle]:
    """A seeded fifteen-minute random walk with moves of up to 1.5% a quarter; the :30
    candle of every seventh hour had no trades."""
    rng = random.Random(seed)
    candles: list[Candle] = []
    close = 1000.0
    for quarter in range(hours * 4):
        if quarter % 28 == 2:
            continue
        open_ = close
        close = open_ * (1 + rng.uniform(-0.015, 0.015))
        high = max(open_, close) * (1 + rng.uniform(0, 0.005))
        low = min(open_, close) * (1 - rng.uniform(0, 0.005))
        candles.append(Candle(T0 + quarter * Q, open_, high, low, close, 1.0, 1))
    return candles
