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
