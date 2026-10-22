"""Re-scoring a recorded run under the current definitions (ADR-0004).

A recorded run is the chart data a replay wrote: every candle the detector
read and every mark it placed. When the harness changes, the run is scored
again, never re-run on today's store: its own candles are replayed through the
detector, which reproduces its marks whatever the store holds now, and the
re-scoring refuses unless those marks are identical in number and time to the
recorded ones. The three family-one runs recorded before slice 5 hold the
three prints that ADR-0005 dropped, so a fresh run on the cleaned store would
not reproduce the floor's or detector one's marks; their own candles do.

A recorded backtest is the chart data `backtest` wrote on top of a recorded
run: every fill the strategy caused. It is re-scored the same way: the run's
own candles replayed and its marks checked, then the strategy walked again,
and the re-scoring refuses unless the fills are identical in number and time
to the recorded ones; the score is then printed under the current cost
models (ADR-0008).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tradingbot.backtest import BacktestResult, Side, backtest
from tradingbot.candles import Candle, iso
from tradingbot.detectors import Detector
from tradingbot.development import development_end
from tradingbot.replay import Replayed, ReplayResult, replay_all, score_replayed
from tradingbot.scoring import SCORING_START
from tradingbot.strategies import Strategy
from tradingbot.turning_points import Kind


class Refused(Exception):
    """The re-scoring did not report; the message says why."""


@dataclass(frozen=True)
class RecordedRun:
    detector: str
    candles: list[Candle]
    """Every candle the run read, within the development period."""
    marks: list[tuple[Kind, int]]
    """Kind and time of every mark the run placed, oldest first."""
    path: Path
    """The file it was read from, named in the messages."""

    @classmethod
    def read(cls, path: Path) -> RecordedRun:
        data = json.loads(path.read_text())
        last = development_end(None)
        return cls(
            data["detector"],
            [c for c in (Candle(**row) for row in data["candles"]) if c.time <= last],
            [(Kind(m["kind"]), m["time"]) for m in data["marks"]],
            path,
        )


@dataclass(frozen=True)
class ReScored:
    marks: int
    """Marks the run placed, over the whole replay."""
    result: ReplayResult


def first_difference(
    fresh: Sequence[tuple[object, int]], recorded: Sequence[tuple[object, int]]
) -> int:
    """The time of the first mark (or fill) the two lists disagree on; they must differ."""
    for ours, theirs in zip(fresh, recorded, strict=False):
        if ours != theirs:
            return ours[1]
    longer = fresh if len(fresh) > len(recorded) else recorded
    return longer[min(len(fresh), len(recorded))][1]


def check_marks(replayed: Replayed, recorded: RecordedRun, detector: Detector) -> None:
    """Raise `Refused` unless the replay's marks are identical in number and time to the
    recorded run's, or when the file records another detector's run."""
    path = recorded.path
    if recorded.detector != detector.name:
        raise Refused(f"{path} records a run of {recorded.detector!r}, not of {detector.name!r}.")
    fresh = [(m.kind, m.time) for m in replayed.marks]
    if fresh != recorded.marks:
        raise Refused(
            f"The fresh replay of {detector.name} placed {len(fresh)} marks where {path} records "
            f"{len(recorded.marks)}; the first difference is at "
            f"{iso(first_difference(fresh, recorded.marks))}. The run is not the recorded one, "
            "so nothing is reported."
        )


def re_score(recorded: RecordedRun, detector: Detector) -> ReScored:
    """Replay the recorded run's candles through the detector and score them over the
    scoring period.

    Raises `Refused` when the file records another detector's run or when the
    marks are not identical to the recorded ones.
    """
    replayed = replay_all(recorded.candles, detector)
    check_marks(replayed, recorded, detector)
    return ReScored(len(replayed.marks), score_replayed(replayed, score_from=SCORING_START))


@dataclass(frozen=True)
class RecordedBacktest:
    detector: str
    strategy: str
    fills: list[tuple[Side, int]]
    """Side and time of every fill the backtest recorded, oldest first."""
    path: Path
    """The file it was read from, named in the messages."""

    @classmethod
    def read(cls, path: Path) -> RecordedBacktest:
        data = json.loads(path.read_text())
        return cls(
            data["detector"],
            data["strategy"],
            [(Side(f["side"]), f["time"]) for f in data["fills"]],
            path,
        )


@dataclass(frozen=True)
class ReScoredBacktest:
    fills: int
    """Fills the backtest made."""
    replay: ReScored
    """The recorded run re-scored: the detector's side."""
    result: BacktestResult


def re_score_backtest(
    recorded_run: RecordedRun,
    recorded: RecordedBacktest,
    detector: Detector,
    strategy: Strategy,
) -> ReScoredBacktest:
    """Re-score the recorded run, walk the strategy over it again and score that under the
    current cost models.

    Raises `Refused` when either file records another detector's or strategy's
    run, when the marks differ from the recorded run's, or when the fills
    differ from the recorded backtest's.
    """
    path = recorded.path
    if recorded.strategy != strategy.name:
        raise Refused(
            f"{path} records a backtest of {recorded.strategy!r}, not of {strategy.name!r}."
        )
    if recorded.detector != detector.name:
        raise Refused(
            f"{path} records a backtest on {recorded.detector!r}, not on {detector.name!r}."
        )
    scored = re_score(recorded_run, detector)
    result = backtest(scored.result, strategy)
    fresh = [(f.side, f.time) for f in result.fills]
    if fresh != recorded.fills:
        raise Refused(
            f"The fresh backtest of {strategy.name} on {detector.name} made {len(fresh)} fills "
            f"where {path} records {len(recorded.fills)}; the first difference is at "
            f"{iso(first_difference(fresh, recorded.fills))}. The backtest is not the recorded "
            "one, so nothing is reported."
        )
    return ReScoredBacktest(len(fresh), scored, result)
