"""Paper trading: the loop on live candles with a simulated account (slice 11, ADR-0009).

The loop keeps the store of the detector's timeframe current from Kraken's
spot endpoint, as `catch-up` does, and consumes every completed candle once,
a step: it hands the candle to the detector through the replayer and to the
strategy through the backtest's walker, in the backtest's order, so the fills
it records are the fills a backtest makes over the same candles. The account
is a notional 500 USD under the perpetual cost model, flat at the loop's first
step, the first candle to close after the loop started; a change of desired
position becomes an order that fills at the next candle's open, recorded when
that candle arrives. Next to the model's numbers the loop records what Kraken
Futures says: the perpetual's mark price, read from the public ticker when an
order is placed and at every hourly close, kept as the basis over spot; and
the rate really charged in every hour, from the public funding history, filled
in as Kraken publishes it. A reading that fails is left missing, never
invented, and the step completes without it.

The record lives in tables of its own in the store's SQLite file, keyed by
detector and strategy so two loops never mix: the steps, the orders, the fills
and the hourly closes. A restart rebuilds the detector's and the strategy's
state by replaying the whole store, consumes the candles that arrived while
the loop was stopped, and never records a fill twice; it refuses a stop longer
than the endpoint's reach, as `catch-up` warns, and a store whose candles no
longer produce the recorded fills. The report sets the account against holding
and the model against the market, and reconciles the record with a backtest
over the same candles. Nothing here places an order or needs a key; the live
numbers of ADR-0008 wait for the paper-trading grilling.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import quantiles
from types import TracebackType
from typing import Protocol

from tradingbot.backtest import (
    PERPETUAL,
    STARTING_USD,
    Fill,
    Side,
    Stepped,
    Walker,
    describe_growth,
    extremes_by_mark,
    walk,
)
from tradingbot.candles import Candle, iso
from tradingbot.detectors import Detector
from tradingbot.kraken import REST_REACH
from tradingbot.kraken_futures import MarkPrice
from tradingbot.replay import Replayer, Step, replay_all, score_replayed
from tradingbot.store import CandleStore
from tradingbot.strategies import MarkWithExtreme, Position, Strategy
from tradingbot.sync import CandleSource, catch_up
from tradingbot.turning_points import Kind

HOUR = 3600

GRACE = 15
"""Seconds after a candle's close before the loop asks the endpoint for it."""

RETRY = 15
"""Seconds between polls while the candle has not appeared yet, or after the endpoint failed."""


class Refused(Exception):
    """The loop did not start or stopped; the message says why. Nothing was written."""


class FuturesSource(Protocol):
    """What the loop asks of Kraken Futures; `KrakenFutures` answers it, a test's fake too."""

    def mark_price(self) -> MarkPrice: ...

    def funding_rates(self) -> dict[int, float]: ...


def basis_of(mark_price: float | None, spot: float) -> float | None:
    """The basis: the mark price over spot, in percent of spot; None without a reading."""
    return None if mark_price is None else (mark_price / spot - 1) * 100


@dataclass(frozen=True, slots=True)
class StepRecord:
    """One candle consumed: what the detector said, where the account stood at the close."""

    time: int
    """The candle's start time."""
    close: float
    mark: Kind | None
    """The mark the detector placed on the candle, if any."""
    position: Position
    """After the step: after the fill at this candle's open, if any."""
    usd: float
    btc: float
    value: float
    """The account at the close, USD plus Bitcoin at the close, after the hour's funding."""
    benchmark: float
    """Holding's value at the close: 500 USD of Bitcoin bought at the first step's open."""
    order: Side | None
    """The order this close placed, to fill at the next candle's open."""
    recorded_at: int
    """When the loop consumed the candle, Unix seconds."""


