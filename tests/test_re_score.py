"""Re-scoring a recorded run: its own candles replayed, its marks checked, the boundary kept."""

import json
from pathlib import Path

import pytest

from tradingbot.api import ReplayOut
from tradingbot.candles import Candle
from tradingbot.detectors import FloorDetector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY
from tradingbot.re_score import RecordedRun, Refused, first_difference, re_score
from tradingbot.replay import run
from tradingbot.turning_points import Kind

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z


def test_the_first_difference_is_the_first_mark_the_lists_disagree_on() -> None:
    same = [(Kind.TOP, T0), (Kind.BOTTOM, T0 + H)]

    assert first_difference(same + [(Kind.TOP, T0 + 5 * H)], same) == T0 + 5 * H
    assert first_difference(same, same + [(Kind.TOP, T0 + 7 * H)]) == T0 + 7 * H
    assert first_difference(same[:1] + [(Kind.TOP, T0 + H)], same) == T0 + H
    assert first_difference(same[:1] + [(Kind.BOTTOM, T0 + 2 * H)], same) == T0 + 2 * H


def swing(path: Path) -> Path:
    """A recorded floor run over a 10% rise and fall straddling the boundary, written as
    `replay` writes it but with every candle kept, the out-of-sample ones included."""
    prices = [100.0] * 30 + [100.0 + h for h in range(1, 11)] + [110.0 - h for h in range(1, 11)]
    candles = [
        Candle(OUT_OF_SAMPLE_BOUNDARY + (i - 40) * H, p, p + 0.5, p - 0.5, p, 1.0, 1)
        for i, p in enumerate(prices)
    ]
    recorded = path / "replay-floor.json"
    recorded.write_text(ReplayOut.of(run(candles, FloorDetector())).model_dump_json())
    return recorded


def test_a_recorded_run_is_read_within_the_development_period(tmp_path: Path) -> None:
    recorded = RecordedRun.read(swing(tmp_path))

    assert recorded.detector == "floor"
    assert recorded.candles[-1].time == OUT_OF_SAMPLE_BOUNDARY - H
    assert len(recorded.candles) == 40


def test_re_scoring_replays_the_recorded_candles_and_keeps_the_marks(tmp_path: Path) -> None:
    path = swing(tmp_path)
    data = json.loads(path.read_text())
    data["marks"] = [m for m in data["marks"] if m["time"] < OUT_OF_SAMPLE_BOUNDARY]
    path.write_text(json.dumps(data))
    recorded = RecordedRun.read(path)

    scored = re_score(recorded, FloorDetector(), path)

    assert scored.marks == len(recorded.marks) > 0
    assert scored.result.candles == recorded.candles


def test_re_scoring_refuses_another_detectors_run(tmp_path: Path) -> None:
    path = swing(tmp_path)

    with pytest.raises(Refused, match="floor"):
        re_score(RecordedRun.read(path), _named("one"), path)


def _named(name: str):
    from tradingbot.detectors import DETECTORS

    return DETECTORS[name]()
