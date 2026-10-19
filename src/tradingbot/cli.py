"""The `tradingbot` command: import the archive, catch up, serve the API, replay a detector."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from tradingbot.detectors import DETECTORS
from tradingbot.development import OUT_OF_SAMPLE_BOUNDARY, read_development
from tradingbot.kraken import KrakenSpot
from tradingbot.replay import ReplayResult, run
from tradingbot.store import CandleStore
from tradingbot.sync import catch_up, import_archive

DEFAULT_DB = "data/candles.sqlite"


def iso(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def describe_score(result: ReplayResult) -> str:
    score = result.score
    first, last = result.candles[0].time, result.candles[-1].time
    if score.median_timing is None or score.median_give_up is None:
        timing = give_up = "n/a (no hits)"
    else:
        early_or_late = (
            "early" if score.median_timing < 0 else "late" if score.median_timing > 0 else "on time"
        )
        timing = f"{score.median_timing:+.1f} candles ({early_or_late})"
        give_up = f"{score.median_give_up:.2f}%"
    return "\n".join(
        [
            f"Replayed {result.detector} over the development period: {len(result.candles)} "
            f"candles from {iso(first)} to {iso(last)}.",
            f"  turning points   {score.turning_points}",
            f"  marks            {score.marks}",
            f"  hits             {score.hits}  (hit rate {score.hit_rate:.1%})",
            f"  false marks      {score.false_marks}  "
            f"(false-mark rate {score.false_mark_rate:.1%})",
            f"  median timing    {timing}",
            f"  median give-up   {give_up}",
        ]
    )


def run_replay(db: Path, detector: str, out: Path | None) -> None:
    from tradingbot.api import ReplayOut

    build = DETECTORS.get(detector)
    if build is None:
        sys.exit(f"Unknown detector {detector!r}. Known detectors: {', '.join(DETECTORS)}.")
    with CandleStore(db) as store:
        candles = read_development(store)
    if not candles:
        sys.exit(
            "The store holds no candles in the development period, which ends before "
            f"{iso(OUT_OF_SAMPLE_BOUNDARY)}. Import an archive that covers it."
        )
    result = run(candles, build())
    print(describe_score(result))
    if out is None:
        out = db.parent / f"replay-{detector}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ReplayOut.of(result).model_dump_json())
    print(f"Wrote the chart data to {out}.")


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
