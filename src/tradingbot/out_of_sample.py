"""The out-of-sample check: the one explicit way to read past the boundary.

`check` replays the whole stored history of the detector's timeframe through
it, so the detector carries every level it would have across the boundary, and
scores only the candles from the boundary on, as a series of their own (`run`
with `score_from`) and without eras, which belong to the scoring period. Every
use is appended to a log, one line per run, and a detector already in the log
is refused: the protocol gives each detector one out-of-sample run (#12).
Nothing here is reachable from the API or the dashboard, which only ever read
the development period.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tradingbot.candles import iso
from tradingbot.detectors import Detector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY
from tradingbot.replay import ReplayResult, run
from tradingbot.scoring import Score, describe_score
from tradingbot.store import CandleStore

DEFAULT_LOG = "out-of-sample.log"
"""In the working directory, like every path the command takes: the repository
root when run as documented, so every run is committed with the code."""


class Refused(Exception):
    """The check did not run; the message says why."""


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One line of the log: when the run happened, the detector, the period and the score."""

    when: str
    detector: str
    period: str
    score: str

    def line(self) -> str:
        return "\t".join([self.when, self.detector, self.period, self.score])

    @classmethod
    def parse(cls, line: str) -> LogEntry:
        when, detector, period, score = line.split("\t")
        return cls(when, detector, period, score)


def summarize(score: Score) -> str:
    """The score on one line, for the log."""
    return ", ".join(f"{label} {value}" for label, value in describe_score(score))


def logged_detectors(log: Path) -> list[str]:
    """The detectors that already had their out-of-sample run, in log order."""
    if not log.exists():
        return []
    return [LogEntry.parse(line).detector for line in log.read_text().splitlines() if line]


def check(store: CandleStore, detector: Detector, log: Path, now: int) -> ReplayResult:
    """Replay everything, score from the boundary on, and log the run.

    `store` holds the candles of the detector's timeframe. Raises `Refused` when
    the detector is already in the log or when the store ends before the
    boundary; nothing is written then.
    """
    if detector.name in logged_detectors(log):
        raise Refused(
            f"Detector {detector.name!r} already had its out-of-sample run; the protocol allows "
            f"one. See {log}."
        )
    candles = store.read()
    if not candles or candles[-1].time < OUT_OF_SAMPLE_BOUNDARY:
        raise Refused(
            "The store holds no candles out of sample, which starts at "
            f"{iso(OUT_OF_SAMPLE_BOUNDARY)}. Import a quarterly archive or catch up first."
        )
    result = run(candles, detector, score_from=OUT_OF_SAMPLE_BOUNDARY, eras=())
    scored = result.scored_candles
    entry = LogEntry(
        when=iso(now),
        detector=detector.name,
        period=f"{len(scored)} candles from {iso(scored[0].time)} to {iso(scored[-1].time)}",
        score=summarize(result.score),
    )
    with log.open("a") as f:
        f.write(entry.line() + "\n")
    return result
