"""The strategy backtest: fills under the two cost models, growth, worst drawdown, the halt
report, trades grouped by the marks that opened and closed them (ADR-0008)."""

from collections.abc import Sequence

import pytest

from tests.walks import quarter_walk
from tradingbot.backtest import (
    PERPETUAL,
    SLIPPAGE,
    SPOT,
    Account,
    Side,
    backtest,
    fill_price,
    growth,
    halt,
    worst_drawdown,
)
from tradingbot.candles import Candle, Timeframe
from tradingbot.detectors import DetectorThree, Level, SwingExtreme
from tradingbot.replay import run
from tradingbot.scoring import SCORING_START
from tradingbot.strategies import Flip, MarkWithExtreme, Position
from tradingbot.turning_points import Kind, TurningPoint

H = 3600
T0 = 1_704_067_200  # 2024-01-01T00:00:00Z, in the 2022-2024 era


def at(hour: int) -> int:
    return T0 + hour * H


def test_a_buy_fills_at_the_open_moved_up_by_the_slippage_and_pays_the_fee_on_its_value() -> None:
    account = Account(SPOT, usd=500.0)

    cost = account.buy(open_=100.0)

    assert fill_price(Side.BUY, 100.0) == pytest.approx(100.05)
    assert SLIPPAGE == 0.0005
    # The whole account goes in: the Bitcoin bought, at the fill price, plus the 0.80% fee on
    # that value, is exactly 500 USD; the fee is 500 x 0.008 / 1.008.
    assert cost.model == "spot"
    assert cost.fee == pytest.approx(3.968253968)
    assert cost.size == pytest.approx((500.0 - 3.968253968) / 100.05)
    assert cost.after == pytest.approx(500.0 - 3.968253968)
    assert account.usd == pytest.approx(0.0)
    assert account.btc == cost.size
    assert account.fees == cost.fee
    assert account.value(100.05) == pytest.approx(cost.after)


def test_a_sell_fills_at_the_open_moved_down_by_the_slippage_and_pays_the_fee_on_its_value() -> (
    None
):
    account = Account(PERPETUAL, usd=0.0, btc=2.0)

    cost = account.sell(open_=200.0)

    assert fill_price(Side.SELL, 200.0) == pytest.approx(199.9)
    # 2 Bitcoin at 199.90 is 399.80 USD; the 0.05% fee on that is 0.1999.
    assert cost.fee == pytest.approx(0.1999)
    assert cost.size == 2.0
    assert cost.after == pytest.approx(399.80 - 0.1999)
    assert account.btc == 0.0
    assert account.usd == pytest.approx(399.80 - 0.1999)


def test_funding_takes_a_share_of_the_position_at_an_hourly_close_only_while_long() -> None:
    perpetual = Account(PERPETUAL, usd=0.0, btc=2.0)
    spot = Account(SPOT, usd=0.0, btc=2.0)
    flat = Account(PERPETUAL, usd=500.0)

    # 2 Bitcoin at a close of 1,000 is a position of 2,000 USD; 0.00125% of it is 0.025 USD,
    # drawn from the USD side so the position itself stays whole.
    assert perpetual.fund(close=1000.0) == pytest.approx(0.025)
    assert perpetual.usd == pytest.approx(-0.025)
    assert perpetual.btc == 2.0
    assert perpetual.funding == pytest.approx(0.025)
    assert spot.fund(close=1000.0) == 0.0
    assert flat.fund(close=1000.0) == 0.0


def test_the_cost_models_are_those_of_adr_0008() -> None:
    assert (SPOT.name, SPOT.fee, SPOT.funding) == ("spot", 0.008, 0.0)
    assert (PERPETUAL.name, PERPETUAL.fee, PERPETUAL.funding) == ("perpetual", 0.0005, 0.0000125)


def test_growth_divides_the_last_close_by_the_value_before_the_period_began() -> None:
    assert growth([510.0, 520.0, 495.0], before=500.0) == pytest.approx(0.99)
    assert growth([1000.0], before=500.0) == 2.0
    assert growth([], before=500.0) is None