@dataclass(frozen=True, slots=True)
class OrderRecord:
    """A change of position awaiting the next candle's open, with the market read when it
    was placed, the moment the order would reach the exchange."""

    placed_at: int
    """The step's candle: the order goes out at its close."""
    side: Side
    mark: int
    """The time of the mark that caused it."""
    spot: float
    """The close the order was placed on: spot at that moment."""
    mark_price: float | None
    """The perpetual's mark price read then; None when the step was not live or the read failed."""
    filled_at: int | None

    @property
    def basis(self) -> float | None:
        return basis_of(self.mark_price, self.spot)


@dataclass(frozen=True, slots=True)
class FillRecord:
    """A fill as the model prices it, next to the market's price at the order's moment."""

    time: int
    """The candle the order filled on, at its open."""
    side: Side
    price: float
    """That open moved 0.05% against the bot."""
    size: float
    fee: float
    after: float
    """The account's value right after the fill, at the fill price."""
    mark: int
    spot: float
    """The close the order was placed on."""
    mark_price: float | None
    """The perpetual's mark price read when the order was placed; None when not read."""

    @property
    def basis(self) -> float | None:
        return basis_of(self.mark_price, self.spot)


@dataclass(frozen=True, slots=True)
class HourRecord:
    """An hourly close: the model's funding on the position, and what Kraken Futures said."""

    time: int
    """The hour's start time; the close is an hour later."""
    close: float
    btc: float
    """The Bitcoin held at the close."""
    value: float
    benchmark: float
    funding: float
    """The model's funding at this close: 0.00125% of the position's value, 0 while flat."""
    rate: float | None
    """Kraken Futures' relative funding rate charged at this close, the rate it published
    for the hour that starts there; None until published, or never when it skipped the hour."""
    mark_price: float | None
    """The perpetual's mark price read at the close; None when not read."""

    @property
    def basis(self) -> float | None:
        return basis_of(self.mark_price, self.close)

    @property
    def funding_real(self) -> float | None:
        """What Kraken's rate charges on the same position; None without a rate."""
        return None if self.rate is None else self.rate * self.btc * self.close


