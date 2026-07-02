"""Backfill OHLCV history from Kraken Futures into local Parquet.

Idempotent: re-running (with any overlapping range) merges, dedupes, and
rewrites — same data in, same file out.

Usage:
    uv run python scripts/backfill.py
    uv run python scripts/backfill.py --symbol PF_XBTUSD --timeframe 1h --since 2022-01-01
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, get_args

from tradingbot.adapters.kraken.provider import KrakenProvider
from tradingbot.adapters.parquet.store import ParquetStore
from tradingbot.core.ports.market_data import Timeframe

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "raw" / "ohlcv"
# PF_XBTUSD history starts 2022-03-23; a slightly earlier default is harmless.
DEFAULT_SINCE = "2022-01-01"


class _Args(argparse.Namespace):
    symbol: str
    timeframe: str
    since: str
    data_dir: Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="PF_XBTUSD")
    parser.add_argument("--timeframe", default="1h", choices=get_args(Timeframe.__value__))
    parser.add_argument("--since", default=DEFAULT_SINCE, help="ISO date, e.g. 2022-01-01")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args(namespace=_Args())

    timeframe = cast(Timeframe, args.timeframe)  # narrowed by argparse choices
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)

    print(f"Fetching {args.symbol} {timeframe} from Kraken Futures since {since.date()}...")
    ohlcv = KrakenProvider().fetch_ohlcv(args.symbol, timeframe, since)
    print(f"Fetched {len(ohlcv)} bars ({ohlcv[0, 'timestamp']} -> {ohlcv[-1, 'timestamp']})")

    store = ParquetStore(args.data_dir)
    added = store.upsert(args.symbol, timeframe, ohlcv)
    print(f"Upserted into {store.path_for(args.symbol, timeframe)} ({added} new rows)")


if __name__ == "__main__":
    main()