def test_the_worst_drawdown_is_the_largest_fall_from_an_earlier_peak_in_percent() -> None:
    # Peak 500, trough 400: a 20% fall; the later peak of 600 and its 10% fall are smaller.
    assert worst_drawdown([500.0, 450.0, 400.0, 600.0, 540.0]) == pytest.approx(20.0)
    assert worst_drawdown([100.0, 110.0, 121.0]) == 0.0
    # A fall before the peak does not count: 80 came before 100.
    assert worst_drawdown([80.0, 100.0, 95.0]) == pytest.approx(5.0)
    assert worst_drawdown([]) is None


def test_the_halt_report_says_when_a_twenty_percent_fall_would_first_have_fired() -> None:
    times = [1, 2, 3, 4, 5, 6, 7, 8]
    #        peak  -19%  -20%  up    new peak  -20%  -21%  up
    values = [500.0, 405.0, 400.0, 480.0, 600.0, 480.0, 474.0, 520.0]

    report = halt(times, values)

    assert report == (3, 2)


def test_a_second_halt_episode_needs_a_new_peak_first() -> None:
    # Halted at 3; the rise to 460 is no new peak, so the fall to 360 is the same episode.
    assert halt([1, 2, 3, 4, 5], [500.0, 450.0, 400.0, 460.0, 360.0]) == (3, 1)
    assert halt([1, 2, 3], [500.0, 450.0, 401.0]) == (None, 0)
    assert halt([], []) == (None, 0)


class Scripted:
    """An hourly detector that marks the candles it was told to, nothing else."""

    name = "scripted"
    timeframe = Timeframe.H1

    def __init__(self, marks: dict[int, Kind]) -> None:
        self._marks = marks

    def mark(self, candles: Sequence[Candle], levels: Sequence[TurningPoint]) -> Kind | None:
        return self._marks.get(candles[-1].time)

    def levels(self, points: Sequence[TurningPoint]) -> list[Level]:
        return []

    def swing_extremes(self) -> list[SwingExtreme]:
        return []


ZIGZAG = [100, 97, 94, 91, 90, 93, 96, 99, 100, 97, 94, 91, 90, 93, 96, 99, 100, 97, 94, 91, 90]
ZIGZAG += [93, 96, 99, 100, 97, 94, 91, 90, 93, 96, 99, 100]
"""Hourly closes, open equal to close and no wicks, zigzagging 10% so that every leg ends in
a turning point: tops at hours 0, 8, 16, 24 and 32 (100), bottoms at 4, 12, 20 and 28 (90).
Without wicks a mark is a hit within 2% of the extreme: 99 or 100 for a top, 90 or 91 for a
bottom."""


def zigzag() -> list[Candle]:
    return [
        Candle(at(h), float(p), float(p), float(p), float(p), 1.0, 1) for h, p in enumerate(ZIGZAG)
    ]


SCRIPT = {
    at(4): Kind.BOTTOM,  # hit: the bottom at hour 4
    at(8): Kind.TOP,  # hit
    at(12): Kind.BOTTOM,  # hit
    at(14): Kind.TOP,  # false: 96 is 4% under the top at hour 16
    at(18): Kind.BOTTOM,  # false: 94 is 4% over the bottom at hour 20
    at(24): Kind.TOP,  # hit
    at(26): Kind.BOTTOM,  # false
    at(30): Kind.TOP,  # false
}
"""Four round trips for the flip, one per group: opened and closed on a hit, on a hit and a
false mark, on a false mark and a hit, on two false marks."""


def flip_on_the_zigzag():
    result = run(zigzag(), Scripted(SCRIPT), score_from=SCORING_START)
    assert [(m.time, m.hit) for m in result.marks] == [
        (t, k in (at(4), at(8), at(12), at(24))) for t, k in zip(SCRIPT, SCRIPT, strict=True)
    ]
    return backtest(result, Flip())