_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_steps (
    detector    TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    time        INTEGER NOT NULL,
    close       REAL    NOT NULL,
    mark        TEXT,
    position    TEXT    NOT NULL,
    usd         REAL    NOT NULL,
    btc         REAL    NOT NULL,
    value       REAL    NOT NULL,
    benchmark   REAL    NOT NULL,
    order_side  TEXT,
    recorded_at INTEGER NOT NULL,
    PRIMARY KEY (detector, strategy, time)
);
CREATE TABLE IF NOT EXISTS paper_orders (
    detector    TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    placed_at   INTEGER NOT NULL,
    side        TEXT    NOT NULL,
    mark        INTEGER NOT NULL,
    spot        REAL    NOT NULL,
    mark_price  REAL,
    filled_at   INTEGER,
    PRIMARY KEY (detector, strategy, placed_at)
);
CREATE TABLE IF NOT EXISTS paper_fills (
    detector    TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    time        INTEGER NOT NULL,
    side        TEXT    NOT NULL,
    price       REAL    NOT NULL,
    size        REAL    NOT NULL,
    fee         REAL    NOT NULL,
    after       REAL    NOT NULL,
    mark        INTEGER NOT NULL,
    spot        REAL    NOT NULL,
    mark_price  REAL,
    PRIMARY KEY (detector, strategy, time)
);
CREATE TABLE IF NOT EXISTS paper_hours (
    detector    TEXT    NOT NULL,
    strategy    TEXT    NOT NULL,
    time        INTEGER NOT NULL,
    close       REAL    NOT NULL,
    btc         REAL    NOT NULL,
    value       REAL    NOT NULL,
    benchmark   REAL    NOT NULL,
    funding     REAL    NOT NULL,
    rate        REAL,
    mark_price  REAL,
    PRIMARY KEY (detector, strategy, time)
);
"""


class PaperStore:
    """The record of one loop, the tables above in the store's SQLite file, keyed by the
    detector and the strategy; `":memory:"` keeps it in memory. Every row is written once:
    the keys refuse a second step, order, fill or hour at the same time."""

    def __init__(self, path: str | Path, detector: str, strategy: str) -> None:
        self.detector = detector
        self.strategy = strategy
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def _key(self) -> tuple[str, str]:
        return (self.detector, self.strategy)

    def _rows(self, table: str, columns: str, order: str) -> list[tuple]:
        return self._conn.execute(
            f"SELECT {columns} FROM {table} WHERE detector = ? AND strategy = ? ORDER BY {order}",
            self._key,
        ).fetchall()

    def first_step(self) -> int | None:
        """The loop's first step, or None before it has one."""
        row = self._conn.execute(
            "SELECT MIN(time) FROM paper_steps WHERE detector = ? AND strategy = ?", self._key
        ).fetchone()
        return None if row is None or row[0] is None else int(row[0])

    def steps(self) -> list[StepRecord]:
        return [
            StepRecord(
                time,
                close,
                None if mark is None else Kind(mark),
                Position(position),
                usd,
                btc,
                value,
                benchmark,
                None if order is None else Side(order),
                recorded_at,
            )
            for time, close, mark, position, usd, btc, value, benchmark, order, recorded_at in (
                self._rows(
                    "paper_steps",
                    "time, close, mark, position, usd, btc, value, benchmark, order_side, "
                    "recorded_at",
                    "time",
                )
            )
        ]

    def orders(self) -> list[OrderRecord]:
        return [
            OrderRecord(placed_at, Side(side), mark, spot, mark_price, filled_at)
            for placed_at, side, mark, spot, mark_price, filled_at in self._rows(
                "paper_orders", "placed_at, side, mark, spot, mark_price, filled_at", "placed_at"
            )
        ]

    def pending_order(self) -> OrderRecord | None:
        """The order placed at the last step and not filled yet, if any."""
        return next((o for o in self.orders() if o.filled_at is None), None)

    def fills(self) -> list[FillRecord]:
        return [
            FillRecord(time, Side(side), price, size, fee, after, mark, spot, mark_price)
            for time, side, price, size, fee, after, mark, spot, mark_price in self._rows(
                "paper_fills", "time, side, price, size, fee, after, mark, spot, mark_price", "time"
            )
        ]

    def hours(self) -> list[HourRecord]:
        return [
            HourRecord(*row)
            for row in self._rows(
                "paper_hours",
                "time, close, btc, value, benchmark, funding, rate, mark_price",
                "time",
            )
        ]

    def record(
        self,
        step: StepRecord,
        hours: Sequence[HourRecord],
        fill: FillRecord | None,
        order: OrderRecord | None,
        filled_order: int | None,
    ) -> None:
        """Write one step with everything it did, in one transaction: the hours it closed,
        the fill at its open and the order it placed; `filled_order` is the placement time
        of the order the fill settled."""
        detector, strategy = self._key
        with self._conn:
            self._conn.execute(
                "INSERT INTO paper_steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    detector,
                    strategy,
                    step.time,
                    step.close,
                    None if step.mark is None else step.mark.value,
                    step.position.value,
                    step.usd,
                    step.btc,
                    step.value,
                    step.benchmark,
                    None if step.order is None else step.order.value,
                    step.recorded_at,
                ),
            )
            self._conn.executemany(
                "INSERT INTO paper_hours VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        detector,
                        strategy,
                        h.time,
                        h.close,
                        h.btc,
                        h.value,
                        h.benchmark,
                        h.funding,
                        h.rate,
                        h.mark_price,
                    )
                    for h in hours
                ],
            )
            if fill is not None:
                self._conn.execute(
                    "INSERT INTO paper_fills VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        detector,
                        strategy,
                        fill.time,
                        fill.side.value,
                        fill.price,
                        fill.size,
                        fill.fee,
                        fill.after,
                        fill.mark,
                        fill.spot,
                        fill.mark_price,
                    ),
                )
            if filled_order is not None:
                self._conn.execute(
                    "UPDATE paper_orders SET filled_at = ? WHERE detector = ? AND strategy = ? "
                    "AND placed_at = ?",
                    (step.time, detector, strategy, filled_order),
                )
            if order is not None:
                self._conn.execute(
                    "INSERT INTO paper_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        detector,
                        strategy,
                        order.placed_at,
                        order.side.value,
                        order.mark,
                        order.spot,
                        order.mark_price,
                        order.filled_at,
                    ),
                )

    def set_rates(self, rates: dict[int, float]) -> int:
        """Fill in Kraken's rate on every hour still without one, where `rates` (by the hour's
        start time) holds the rate published for the hour the close starts; answers how many."""
        detector, strategy = self._key
        missing = self._conn.execute(
            "SELECT time FROM paper_hours WHERE detector = ? AND strategy = ? AND rate IS NULL",
            self._key,
        ).fetchall()
        found = [(rates[t + HOUR], detector, strategy, t) for (t,) in missing if t + HOUR in rates]
        with self._conn:
            self._conn.executemany(
                "UPDATE paper_hours SET rate = ? WHERE detector = ? AND strategy = ? AND time = ?",
                found,
            )
        return len(found)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PaperStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class Notice:
    """A line the loop has to say that is no step and no fill: a warning, mostly."""

    text: str


