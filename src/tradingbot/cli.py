"""The `tradingbot` command: import the archive, catch up, serve the API, replay a detector,
re-score a recorded run (and a recorded backtest on it), check the hourly candles built from
the fifteen-minute ones, run the one out-of-sample check, backtest a strategy."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from tradingbot import out_of_sample, re_score
from tradingbot.backtest import (
    COST_MODELS_ADR,
    BacktestResult,
    backtest,
    describe_strategy_score,
    describe_verdict,
)
from tradingbot.candles import Candle, Timeframe, iso
from tradingbot.detectors import DETECTORS, Detector, DetectorThree
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY, read_development
from tradingbot.hourly_check import check_hourly
from tradingbot.kraken import REST_REACH, KrakenSpot
from tradingbot.replay import ReplayResult, replay_all, run, score_replayed
from tradingbot.scoring import HARNESS_ADR, SCORING_START, describe_score
from tradingbot.store import STORED_TIMEFRAMES, CandleStore
from tradingbot.strategies import STRATEGIES, Strategy
from tradingbot.sync import catch_up, import_archive

DEFAULT_DB = "data/candles.sqlite"


def describe(store: CandleStore) -> str:
    time_range = store.time_range()
    label = store.timeframe.label
    if time_range is None:
        return f"The store holds no {label} candles."
    first, last = time_range
    return f"The store holds {store.count()} {label} candles from {iso(first)} to {iso(last)}."


def run_import(db: Path, timeframe: Timeframe, files: list[Path]) -> None:
    with CandleStore(db, timeframe) as store:
        for path in files:
            result = import_archive(path, store)
            print(f"Imported {path.name}: {result.stored} new {timeframe.label} candles.")
        print(describe(store))


def run_catch_up(db: Path, timeframe: Timeframe) -> None:
    kraken = KrakenSpot()
    with CandleStore(db, timeframe) as store:
        result = catch_up(
            store, lambda since: kraken.candles(timeframe, since), now=int(time.time())
        )
        print(f"Caught up from Kraken: {result.stored} new {timeframe.label} candles.")
        if result.unreachable is not None:
            first, last = result.unreachable
            print(
                f"Warning: the {timeframe.label} candles from {iso(first)} to {iso(last)} are "
                f"missing. The endpoint reaches back only {REST_REACH} candles; import an "
                "archive that covers them."
            )
        print(describe(store))


def run_serve(db: Path, host: str, port: int) -> None:
    import uvicorn

    from tradingbot.api import create_app

    uvicorn.run(create_app(db), host=host, port=port)


def span(candles: list[Candle]) -> str:
    return f"{len(candles)} candles from {iso(candles[0].time)} to {iso(candles[-1].time)}"


def report(result: ReplayResult, period: str) -> str:
    """The score as the batch commands print it; `period` names what was scored."""
    heading = (
        f"Replayed {result.detector} over {span(result.candles)}, scored {period}: "
        f"{span(result.scored_candles)}."
    )
    lines = [
        f"  {label:<16} {value}" for label, value in describe_score(result.score, result.reversal)
    ]
    return "\n".join([heading, *lines])


def report_backtest(result: BacktestResult, replay: ReplayResult) -> str:
    """The strategy score as the batch commands print it, under each cost model."""
    scored = replay.scored_candles
    heading = (
        f"Backtested {result.strategy} on {result.detector} over {span(replay.candles)}, the "
        f"account from {iso(scored[0].time)}: {len(scored)} candles, {len(result.fills)} fills."
    )
    lines = [heading]
    for scored in result.scores:
        lines.append(f"  under the {scored.model} cost model")
        lines.extend(
            f"    {label:<16} {value}" for label, value in describe_strategy_score(scored.score)
        )
    label, value = describe_verdict(result)
    lines.append(f"  {label:<18} {value}")
    return "\n".join(lines)


def detector_named(name: str) -> Detector:
    build = DETECTORS.get(name)
    if build is None:
        sys.exit(f"Unknown detector {name!r}. Known detectors: {', '.join(DETECTORS)}.")
    return build()


def strategy_named(name: str) -> Strategy:
    build = STRATEGIES.get(name)
    if build is None:
        sys.exit(f"Unknown strategy {name!r}. Known strategies: {', '.join(STRATEGIES)}.")
    return build()


def read_development_candles(db: Path, detector: Detector) -> list[Candle]:
    """The development candles of the detector's timeframe, or exit when there are none."""
    with CandleStore(db, detector.timeframe) as store:
        candles = read_development(store)
    if not candles:
        sys.exit(
            f"The store holds no {detector.timeframe.label} candles in the development period, "
            f"which ends before {iso(OUT_OF_SAMPLE_BOUNDARY)}. Import an archive that covers it."
        )
    return candles


