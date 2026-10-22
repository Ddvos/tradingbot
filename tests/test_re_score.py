"""Re-scoring a recorded run: its own candles replayed, its marks checked, the boundary kept."""

import json
from pathlib import Path

import pytest

from tradingbot.api import ReplayOut
from tradingbot.candles import Candle, iso
from tradingbot.detectors import FloorDetector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY
from tradingbot.re_score import RecordedRun, Refused, first_difference, re_score
from tradingbot.replay import run
from tradingbot.scoring import describe_score
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

    scored = re_score(recorded, FloorDetector())

    assert scored.marks == len(recorded.marks) > 0
    assert scored.result.candles == recorded.candles


RECORDED_THREE = Path(__file__).resolve().parents[1] / "data" / "replay-three.json"
"""The recorded run of detector three (#20), kept out of git like all of `data/`; found from
the repository root whatever the working directory, so the test skips only when it is absent."""


@pytest.mark.skipif(not RECORDED_THREE.exists(), reason=f"{RECORDED_THREE} is not on disk")
def test_the_recorded_run_of_detector_three_scores_six_and_a_half_false_marks_per_hit() -> None:
    # The development run on #20: 719 hits and 4,698 false marks over the scoring period.
    scored = re_score(RecordedRun.read(RECORDED_THREE), _named("three"))

    assert (scored.result.score.hits, scored.result.score.false_marks) == (719, 4698)
    assert round(scored.result.score.false_marks_per_hit, 1) == 6.5
    assert ("false marks/hit", "6.5 per hit") in describe_score(scored.result.score, reversal=0.08)


RECORDED_HOURLY = {
    "floor": (259, 2921),
    "one": (313, 6049),
    "two": (135, 1522),
}
"""Hits and false marks over the scoring period of the three family-one runs, as re-scored
under ADR-0007 on #11, #12 and #16; unchanged by slice 10, since nothing in their
definitions changed (ADR-0009)."""


@pytest.mark.parametrize(("name", "expected"), sorted(RECORDED_HOURLY.items()))
def test_the_recorded_hourly_runs_re_score_to_their_recorded_numbers(
    name: str, expected: tuple[int, int]
) -> None:
    recorded = RECORDED_THREE.with_name(f"replay-{name}.json")
    if not recorded.exists():
        pytest.skip(f"{recorded} is not on disk")

    scored = re_score(RecordedRun.read(recorded), _named(name))

    assert (scored.result.score.hits, scored.result.score.false_marks) == expected
    assert scored.result.score.turning_points == 798
    assert scored.result.reversal == 0.08


def test_re_scoring_refuses_another_detectors_run(tmp_path: Path) -> None:
    path = swing(tmp_path)

    with pytest.raises(Refused, match="floor"):
        re_score(RecordedRun.read(path), _named("one"))


def _named(name: str):
    from tradingbot.detectors import DETECTORS

    return DETECTORS[name]()


# --- backtests -----------------------------------------------------------------------


def floor_flip(path: Path) -> tuple[Path, Path]:
    """A recorded floor run over a seeded walk and the flip's recorded backtest on it, written
    as `replay` and `backtest` write them."""
    from tests.walks import random_walk
    from tradingbot.api import BacktestOut
    from tradingbot.backtest import backtest
    from tradingbot.scoring import SCORING_START
    from tradingbot.strategies import Flip

    candles = random_walk(hours=2000, seed=7)
    result = run(candles, FloorDetector(), score_from=SCORING_START)
    recorded = path / "replay-floor.json"
    recorded.write_text(ReplayOut.of(result).model_dump_json())
    recorded_backtest = path / "backtest-flip.json"
    recorded_backtest.write_text(BacktestOut.of(backtest(result, Flip())).model_dump_json())
    return recorded, recorded_backtest


def test_a_recorded_backtest_is_read_with_its_fills(tmp_path: Path) -> None:
    from tradingbot.backtest import Side
    from tradingbot.re_score import RecordedBacktest

    _, recorded_backtest = floor_flip(tmp_path)

    recorded = RecordedBacktest.read(recorded_backtest)

    assert (recorded.detector, recorded.strategy) == ("floor", "flip")
    assert len(recorded.fills) > 10
    assert recorded.fills[0][0] is Side.BUY
    assert [side for side, _ in recorded.fills[:4]] == [Side.BUY, Side.SELL] * 2


def test_re_scoring_a_backtest_reproduces_the_recorded_fills_and_the_score(
    tmp_path: Path,
) -> None:
    from tradingbot.re_score import RecordedBacktest, re_score_backtest
    from tradingbot.strategies import Flip

    recorded, recorded_backtest = floor_flip(tmp_path)
    expected = json.loads(recorded_backtest.read_text())

    scored = re_score_backtest(
        RecordedRun.read(recorded),
        RecordedBacktest.read(recorded_backtest),
        FloorDetector(),
        Flip(),
    )

    assert scored.fills == len(expected["fills"]) > 10
    assert scored.replay.marks == len(json.loads(recorded.read_text())["marks"]) > 0
    assert [s.score.growth for s in scored.result.scores] == [
        s["score"]["growth"] for s in expected["scores"]
    ]
    assert scored.result.passes == expected["passes"]