Event = StepRecord | FillRecord | Notice
"""What the loop reports as it goes: one per step, one per fill, and the notices."""


def missing_candles(unreachable: tuple[int, int], label: str) -> str:
    first, last = unreachable
    return (
        f"the {label} candles from {iso(first)} to {iso(last)} are missing and the endpoint "
        f"cannot reach them: it reaches back only {REST_REACH} candles"
    )


class Loop:
    """The paper-trading loop of one detector and one strategy over one store.

    `start` catches up, rebuilds the state from the whole store and consumes
    what arrived while the loop was stopped; `tick` catches up and consumes
    the candles that have closed since; `wait` says how long until the next
    one. `run` drives it until stopped.
    """

    def __init__(
        self,
        store: CandleStore,
        paper: PaperStore,
        detector: Detector,
        strategy: Strategy,
        source: CandleSource,
        futures: FuturesSource,
    ) -> None:
        if store.timeframe is not detector.timeframe:
            raise ValueError(
                f"the loop needs the {detector.timeframe.label} store for {detector.name}, not "
                f"the {store.timeframe.label} one"
            )
        self._store = store
        self._paper = paper
        self._detector = detector
        self._strategy = strategy
        self._source = source
        self._futures = futures
        self._size = detector.timeframe.seconds
        self._replayer = Replayer(detector)
        self._walker = Walker(strategy)
        self._newest: int | None = None
        """The last candle consumed, history included."""
        self._pending: OrderRecord | None = None
        """The recorded order awaiting its fill, so the fill keeps the market read for it."""

    @property
    def newest(self) -> int | None:
        return self._newest

    @property
    def first_step(self) -> int | None:
        return self._walker.account_from

    def start(self, now: int) -> list[Event]:
        """Catch up, replay the whole store to rebuild the state, consume the steps that
        arrived while the loop was stopped and fill in the funding rates since published.

        Raises `Refused` when the loop has steps and the stop was longer than
        the endpoint's reach, or when the stored candles no longer produce the
        recorded fills. A loop without steps starts with whatever the store
        holds: a hole before its first step is history, warned about.
        """
        events: list[Event] = []
        first = self._paper.first_step()
        caught = catch_up(self._store, self._source, now=now)
        label = self._detector.timeframe.label
        if caught.unreachable is not None:
            if first is not None:
                raise Refused(
                    "The loop was stopped for longer than the endpoint's reach: "
                    f"{missing_candles(caught.unreachable, label)}. Import the quarterly "
                    f"archive that covers them first (`tradingbot import --timeframe "
                    f"{self._detector.timeframe.value} <csv>`), then start the loop again; it "
                    "continues from its last step. Nothing was written."
                )
            events.append(
                Notice(
                    f"Warning: {missing_candles(caught.unreachable, label)}. They lie before "
                    "the loop's first step, so the loop starts with that hole in the "
                    "detector's history and keeps it: the loop rebuilds its state from the "
                    "stored candles on every start, and refuses a store that no longer "
                    "produces its recorded fills."
                )
            )
        recorded = {s.time: s for s in self._paper.steps()}
        fills = {f.time: f for f in self._paper.fills()}
        orders = {o.placed_at: o for o in self._paper.orders()}
        self._walker.account_from = first
        for candle in self._store.read():
            step, stepped = self._advance(candle)
            if first is not None and candle.time >= first:
                if candle.time in recorded:
                    self._verify(candle, stepped, recorded[candle.time], fills.get(candle.time))
                    if stepped.order is not None:
                        self._pending = orders[candle.time]
                else:
                    live = now < candle.time + 2 * self._size
                    events.extend(self._record(candle, step, stepped, now, live=live))
            self._newest = candle.time
        if first is not None:
            events.extend(self._fill_in_rates())
        return events

    def fetch(self, now: int) -> None:
        """Store the candles that have completed since; raises `Refused` when the endpoint
        could not reach back to the loop's last candle."""
        caught = catch_up(self._store, self._source, now=now)
        if caught.unreachable is not None:
            raise Refused(
                "The loop fell behind the endpoint's reach: "
                f"{missing_candles(caught.unreachable, self._detector.timeframe.label)}. "
                "Import the quarterly archive that covers them, then start the loop again."
            )

    def consume(self, now: int) -> list[Event]:
        """Consume every stored candle newer than the last one consumed, as steps."""
        events: list[Event] = []
        closed_an_hour = False
        since = None if self._newest is None else self._newest + self._size
        for candle in self._store.read(start=since):
            if self._walker.account_from is None:
                self._walker.account_from = candle.time
            step, stepped = self._advance(candle)
            live = now < candle.time + 2 * self._size
            events.extend(self._record(candle, step, stepped, now, live=live))
            closed_an_hour = closed_an_hour or bool(stepped.hours)
            self._newest = candle.time
        if closed_an_hour:
            events.extend(self._fill_in_rates())
        return events

    def tick(self, now: int) -> list[Event]:
        """`fetch` then `consume`."""
        self.fetch(now)
        return self.consume(now)

    def wait(self, now: int) -> int:
        """Seconds until the next candle is due, `GRACE` after its close; `RETRY` when it is
        due already and has not appeared."""
        if self._newest is None:
            return RETRY
        due = self._newest + 2 * self._size + GRACE
        return due - now if now < due else RETRY

    def _advance(self, candle: Candle) -> tuple[Step, Stepped]:
        """The candle through the detector, then through the strategy and the account."""
        step = self._replayer.push(candle)
        mark = None
        if step.mark is not None:
            extremes = self._detector.swing_extremes()
            extreme = extremes_by_mark([step.mark], extremes)[step.mark.time]
            mark = MarkWithExtreme(step.mark.kind, step.mark.time, step.mark.price, extreme)
        return step, self._walker.step(candle, step.completed, mark, step.confirmed)

    def _verify(
        self, candle: Candle, stepped: Stepped, step: StepRecord, fill: FillRecord | None
    ) -> None:
        """Raise `Refused` unless the walk over the stored candles did at this step what the
        record says it did: the same fill, the same order, the same position."""
        made = stepped.fill
        if (made is None) != (fill is None) or (
            made is not None
            and fill is not None
            and (made.side is not fill.side or made.price != fill.price)
        ):
            walked = "no fill" if made is None else f"a {made.side.value} at {made.price:,.2f}"
            held = "no fill" if fill is None else f"a {fill.side.value} at {fill.price:,.2f}"
            self._refuse_record(candle, f"the walk makes {walked} where the record holds {held}")
        placed = None if stepped.order is None else stepped.order.side
        if placed is not step.order:
            walked = "no order" if placed is None else f"a {placed.value} order"
            held = "no order" if step.order is None else f"a {step.order.value} order"
            self._refuse_record(candle, f"the walk places {walked} where the record holds {held}")
        if self._walker.position is not step.position:
            self._refuse_record(
                candle,
                f"the walk is {self._walker.position.value} where the record is "
                f"{step.position.value}",
            )
        if made is not None:
            self._pending = None

    def _refuse_record(self, candle: Candle, difference: str) -> None:
        raise Refused(
            f"The stored candles no longer produce the loop's record: at {iso(candle.time)} "
            f"{difference}. The store changed under the loop since it recorded that step. "
            "Nothing was written; `paper report` counts the mismatches."
        )

    def _record(
        self, candle: Candle, step: Step, stepped: Stepped, now: int, *, live: bool
    ) -> list[Event]:
        """Record the step with everything it did; read the market only when the step is
        live, the candle having closed within the last period."""
        events: list[Event] = []
        reading: list[MarkPrice | None] = []

        def mark_price() -> float | None:
            """The ticker, read once per step at most, and only live."""
            if not live:
                return None
            if not reading:
                try:
                    reading.append(self._futures.mark_price())
                except Exception as failed:  # noqa: BLE001 - the step completes without it
                    reading.append(None)
                    events.append(
                        Notice(
                            f"Warning: the Futures ticker failed at {iso(candle.time)} "
                            f"({failed}); the mark price there is missing."
                        )
                    )
            return None if reading[0] is None else reading[0].price

        model = PERPETUAL.name
        hours = [
            HourRecord(
                closed.hour.time,
                closed.hour.close,
                closed.btc[model],
                closed.values[model],
                closed.benchmark,
                closed.funding[model],
                None,
                mark_price(),
            )
            for closed in stepped.hours
        ]
        fill = None
        filled_order = None
        if stepped.fill is not None:
            fill = self._fill_record(stepped.fill, candle)
            filled_order = None if self._pending is None else self._pending.placed_at
            self._pending = None
        order = None
        if stepped.order is not None:
            order = OrderRecord(
                candle.time,
                stepped.order.side,
                stepped.order.mark,
                candle.close,
                mark_price(),
                None,
            )
            self._pending = order
        account = self._walker.account(PERPETUAL)
        record = StepRecord(
            candle.time,
            candle.close,
            None if step.mark is None else step.mark.kind,
            self._walker.position,
            account.usd,
            account.btc,
            account.value(candle.close),
            self._walker.benchmark.value(candle.close),
            None if order is None else order.side,
            now,
        )
        self._paper.record(record, hours, fill, order, filled_order)
        if fill is not None:
            events.append(fill)
        events.append(record)
        return events

    def _fill_record(self, fill: Fill, candle: Candle) -> FillRecord:
        """The fill under the perpetual cost model, with the market read when its order was
        placed; spot is then the candle before, the close the order was placed on."""
        cost = fill.cost(PERPETUAL)
        pending = self._pending
        spot = self._walker.seen[-2].close if pending is None else pending.spot
        return FillRecord(
            candle.time,
            fill.side,
            fill.price,
            cost.size,
            cost.fee,
            cost.after,
            fill.mark,
            spot,
            None if pending is None else pending.mark_price,
        )

    def _fill_in_rates(self) -> list[Event]:
        """Kraken's funding rates onto every recorded hour still without one."""
        try:
            rates = self._futures.funding_rates()
        except Exception as failed:  # noqa: BLE001 - the rates come with a later hour
            return [
                Notice(
                    f"Warning: the Futures funding history failed ({failed}); the real "
                    "funding of the latest hours stays unknown until the next hour."
                )
            ]
        self._paper.set_rates(rates)
        return []


