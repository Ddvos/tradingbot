"""The out-of-sample check logs every run on one line, and reads its own lines back; with
the flip it walks the account from the boundary's first candle (ADR-0009)."""

from pathlib import Path

import pytest

from tradingbot.candles import Candle
from tradingbot.detectors import FloorDetector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY
from tradingbot.out_of_sample import LogEntry, Refused, check, logged_detectors
from tradingbot.store import CandleStore
from tradingbot.strategies import Flip

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

    checked = check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, now=1_760_000_000)

    result = checked.replay
    assert checked.backtest is None
    assert result.scored_from == OUT_OF_SAMPLE_BOUNDARY
    assert result.scored_candles[0].time == OUT_OF_SAMPLE_BOUNDARY
    assert result.candles[0].time < OUT_OF_SAMPLE_BOUNDARY, "the whole run is recorded"
    entry = LogEntry.parse(log.read_text().splitlines()[0])
    assert entry.when == "2025-10-09T08:53:20Z"
    assert entry.detector == "floor"
    assert entry.period == "20 candles from 2025-01-01T00:00:00Z to 2025-01-01T19:00:00Z"
    assert entry.score.startswith("reversal size 8%, turning points ")
    assert "hit rate" in entry.score and "median give-up" in entry.score
    assert "false marks/hit" in entry.score
    assert "2022-2024" not in entry.score, "an out-of-sample score has no eras"
    assert entry.strategy is None
    assert result.score.eras == ()
    assert logged_detectors(log) == ["floor"]


def test_with_the_flip_the_account_starts_at_the_boundarys_first_candle_and_the_bar_is_the_period(
    tmp_path: Path,
) -> None:
    log = tmp_path / "out-of-sample.log"

    checked = check(
        store_with_a_swing_past_the_boundary(), FloorDetector(), log, 1_760_000_000, Flip()
    )

    tested = checked.backtest
    assert tested is not None
    assert tested.scored_from == OUT_OF_SAMPLE_BOUNDARY
    assert tested.values.times[0] == OUT_OF_SAMPLE_BOUNDARY
    # Flat until a bottom mark: 500 USD at the first close. The benchmark bought 500 USD of
    # Bitcoin at the boundary candle's open of 101, the first candle of the rise, with one
    # spot fill (x 1.0005, 0.80% fee) and is valued at that candle's close of 101.
    assert tested.values.accounts["perpetual"][0] == 500.0
    assert tested.values.benchmark[0] == pytest.approx(500 / (1.0005 * 1.008))
    # Judged over the period as one, with no eras: the floor's bottom mark on the close of
    # 103 (3.5% above the lowest low of 99.5) puts the flip long at 104's open, its top mark
    # on the close of 107 (3.2% below the highest high of 110.5) flat at 106's open: +1.82%
    # gross, +1.7% after the perpetual's two fees of 0.05%; holding from 101 to the period's
    # last close of 100 lost 1% and its fee.
    spot, perpetual = (s.score for s in tested.scores)
    assert perpetual.eras == () and spot.eras == ()
    assert perpetual.trades == 1
    assert perpetual.growth == pytest.approx(1.017, abs=0.001)
    assert perpetual.benchmark_growth == pytest.approx(100 / 101 / (1.0005 * 1.008))
    assert tested.passes is True


def test_with_the_flip_the_log_line_holds_the_detectors_score_and_the_strategys(
    tmp_path: Path,
) -> None:
    log = tmp_path / "out-of-sample.log"

    check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, 1_760_000_000, Flip())

    lines = log.read_text().splitlines()
    assert len(lines) == 1
    entry = LogEntry.parse(lines[0])
    assert entry.detector == "floor"
    assert entry.score.startswith("reversal size 8%, turning points ")
    assert entry.strategy is not None
    assert entry.strategy.startswith("flip")
    assert "under the spot cost model" in entry.strategy
    assert "under the perpetual cost model" in entry.strategy
    assert "growth" in entry.strategy and "trades 1" in entry.strategy
    assert "bar (ADR-0009)" in entry.strategy and ": pass (" in entry.strategy
    assert logged_detectors(log) == ["floor"]


def test_a_logged_detector_is_refused_in_both_forms(tmp_path: Path) -> None:
    log = tmp_path / "out-of-sample.log"
    check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, 1_760_000_000)
    logged = log.read_text()

    with pytest.raises(Refused, match="floor"):
        check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, 1_760_000_001, Flip())
    with pytest.raises(Refused, match="floor"):
        check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, 1_760_000_002)

    assert log.read_text() == logged


def test_a_detector_checked_with_the_flip_is_refused_without_it_afterwards(tmp_path: Path) -> None:
    log = tmp_path / "out-of-sample.log"
    check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, 1_760_000_000, Flip())

    with pytest.raises(Refused, match="already"):
        check(store_with_a_swing_past_the_boundary(), FloorDetector(), log, 1_760_000_001)


def test_the_log_reads_lines_written_before_slice_10_too() -> None:
    old = (
        "2026-10-20T19:47:32Z\tthree\t68296 candles from 2024-10-19T00:00:00Z to "
        "2026-09-30T23:45:00Z\tturning points 66, marks 752"
    )

    entry = LogEntry.parse(old)

    assert (entry.detector, entry.strategy) == ("three", None)
    assert entry.line() == old
