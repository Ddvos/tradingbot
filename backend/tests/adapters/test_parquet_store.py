from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from tradingbot.adapters.parquet.store import ParquetStore

type OhlcvFactory = Callable[[list[float]], pl.DataFrame]


def test_upsert_read_roundtrip(tmp_path: Path, make_ohlcv: OhlcvFactory) -> None:
    store = ParquetStore(tmp_path)
    ohlcv = make_ohlcv([100.0, 101.0, 102.0])

    added = store.upsert("PF_XBTUSD", "1h", ohlcv)

    assert added == 3
    assert_frame_equal(store.read("PF_XBTUSD", "1h"), ohlcv)


def test_upsert_is_idempotent(tmp_path: Path, make_ohlcv: OhlcvFactory) -> None:
    store = ParquetStore(tmp_path)
    ohlcv = make_ohlcv([100.0, 101.0, 102.0])

    store.upsert("PF_XBTUSD", "1h", ohlcv)
    added_again = store.upsert("PF_XBTUSD", "1h", ohlcv)

    assert added_again == 0
    assert_frame_equal(store.read("PF_XBTUSD", "1h"), ohlcv)


def test_upsert_merges_overlap_new_rows_win(tmp_path: Path, make_ohlcv: OhlcvFactory) -> None:
    store = ParquetStore(tmp_path)
    store.upsert("PF_XBTUSD", "1h", make_ohlcv([100.0, 101.0, 102.0]))

    overlap = make_ohlcv([100.0, 101.0, 999.0, 103.0]).tail(2)
    added = store.upsert("PF_XBTUSD", "1h", overlap)

    merged = store.read("PF_XBTUSD", "1h")
    assert added == 1
    assert len(merged) == 4
    assert merged.get_column("close").to_list() == [100.0, 101.0, 999.0, 103.0]


def test_upsert_sorts_unsorted_input(tmp_path: Path, make_ohlcv: OhlcvFactory) -> None:
    store = ParquetStore(tmp_path)
    store.upsert("PF_XBTUSD", "1h", make_ohlcv([100.0, 101.0, 102.0]).reverse())

    timestamps = store.read("PF_XBTUSD", "1h").get_column("timestamp")
    assert timestamps.is_sorted()


def test_upsert_rejects_wrong_schema(tmp_path: Path) -> None:
    store = ParquetStore(tmp_path)
    with pytest.raises(ValueError, match="schema mismatch"):
        store.upsert("PF_XBTUSD", "1h", pl.DataFrame({"close": [1.0]}))


def test_read_missing_file_raises(tmp_path: Path) -> None:
    store = ParquetStore(tmp_path)
    with pytest.raises(FileNotFoundError, match="backfill"):
        store.read("PF_XBTUSD", "1h")
