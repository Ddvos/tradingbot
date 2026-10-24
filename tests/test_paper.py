"""Paper trading: the loop consumes each closing candle once, records the backtest's fills
next to the market's mark price and funding, continues after a restart without a double
fill, refuses a stop longer than the endpoint's reach, and reconciles its record with a
backtest over the same candles (slice 11, ADR-0009)."""

import sqlite3
from pathlib import Path

import pytest

from tests.test_backtest import SCRIPT, Scripted, at, zigzag
from tradingbot.backtest import PERPETUAL, Side
from tradingbot.candles import Candle, Timeframe
from tradingbot.kraken_futures import MarkPrice
from tradingbot.paper import (
    GRACE,
    RETRY,
    FillRecord,
    Loop,
    Notice,
    PaperStore,
    Reconciliation,
    Refused,
    StepRecord,
    describe_event,
    describe_report,
    report,
    run,
)
from tradingbot.store import CandleStore
from tradingbot.strategies import Flip, Position
from tradingbot.turning_points import Kind

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z

BUY_PRICE = 91 * 1.0005
"""Hour 27 opens at 91: the buy the bottom mark at hour 26 causes fills there."""
SELL_PRICE = 99 * 0.9995
"""Hour 31 opens at 99: the sale the top mark at hour 30 causes fills there."""


def fake_source(*candles: Candle):
    """A stand-in for the REST endpoint that answers the candles from `since` on."""

    def source(since: int | None) -> list[Candle]:
        return [c for c in candles if since is None or c.time >= since]

    return source


class FakeFutures:
    """A stand-in for Kraken Futures: one mark price for every read, one set of rates; or
    down, every read failing."""

    def __init__(
        self, price: float = 95.0, rates: dict[int, float] | None = None, down: bool = False
    ) -> None:
        self.price = price
        self.rates = rates or {}
        self.down = down
        self.mark_reads = 0
        self.rate_reads = 0

    def mark_price(self) -> MarkPrice:
        self.mark_reads += 1
        if self.down:
            raise RuntimeError("futures.kraken.com is down")
        return MarkPrice(self.price, 0)

    def funding_rates(self) -> dict[int, float]:
        self.rate_reads += 1
        if self.down:
            raise RuntimeError("futures.kraken.com is down")
        return dict(self.rates)


RATES = {at(h): 0.00001 * h for h in range(40)}
"""Kraken's rate for the hour starting at hour h: 0.001% x h, so each is its own number."""


def loop_on_the_zigzag(
    path: Path, futures: FakeFutures, history: int = 21
) -> tuple[Loop, CandleStore, PaperStore]:
    """The zigzag's first `history` hours stored, the scripted detector and the flip, the
    endpoint answering the whole zigzag."""
    db = path / "candles.sqlite"
    store = CandleStore(db)
    store.upsert(zigzag()[:history])
    paper = PaperStore(db, "scripted", "flip")
    loop = Loop(store, paper, Scripted(SCRIPT), Flip(), fake_source(*zigzag()), futures)
    return loop, store, paper


def tick_through(loop: Loop, hours: range) -> list[StepRecord | FillRecord | Notice]:
    """One tick per hour, `GRACE` seconds after each closes."""
    events = []
    for hour in hours:
        events.extend(loop.tick(now=at(hour + 1) + GRACE))
    return events


def test_the_loops_first_step_is_the_first_candle_to_close_after_it_started(tmp_path: Path) -> None:
    loop, store, paper = loop_on_the_zigzag(tmp_path, FakeFutures())

    assert loop.start(now=at(21)) == [], "hours 0 to 20 are history; hour 21 is still forming"
    assert loop.first_step is None and loop.newest == at(20)
    events = loop.tick(now=at(22) + GRACE)

    assert store.time_range() == (T0, at(21)), "hour 21 was stored"
    assert loop.first_step == at(21)
    [step] = events
    assert isinstance(step, StepRecord)
    assert (step.time, step.close, step.mark, step.position) == (at(21), 93.0, None, Position.FLAT)
    assert (step.usd, step.btc, step.value) == (500.0, 0.0, 500.0)
    # Holding bought 500 USD of Bitcoin at hour 21's open of 93 with one spot fill.
    assert step.benchmark == pytest.approx(500 / (1.0005 * 1.008))
    assert step.order is None and step.recorded_at == at(22) + GRACE
    assert paper.first_step() == at(21) and paper.steps() == [step]