def test_re_scoring_a_backtest_refuses_when_the_fills_differ(tmp_path: Path) -> None:
    from tradingbot.re_score import RecordedBacktest, re_score_backtest
    from tradingbot.strategies import Flip

    recorded, recorded_backtest = floor_flip(tmp_path)
    data = json.loads(recorded_backtest.read_text())
    dropped = data["fills"].pop(2)
    recorded_backtest.write_text(json.dumps(data))

    with pytest.raises(Refused) as refused:
        re_score_backtest(
            RecordedRun.read(recorded),
            RecordedBacktest.read(recorded_backtest),
            FloorDetector(),
            Flip(),
        )

    message = str(refused.value)
    assert f"{len(data['fills']) + 1} fills" in message and f"{len(data['fills'])}" in message
    assert iso(dropped["time"]) in message and "backtest-flip.json" in message


def test_re_scoring_a_backtest_refuses_another_strategys_or_detectors_file(tmp_path: Path) -> None:
    from tradingbot.re_score import RecordedBacktest, re_score_backtest
    from tradingbot.strategies import Flip

    recorded, recorded_backtest = floor_flip(tmp_path)
    data = json.loads(recorded_backtest.read_text())
    data["strategy"] = "undo"
    recorded_backtest.write_text(json.dumps(data))

    with pytest.raises(Refused, match="undo"):
        re_score_backtest(
            RecordedRun.read(recorded),
            RecordedBacktest.read(recorded_backtest),
            FloorDetector(),
            Flip(),
        )

    data["strategy"], data["detector"] = "flip", "one"
    recorded_backtest.write_text(json.dumps(data))
    with pytest.raises(Refused, match="one"):
        re_score_backtest(
            RecordedRun.read(recorded),
            RecordedBacktest.read(recorded_backtest),
            FloorDetector(),
            Flip(),
        )


def test_check_marks_refuses_a_fresh_replay_whose_marks_differ_from_the_recorded_run(
    tmp_path: Path,
) -> None:
    from tradingbot.re_score import check_marks
    from tradingbot.replay import replay_all

    recorded, _ = floor_flip(tmp_path)
    run_ = RecordedRun.read(recorded)
    replayed = replay_all(run_.candles, FloorDetector())
    check_marks(replayed, run_, FloorDetector())  # identical: nothing happens

    shorter = replay_all(run_.candles[:-200], FloorDetector())
    with pytest.raises(Refused, match="replay-floor.json"):
        check_marks(shorter, run_, FloorDetector())


RECORDED_FLIP = Path(__file__).resolve().parents[1] / "data" / "backtest-flip.json"
"""The flip's recorded backtest on detector three's recorded run (#32), kept out of git like
all of `data/`; the test skips when either file is absent."""


@pytest.mark.skipif(
    not (RECORDED_THREE.exists() and RECORDED_FLIP.exists()),
    reason=f"{RECORDED_THREE} or {RECORDED_FLIP} is not on disk",
)
def test_the_recorded_backtest_of_the_flip_is_reproduced_with_its_score() -> None:
    from tradingbot.re_score import RecordedBacktest, re_score_backtest
    from tradingbot.strategies import Flip

    # The one run on #32: 868 fills, 434 round trips, x0.00174 under spot and x0.82 under the
    # perpetual against the benchmark's x156; 21, 85, 54 and 274 trades in the four groups.
    scored = re_score_backtest(
        RecordedRun.read(RECORDED_THREE),
        RecordedBacktest.read(RECORDED_FLIP),
        _named("three"),
        Flip(),
    )

    assert scored.fills == 868
    spot, perpetual = (s.score for s in scored.result.scores)
    assert (spot.trades, perpetual.trades) == (434, 434)
    assert spot.growth == pytest.approx(0.00174, rel=0.01)
    assert perpetual.growth == pytest.approx(0.82, abs=0.005)
    assert spot.benchmark_growth == pytest.approx(156, abs=0.5)
    assert [g.trades for g in spot.groups] == [21, 85, 54, 274]
    assert scored.result.passes is False
    recorded = json.loads(RECORDED_FLIP.read_text())
    assert [s.score.growth for s in scored.result.scores] == [
        s["score"]["growth"] for s in recorded["scores"]
    ]
    assert [s.score.funding for s in scored.result.scores] == [
        s["score"]["funding"] for s in recorded["scores"]
    ]
