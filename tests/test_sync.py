"""Keeping the store up to date: archive import and catch-up, both safe to re-run."""

from pathlib import Path

from tradingbot.candles import Candle
from tradingbot.store import CandleStore
from tradingbot.sync import catch_up, import_archive

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z

ARCHIVE_CSV = (
    # timestamp,open,high,low,close,volume,trades; no header; 01:00 has no trades
    "1704067200,100.0,110.0,95.0,105.0,1.5,10\n"
    "1704074400,105.0,120.0,100.0,115.0,2.25,20\n"
    "1704078000,115.0,118.0,90.0,92.0,3.0,30\n"
)


def test_import_archive_stores_the_csv_rows_and_reports_the_range(tmp_path: Path) -> None:
    csv = tmp_path / "XBTUSD_60.csv"
    csv.write_text(ARCHIVE_CSV)
    store = CandleStore(":memory:")

    result = import_archive(csv, store)

    assert result.stored == 3
    assert result.time_range == (T0, T0 + 3 * H)
    assert store.read() == [
        Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.5, 10),
        Candle(T0 + 2 * H, 105.0, 120.0, 100.0, 115.0, 2.25, 20),
        Candle(T0 + 3 * H, 115.0, 118.0, 90.0, 92.0, 3.0, 30),
    ]


def test_importing_the_same_archive_twice_stores_nothing_new(tmp_path: Path) -> None:
    csv = tmp_path / "XBTUSD_60.csv"
    csv.write_text(ARCHIVE_CSV)
    store = CandleStore(":memory:")
    import_archive(csv, store)

    result = import_archive(csv, store)

    assert result.stored == 0
    assert store.count() == 3


def fake_source(*candles: Candle):
    """A stand-in for the REST endpoint that always answers the same candles."""

    def hourly_candles(since: int | None) -> list[Candle]:
        return [c for c in candles if since is None or c.time >= since]

    return hourly_candles


def test_catch_up_never_stores_the_still_forming_hour() -> None:
    store = CandleStore(":memory:")
    source = fake_source(
        Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.0, 10),
        Candle(T0 + H, 105.0, 120.0, 100.0, 115.0, 2.0, 20),
        Candle(T0 + 2 * H, 115.0, 118.0, 90.0, 92.0, 3.0, 30),  # still forming
    )

    result = catch_up(store, source, now=T0 + 2 * H + 600)

    assert result.stored == 2
    assert store.time_range() == (T0, T0 + H)


def test_catch_up_stores_the_hour_once_it_has_completed() -> None:
    store = CandleStore(":memory:")
    source = fake_source(Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.0, 10))

    result = catch_up(store, source, now=T0 + H)

    assert result.stored == 1


def test_running_catch_up_again_stores_nothing_new() -> None:
    store = CandleStore(":memory:")
    source = fake_source(
        Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.0, 10),
        Candle(T0 + H, 105.0, 120.0, 100.0, 115.0, 2.0, 20),
    )
    catch_up(store, source, now=T0 + 3 * H)

    result = catch_up(store, source, now=T0 + 3 * H)

    assert result.stored == 0
    assert store.count() == 2


def test_catch_up_reports_the_hours_the_endpoint_could_not_reach() -> None:
    store = CandleStore(":memory:")
    store.upsert([Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.0, 10)])
    # The endpoint answers its full reach of 720 candles plus the forming one,
    # the oldest of them four hours after the store's newest.
    source = fake_source(
        *(Candle(T0 + (4 + i) * H, 105.0, 120.0, 100.0, 115.0, 2.0, 20) for i in range(721))
    )

    result = catch_up(store, source, now=T0 + (4 + 720) * H + 600)

    assert result.stored == 720
    assert result.unreachable == (T0 + H, T0 + 3 * H)


def test_a_quiet_hour_after_the_newest_candle_is_not_unreachable() -> None:
    store = CandleStore(":memory:")
    store.upsert([Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.0, 10)])
    # The endpoint had everything since the store's newest hour; 01:00 just had no trades.
    source = fake_source(Candle(T0 + 2 * H, 105.0, 120.0, 100.0, 115.0, 2.0, 20))

    result = catch_up(store, source, now=T0 + 6 * H)

    assert result.stored == 1
    assert result.unreachable is None


def test_catch_up_reports_no_unreachable_hours_when_the_store_is_contiguous() -> None:
    store = CandleStore(":memory:")
    store.upsert([Candle(T0, 100.0, 110.0, 95.0, 105.0, 1.0, 10)])
    source = fake_source(Candle(T0 + H, 105.0, 120.0, 100.0, 115.0, 2.0, 20))

    result = catch_up(store, source, now=T0 + 6 * H)

    assert result.unreachable is None