def test_a_step_hands_the_candle_to_the_detector_and_the_strategy_and_an_order_fills_next(
    tmp_path: Path,
) -> None:
    futures = FakeFutures(price=95.0, rates=RATES)
    loop, store, paper = loop_on_the_zigzag(tmp_path, futures)
    loop.start(now=at(21))

    events = tick_through(loop, range(21, 27))

    steps = [e for e in events if isinstance(e, StepRecord)]
    assert [s.time for s in steps] == [at(h) for h in range(21, 27)]
    assert [s.mark for s in steps] == [None, None, None, Kind.TOP, None, Kind.BOTTOM]
    assert [s.order for s in steps] == [None] * 5 + [Side.BUY], "a top while flat does nothing"
    assert all(s.position is Position.FLAT for s in steps)
    [order] = paper.orders()
    assert (order.placed_at, order.side, order.mark, order.spot) == (at(26), Side.BUY, at(26), 94.0)
    assert order.mark_price == 95.0 and order.filled_at is None
    assert order.basis == pytest.approx((95 / 94 - 1) * 100)
    assert paper.pending_order() == order
    assert futures.mark_reads == 6, "one read per live step: the hourly close, the order with it"

    [fill, step] = loop.tick(now=at(28) + GRACE)

    assert isinstance(fill, FillRecord) and isinstance(step, StepRecord)
    assert (fill.time, fill.side, fill.price) == (at(27), Side.BUY, pytest.approx(BUY_PRICE))
    size = 500 / (BUY_PRICE * (1 + PERPETUAL.fee))
    assert fill.size == pytest.approx(size)
    assert fill.fee == pytest.approx(size * BUY_PRICE * PERPETUAL.fee)
    assert fill.after == pytest.approx(500 - fill.fee)
    assert (fill.mark, fill.spot, fill.mark_price) == (at(26), 94.0, 95.0)
    assert fill.basis == pytest.approx((95 / 94 - 1) * 100)
    assert step.position is Position.LONG and step.btc == pytest.approx(size)
    assert paper.fills() == [fill]
    assert paper.pending_order() is None
    assert paper.orders()[0].filled_at == at(27)


def test_funding_is_the_models_at_every_hourly_close_long_and_krakens_rate_is_filled_in(
    tmp_path: Path,
) -> None:
    futures = FakeFutures(price=95.0, rates=RATES)
    loop, store, paper = loop_on_the_zigzag(tmp_path, futures)
    loop.start(now=at(21))

    tick_through(loop, range(21, 29))

    hours = paper.hours()
    assert [h.time for h in hours] == [at(h) for h in range(21, 29)]
    flat = hours[0]
    assert (flat.btc, flat.funding, flat.value, flat.mark_price) == (0.0, 0.0, 500.0, 95.0)
    assert flat.basis == pytest.approx((95 / 93 - 1) * 100)
    long = hours[6]
    size = 500 / (BUY_PRICE * (1 + PERPETUAL.fee))
    assert long.time == at(27) and long.close == 91.0
    assert long.btc == pytest.approx(size)
    assert long.funding == pytest.approx(size * 91 * PERPETUAL.funding)
    assert long.value == pytest.approx(size * 91 - long.funding)
    # Kraken's rate for the same hour, charged at its close on the position valued at the
    # mark price read there.
    assert long.rate == RATES[at(27)]
    assert long.funding_real == pytest.approx(RATES[at(27)] * size * 95)
    assert all(h.rate == RATES[h.time] for h in hours)
    assert futures.rate_reads == 8, "the history is read once per hourly close"