def write_chart_data(result: ReplayResult | BacktestResult, out: Path) -> None:
    from tradingbot.api import BacktestOut, ReplayOut

    chart = BacktestOut.of(result) if isinstance(result, BacktestResult) else ReplayOut.of(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(chart.model_dump_json())
    print(f"Wrote the chart data to {out}.")


def run_replay(db: Path, name: str, out: Path | None) -> None:
    detector = detector_named(name)
    out = out or db.parent / f"replay-{name}.json"
    if out.exists():
        sys.exit(
            f"{out} exists and holds a recorded run, which is never replaced (ADR-0004). "
            "Pass --out to write the chart data elsewhere."
        )
    candles = read_development_candles(db, detector)
    result = run(candles, detector, score_from=SCORING_START)
    if not result.scored_candles:
        sys.exit(
            f"No candle falls in the scoring period, which starts at {iso(SCORING_START)}; "
            "the development candles end before it."
        )
    print(report(result, "over the scoring period"))
    write_chart_data(result, out)


def run_re_score(
    db: Path,
    name: str,
    recorded: Path | None,
    strategy_name: str | None = None,
    recorded_backtest: Path | None = None,
) -> None:
    detector = detector_named(name)
    recorded = recorded or db.parent / f"replay-{name}.json"
    strategy = None if strategy_name is None else strategy_named(strategy_name)
    try:
        if strategy is None:
            scored = re_score.re_score(re_score.RecordedRun.read(recorded), detector)
            strategy_scored = None
        else:
            recorded_backtest = recorded_backtest or db.parent / f"backtest-{strategy.name}.json"
            strategy_scored = re_score.re_score_backtest(
                re_score.RecordedRun.read(recorded),
                re_score.RecordedBacktest.read(recorded_backtest),
                detector,
                strategy,
            )
            scored = strategy_scored.replay
    except re_score.Refused as refused:
        sys.exit(str(refused))
    print(
        f"Re-scored {name} under {HARNESS_ADR}: {scored.marks} marks, identical in number and "
        f"time to the recorded run in {recorded}."
    )
    print(report(scored.result, "over the scoring period"))
    if strategy_scored is not None:
        print(
            f"Re-scored {strategy_scored.result.strategy} under {COST_MODELS_ADR}: "
            f"{strategy_scored.fills} fills, identical in number and time to the recorded "
            f"backtest in {recorded_backtest}."
        )
        print(report_backtest(strategy_scored.result, scored.result))


def run_backtest(db: Path, name: str, recorded: Path | None, out: Path | None) -> None:
    """The strategy over detector three's replay of the store, checked against the recorded
    run of detector three: the marks must be the recorded ones (ADR-0004)."""
    strategy = strategy_named(name)
    detector = DetectorThree()
    out = out or db.parent / f"backtest-{name}.json"
    if out.exists():
        sys.exit(
            f"{out} exists and holds a recorded backtest, which is never replaced (ADR-0004). "
            "Pass --out to write the chart data elsewhere."
        )
    recorded = recorded or db.parent / f"replay-{detector.name}.json"
    if not recorded.exists():
        sys.exit(
            f"{recorded} does not exist: a backtest runs on the recorded run of detector "
            f"{detector.name}, whose marks it must reproduce. Run `replay {detector.name}` "
            "first, or pass --recorded."
        )
    candles = read_development_candles(db, detector)
    replayed = replay_all(candles, detector)
    try:
        re_score.check_marks(replayed, re_score.RecordedRun.read(recorded), detector)
    except re_score.Refused as refused:
        sys.exit(str(refused))
    result = score_replayed(replayed, score_from=SCORING_START)
    if not result.scored_candles:
        sys.exit(
            f"No candle falls in the scoring period, which starts at {iso(SCORING_START)}; "
            "the development candles end before it."
        )
    tested = backtest(result, strategy)
    print(report_backtest(tested, result))
    write_chart_data(tested, out)


def run_check_hourly(db: Path) -> None:
    with CandleStore(db, Timeframe.M15) as fifteen, CandleStore(db) as hourly:
        fifteen_minute = read_development(fifteen)
        stored = read_development(hourly)
    for candles, timeframe in ((fifteen_minute, Timeframe.M15), (stored, Timeframe.H1)):
        if not candles:
            sys.exit(
                f"The store holds no {timeframe.label} candles in the development period. "
                "Import the archive that holds them."
            )
    try:
        result = check_hourly(fifteen_minute, stored, SCORING_START)
    except ValueError:
        sys.exit(
            f"No hourly candle falls in the scoring period, which starts at {iso(SCORING_START)}; "
            "the development candles end before it."
        )
    print(
        f"Built {result.built} hourly candles from {result.fifteen_minute} 15-minute candles over "
        f"the scoring period, {iso(result.first)} to {iso(result.last)}; the hourly table holds "
        f"{result.stored}."
    )
    counted = [
        ("only in the 15-minute build", result.only_built),
        ("only in the hourly table", result.only_stored),
        ("differing hours", result.differing),
    ]
    for what, times in counted:
        first = f"  (first {iso(times[0])})" if times else ""
        print(f"  {what:<29} {len(times)}{first}")
    first_point = (
        f"  (first {iso(result.differing_points[0].time)})" if result.differing_points else ""
    )
    print(
        f"  {'turning points':<29} {result.points_built} built, {result.points_stored} stored, "
        f"{len(result.differing_points)} differing{first_point}"
    )


def run_out_of_sample(db: Path, name: str, out: Path | None) -> None:
    detector = detector_named(name)
    log = Path(out_of_sample.DEFAULT_LOG)
    try:
        with CandleStore(db, detector.timeframe) as store:
            result = out_of_sample.check(store, detector, log, now=int(time.time()))
    except out_of_sample.Refused as refused:
        sys.exit(str(refused))
    print(report(result, "out of sample"))
    print(f"Logged this run in {log}.")
    write_chart_data(result, out or db.parent / f"out-of-sample-{name}.json")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("TRADINGBOT_DB", DEFAULT_DB)),
        help=f"SQLite file holding the candles (default: $TRADINGBOT_DB or {DEFAULT_DB})",
    )
    stored = argparse.ArgumentParser(add_help=False)
    stored.add_argument(
        "--timeframe",
        type=Timeframe,
        choices=STORED_TIMEFRAMES,
        default=Timeframe.H1,
        metavar="|".join(t.value for t in STORED_TIMEFRAMES),
        help="the candles to store: 15m or 1h (default: 1h)",
    )
    parser = argparse.ArgumentParser(
        prog="tradingbot", description="Kraken spot XBTUSD candles in SQLite."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser(
        "import",
        parents=[common, stored],
        help="load candles from Kraken OHLCVT archive files",
    )
    importer.add_argument(
        "csv", nargs="+", type=Path, help="archive file(s), e.g. XBTUSD_60.csv or XBTUSD_15.csv"
    )
    commands.add_parser(
        "catch-up",
        parents=[common, stored],
        help="append the newest completed candles from the Kraken REST endpoint",
    )
    server = commands.add_parser("serve", parents=[common], help="start the HTTP API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    replayer = commands.add_parser(
        "replay",
        parents=[common],
        help=(
            "replay the development period through a detector, print its score over the "
            "scoring period, write chart data"
        ),
    )
    replayer.add_argument("detector", help=f"detector name: {', '.join(DETECTORS)}")
    replayer.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSON file for the chart data (default: replay-<detector>.json next to the store)",
    )
    rescorer = commands.add_parser(
        "re-score",
        parents=[common],
        help=(
            "replay a recorded run's own candles again and print its score under the current "
            "definitions; refuses unless the marks are identical to the recorded ones"
        ),
    )
    rescorer.add_argument("detector", help=f"detector name: {', '.join(DETECTORS)}")
    rescorer.add_argument(
        "--recorded",
        type=Path,
        default=None,
        help="the recorded run's chart data (default: replay-<detector>.json next to the store)",
    )
    rescorer.add_argument(
        "--strategy",
        default=None,
        help=(
            "also re-score this strategy's recorded backtest on the run; refuses unless the "
            f"fills are identical to the recorded ones: {', '.join(STRATEGIES)}"
        ),
    )
    rescorer.add_argument(
        "--recorded-backtest",
        type=Path,
        default=None,
        help=(
            "the recorded backtest's chart data "
            "(default: backtest-<strategy>.json next to the store)"
        ),
    )
    commands.add_parser(
        "check-hourly",
        parents=[common],
        help=(
            "build hourly candles from the stored 15-minute ones as a replay does and compare "
            "them with the stored hourly table over the scoring period"
        ),
    )
    checker = commands.add_parser(
        "out-of-sample",
        parents=[common],
        help=(
            "the one out-of-sample run a detector gets: score it past the boundary and log the "
            f"run in {out_of_sample.DEFAULT_LOG} in the working directory"
        ),
    )
    checker.add_argument("detector", help=f"detector name: {', '.join(DETECTORS)}")
    checker.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "JSON file for the chart data "
            "(default: out-of-sample-<detector>.json next to the store)"
        ),
    )
    tester = commands.add_parser(
        "backtest",
        parents=[common],
        help=(
            "run a strategy over detector three's replay of the development period with a "
            "notional account under both cost models, print its score over the scoring period, "
            "write chart data; refuses unless the marks are those of the recorded run"
        ),
    )
    tester.add_argument("strategy", help=f"strategy name: {', '.join(STRATEGIES)}")
    tester.add_argument(
        "--recorded",
        type=Path,
        default=None,
        help="detector three's recorded run (default: replay-three.json next to the store)",
    )
    tester.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSON file for the chart data (default: backtest-<strategy>.json next to the store)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    match args.command:
        case "import":
            run_import(args.db, args.timeframe, args.csv)
        case "catch-up":
            run_catch_up(args.db, args.timeframe)
        case "serve":
            run_serve(args.db, args.host, args.port)
        case "replay":
            run_replay(args.db, args.detector, args.out)
        case "re-score":
            run_re_score(
                args.db, args.detector, args.recorded, args.strategy, args.recorded_backtest
            )
        case "check-hourly":
            run_check_hourly(args.db)
        case "out-of-sample":
            run_out_of_sample(args.db, args.detector, args.out)
        case "backtest":
            run_backtest(args.db, args.strategy, args.recorded, args.out)
