"""The SQLite store of spot candles.

One table per stored timeframe, `candles_1h` for hourly and `candles_15m` for
fifteen-minute candles, with the same columns: one row per period, keyed by
the candle's start time. Periods with no trades have no row. Writing the same
candle twice replaces it, so every import and catch-up can be re-run safely.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from types import TracebackType

from tradingbot.candles import Candle, Timeframe

STORED_TIMEFRAMES = (Timeframe.M15, Timeframe.H1)
"""The timeframes with a table of their own; 4-hour and daily candles are resampled."""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
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
INSERT INTO {table} (time, open, high, low, close, volume, trades)
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
    """The candles of one timeframe in a SQLite file; `":memory:"` keeps them in memory.

    Several stores may open the same file, one per timeframe; each reads and
    writes only its own table.
    """

    def __init__(self, path: str | Path, timeframe: Timeframe = Timeframe.H1) -> None:
        if timeframe not in STORED_TIMEFRAMES:
            stored = ", ".join(t.value for t in STORED_TIMEFRAMES)
            raise ValueError(f"only {stored} candles are stored, not {timeframe.value}")
        self.timeframe = timeframe
        self._table = f"candles_{timeframe.value}"
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute(_SCHEMA.format(table=self._table))
        self._conn.commit()

    def upsert(self, candles: Iterable[Candle]) -> int:
        """Store the candles and return how many periods were new."""
        before = self.count()
        rows = [(c.time, c.open, c.high, c.low, c.close, c.volume, c.trades) for c in candles]
        with self._conn:
            self._conn.executemany(_UPSERT.format(table=self._table), rows)
        return self.count() - before

    def read(self, start: int | None = None, end: int | None = None) -> list[Candle]:
        """Candles with `start <= time <= end`, oldest first."""
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
            f"SELECT time, open, high, low, close, volume, trades FROM {self._table} {where} "
            "ORDER BY time",
            params,
        )
        return [Candle(*row) for row in cursor]

    def time_range(self) -> tuple[int, int] | None:
        """Start time of the oldest and the newest candle, or None when empty."""
        row = self._conn.execute(f"SELECT MIN(time), MAX(time) FROM {self._table}").fetchone()
        if row is None or row[0] is None:
            return None
        return (int(row[0]), int(row[1]))

    def count(self) -> int:
        row = self._conn.execute(f"SELECT COUNT(*) FROM {self._table}").fetchone()
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