def test_a_restart_rebuilds_the_state_consumes_the_stopped_hours_and_double_fills_nothing(
    tmp_path: Path,
) -> None:
    futures = FakeFutures(price=95.0, rates=RATES)
    loop, store, paper = loop_on_the_zigzag(tmp_path, futures)
    loop.start(now=at(21))
    tick_through(loop, range(21, 28))
    assert [f.time for f in paper.fills()] == [at(27)]

    # Stopped after hour 27, started again 15 seconds after hour 29 closed: a stop shorter
    # than the reach, two hours to catch up on.
    restarted = Loop(
        store, paper, Scripted(SCRIPT), Flip(), fake_source(*zigzag()), FakeFutures(96.0, RATES)
    )
    events = restarted.start(now=at(30) + GRACE)

    assert [(type(e).__name__, e.time) for e in events if not isinstance(e, Notice)] == [
        ("StepRecord", at(28)),
        ("StepRecord", at(29)),
    ]
    assert restarted.first_step == at(21) and restarted.newest == at(29)
    hours = {h.time: h for h in paper.hours()}
    assert hours[at(28)].mark_price is None, "hour 28 closed while the loop was stopped"
    assert hours[at(29)].mark_price == 96.0, "hour 29 closed just before the start"
    assert hours[at(28)].rate == RATES[at(28)], "its rate was filled in at the start"

    tick_through(restarted, range(30, 33))

    fills = paper.fills()
    assert [(f.time, f.side) for f in fills] == [(at(27), Side.BUY), (at(31), Side.SELL)]
    assert fills[1].price == pytest.approx(SELL_PRICE)
    assert fills[1].mark_price == 96.0 and fills[1].spot == 96.0, "the top mark's close"
    assert [s.time for s in paper.steps()] == [at(h) for h in range(21, 33)]
    assert [s.position for s in paper.steps()][6:] == [Position.LONG] * 4 + [Position.FLAT] * 2
    assert len(paper.hours()) == 12 and len(paper.orders()) == 2


def test_a_stop_longer_than_the_reach_is_refused_with_the_import_instruction(
    tmp_path: Path,
) -> None:
    futures = FakeFutures(rates=RATES)
    loop, store, paper = loop_on_the_zigzag(tmp_path, futures)
    loop.start(now=at(21))
    tick_through(loop, range(21, 28))
    recorded = paper.steps()
    # The endpoint answers its full reach of 720 candles plus the forming one, the oldest
    # of them four hours after the store's newest.
    far = [Candle(at(32 + i), 100.0, 100.0, 100.0, 100.0, 1.0, 1) for i in range(721)]
    restarted = Loop(store, paper, Scripted(SCRIPT), Flip(), fake_source(*far), futures)

    with pytest.raises(Refused) as refused:
        restarted.start(now=at(32 + 721) + GRACE)

    message = str(refused.value)
    assert "longer than the endpoint's reach" in message
    assert "2024-01-02T04:00:00Z to 2024-01-02T07:00:00Z" in message, "hours 28 to 31"
    assert "Import the quarterly archive" in message and "import --timeframe 1h" in message
    assert paper.steps() == recorded, "nothing was written"


def test_falling_behind_the_reach_while_running_is_refused_too(tmp_path: Path) -> None:
    loop, store, paper = loop_on_the_zigzag(tmp_path, FakeFutures())
    loop.start(now=at(21))
    tick_through(loop, range(21, 23))
    far = [Candle(at(27 + i), 100.0, 100.0, 100.0, 100.0, 1.0, 1) for i in range(721)]
    behind = Loop(store, paper, Scripted(SCRIPT), Flip(), fake_source(*zigzag()), FakeFutures())
    behind.start(now=at(23) + GRACE)
    behind._source = fake_source(*far)  # the machine slept; the endpoint moved on

    with pytest.raises(Refused, match="fell behind"):
        behind.tick(now=at(27 + 721) + GRACE)


def test_a_first_start_takes_the_store_as_it_is_and_warns_about_a_hole_before_the_loop(
    tmp_path: Path,
) -> None:
    db = tmp_path / "candles.sqlite"
    store = CandleStore(db)
    store.upsert(zigzag()[:5])  # the archive ended at hour 4
    far = [Candle(at(9 + i), 100.0, 100.0, 100.0, 100.0, 1.0, 1) for i in range(721)]
    paper = PaperStore(db, "scripted", "flip")
    loop = Loop(store, paper, Scripted(SCRIPT), Flip(), fake_source(*far), FakeFutures())

    events = loop.start(now=at(9 + 721) + GRACE)

    [notice] = events
    assert isinstance(notice, Notice)
    assert notice.text.startswith("Warning: the hourly candles from 2024-01-01T05:00:00Z to ")
    assert "before the loop's first step" in notice.text and "hole" in notice.text
    assert loop.first_step is None and loop.newest == at(9 + 720)
    assert paper.steps() == []


