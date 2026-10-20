"""Re-scoring a recorded run under the current definitions (ADR-0004).

A recorded run is the chart data a replay wrote: every candle the detector
read and every mark it placed. When the harness changes, the run is scored
again, never re-run on today's store: its own candles are replayed through the
detector, which reproduces its marks whatever the store holds now, and the
re-scoring refuses unless those marks are identical in number and time to the
recorded ones. The three family-one runs recorded before slice 5 hold the
three prints that ADR-0005 dropped, so a fresh run on the cleaned store would
not reproduce the floor's or detector one's marks; their own candles do.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tradingbot.candles import Candle, iso
from tradingbot.detectors import Detector
from tradingbot.development import development_end
from tradingbot.replay import ReplayResult, replay_all, score_replayed
from tradingbot.scoring import SCORING_START
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

    @classmethod
    def read(cls, path: Path) -> RecordedRun:
        data = json.loads(path.read_text())
        last = development_end(None)
        return cls(
            data["detector"],
            [c for c in (Candle(**row) for row in data["candles"]) if c.time <= last],
            [(Kind(m["kind"]), m["time"]) for m in data["marks"]],
        )


@dataclass(frozen=True)
class ReScored:
    marks: int
    """Marks the run placed, over the whole replay."""
    result: ReplayResult


def first_difference(fresh: list[tuple[Kind, int]], recorded: list[tuple[Kind, int]]) -> int:
    """The time of the first mark the two lists disagree on; they must differ."""
    for ours, theirs in zip(fresh, recorded, strict=False):
        if ours != theirs:
            return ours[1]
    longer = fresh if len(fresh) > len(recorded) else recorded
    return longer[min(len(fresh), len(recorded))][1]


def re_score(recorded: RecordedRun, detector: Detector, path: Path) -> ReScored:
    """Replay the recorded run's candles through the detector and score them over the
    scoring period; `path` names the file in the messages.

    Raises `Refused` when the file records another detector's run or when the
    marks are not identical to the recorded ones.
    """
    if recorded.detector != detector.name:
        raise Refused(f"{path} records a run of {recorded.detector!r}, not of {detector.name!r}.")
    replayed = replay_all(recorded.candles, detector)
    fresh = [(m.kind, m.time) for m in replayed.marks]
    if fresh != recorded.marks:
        raise Refused(
            f"The fresh replay of {detector.name} placed {len(fresh)} marks where {path} records "
            f"{len(recorded.marks)}; the first difference is at "
            f"{iso(first_difference(fresh, recorded.marks))}. The run is not the recorded one, "
            "so nothing is reported."
        )
    return ReScored(len(fresh), score_replayed(replayed, score_from=SCORING_START))
