"""The command line: `tradingbot import` reports what it stored, `tradingbot replay`,
`tradingbot re-score` and `tradingbot out-of-sample` the score, `tradingbot check-hourly` how
the hourly candles built from the fifteen-minute ones compare with the stored hourly table."""

import json
import random
from pathlib import Path

import pytest

from tradingbot.candles import Candle, Timeframe
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
    assert "3 new hourly candles" in out
    assert "The store holds 3 hourly candles" in out
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

    assert "0 new hourly candles" in capsys.readouterr().out


def test_import_stores_fifteen_minute_candles_in_their_own_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv = tmp_path / "XBTUSD_15.csv"
    csv.write_text(
        "1704067200,100.0,104.0,99.0,103.0,1.0,10\n"
        "1704068100,103.0,108.0,102.0,107.0,2.0,20\n"
        "1704069000,107.0,110.0,105.0,106.0,3.0,30\n"
        "1704069900,106.0,107.5,101.0,102.0,4.0,40\n"
    )
    db = tmp_path / "candles.sqlite"

    main(["import", "--timeframe", "15m", str(csv), "--db", str(db)])

    out = capsys.readouterr().out
    assert "4 new 15-minute candles" in out
    assert (
        "The store holds 4 15-minute candles from 2024-01-01T00:00:00Z to 2024-01-01T00:45:00Z"
        in out
    )
    with CandleStore(db, Timeframe.M15) as fifteen, CandleStore(db) as hourly:
        assert fifteen.count() == 4
        assert hourly.count() == 0


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
    assert (
        "Replayed floor over 15 candles from 2024-01-01T00:00:00Z to 2024-01-01T15:00:00Z"
        in printed
    )
    assert "scored over the scoring period: 15 candles from 2024-01-01T00:00:00Z" in printed
    assert "turning points" in printed and "hit rate" in printed and "false-mark rate" in printed
    assert "  false marks/hit  " in printed and " per hit" in printed
    assert "median timing" in printed and "median give-up" in printed
    assert "  2016-2018 " in printed and "  2019-2021 " in printed and "  2022-2024 " in printed
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["detector"] == "floor"
    assert data["timeframe"] == "1h"
    assert set(data) == {
        "detector",
        "timeframe",
        "scored_from",
        "candles",
        "turning_points",
        "levels",
        "swing_extremes",
        "marks",
        "score",
    }
    assert [era["era"]["name"] for era in data["score"]["eras"]] == [
        "2016-2018",
        "2019-2021",
        "2022-2024",
    ]


def test_replay_prints_the_same_score_run_after_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = sixteen_hours_db(tmp_path)
    main(["replay", "floor", "--db", str(db), "--out", str(tmp_path / "first.json")])
    first = capsys.readouterr().out

    main(["replay", "floor", "--db", str(db), "--out", str(tmp_path / "second.json")])

    assert capsys.readouterr().out.replace("second.json", "first.json") == first


def test_replay_never_overwrites_a_recorded_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = sixteen_hours_db(tmp_path)
    out = tmp_path / "replay-floor.json"
    main(["replay", "floor", "--db", str(db), "--out", str(out)])
    capsys.readouterr()
    recorded = out.read_text()

    with pytest.raises(SystemExit) as stopped:
        main(["replay", "floor", "--db", str(db), "--out", str(out)])

    assert "replay-floor.json" in str(stopped.value) and "recorded" in str(stopped.value)
    assert out.read_text() == recorded


def test_replay_stops_when_no_candle_falls_in_the_scoring_period(tmp_path: Path) -> None:
    db = tmp_path / "candles.sqlite"
    before_2016 = 1_451_606_400 - 10 * H
    with CandleStore(db) as store:
        store.upsert(Candle(before_2016 + h * H, 1.0, 1.0, 1.0, 1.0, 1.0, 1) for h in range(5))

    with pytest.raises(SystemExit) as stopped:
        main(["replay", "floor", "--db", str(db), "--out", str(tmp_path / "out.json")])

    assert "scoring period" in str(stopped.value)
    assert not (tmp_path / "out.json").exists()


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

    assert "Replayed one over 15 candles" in capsys.readouterr().out
    assert json.loads(out.read_text())["detector"] == "one"