def describe_event(event: Event) -> str:
    """An event as the loop prints it, one line."""
    if isinstance(event, Notice):
        return event.text
    if isinstance(event, FillRecord):
        market = (
            "mark price missing"
            if event.mark_price is None or event.basis is None
            else f"mark price {event.mark_price:,.2f} USD, basis {event.basis:+.3f}%"
        )
        return (
            f"fill {iso(event.time)}  {event.side.value} {event.size:.6f} BTC at "
            f"{event.price:,.2f} USD, fee {event.fee:.2f} USD, account {event.after:,.2f} USD; "
            f"{market}"
        )
    mark = "no mark" if event.mark is None else f"{event.mark.value} mark"
    order = "" if event.order is None else f", {event.order.value} order"
    return (
        f"step {iso(event.time)}  close {event.close:,.2f}  {mark}  {event.position.value}  "
        f"account {event.value:,.2f} USD  holding {event.benchmark:,.2f} USD{order}"
    )


def run(
    loop: Loop,
    now: Callable[[], float],
    sleep: Callable[[float], None],
    out: Callable[[str], None],
) -> None:
    """Tick until stopped: every candle as it closes, `GRACE` seconds after; a failing candle
    source is tried again after `RETRY` seconds, a `Refused` ends the loop."""
    while True:
        moment = int(now())
        try:
            loop.fetch(moment)
        except Refused:
            raise
        except Exception as failed:  # noqa: BLE001 - the endpoint will be back
            out(f"Warning: the candle source failed ({failed}); trying again in {RETRY} seconds.")
            sleep(RETRY)
            continue
        for event in loop.consume(moment):
            out(describe_event(event))
        sleep(loop.wait(int(now())))


