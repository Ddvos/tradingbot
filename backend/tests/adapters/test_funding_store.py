from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from tradingbot.adapters.parquet.funding_store import FundingStore
from tradingbot.core.ports.market_data import FUNDING_SCHEMA


def rates(start_hour: int, values: list[float]) -> pl.DataFrame:
    start = datetime(2025, 7, 2, start_hour, tzinfo=UTC)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=i) for i in range(len(values))],
            "relative_rate": values,
            "absolute_rate": [v * 100_000 for v in values],
        },
        schema=FUNDING_SCHEMA,
    )


def test_upsert_is_idempotent(tmp_path: Path) -> None:
    store = FundingStore(tmp_path)
    frame = rates(0, [1e-6, 2e-6, 3e-6])

    assert store.upsert("PF_XBTUSD", frame) == 3
    assert store.upsert("PF_XBTUSD", frame) == 0
    assert store.read("PF_XBTUSD").equals(frame)


def test_upsert_merges_overlap_and_new_wins(tmp_path: Path) -> None:
    store = FundingStore(tmp_path)
    store.upsert("PF_XBTUSD", rates(0, [1e-6, 2e-6]))

    added = store.upsert("PF_XBTUSD", rates(1, [5e-6, 6e-6]))  # hour 1 overlaps

    assert added == 1
    merged = store.read("PF_XBTUSD")
    assert merged.get_column("relative_rate").to_list() == [1e-6, 5e-6, 6e-6]


def test_read_missing_file_points_at_backfill(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="backfill_funding"):
        FundingStore(tmp_path).read("PF_XBTUSD")


def test_upsert_rejects_wrong_schema(tmp_path: Path) -> None:
    bad = pl.DataFrame({"timestamp": [datetime(2025, 7, 2, tzinfo=UTC)], "rate": [1e-6]})
    with pytest.raises(ValueError, match="schema mismatch"):
        FundingStore(tmp_path).upsert("PF_XBTUSD", bad)
