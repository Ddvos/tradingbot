"""The SQLite store of hourly spot candles.

One table, one row per hour, keyed by the candle's start time. Hours with no
trades have no row. Writing the same candle twice replaces it, so every import
and catch-up can be re-run safely.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from types import TracebackType

from tradingbot.candles import Candle

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles_1h (
    time    INTEGER PRIMARY KEY,
    open    REAL NOT NULL,
    high    REAL NOT NULL,
    low     REAL NOT NULL,
    close   REAL NOT NULL,
    volume  REAL NOT NULL,
    trades  INTEGER NOT NULL
)
"""

_UPSERT = """
INSERT INTO candles_1h (time, open, high, low, close, volume, trades)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(time) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume,
    trades = excluded.trades
"""


class CandleStore:
    """Hourly candles in a SQLite file; `":memory:"` keeps them in memory."""

    def __init__(self, path: str | Path) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def upsert(self, candles: Iterable[Candle]) -> int:
        """Store the candles and return how many hours were new."""
        before = self.count()
        rows = [(c.time, c.open, c.high, c.low, c.close, c.volume, c.trades) for c in candles]
        with self._conn:
            self._conn.executemany(_UPSERT, rows)
        return self.count() - before

    def read(self, start: int | None = None, end: int | None = None) -> list[Candle]:
        """Hourly candles with `start <= time <= end`, oldest first."""
        clauses: list[str] = []
        params: list[int] = []
        if start is not None:
            clauses.append("time >= ?")
            params.append(start)
        if end is not None:
            clauses.append("time <= ?")
            params.append(end)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cursor = self._conn.execute(
            f"SELECT time, open, high, low, close, volume, trades FROM candles_1h {where} "
            "ORDER BY time",
            params,
        )
        return [Candle(*row) for row in cursor]

    def time_range(self) -> tuple[int, int] | None:
        """Start time of the oldest and the newest candle, or None when empty."""
        row = self._conn.execute("SELECT MIN(time), MAX(time) FROM candles_1h").fetchone()
        if row is None or row[0] is None:
            return None
        return (int(row[0]), int(row[1]))

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM candles_1h").fetchone()
        return int(row[0])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> CandleStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
