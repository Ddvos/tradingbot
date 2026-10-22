"""The out-of-sample check: the one explicit way to read past the boundary.

`check` replays the whole stored history of the detector's timeframe through
it, so the detector carries every level it would have across the boundary, and
scores only the candles from the boundary on, as a series of their own (`run`
with `score_from`) and without eras, which belong to the scoring period. With
a strategy, the flip for a detector of family three (ADR-0009), it then walks
that strategy over the replay from the boundary on: the account starts flat
with 500 USD at the boundary's first candle, the benchmark buys there with one
spot fill, and the bar is growth at least the benchmark's over the period as
one under the perpetual cost model. Every use is appended to a log, one line
per run holding the detector's score and, with a strategy, the strategy's,
and a detector already in the log is refused in either form: the protocol
gives each detector one out-of-sample run (#12). Nothing here is reachable
from the API or the dashboard, which only ever read the development period.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tradingbot.backtest import (
    BacktestResult,
    backtest,
    describe_strategy_score,
    describe_verdict,
)
from tradingbot.candles import iso
from tradingbot.detectors import Detector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY
from tradingbot.replay import ReplayResult, run
from tradingbot.scoring import Score, describe_score
from tradingbot.store import CandleStore
from tradingbot.strategies import Strategy

DEFAULT_LOG = "out-of-sample.log"
"""In the working directory, like every path the command takes: the repository
root when run as documented, so every run is committed with the code."""


class Refused(Exception):
    """The check did not run; the message says why."""


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One line of the log, tab-separated: when the run happened, the detector, the period,
    the detector's score and, since slice 10, the strategy's score when one was walked."""

    when: str
    detector: str
    period: str
    score: str
    strategy: str | None = None
    """The strategy's name and score over the period, with the bar read out; None for a
    run without a strategy, as every line before slice 10 is."""

    def line(self) -> str:
        fields = [self.when, self.detector, self.period, self.score]
        if self.strategy is not None:
            fields.append(self.strategy)
        return "\t".join(fields)

    @classmethod
    def parse(cls, line: str) -> LogEntry:
        fields = line.split("\t")
        if len(fields) not in (4, 5):
            raise ValueError(
                f"a log line has four or five tab-separated fields, not {len(fields)}: {line!r}"
            )
        when, detector, period, score = fields[:4]
        return cls(when, detector, period, score, fields[4] if len(fields) == 5 else None)


def summarize(score: Score, reversal: float) -> str:
    """The score on one line, for the log."""
    return ", ".join(f"{label} {value}" for label, value in describe_score(score, reversal))


def summarize_backtest(result: BacktestResult) -> str:
    """The strategy's score under each cost model and the bar on one line, for the log."""
    models = "; ".join(
        f"under the {scored.model} cost model: "
        + ", ".join(f"{label} {value}" for label, value in describe_strategy_score(scored.score))
        for scored in result.scores
    )
    label, value = describe_verdict(result)
    return f"{result.strategy}: {models}; {label} {value}"


def logged_detectors(log: Path) -> list[str]:
    """The detectors that already had their out-of-sample run, in log order."""
    if not log.exists():
        return []
    return [LogEntry.parse(line).detector for line in log.read_text().splitlines() if line]


@dataclass(frozen=True)
class Checked:
    """What the check produced: the replay scored from the boundary on, and the strategy's
    backtest over it when one was asked for."""

    replay: ReplayResult
    backtest: BacktestResult | None


def check(
    store: CandleStore, detector: Detector, log: Path, now: int, strategy: Strategy | None = None
) -> Checked:
    """Replay everything, score from the boundary on, walk the strategy if given, and log
    the run.

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
    tested = None if strategy is None else backtest(result, strategy, eras=())
    scored = result.scored_candles
    entry = LogEntry(
        when=iso(now),
        detector=detector.name,
        period=f"{len(scored)} candles from {iso(scored[0].time)} to {iso(scored[-1].time)}",
        score=summarize(result.score, result.reversal),
        strategy=None if tested is None else summarize_backtest(tested),
    )
    with log.open("a") as f:
        f.write(entry.line() + "\n")
    return Checked(result, tested)