def test_replay_knows_detector_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = sixteen_hours_db(tmp_path)
    out = tmp_path / "replay-two.json"

    main(["replay", "two", "--db", str(db), "--out", str(out)])

    assert "Replayed two over 15 candles" in capsys.readouterr().out
    data = json.loads(out.read_text())
    assert data["detector"] == "two"
    assert [level["time"] for level in data["levels"]] == [
        p["time"] for p in data["turning_points"]
    ]


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
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # the log lands in the working directory
    db = store_across_the_boundary(tmp_path)
    log = tmp_path / "out-of-sample.log"
    out = tmp_path / "out-of-sample-floor.json"

    main(["out-of-sample", "floor", "--db", str(db), "--out", str(out)])

    printed = capsys.readouterr().out
    assert "Replayed floor over 600 candles" in printed
    assert "scored out of sample: 300 candles from 2024-10-19T00:00:00Z" in printed
    assert "hit rate" in printed and "false-mark rate" in printed and " per hit" in printed
    assert "out-of-sample.log" in printed
    data = json.loads(out.read_text())
    assert data["detector"] == "floor"
    assert data["scored_from"] == OUT_OF_SAMPLE_BOUNDARY
    assert len(data["candles"]) == 600, "the whole run is recorded"
    assert all((m["time"] >= OUT_OF_SAMPLE_BOUNDARY) == m["scored"] for m in data["marks"])
    assert any(m["scored"] for m in data["marks"]) and any(not m["scored"] for m in data["marks"])
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    assert "\tfloor\t" in lines[0]
    assert "2024-10-19T00:00:00Z" in lines[0] and "hit rate" in lines[0]