def test_a_change_of_position_fills_at_the_next_candles_open_against_the_latest_mark() -> None:
    bt = flip_on_the_zigzag()

    assert [(f.side, f.time, f.mark) for f in bt.fills] == [
        (Side.BUY, at(5), at(4)),
        (Side.SELL, at(9), at(8)),
        (Side.BUY, at(13), at(12)),
        (Side.SELL, at(15), at(14)),
        (Side.BUY, at(19), at(18)),
        (Side.SELL, at(25), at(24)),
        (Side.BUY, at(27), at(26)),
        (Side.SELL, at(31), at(30)),
    ]
    # Hour 5 opens at 93: a buy fills at 93 x 1.0005; hour 9 opens at 97: a sell at 97 x 0.9995.
    assert bt.fills[0].price == pytest.approx(93.0465)
    assert bt.fills[1].price == pytest.approx(96.9515)
    assert [c.model for c in bt.fills[0].costs] == ["spot", "perpetual"]
    assert bt.detector == "scripted" and bt.strategy == "flip"
    assert bt.timeframe is Timeframe.H1
    assert bt.scored_from == SCORING_START


def test_the_trades_are_grouped_by_the_outcomes_of_the_marks_that_opened_and_closed_them() -> None:
    bt = flip_on_the_zigzag()
    spot = bt.scores[0].score

    assert bt.scores[0].model == "spot"
    assert spot.trades == 4
    assert [(g.opened_on_hit, g.closed_on_hit, g.trades) for g in spot.groups] == [
        (True, True, 1),
        (True, False, 1),
        (False, True, 1),
        (False, False, 1),
    ]
    # The first trade: 500 USD buys at 93.0465 after the 0.80% fee (496.03 USD of Bitcoin,
    # 5.33101 BTC), sold at 96.9515 for 516.85 USD less 4.13 USD fee: 512.71 USD, +3.36% of
    # the 496.03 the trade started with.
    assert spot.groups[0].mean == pytest.approx(3.363, abs=0.001)
    assert spot.groups[0].median == spot.groups[0].mean
    # The fourth trade buys at 91 x 1.0005 and sells at 99 x 0.9995, 8.68% gross; the exit
    # fee takes 0.8% of the proceeds: x 1.08682 x 0.992 is +7.81%.
    assert spot.groups[3].mean == pytest.approx(7.81, abs=0.01)


def test_the_account_is_valued_at_every_close_and_the_benchmark_holds_from_the_first_open() -> None:
    bt = flip_on_the_zigzag()
    spot, perpetual = (s.score for s in bt.scores)

    # The benchmark buys 500 USD of Bitcoin at hour 0's open, 100 x 1.0005, less 0.80%, and
    # ends at hour 32's close of 100: x 0.99156.
    assert spot.benchmark_growth == pytest.approx(1 / (1.0005 * 1.008))
    assert perpetual.benchmark_growth == spot.benchmark_growth
    # Each round trip multiplies the USD by its gross ratio x 0.992 / 1.008, both fees: the
    # four trades at 93 to 97, 93 to 99, 91 to 97 and 91 to 99 (slippage on each side) are
    # x 1.02543, x 1.04657, x 1.04797 and x 1.06957, together x 1.2029.
    assert spot.growth == pytest.approx(1.2029, abs=0.0005)
    assert spot.growth is not None and perpetual.growth is not None
    assert perpetual.growth > spot.growth
    assert spot.fees == pytest.approx(sum(f.costs[0].fee for f in bt.fills))
    assert spot.funding == 0.0
    # Long at the closes of hours 5 to 8, 13 and 14, 19 to 24 and 27 to 30: 16 of 33.
    assert spot.share_long == pytest.approx(16 / 33)
    assert spot.halt_at is None and spot.halt_episodes == 0
    assert spot.worst_drawdown is not None and 0 < spot.worst_drawdown < 10
    assert spot.benchmark_worst_drawdown == pytest.approx(10.0)


def test_funding_is_charged_at_every_hourly_close_spent_long_under_the_perpetual() -> None:
    bt = flip_on_the_zigzag()
    perpetual = bt.scores[1].score

    # The first trade is long at the closes of hours 5, 6, 7 and 8 (93, 96, 99 and 100), with
    # the Bitcoin the perpetual fill bought; the other three trades likewise.
    sizes = [f.costs[1].size for f in bt.fills if f.side is Side.BUY]
    closes = [[93, 96, 99, 100], [93, 96], [91, 90, 93, 96, 99, 100], [91, 90, 93, 96]]
    expected = sum(s * sum(c) * 0.0000125 for s, c in zip(sizes, closes, strict=True))
    assert perpetual.funding == pytest.approx(expected)
    assert bt.scores[1].model == "perpetual"