def test_a_missing_futures_answer_leaves_the_basis_empty_and_the_step_complete(
    tmp_path: Path,
) -> None:
    down = FakeFutures(down=True)
    loop, store, paper = loop_on_the_zigzag(tmp_path, down)
    loop.start(now=at(21))

    events = tick_through(loop, range(21, 28))

    notices = [e.text for e in events if isinstance(e, Notice)]
    assert len(notices) == 14, "the ticker and the funding history, once per hour each"
    assert notices[0].startswith("Warning: the Futures ticker failed at 2024-01-01T21:00:00Z")
    assert "mark price there is missing" in notices[0]
    assert "funding history failed" in notices[1]
    steps = [e for e in events if isinstance(e, StepRecord)]
    assert [s.time for s in steps] == [at(h) for h in range(21, 28)]
    [fill] = paper.fills()
    assert fill.time == at(27) and fill.price == pytest.approx(BUY_PRICE)
    assert (fill.mark_price, fill.basis) == (None, None)
    assert all(h.mark_price is None and h.basis is None and h.rate is None for h in paper.hours())
    assert paper.orders()[0].mark_price is None
    assert down.mark_reads == 7, "tried once per step, not twice for the order"


def test_a_store_that_no_longer_produces_the_recorded_fills_is_refused(tmp_path: Path) -> None:
    loop, store, paper = loop_on_the_zigzag(tmp_path, FakeFutures(rates=RATES))
    loop.start(now=at(21))
    tick_through(loop, range(21, 29))
    # An import rewrote hour 27: it now opens at 95, so the recorded buy at 91.05 no longer
    # follows from the store.
    store.upsert([Candle(at(27), 95.0, 95.0, 91.0, 91.0, 1.0, 1)])
    recorded = (paper.steps(), paper.fills())
    restarted = Loop(
        store, paper, Scripted(SCRIPT), Flip(), fake_source(*zigzag()), FakeFutures(rates=RATES)
    )

    with pytest.raises(Refused) as refused:
        restarted.start(now=at(30) + GRACE)

    message = str(refused.value)
    assert "no longer produce the loop's record" in message
    assert "2024-01-02T03:00:00Z" in message and "95.05" in message and "91.05" in message
    assert (paper.steps(), paper.fills()) == recorded


def test_the_wait_runs_to_grace_seconds_after_the_next_close_then_retries(tmp_path: Path) -> None:
    loop, store, paper = loop_on_the_zigzag(tmp_path, FakeFutures())
    assert loop.wait(now=at(21)) == RETRY, "nothing consumed yet"
    loop.start(now=at(21))
    loop.tick(now=at(22) + GRACE)

    assert loop.wait(now=at(22) + GRACE) == H, "hour 22 closes at 23:00; ask at 23:00:15"
    assert loop.wait(now=at(23) + GRACE + 5) == RETRY, "due and not there yet"


def test_the_loop_needs_the_store_of_the_detectors_timeframe(tmp_path: Path) -> None:
    db = tmp_path / "candles.sqlite"
    with pytest.raises(ValueError, match="hourly store"):
        Loop(
            CandleStore(db, Timeframe.M15),
            PaperStore(db, "scripted", "flip"),
            Scripted(SCRIPT),
            Flip(),
            fake_source(),
            FakeFutures(),
        )


def test_the_record_refuses_a_second_step_at_the_same_time() -> None:
    paper = PaperStore(":memory:", "scripted", "flip")
    step = StepRecord(T0, 1.0, None, Position.FLAT, 500.0, 0.0, 500.0, 500.0, None, T0)
    paper.record(step, [], None, None, None)

    with pytest.raises(sqlite3.IntegrityError):
        paper.record(step, [], None, None, None)


def test_two_loops_in_one_file_never_mix() -> None:
    first = PaperStore(":memory:", "scripted", "flip")
    step = StepRecord(T0, 1.0, None, Position.FLAT, 500.0, 0.0, 500.0, 500.0, None, T0)
    first.record(step, [], None, None, None)
    other = PaperStore(":memory:", "three", "flip")

    assert first.steps() == [step] and other.steps() == [] and other.first_step() is None


