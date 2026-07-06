"""Market data port: the OHLCV contract every provider must honor.

The schema and invariants defined here are the contract of the DataFrame that
crosses this port — adapters validate against them on entry (Kraken) and on
read/write (Parquet). See CLAUDE.md → Data layout.
"""

from datetime import datetime, timedelta
from typing import Literal, Protocol

import polars as pl

type Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d", "1w"]

TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}

OHLCV_SCHEMA = pl.Schema(
    {
        "timestamp": pl.Datetime("ms", "UTC"),
        "open": pl.Float64(),
        "high": pl.Float64(),
        "low": pl.Float64(),
        "close": pl.Float64(),
        "volume": pl.Float64(),
    }
)

FUNDING_SCHEMA = pl.Schema(
    {
        "timestamp": pl.Datetime("ms", "UTC"),
        "relative_rate": pl.Float64(),
        "absolute_rate": pl.Float64(),
    }
)
"""One row per hourly funding settlement (Kraken accrues funding hourly).
relative_rate is the dimensionless per-hour rate a position pays (long) or
receives (short) on its notional; absolute_rate is Kraken's quote-currency
equivalent, kept for cross-checking."""


def _validate_frame(df: pl.DataFrame, schema: pl.Schema, name: str) -> None:
    """Contract shared by every market-data frame: exact schema, timestamps
    strictly increasing (implies sorted ascending and no duplicates), no
    null values."""
    if df.schema != schema:
        raise ValueError(f"{name} schema mismatch: expected {schema}, got {df.schema}")
    if df.null_count().sum_horizontal().item() > 0:
        raise ValueError(f"{name} frame contains null values")
    if len(df) > 1:
        min_delta = df.get_column("timestamp").diff().drop_nulls().min()
        if isinstance(min_delta, timedelta) and min_delta <= timedelta(0):
            raise ValueError(
                f"{name} timestamps must be strictly increasing (sorted, no duplicates)"
            )


def validate_ohlcv(df: pl.DataFrame) -> None:
    """Raise ValueError unless df satisfies the OHLCV contract."""
    _validate_frame(df, OHLCV_SCHEMA, "OHLCV")


def validate_funding(df: pl.DataFrame) -> None:
    """Raise ValueError unless df satisfies the funding-rate contract."""
    _validate_frame(df, FUNDING_SCHEMA, "Funding")


class MarketDataProvider(Protocol):
    """Port with two implementations: KrakenProvider (live), ParquetStore (backtest)."""

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, since: datetime) -> pl.DataFrame:
        """Return OHLCV bars from `since` (inclusive) up to now, satisfying validate_ohlcv."""
        ...
