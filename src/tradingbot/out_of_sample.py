"""The out-of-sample check: the one explicit way to read past the boundary.

`check` replays the whole stored history through a detector, so the detector
carries every level it would have across the boundary, and scores only the
candles from the boundary on, as a series of their own (`run` with
`score_from`). Every use is appended to a log, one line per run, and a
detector already in the log is refused: the protocol gives each detector one
out-of-sample run (#12). Nothing here is reachable from the API or the
dashboard, which only ever read the development period.
"""

from __future__ import annotations

from pathlib import Path

from tradingbot.candles import iso
from tradingbot.detectors import Detector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY
from tradingbot.replay import ReplayResult, run
from tradingbot.scoring import Score
from tradingbot.store import CandleStore

DEFAULT_LOG = "out-of-sample.log"
"""Next to the code rather than the data, so every run is committed with the repository."""


class Refused(Exception):
    """The check did not run; the message says why."""


def summarize(score: Score) -> str:
    """The score on one line, for the log."""
    if score.median_timing is None or score.median_give_up is None:
        timing = give_up = "n/a"
    else:
        timing = f"{score.median_timing:+.1f} candles"
        give_up = f"{score.median_give_up:.2f}%"
    return (
        f"turning points {score.turning_points}, marks {score.marks}, "
        f"hits {score.hits} (hit rate {score.hit_rate:.1%}), "
        f"false marks {score.false_marks} (false-mark rate {score.false_mark_rate:.1%}), "
        f"median timing {timing}, median give-up {give_up}"
    )


def logged_detectors(log: Path) -> list[str]:
    """The detectors that already had their out-of-sample run, in log order."""
    if not log.exists():
        return []
    return [line.split("\t")[1] for line in log.read_text().splitlines() if "\t" in line]


def check(store: CandleStore, detector: Detector, log: Path, now: int) -> ReplayResult:
    """Replay everything, score from the boundary on, and log the run.

    Raises `Refused` when the detector is already in the log or when the store
    ends before the boundary; nothing is written then.
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
    result = run(candles, detector, score_from=OUT_OF_SAMPLE_BOUNDARY)
    first, last = result.candles[0].time, result.candles[-1].time
    line = "\t".join(
        [
            iso(now),
            detector.name,
            f"{len(result.candles)} candles from {iso(first)} to {iso(last)}",
            summarize(result.score),
        ]
    )
    with log.open("a") as f:
        f.write(line + "\n")
    return result