class Clock:
    """A clock the fake sleep moves; it stops the run after a number of sleeps."""

    def __init__(self, now: int, sleeps: int) -> None:
        self.now = float(now)
        self.sleeps = sleeps
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        if len(self.slept) == self.sleeps:
            raise KeyboardInterrupt


def test_run_ticks_once_per_candle_and_prints_a_line_per_step_and_per_fill(tmp_path: Path) -> None:
    loop, store, paper = loop_on_the_zigzag(tmp_path, FakeFutures(price=95.0, rates=RATES))
    loop.start(now=at(21))
    clock = Clock(at(22) + GRACE, sleeps=7)
    lines: list[str] = []

    with pytest.raises(KeyboardInterrupt):
        run(loop, now=clock, sleep=clock.sleep, out=lines.append)

    assert clock.slept == [H] * 7
    assert [line.split("  ")[0] for line in lines] == [
        *(f"step {iso_(h)}" for h in range(21, 27)),
        f"fill {iso_(27)}",
        f"step {iso_(27)}",
    ]
    assert lines[5].endswith("bottom mark  flat  account 500.00 USD  holding 501.11 USD, buy order")
    assert lines[6] == (
        "fill 2024-01-02T03:00:00Z  buy 5.489015 BTC at 91.05 USD, fee 0.25 USD, account "
        "499.75 USD; mark price 95.00 USD, basis +1.064%"
    )
    assert "long  account 499.49 USD" in lines[7]


def iso_(hour: int) -> str:
    from tradingbot.candles import iso

    return iso(at(hour))


def test_run_tries_again_after_the_candle_source_fails(tmp_path: Path) -> None:
    loop, store, paper = loop_on_the_zigzag(tmp_path, FakeFutures())
    loop.start(now=at(21))
    calls = [0]

    def flaky(since: int | None) -> list[Candle]:
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("Kraken OHLC error: EService:Unavailable")
        return fake_source(*zigzag())(since)

    loop._source = flaky
    clock = Clock(at(22) + GRACE, sleeps=2)
    lines: list[str] = []

    with pytest.raises(KeyboardInterrupt):
        run(loop, now=clock, sleep=clock.sleep, out=lines.append)

    assert lines[0] == (
        "Warning: the candle source failed (Kraken OHLC error: EService:Unavailable); trying "
        f"again in {RETRY} seconds."
    )
    assert lines[1].startswith("step 2024-01-01T21:00:00Z")
    assert clock.slept == [RETRY, H - RETRY]


def test_describe_event_prints_a_fill_without_a_mark_price_as_missing() -> None:
    fill = FillRecord(at(27), Side.BUY, BUY_PRICE, 5.489015, 0.25, 499.75, at(26), 94.0, None)

    assert describe_event(fill).endswith("account 499.75 USD; mark price missing")
    assert describe_event(Notice("Warning: x")) == "Warning: x"


# --- the report -------------------------------------------------------------------------------


def recorded_run(path: Path, futures: FakeFutures | None = None) -> tuple[CandleStore, PaperStore]:
    """The zigzag loop run from hour 21 to its end: a buy at 27 and a sale at 31."""
    loop, store, paper = loop_on_the_zigzag(path, futures or FakeFutures(price=95.0, rates=RATES))
    loop.start(now=at(21))
    tick_through(loop, range(21, 33))
    return store, paper


def test_the_report_sets_the_account_against_holding_and_reconciles_with_zero_mismatches(
    tmp_path: Path,
) -> None:
    store, paper = recorded_run(tmp_path)

    reported = report(paper, store, Scripted(SCRIPT), Flip())

    assert reported is not None
    assert reported.reconciliation == Reconciliation(expected=2, mismatches=0, first=None)
    assert [f.time for f in reported.fills] == [at(27), at(31)]
    assert len(reported.steps) == 12 and len(reported.hours) == 12
    # Bought at 91.05 and sold at 98.95 with two fees of 0.05% and four hours of funding;
    # holding bought at 93 and ends at hour 32's close of 100.
    assert reported.growth == pytest.approx(SELL_PRICE / BUY_PRICE * (1 - 0.0005) ** 2, abs=0.0002)
    assert reported.benchmark_growth == pytest.approx(100 / 93 / (1.0005 * 1.008))
    assert reported.share_long == pytest.approx(4 / 12), "long at the closes of hours 27 to 30"


