"""Parquet storage — MarketDataProvider impl for backtest.

store.py: ParquetStore — read/write OHLCV with schema validation + invariants
(sorted, no dupes, UTC) + idempotent backfill. Slice 0.
"""