def test_out_of_sample_refuses_a_second_run_for_the_same_detector(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    db = store_across_the_boundary(tmp_path)
    log = tmp_path / "out-of-sample.log"
    out = tmp_path / "out-of-sample-floor.json"
    main(["out-of-sample", "floor", "--db", str(db), "--out", str(out)])
    capsys.readouterr()
    logged = log.read_text()
    out.unlink()

    with pytest.raises(SystemExit) as stopped:
        main(["out-of-sample", "floor", "--db", str(db), "--out", str(out)])

    assert "floor" in str(stopped.value) and "already" in str(stopped.value)
    assert log.read_text() == logged
    assert not out.exists()


def test_out_of_sample_stops_when_the_store_ends_before_the_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    db = sixteen_hours_db(tmp_path)

    with pytest.raises(SystemExit) as stopped:
        main(["out-of-sample", "floor", "--db", str(db)])

    assert "out of sample" in str(stopped.value)
    assert not (tmp_path / "out-of-sample.log").exists()


def test_re_score_reports_the_recorded_run_under_the_current_definitions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = sixteen_hours_db(tmp_path)
    recorded = tmp_path / "replay-floor.json"
    main(["replay", "floor", "--db", str(db), "--out", str(recorded)])
    capsys.readouterr()

    main(["re-score", "floor", "--recorded", str(recorded)])

    printed = capsys.readouterr().out
    assert "Re-scored floor under ADR-0007" in printed
    assert "4 marks, identical" in printed and "replay-floor.json" in printed
    assert "Replayed floor over 15 candles" in printed
    assert "hit rate" in printed and " per hit" in printed and "  2022-2024 " in printed


def test_re_score_refuses_when_the_marks_differ_from_the_recorded_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = sixteen_hours_db(tmp_path)
    recorded = tmp_path / "replay-floor.json"
    main(["replay", "floor", "--db", str(db), "--out", str(recorded)])
    capsys.readouterr()
    data = json.loads(recorded.read_text())
    data["marks"] = data["marks"][1:]  # as if the recorded run had placed three marks
    recorded.write_text(json.dumps(data))

    with pytest.raises(SystemExit) as stopped:
        main(["re-score", "floor", "--recorded", str(recorded)])

    message = str(stopped.value)
    assert "4 marks" in message and "3" in message and "2024-01-01T01:00:00Z" in message
    assert "hit rate" not in capsys.readouterr().out


def test_re_score_refuses_a_recorded_run_of_another_detector(tmp_path: Path) -> None:
    db = sixteen_hours_db(tmp_path)
    recorded = tmp_path / "replay-floor.json"
    main(["replay", "floor", "--db", str(db), "--out", str(recorded)])

    with pytest.raises(SystemExit) as stopped:
        main(["re-score", "one", "--recorded", str(recorded)])

    assert "floor" in str(stopped.value) and "one" in str(stopped.value)


Q = 900


def two_table_db(path: Path, *, break_an_hour: bool) -> Path:
    """Two hours of fifteen-minute candles, 2024-01-01 00:00 and 01:00, with 01:30 missing,
    and the hourly table that matches them unless `break_an_hour` lifts 01:00's high."""
    rows = [
        (0, 100.0, 104.0, 99.0, 103.0),
        (1, 103.0, 108.0, 102.0, 107.0),
        (2, 107.0, 110.0, 105.0, 106.0),
        (3, 106.0, 107.5, 101.0, 102.0),
        (4, 102.0, 103.0, 98.0, 99.0),
        (5, 99.0, 100.0, 97.0, 98.0),
        (7, 98.0, 101.0, 96.0, 100.0),
    ]
    quarters = [Candle(DAY_START + q * Q, o, h, lo, c, 1.0, 1) for q, o, h, lo, c in rows]
    hours = [
        Candle(DAY_START, 100.0, 110.0, 99.0, 102.0, 4.0, 4),
        Candle(DAY_START + H, 102.0, 500.0 if break_an_hour else 103.0, 96.0, 100.0, 3.0, 3),
    ]
    db = path / "candles.sqlite"
    with CandleStore(db, Timeframe.M15) as fifteen, CandleStore(db) as hourly:
        fifteen.upsert(quarters)
        hourly.upsert(hours)
    return db


def test_replay_knows_detector_three_and_reads_the_fifteen_minute_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = two_table_db(tmp_path, break_an_hour=False)
    out = tmp_path / "replay-three.json"

    main(["replay", "three", "--db", str(db), "--out", str(out)])

    assert "Replayed three over 7 candles from 2024-01-01T00:00:00Z" in capsys.readouterr().out
    data = json.loads(out.read_text())
    assert data["detector"] == "three"
    assert data["timeframe"] == "15m"
    # Hour 1's low of 96 is 12.7% below hour 0's high: a top, confirmed on the last candle,
    # from which the detector reads the swing extreme, that candle's own high.
    assert data["swing_extremes"] == [
        {
            "kind": "top",
            "price": 101.0,
            "time": DAY_START + 7 * Q,
            "active_from": DAY_START + 7 * Q,
            "active_until": None,
        }
    ]


def test_check_hourly_finds_no_difference_when_the_tables_agree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = two_table_db(tmp_path, break_an_hour=False)

    main(["check-hourly", "--db", str(db)])

    printed = capsys.readouterr().out
    assert "2 hourly candles from 7 15-minute candles" in printed
    assert "2024-01-01T00:00:00Z" in printed and "2024-01-01T01:00:00Z" in printed
    assert "only in the 15-minute build   0" in printed
    assert "only in the hourly table      0" in printed
    assert "differing hours               0" in printed
    assert "turning points                1 built, 1 stored, 0 differing" in printed


def test_check_hourly_counts_a_differing_hour(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = two_table_db(tmp_path, break_an_hour=True)

    main(["check-hourly", "--db", str(db)])

    printed = capsys.readouterr().out
    assert "differing hours               1  (first 2024-01-01T01:00:00Z)" in printed


def test_check_hourly_stops_when_nothing_falls_in_the_scoring_period(tmp_path: Path) -> None:
    db = tmp_path / "candles.sqlite"
    before_2016 = 1_451_606_400 - 10 * H
    with CandleStore(db, Timeframe.M15) as fifteen, CandleStore(db) as hourly:
        fifteen.upsert(Candle(before_2016 + q * Q, 1.0, 1.0, 1.0, 1.0, 1.0, 1) for q in range(8))
        hourly.upsert(Candle(before_2016 + h * H, 1.0, 1.0, 1.0, 1.0, 4.0, 4) for h in range(2))

    with pytest.raises(SystemExit) as stopped:
        main(["check-hourly", "--db", str(db)])

    assert "scoring period" in str(stopped.value)


def test_check_hourly_stops_without_fifteen_minute_candles(tmp_path: Path) -> None:
    db = sixteen_hours_db(tmp_path)

    with pytest.raises(SystemExit) as stopped:
        main(["check-hourly", "--db", str(db)])

    assert "15-minute" in str(stopped.value)