# --- the report --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reconciliation:
    """The record against a backtest of the same detector and strategy over the stored
    candles of the loop's period: the fills must agree candle for candle and price for price."""

    expected: int
    """Fills the backtest made."""
    mismatches: int
    """Fills that differ in time, side or price, plus the fills only one side has."""
    first: int | None
    """Time of the first fill the two disagree on."""


def reconcile(
    candles: Sequence[Candle],
    detector: Detector,
    strategy: Strategy,
    account_from: int,
    recorded: Sequence[FillRecord],
) -> Reconciliation:
    """Backtest the strategy on the detector over `candles`, the account from `account_from`,
    and count the fills that differ from the recorded ones."""
    result = score_replayed(replay_all(candles, detector))
    expected = walk(result, strategy, account_from=account_from).fills
    ours = [(f.time, f.side, f.price) for f in recorded]
    theirs = [(f.time, f.side, f.price) for f in expected]
    differing = [i for i, (a, b) in enumerate(zip(ours, theirs, strict=False)) if a != b]
    shorter = min(len(ours), len(theirs))
    extra = abs(len(ours) - len(theirs))
    first = None
    if differing:
        first = min(ours[differing[0]][0], theirs[differing[0]][0])
    elif extra:
        first = (ours if len(ours) > shorter else theirs)[shorter][0]
    return Reconciliation(len(expected), len(differing) + extra, first)


