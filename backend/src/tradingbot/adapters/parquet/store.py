"""Parquet-backed OHLCV storage with validated invariants and idempotent upserts.

Layout: {base_path}/{symbol}/{timeframe}.parquet — one file per (symbol,
timeframe) holding the full history. See CLAUDE.md → Data layout.
"""

from datetime import datetime
from pathlib import Path

import polars as pl

from tradingbot.core.ports.market_data import OHLCV_SCHEMA, Timeframe, validate_ohlcv


class ParquetStore:
    """Implements the MarketDataProvider port for backtests, plus write access."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    def path_for(self, symbol: str, timeframe: Timeframe) -> Path:
        return self._base_path / symbol / f"{timeframe}.parquet"

    def read(self, symbol: str, timeframe: Timeframe) -> pl.DataFrame:
        """Read the full history for (symbol, timeframe), validating invariants."""
        path = self.path_for(symbol, timeframe)
        if not path.exists():
            raise FileNotFoundError(f"No OHLCV data at {path} — run scripts/backfill.py first")
        df = pl.read_parquet(path)
        validate_ohlcv(df)
        return df

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, since: datetime) -> pl.DataFrame:
        return self.read(symbol, timeframe).filter(pl.col("timestamp") >= since)

    def upsert(self, symbol: str, timeframe: Timeframe, new_rows: pl.DataFrame) -> int:
        """Merge new rows into the file: dedupe on timestamp (new wins), sort, rewrite.

        Idempotent: upserting the same rows twice leaves the file unchanged.
        Returns the number of rows added.
        """
        if new_rows.schema != OHLCV_SCHEMA:
            raise ValueError(
                f"OHLCV schema mismatch: expected {OHLCV_SCHEMA}, got {new_rows.schema}"
            )
        path = self.path_for(symbol, timeframe)
        existing = pl.read_parquet(path) if path.exists() else None
        combined = pl.concat([existing, new_rows]) if existing is not None else new_rows
        merged = combined.unique(subset="timestamp", keep="last").sort("timestamp")
        validate_ohlcv(merged)

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".parquet.tmp")
        merged.write_parquet(tmp_path)
        tmp_path.replace(path)
        return len(merged) - (len(existing) if existing is not None else 0)
