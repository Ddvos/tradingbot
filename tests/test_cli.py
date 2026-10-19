"""The command line: `tradingbot import` reports what it stored, `tradingbot replay` and
`tradingbot out-of-sample` the score."""

import json
import random
from pathlib import Path

import pytest

from tradingbot.candles import Candle
from tradingbot.cli import main
from tradingbot.store import CandleStore

H = 3600
DAY_START = 1_704_067_200  # 2024-01-01T00:00:00Z
OUT_OF_SAMPLE_BOUNDARY = 1_729_296_000  # 2024-10-19T00:00:00Z

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


def sixteen_hours_db(path: Path) -> Path:
    """The hand-built series of test_turning_points, stored in a SQLite file."""
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
    db = tmp_path / "candles.sqlite"
    with CandleStore(db) as store:
        store.upsert([Candle(OUT_OF_SAMPLE_BOUNDARY + H, 1.0, 1.0, 1.0, 1.0, 1.0, 1)])

    with pytest.raises(SystemExit) as stopped:
        main(["replay", "floor", "--db", str(db), "--out", str(tmp_path / "out.json")])

    assert "development period" in str(stopped.value)
    assert not (tmp_path / "out.json").exists()


def test_replay_knows_detector_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = sixteen_hours_db(tmp_path)
    out = tmp_path / "replay-one.json"

    main(["replay", "one", "--db", str(db), "--out", str(out)])

    assert "Replayed one over the development period" in capsys.readouterr().out
    assert json.loads(out.read_text())["detector"] == "one"


def store_across_the_boundary(path: Path) -> Path:
    """300 hours of a seeded walk before the boundary and 300 after, in a SQLite file."""
    rng = random.Random(12)
    close = 1000.0
    candles: list[Candle] = []
    for hour in range(-300, 300):
        open_ = close
        close = open_ * (1 + rng.uniform(-0.03, 0.03))
        high = max(open_, close) * (1 + rng.uniform(0, 0.01))
        low = min(open_, close) * (1 - rng.uniform(0, 0.01))
        candles.append(Candle(OUT_OF_SAMPLE_BOUNDARY + hour * H, open_, high, low, close, 1.0, 1))
    db = path / "candles.sqlite"
    with CandleStore(db) as store:
        store.upsert(candles)
    return db


def test_out_of_sample_scores_only_the_candles_past_the_boundary_and_logs_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = store_across_the_boundary(tmp_path)
    log = tmp_path / "out-of-sample.log"
    out = tmp_path / "out-of-sample-floor.json"

    main(["out-of-sample", "floor", "--db", str(db), "--log", str(log), "--out", str(out)])

    printed = capsys.readouterr().out
    assert "Replayed floor out of sample: 300 candles from 2024-10-19T00:00:00Z" in printed
    assert "hit rate" in printed and "false-mark rate" in printed
    assert str(log) in printed
    data = json.loads(out.read_text())
    assert data["detector"] == "floor"
    assert all(c["time"] >= OUT_OF_SAMPLE_BOUNDARY for c in data["candles"])
    assert all(m["time"] >= OUT_OF_SAMPLE_BOUNDARY for m in data["marks"])
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    assert "\tfloor\t" in lines[0]
    assert "2024-10-19T00:00:00Z" in lines[0] and "hit rate" in lines[0]


def test_out_of_sample_refuses_a_second_run_for_the_same_detector(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = store_across_the_boundary(tmp_path)
    log = tmp_path / "out-of-sample.log"
    out = tmp_path / "out-of-sample-floor.json"
    main(["out-of-sample", "floor", "--db", str(db), "--log", str(log), "--out", str(out)])
    capsys.readouterr()
    logged = log.read_text()
    out.unlink()

    with pytest.raises(SystemExit) as stopped:
        main(["out-of-sample", "floor", "--db", str(db), "--log", str(log), "--out", str(out)])

    assert "floor" in str(stopped.value) and "already" in str(stopped.value)
    assert log.read_text() == logged
    assert not out.exists()


def test_out_of_sample_stops_when_the_store_ends_before_the_boundary(tmp_path: Path) -> None:
    db = sixteen_hours_db(tmp_path)
    log = tmp_path / "out-of-sample.log"

    with pytest.raises(SystemExit) as stopped:
        main(["out-of-sample", "floor", "--db", str(db), "--log", str(log)])

    assert "out of sample" in str(stopped.value)
    assert not log.exists()
