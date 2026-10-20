"""The out-of-sample check logs every run on one line, and reads its own lines back."""

from pathlib import Path

from tradingbot.candles import Candle
from tradingbot.detectors import FloorDetector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY
from tradingbot.out_of_sample import LogEntry, check, logged_detectors
from tradingbot.store import CandleStore

H = 3600


def store_with_a_swing_past_the_boundary() -> CandleStore:
    """Flat before the boundary, then a 10% rise and fall: one top for the floor to find."""
    store = CandleStore(":memory:")
    prices = [100.0] * 30 + [100.0 + h for h in range(1, 11)] + [110.0 - h for h in range(1, 11)]
    store.upsert(
        Candle(OUT_OF_SAMPLE_BOUNDARY + (i - 30) * H, p, p + 0.5, p - 0.5, p, 1.0, 1)
        for i, p in enumerate(prices)
    )
    return store


def test_a_run_is_logged_with_its_time_detector_period_and_score(tmp_path: Path) -> None:
    log = tmp_path / "out-of-sample.log"

    result = check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, now=1_760_000_000)

    assert result.scored_from == OUT_OF_SAMPLE_BOUNDARY
    assert result.scored_candles[0].time == OUT_OF_SAMPLE_BOUNDARY
    assert result.candles[0].time < OUT_OF_SAMPLE_BOUNDARY, "the whole run is recorded"
    entry = LogEntry.parse(log.read_text().splitlines()[0])
    assert entry.when == "2025-10-09T08:53:20Z"
    assert entry.detector == "floor"
    assert entry.period == "20 candles from 2024-10-19T00:00:00Z to 2024-10-19T19:00:00Z"
    assert entry.score.startswith("turning points ")
    assert "hit rate" in entry.score and "median give-up" in entry.score
    assert "false marks/hit" in entry.score
    assert "2022-2024" not in entry.score, "an out-of-sample score has no eras"
    assert result.score.eras == ()
    assert logged_detectors(log) == ["floor"]
