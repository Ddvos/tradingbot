"""Backfill funding-rate history from Kraken Futures into local Parquet.

IMPORTANT: Kraken serves only the trailing ~12 months of hourly funding
rates (verified 6 Jul 2026) — the local archive is the system of record.
Run this at least monthly, or history scrolls out of the API window and is
lost for good. Idempotent: re-running merges, dedupes, and rewrites.

Usage:
    uv run python scripts/backfill_funding.py
    uv run python scripts/backfill_funding.py --symbol PF_XBTUSD
"""

import argparse
from pathlib import Path

from tradingbot.adapters.kraken.provider import KrakenProvider
from tradingbot.adapters.parquet.funding_store import FundingStore

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "raw" / "funding"


class _Args(argparse.Namespace):
    symbol: str
    data_dir: Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="PF_XBTUSD")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args(namespace=_Args())

    print(f"Fetching {args.symbol} funding rates from Kraken Futures...")
    rates = KrakenProvider().fetch_funding_rates(args.symbol)
    print(f"Fetched {len(rates)} settlements ({rates[0, 'timestamp']} -> {rates[-1, 'timestamp']})")

    store = FundingStore(args.data_dir)
    added = store.upsert(args.symbol, rates)
    print(f"Upserted into {store.path_for(args.symbol)} ({added} new rows)")


if __name__ == "__main__":
    main()