@dataclass(frozen=True)
class Report:
    detector: str
    strategy: str
    steps: list[StepRecord]
    fills: list[FillRecord]
    hours: list[HourRecord]
    reconciliation: Reconciliation

    @property
    def first(self) -> StepRecord:
        return self.steps[0]

    @property
    def last(self) -> StepRecord:
        return self.steps[-1]

    @property
    def growth(self) -> float:
        return self.last.value / STARTING_USD

    @property
    def benchmark_growth(self) -> float:
        return self.last.benchmark / STARTING_USD

    @property
    def share_long(self) -> float:
        """The share of the steps whose close found the account long."""
        return sum(s.position is Position.LONG for s in self.steps) / len(self.steps)


def report(
    paper: PaperStore, store: CandleStore, detector: Detector, strategy: Strategy
) -> Report | None:
    """The loop's record read back and reconciled, or None when the loop has no step yet.
    `detector` and `strategy` are fresh instances for the reconciliation's backtest."""
    steps = paper.steps()
    if not steps:
        return None
    fills = paper.fills()
    candles = store.read(end=steps[-1].time)
    return Report(
        paper.detector,
        paper.strategy,
        steps,
        fills,
        paper.hours(),
        reconcile(candles, detector, strategy, steps[0].time, fills),
    )


