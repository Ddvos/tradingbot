"""The `tradingbot` command: import the archive, catch up, serve the API, replay a detector,
run the one out-of-sample check."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from tradingbot import out_of_sample
from tradingbot.candles import iso
from tradingbot.detectors import DETECTORS, Detector
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY, read_development
from tradingbot.kraken import KrakenSpot
from tradingbot.replay import ReplayResult, run
from tradingbot.scoring import describe_score
from tradingbot.store import CandleStore
from tradingbot.sync import catch_up, import_archive

DEFAULT_DB = "data/candles.sqlite"


def describe(store: CandleStore) -> str:
    time_range = store.time_range()
    if time_range is None:
        return "The store is empty."
    first, last = time_range
    return f"The store holds {store.count()} hours from {iso(first)} to {iso(last)}."


def run_import(db: Path, files: list[Path]) -> None:
    with CandleStore(db) as store:
        for path in files:
            result = import_archive(path, store)
            print(f"Imported {path.name}: {result.stored} new hours.")
        print(describe(store))


def run_catch_up(db: Path) -> None:
    with CandleStore(db) as store:
        result = catch_up(store, KrakenSpot().hourly_candles, now=int(time.time()))
        print(f"Caught up from Kraken: {result.stored} new hours.")
        if result.unreachable is not None:
            first, last = result.unreachable
            print(
                f"Warning: the hours from {iso(first)} to {iso(last)} are missing. The endpoint "
                "reaches back only 720 hours; import a quarterly archive that covers them."
            )
        print(describe(store))


def run_serve(db: Path, host: str, port: int) -> None:
    import uvicorn

    from tradingbot.api import create_app

    uvicorn.run(create_app(db), host=host, port=port)


def report(result: ReplayResult, period: str) -> str:
    """The score as the batch commands print it; `period` names what was replayed."""
    first, last = result.candles[0].time, result.candles[-1].time
    heading = (
        f"Replayed {result.detector} {period}: {len(result.candles)} "
        f"candles from {iso(first)} to {iso(last)}."
    )
    lines = [f"  {label:<16} {value}" for label, value in describe_score(result.score)]
    return "\n".join([heading, *lines])


def detector_named(name: str) -> Callable[[], Detector]:
    build = DETECTORS.get(name)
    if build is None:
        sys.exit(f"Unknown detector {name!r}. Known detectors: {', '.join(DETECTORS)}.")
    return build


def write_chart_data(result: ReplayResult, out: Path) -> None:
    from tradingbot.api import ReplayOut

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ReplayOut.of(result).model_dump_json())
    print(f"Wrote the chart data to {out}.")


def run_replay(db: Path, detector: str, out: Path | None) -> None:
    build = detector_named(detector)
    with CandleStore(db) as store:
        candles = read_development(store)
    if not candles:
        sys.exit(
            "The store holds no candles in the development period, which ends before "
            f"{iso(OUT_OF_SAMPLE_BOUNDARY)}. Import an archive that covers it."
        )
    result = run(candles, build())
    print(report(result, "over the development period"))
    write_chart_data(result, out or db.parent / f"replay-{detector}.json")


def run_out_of_sample(db: Path, detector: str, out: Path | None) -> None:
    build = detector_named(detector)
    log = Path(out_of_sample.DEFAULT_LOG)
    try:
        with CandleStore(db) as store:
            result = out_of_sample.check(store, build(), log, now=int(time.time()))
    except out_of_sample.Refused as refused:
        sys.exit(str(refused))
    print(report(result, "out of sample"))
    print(f"Logged this run in {log}.")
    write_chart_data(result, out or db.parent / f"out-of-sample-{detector}.json")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("TRADINGBOT_DB", DEFAULT_DB)),
        help=f"SQLite file holding the hourly candles (default: $TRADINGBOT_DB or {DEFAULT_DB})",
    )
    parser = argparse.ArgumentParser(
        prog="tradingbot", description="Hourly Kraken spot XBTUSD candles in SQLite."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser(
        "import", parents=[common], help="load hourly candles from Kraken OHLCVT archive files"
    )
    importer.add_argument("csv", nargs="+", type=Path, help="archive file(s), e.g. XBTUSD_60.csv")
    commands.add_parser(
        "catch-up",
        parents=[common],
        help="append the newest completed hourly candles from the Kraken REST endpoint",
    )
    server = commands.add_parser("serve", parents=[common], help="start the HTTP API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    replayer = commands.add_parser(
        "replay",
        parents=[common],
        help="replay the development period through a detector, print its score, write chart data",
    )
    replayer.add_argument("detector", help=f"detector name: {', '.join(DETECTORS)}")
    replayer.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSON file for the chart data (default: replay-<detector>.json next to the store)",
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
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    match args.command:
        case "import":
            run_import(args.db, args.csv)
        case "catch-up":
            run_catch_up(args.db)
        case "serve":
            run_serve(args.db, args.host, args.port)
        case "replay":
            run_replay(args.db, args.detector, args.out)
        case "out-of-sample":
            run_out_of_sample(args.db, args.detector, args.out)