def test_the_score_is_split_per_era_and_the_verdict_reads_the_perpetual_in_every_era() -> None:
    bt = flip_on_the_zigzag()
    spot = bt.scores[0].score

    assert [e.era.name for e in spot.eras] == ["2016-2018", "2019-2021", "2022-2024"]
    empty = spot.eras[0].score
    assert (empty.growth, empty.benchmark_growth, empty.trades, empty.share_long) == (
        None,
        None,
        0,
        0.0,
    )
    assert spot.eras[2].score.growth == spot.growth
    assert spot.eras[2].score.trades == 4
    assert spot.eras[2].score.eras == ()
    assert bt.passes is True


def test_the_chart_data_holds_the_values_at_every_hourly_close_under_each_model() -> None:
    bt = flip_on_the_zigzag()

    assert bt.values.times == [at(h) for h in range(33)]
    assert list(bt.values.accounts) == ["spot", "perpetual"]
    assert bt.values.accounts["spot"][:5] == [500.0] * 5, "flat until the fill at hour 5"
    assert bt.values.benchmark[0] == pytest.approx(500 / (1.0005 * 1.008))
    growth_ = bt.scores[0].score.growth
    assert growth_ is not None
    assert bt.values.accounts["spot"][-1] == pytest.approx(500 * growth_)
    assert bt.cost_models == (SPOT, PERPETUAL)


class SpyStrategy:
    """A strategy that records what it is handed and never changes its mind."""

    name = "spy"

    def __init__(self) -> None:
        self.asked: list[
            tuple[
                tuple[Candle, ...], tuple[MarkWithExtreme, ...], tuple[TurningPoint, ...], Position
            ]
        ] = []

    def desired(
        self,
        candles: Sequence[Candle],
        marks: Sequence[MarkWithExtreme],
        turning_points: Sequence[TurningPoint],
        position: Position,
    ) -> Position:
        self.asked.append((tuple(candles), tuple(marks), tuple(turning_points), position))
        return position


def test_the_strategy_is_asked_from_the_first_scored_candle_on_and_sees_nothing_later() -> None:
    candles = zigzag()
    from_hour_10 = at(10)
    result = run(candles, Scripted(SCRIPT), score_from=from_hour_10)
    spy = SpyStrategy()

    bt = backtest(result, spy)

    assert bt.scored_from == from_hour_10
    assert len(spy.asked) == 23, "hours 10 to 32"
    for (seen, marks, points, position), candle in zip(spy.asked, candles[10:], strict=True):
        assert seen[-1] == candle
        assert seen == tuple(candles[: len(seen)])
        assert all(m.time <= candle.time for m in marks)
        assert all(p.confirmed_at <= candle.time for p in points)
        assert position is Position.FLAT
    # The marks before hour 10 are history the strategy may read: handed over, never acted on.
    assert [m.time for m in spy.asked[0][1]] == [at(4), at(8)]
    assert [m.time for m in spy.asked[-1][1]] == list(SCRIPT)
    assert bt.fills == []
    # The turning points confirmed so far: the top at hour 8 is confirmed by hour 11's close.
    assert [p.time for p in spy.asked[0][2]] == [at(0), at(4)]
    assert [p.time for p in spy.asked[1][2]] == [at(0), at(4), at(8)]


def test_a_mark_is_handed_over_with_the_swing_extreme_detector_three_measured_it_against() -> None:
    quarters = quarter_walk(hours=600, seed=24)
    result = run(quarters, DetectorThree())
    spy = SpyStrategy()

    backtest(result, spy)

    handed = spy.asked[-1][1]
    assert [(m.kind, m.time, m.price) for m in handed] == [
        (m.kind, m.time, m.price) for m in result.marks
    ]
    assert len(handed) > 10
    for mark in handed:
        # The extreme standing on the mark's candle, on the mark's side: the one read from
        # a candle at or before the mark up to a candle at or after it.
        spans = [
            e
            for e in result.swing_extremes
            if e.kind is mark.kind
            and e.active_from <= mark.time
            and (e.active_until is None or mark.time <= e.active_until)
        ]
        assert len(spans) == 1
        assert mark.extreme is not None and mark.extreme == spans[0].price
        assert mark.extreme > mark.price if mark.kind is Kind.TOP else mark.extreme < mark.price


