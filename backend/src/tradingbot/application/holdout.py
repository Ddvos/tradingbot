"""The holdout boundary, enforced in code — the companion of HOLDOUT.md.

Every development entry point that reads market data (train, backtest,
walk-forward) clamps through `clamp_to_development`; there is deliberately
no flag anywhere to cross the boundary. The one-shot holdout run will get
its own explicitly named script when a strategy earns it.
"""

from datetime import UTC, datetime

import polars as pl

HOLDOUT_START = datetime(2026, 7, 4, tzinfo=UTC)
"""Start of the holdout period (HOLDOUT.md). Moved from 2025-07-01 on
5 Jul 2026 by the rule-4 ruling logged there: full-history baseline
backtests and train.py's validation window had already observed aggregate
results from the original holdout year, so that year is development data
now and the holdout regrows from this boundary."""

H2_EVAL_END = datetime(2025, 7, 1, tzinfo=UTC)
"""End of the walk-forward evaluation window for hypothesis H2 and its
feature trials (HYPOTHESES.md). Iterations 2-5 stay comparable to
iteration 1 by evaluating on exactly the window it used, even though data
up to HOLDOUT_START is development data since the boundary move."""


def clamp_to_development(ohlcv: pl.DataFrame, *, end: datetime = HOLDOUT_START) -> pl.DataFrame:
    """Return only bars strictly before `end`, capped at HOLDOUT_START.

    The cap makes crossing the holdout impossible even with a caller-supplied
    `end`; raises if nothing remains rather than silently returning an empty
    frame.
    """
    boundary = min(end, HOLDOUT_START)
    clamped = ohlcv.filter(pl.col("timestamp") < boundary)
    if clamped.is_empty():
        raise ValueError(f"No data before development boundary {boundary}")
    return clamped
