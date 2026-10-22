"""The floor detector: the reference every detector must beat."""

from tradingbot.candles import Candle
from tradingbot.detectors import DETECTORS, FloorDetector, Mark
from tradingbot.turning_points import Kind

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def candle(hour: int, high: float, low: float, close: float) -> Candle:
    return Candle(T0 + hour * H, close, high, low, close, 1.0, 1)


def marks_of(detector: FloorDetector, candles: list[Candle]) -> list[Mark]:
    """Hand the detector the candles one at a time, as replay does, and collect its marks."""
    marks: list[Mark] = []
    for i, latest in enumerate(candles):
        kind = detector.mark(candles[: i + 1], levels=[])
        if kind is not None:
            marks.append(Mark(kind, latest.time, latest.close))
    return marks


def test_the_floor_marks_the_first_close_three_percent_past_the_extreme_since_its_last_mark() -> (
    None
):
    candles = [
        candle(0, high=100.0, low=99.0, close=100.0),
        candle(1, high=101.0, low=98.0, close=99.0),  # highest high 101
        candle(2, high=100.0, low=96.0, close=97.0),  # closes 3.96% below 101: top mark
        candle(3, high=98.0, low=95.0, close=96.0),  # lowest low since the top mark: 95
        candle(4, high=99.0, low=96.0, close=98.5),  # closes 3.68% above 95: bottom mark
        candle(5, high=103.0, low=98.0, close=102.0),  # highest high since the bottom mark: 103
        candle(6, high=103.0, low=99.0, close=99.5),  # closes 3.40% below 103: top mark
    ]

    assert marks_of(FloorDetector(), candles) == [
        Mark(Kind.TOP, T0 + 2 * H, 97.0),
        Mark(Kind.BOTTOM, T0 + 4 * H, 98.5),
        Mark(Kind.TOP, T0 + 6 * H, 99.5),
    ]


def test_the_floor_waits_for_a_full_three_percent() -> None:
    candles = [
        candle(0, high=100.0, low=99.0, close=100.0),
        candle(1, high=100.0, low=97.5, close=97.5),  # 2.5% below: not yet
        candle(2, high=98.0, low=97.0, close=97.0),  # 3.0% below: top mark
    ]

    assert marks_of(FloorDetector(), candles) == [Mark(Kind.TOP, T0 + 2 * H, 97.0)]


def test_the_floor_is_registered_under_its_name() -> None:
    assert isinstance(DETECTORS["floor"](), FloorDetector)


def test_every_detector_declares_the_reversal_size_of_its_family() -> None:
    # Families one and two were run at 8% (#11); a detector of family three declares its
    # own size in code, next to its name and timeframe (ADR-0009).
    assert {name: build().reversal for name, build in DETECTORS.items()} == {
        "floor": 0.08,
        "one": 0.08,
        "two": 0.08,
        "three": 0.08,
    }