def describe_quartiles(values: Sequence[float]) -> str:
    """Three quartiles in percent, inclusive so they never lie outside the readings; the one
    value thrice."""
    q1, q2, q3 = quantiles(values, n=4, method="inclusive") if len(values) > 1 else [values[0]] * 3
    return f"quartiles {q1:+.3f}% / {q2:+.3f}% / {q3:+.3f}%"


def describe_basis(label: str, readings: Sequence[float | None]) -> tuple[str, str]:
    """`label` with the count of readings taken and their quartiles."""
    read = [b for b in readings if b is not None]
    if not readings:
        return label, "none"
    if not read:
        return label, f"0 of {len(readings)} read"
    return label, f"{len(read)} of {len(readings)} read: {describe_quartiles(read)}"


def month_of(time: int) -> str:
    return datetime.fromtimestamp(time, UTC).strftime("%Y-%m")


def describe_funding(hours: Sequence[HourRecord]) -> str:
    """The model's funding against Kraken's over the hours long with a rate published, and the
    hours long without one."""
    long = [h for h in hours if h.btc > 0]
    if not long:
        return "no hour long"
    known = [h for h in long if h.rate is not None]
    modelled = sum(h.funding for h in known)
    real = sum(h.funding_real or 0.0 for h in known)
    hours_ = "hour" if len(known) == 1 else "hours"
    line = f"modelled {modelled:.4f} USD, real {real:.4f} USD over {len(known)} {hours_} long"
    unknown = [h for h in long if h.rate is None]
    if unknown:
        hours_ = "hour" if len(unknown) == 1 else "hours"
        line += (
            f" with a rate published; {len(unknown)} {hours_} long without one "
            f"(modelled {sum(h.funding for h in unknown):.4f} USD)"
        )
    return line


def describe_report(report: Report) -> list[str]:
    """The report as the command prints it."""
    first, last = report.first, report.last
    steps = "step" if len(report.steps) == 1 else "steps"
    fills = "fill" if len(report.fills) == 1 else "fills"
    lines = [
        f"Paper trading {report.strategy} on {report.detector}: {len(report.steps)} {steps} from "
        f"{iso(first.time)} to {iso(last.time)}, {len(report.fills)} {fills}, long "
        f"{report.share_long:.1%} of the closes.",
        f"  {'account':<16} {last.value:,.2f} USD  ({describe_growth(report.growth)})",
        f"  {'holding':<16} {last.benchmark:,.2f} USD  "
        f"({describe_growth(report.benchmark_growth)})",
        f"  {'fills':<16} {len(report.fills)}",
    ]
    for fill in report.fills:
        lines.append(f"    {describe_event(fill).removeprefix('fill ')}")
    label, value = describe_basis("basis at fills", [f.basis for f in report.fills])
    lines.append(f"  {label:<16} {value}")
    label, value = describe_basis("basis at hours", [h.basis for h in report.hours])
    lines.append(f"  {label:<16} {value}")
    lines.append(f"  {'funding':<16} {describe_funding(report.hours)}")
    months = sorted({month_of(h.time) for h in report.hours if h.btc > 0})
    for month in months:
        in_month = [h for h in report.hours if month_of(h.time) == month]
        lines.append(f"    {month:<14} {describe_funding(in_month)}")
    reconciled = report.reconciliation
    expected = "fill" if reconciled.expected == 1 else "fills"
    mismatches = "mismatch" if reconciled.mismatches == 1 else "mismatches"
    first_difference = "" if reconciled.first is None else f" (first at {iso(reconciled.first)})"
    lines.append(
        f"  {'reconciliation':<16} {reconciled.expected} {expected} in the backtest over the same "
        f"candles, {reconciled.mismatches} {mismatches}{first_difference}"
    )
    return lines