def test_the_report_counts_one_mismatch_when_a_fill_is_edited(tmp_path: Path) -> None:
    store, paper = recorded_run(tmp_path)
    with sqlite3.connect(tmp_path / "candles.sqlite") as conn:
        conn.execute("UPDATE paper_fills SET price = price + 1 WHERE time = ?", (at(31),))

    reported = report(paper, store, Scripted(SCRIPT), Flip())

    assert reported is not None
    assert reported.reconciliation == Reconciliation(expected=2, mismatches=1, first=at(31))


def test_the_report_counts_a_fill_only_one_side_has(tmp_path: Path) -> None:
    store, paper = recorded_run(tmp_path)
    with sqlite3.connect(tmp_path / "candles.sqlite") as conn:
        conn.execute("DELETE FROM paper_fills WHERE time = ?", (at(31),))

    reported = report(paper, store, Scripted(SCRIPT), Flip())

    assert reported is not None
    assert reported.reconciliation == Reconciliation(expected=2, mismatches=1, first=at(31))


def test_a_fill_missing_early_counts_once_not_for_every_later_fill(tmp_path: Path) -> None:
    store, paper = recorded_run(tmp_path)
    with sqlite3.connect(tmp_path / "candles.sqlite") as conn:
        conn.execute("DELETE FROM paper_fills WHERE time = ?", (at(27),))

    reported = report(paper, store, Scripted(SCRIPT), Flip())

    assert reported is not None
    assert reported.reconciliation == Reconciliation(expected=2, mismatches=1, first=at(27))


def test_there_is_no_report_before_the_first_step(tmp_path: Path) -> None:
    loop, store, paper = loop_on_the_zigzag(tmp_path, FakeFutures())

    assert report(paper, store, Scripted(SCRIPT), Flip()) is None


def test_describe_report_prints_the_money_the_fills_the_basis_the_funding_and_the_check(
    tmp_path: Path,
) -> None:
    store, paper = recorded_run(tmp_path)
    reported = report(paper, store, Scripted(SCRIPT), Flip())
    assert reported is not None

    lines = describe_report(reported)

    assert lines[0] == (
        "Paper trading flip on scripted: 12 steps from 2024-01-01T21:00:00Z to "
        "2024-01-02T08:00:00Z, 2 fills, long 33.3% of the closes, 4 of 12 hourly closes."
    )
    assert lines[1].startswith("  account          542.") and "(×1.09)" in lines[1]
    assert lines[2].startswith("  holding          533.") and "(×1.07" in lines[2]
    assert lines[3] == "  fills            2"
    assert lines[4].startswith("    2024-01-02T03:00:00Z  buy 5.489015 BTC at 91.05 USD")
    assert lines[5].startswith("    2024-01-02T07:00:00Z  sell 5.489015 BTC at 98.95 USD")
    assert lines[5].endswith("mark price 95.00 USD, basis -1.042%"), "95 over hour 30's close of 96"
    # The basis at the two fills: +1.064% (95 over 94) and -1.042% (95 over 96).
    assert lines[6] == "  basis at fills   2 of 2 read: quartiles -0.515% / +0.011% / +0.537%"
    assert lines[7].startswith("  basis at hours   12 of 12 read: quartiles ")
    assert lines[8].startswith("  funding          modelled 0.0")
    assert lines[8] == "  funding          modelled 0.0254 USD, real 0.5945 USD over 4 hours long"
    assert lines[9].startswith("    2024-01        modelled 0.0")
    assert lines[10] == (
        "  reconciliation   2 fills in the backtest over the same candles, 0 mismatches"
    )


def test_describe_report_says_which_hours_long_have_no_rate_yet(tmp_path: Path) -> None:
    store, paper = recorded_run(tmp_path, FakeFutures(price=95.0, rates={at(27): 0.00001}))
    reported = report(paper, store, Scripted(SCRIPT), Flip())
    assert reported is not None

    lines = describe_report(reported)

    funding = next(line for line in lines if line.startswith("  funding"))
    assert "over 1 hour long with a rate published; 3 hours long without one (modelled 0.0" in (
        funding
    )
    assert any("0 of 12 read" in line or "12 of 12 read" in line for line in lines)
