"""The command line: `tradingbot import` reports what it stored."""

from pathlib import Path

import pytest

from tradingbot.cli import main

ARCHIVE_CSV = (
    "1704067200,100.0,110.0,95.0,105.0,1.5,10\n"
    "1704074400,105.0,120.0,100.0,115.0,2.25,20\n"
    "1704078000,115.0,118.0,90.0,92.0,3.0,30\n"
)


def test_import_on_an_empty_database_reports_the_stored_range(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv = tmp_path / "XBTUSD_60.csv"
    csv.write_text(ARCHIVE_CSV)
    db = tmp_path / "candles.sqlite"

    main(["import", str(csv), "--db", str(db)])

    out = capsys.readouterr().out
    assert "3 new hours" in out
    assert "2024-01-01T00:00:00Z" in out
    assert "2024-01-01T03:00:00Z" in out


def test_importing_again_reports_zero_new_hours(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv = tmp_path / "XBTUSD_60.csv"
    csv.write_text(ARCHIVE_CSV)
    db = tmp_path / "candles.sqlite"
    main(["import", str(csv), "--db", str(db)])
    capsys.readouterr()

    main(["import", str(csv), "--db", str(db)])

    assert "0 new hours" in capsys.readouterr().out


H = 3600
DAY_START = 1_704_067_200  # 2024-01-01T00:00:00Z
OUT_OF_SAMPLE_BOUNDARY = 1_729_296_000  # 2024-10-19T00:00:00Z


def sixteen_hours_db(path: Path) -> Path:
    """The hand-built series of test_turning_points, stored in a SQLite file."""
    from tradingbot.candles import Candle
    from tradingbot.store import CandleStore

    rows = [
        (0, 96.0, 94.0, 95.0),
        (1, 95.0, 92.0, 93.0),
        (3, 93.0, 90.0, 91.0),
        (4, 94.0, 91.0, 93.0),
        (5, 96.0, 92.0, 95.0),
        (6, 98.0, 94.0, 97.0),
        (7, 99.0, 96.0, 98.0),
        (8, 100.0, 97.0, 99.0),
        (9, 99.0, 95.0, 96.0),
        (10, 97.0, 93.0, 94.0),
        (11, 95.0, 91.0, 92.0),
        (12, 93.0, 90.0, 91.0),
        (13, 95.0, 91.0, 94.0),
        (14, 98.0, 93.0, 97.0),
        (15, 101.0, 96.0, 100.0),
    ]
    db = path / "candles.sqlite"
    with CandleStore(db) as store:
        store.upsert(Candle(DAY_START + h * H, c, hi, lo, c, 1.0, 1) for h, hi, lo, c in rows)
    return db


def test_replay_prints_the_floor_score_and_writes_the_chart_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = sixteen_hours_db(tmp_path)
    out = tmp_path / "replay-floor.json"

    main(["replay", "floor", "--db", str(db), "--out", str(out)])

    printed = capsys.readouterr().out
    assert "floor" in printed
    assert "15 candles" in printed
    assert "2024-01-01T00:00:00Z" in printed and "2024-01-01T15:00:00Z" in printed
    assert "turning points" in printed and "hit rate" in printed and "false-mark rate" in printed
    assert "median timing" in printed and "median give-up" in printed
    assert out.exists()
    import json

    data = json.loads(out.read_text())
    assert data["detector"] == "floor"
    assert set(data) == {"detector", "candles", "turning_points", "marks", "score"}


def test_replay_prints_the_same_score_run_after_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = sixteen_hours_db(tmp_path)
    out = tmp_path / "replay-floor.json"
    main(["replay", "floor", "--db", str(db), "--out", str(out)])
    first = capsys.readouterr().out

    main(["replay", "floor", "--db", str(db), "--out", str(out)])

    assert capsys.readouterr().out == first


def test_replay_refuses_an_unknown_detector(tmp_path: Path) -> None:
    db = sixteen_hours_db(tmp_path)

    with pytest.raises(SystemExit):
        main(["replay", "oracle", "--db", str(db)])


def test_replay_stops_when_the_store_holds_no_development_candles(tmp_path: Path) -> None:
    from tradingbot.candles import Candle
    from tradingbot.store import CandleStore

    db = tmp_path / "candles.sqlite"
    with CandleStore(db) as store:
        store.upsert([Candle(OUT_OF_SAMPLE_BOUNDARY + H, 1.0, 1.0, 1.0, 1.0, 1.0, 1)])

    with pytest.raises(SystemExit) as stopped:
        main(["replay", "floor", "--db", str(db), "--out", str(tmp_path / "out.json")])

    assert "development period" in str(stopped.value)
    assert not (tmp_path / "out.json").exists()