def test_a_detector_without_swing_extremes_hands_over_marks_without_one() -> None:
    spy = SpyStrategy()

    backtest(run(zigzag(), Scripted(SCRIPT), score_from=SCORING_START), spy)

    assert all(m.extreme is None for m in spy.asked[-1][1])


def test_a_position_still_open_at_the_end_is_a_fill_but_no_trade() -> None:
    script = {at(4): Kind.BOTTOM, at(8): Kind.TOP, at(12): Kind.BOTTOM}

    bt = backtest(run(zigzag(), Scripted(script), score_from=SCORING_START), Flip())

    assert [(f.side, f.time) for f in bt.fills] == [
        (Side.BUY, at(5)),
        (Side.SELL, at(9)),
        (Side.BUY, at(13)),
    ]
    assert bt.scores[0].score.trades == 1
    assert bt.scores[0].score.share_long == pytest.approx((4 + 20) / 33)


def test_describe_strategy_score_prints_the_period_lines_then_one_line_per_era() -> None:
    from tradingbot.backtest import describe_strategy_score

    bt = flip_on_the_zigzag()

    lines = describe_strategy_score(bt.scores[0].score)

    labels = [label for label, _ in lines]
    assert labels == [
        "growth",
        "worst drawdown",
        "trades",
        "fees",
        "funding",
        "time long",
        "hit→hit",
        "hit→false",
        "false→hit",
        "false→false",
        "20% halt",
        "2016-2018",
        "2019-2021",
        "2022-2024",
    ]
    values = dict(lines)
    assert values["growth"] == "×1.20  (benchmark ×0.992)"
    assert values["worst drawdown"].endswith("%  (benchmark 10.0%)")
    assert values["trades"] == "4"
    assert values["fees"].endswith(" USD") and values["funding"] == "0.00 USD"
    assert values["time long"] == "48.5%"
    assert values["hit→hit"] == "1 trade, mean +3.36%, median +3.36%"
    assert values["false→false"] == "1 trade, mean +7.81%, median +7.81%"
    assert values["20% halt"] == "never"
    assert values["2016-2018"].startswith("no candles")
    assert values["2022-2024"].startswith("growth ×1.20 (benchmark ×0.992), worst drawdown ")
    assert "4 trades" in values["2022-2024"] and "hit→hit 1 (+3.36%)" in values["2022-2024"]
    assert values["2022-2024"].endswith("20% halt never")


def test_describe_strategy_score_prints_the_halt_and_the_big_numbers_readably() -> None:
    from tradingbot.backtest import StrategyScore, TradeGroup, describe_strategy_score

    groups = tuple(
        TradeGroup(o, c, 0, None, None)
        for o, c in ((True, True), (True, False), (False, True), (False, False))
    )
    score = StrategyScore(0.0123, 158.4, 99.1, 83.4, 434, 12345.678, 0.5, 0.482, groups, at(3), 7)

    values = dict(describe_strategy_score(score))

    assert values["growth"] == "×0.0123  (benchmark ×158)"
    assert values["worst drawdown"] == "99.1%  (benchmark 83.4%)"
    assert values["fees"] == "12,345.68 USD"
    assert values["hit→hit"] == "0 trades"
    assert values["20% halt"] == "first 2024-01-01T03:00:00Z, 7 episodes"
    assert describe_strategy_score(
        StrategyScore(None, None, None, None, 0, 0.0, 0.0, 0.0, groups, None, 0)
    )[0] == (
        "growth",
        "n/a (no candles)",
    )


def test_describe_verdict_reads_the_bar_of_adr_0008_under_the_perpetual() -> None:
    from tradingbot.backtest import describe_verdict

    bt = flip_on_the_zigzag()

    assert describe_verdict(bt) == (
        "bar (ADR-0008)",
        "growth at least the benchmark's in every era under the perpetual cost model: pass "
        "(2022-2024 ×1.28 vs ×0.992)",
    )
