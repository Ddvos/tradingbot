"""Parquet-backed funding-rate archive with idempotent upserts.

Layout: {base_path}/{symbol}.parquet — the full archive per symbol
(CLAUDE.md → Data layout, `data/raw/funding/`). Unlike OHLCV, this file is
the system of record, not a cache: Kraken's API serves only the trailing
~12 months, so history older than that survives *only* here. Grow it with
regular backfills (scripts/backfill_funding.py, at least monthly).
"""

from pathlib import Path

import polars as pl

from tradingbot.core.ports.market_data import FUNDING_SCHEMA, validate_funding


class FundingStore:
    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def path_for(self, symbol: str) -> Path:
        return self._base_path / f"{symbol}.parquet"

    def read(self, symbol: str) -> pl.DataFrame:
        """Read the full funding archive for `symbol`, validating invariants."""
        path = self.path_for(symbol)
        if not path.exists():
            raise FileNotFoundError(
                f"No funding data at {path} — run scripts/backfill_funding.py first"
            )
        df = pl.read_parquet(path)
        validate_funding(df)
        return df

    def upsert(self, symbol: str, new_rows: pl.DataFrame) -> int:
        """Merge new rows into the archive: dedupe on timestamp (new wins),
        sort, rewrite. Idempotent; returns the number of rows added."""
        if new_rows.schema != FUNDING_SCHEMA:
            raise ValueError(
                f"Funding schema mismatch: expected {FUNDING_SCHEMA}, got {new_rows.schema}"
            )
        path = self.path_for(symbol)
        existing = pl.read_parquet(path) if path.exists() else None
        combined = pl.concat([existing, new_rows]) if existing is not None else new_rows
        merged = combined.unique(subset="timestamp", keep="last").sort("timestamp")
        validate_funding(merged)

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".parquet.tmp")
        merged.write_parquet(tmp_path)
        tmp_path.replace(path)
        return len(merged) - (len(existing) if existing is not None else 0)
