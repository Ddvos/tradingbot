"""Calendar features from the (UTC) bar timestamp."""

import polars as pl


def hour_of_day() -> pl.Expr:
    """0-23, UTC."""
    return pl.col("timestamp").dt.hour()


def day_of_week() -> pl.Expr:
    """1 = Monday ... 7 = Sunday."""
    return pl.col("timestamp").dt.weekday()
