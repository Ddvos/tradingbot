"""The strategy backtest: a strategy run over a recorded replay with money (ADR-0008).

The account starts flat with a notional 500 USD at the first candle of the
scoring period. From that candle on, at the close of every candle of the
detector's timeframe, the strategy is asked for its desired position, long or
flat, and a change becomes a market order filled at the next candle's open.
Marks before the scoring period are history the strategy may read, never
acted on: a change of position is placed only while the latest mark lies in
the scoring period.

Two cost models, fixed by ADR-0008, are applied to every run, one account
each; the strategy's decisions are the same under both, since it reads no
money. A fill is the next candle's open moved `SLIPPAGE` against the bot, and
pays the model's fee on the fill's value. Under both models the position is
1x: the whole account at the fill. The perpetual pays funding at every hourly
close while long, drawn from the account's USD side, which is margin under the
perpetual and so goes below zero until the sale settles it; a trade's result
therefore carries the funding paid while it was open. The benchmark is one account that
buys Bitcoin at the first candle of the scoring period with one spot fill and
holds; it is the same under both models.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from statistics import median

from tradingbot.candles import Candle, Timeframe, iso, period_start
from tradingbot.detectors import SwingExtreme
from tradingbot.replay import HourBuilder, MarkOutcome, ReplayResult
from tradingbot.scoring import ERAS, Era
from tradingbot.strategies import MarkWithExtreme, Position, Strategy
from tradingbot.turning_points import Kind, TurningPoint

SLIPPAGE = 0.0005
"""How far the next candle's open is moved against the bot at a fill: 0.05%."""

STARTING_USD = 500.0
"""The notional account the backtest starts with, flat, at the first scoring candle."""


@dataclass(frozen=True, slots=True)
class CostModel:
    """The fees and funding a backtest charges for trading one market."""

    name: str
    fee: float
    """The taker fee, as a fraction of the fill's value."""
    funding: float
    """Funding paid at every hourly close while long, as a fraction of the position's value."""


SPOT = CostModel("spot", fee=0.008, funding=0.0)
"""Kraken spot at the entry tier: 0.80% a fill, no funding."""

PERPETUAL = CostModel("perpetual", fee=0.0005, funding=0.0000125)
"""Kraken Futures at the entry tier: 0.05% a fill, and 0.00125% of the position an hour
while long, 11% a year, kept high on purpose (ADR-0008)."""

COST_MODELS = (SPOT, PERPETUAL)
"""Every backtest reports under both, in this order."""


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


def fill_price(side: Side, open_: float) -> float:
    """The next candle's open moved against the bot: up for a buy, down for a sell."""
    return open_ * (1 + SLIPPAGE) if side is Side.BUY else open_ * (1 - SLIPPAGE)


@dataclass(frozen=True, slots=True)
class FillCost:
    """What one fill did to the account under one cost model."""

    model: str
    size: float
    """Bitcoin bought or sold."""
    fee: float
    """The fee paid, in USD."""
    after: float
    """The account's value right after the fill, at the fill price."""


@dataclass
class Account:
    """One account under one cost model: USD and Bitcoin, and the costs paid so far."""

    model: CostModel
    usd: float
    btc: float = 0.0
    fees: float = 0.0
    funding: float = 0.0

    def value(self, price: float) -> float:
        return self.usd + self.btc * price

    def buy(self, open_: float) -> FillCost:
        """All in: the Bitcoin bought at the fill price plus the fee on its value is the
        account's whole USD side."""
        price = fill_price(Side.BUY, open_)
        size = self.usd / (price * (1 + self.model.fee))
        fee = size * price * self.model.fee
        self.usd = 0.0
        self.btc = size
        self.fees += fee
        return FillCost(self.model.name, size, fee, self.value(price))

    def sell(self, open_: float) -> FillCost:
        """All out: the Bitcoin sold at the fill price, less the fee on its value."""
        price = fill_price(Side.SELL, open_)
        size = self.btc
        fee = size * price * self.model.fee
        self.usd += size * price - fee
        self.btc = 0.0
        self.fees += fee
        return FillCost(self.model.name, size, fee, self.value(price))

    def fund(self, close: float) -> float:
        """Pay the hour's funding on the position at `close`, and answer it; nothing while
        flat or under a model without funding."""
        cost = self.btc * close * self.model.funding
        self.usd -= cost
        self.funding += cost
        return cost


DRAWDOWN_HALT = 0.20
"""The fall from the account's peak at which a halt would fire; reported, never applied."""


def growth(values: list[float], before: float) -> float | None:
    """What a period made of the account: its value at the period's last close divided by
    its value at the close before the period began; None for a period without closes."""
    return values[-1] / before if values else None


def worst_drawdown(values: list[float]) -> float | None:
    """The largest fall from an earlier peak over the closes, in percent of that peak;
    None without closes."""
    if not values:
        return None
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak * 100)
    return worst


def halt(times: list[int], values: list[float]) -> tuple[int | None, int]:
    """Whether a `DRAWDOWN_HALT` would have fired over the closes: the time of the first
    close at which it would have, or None, and the number of separate episodes. A new
    episode needs a new peak first: a halt fires once per peak."""
    first: int | None = None
    episodes = 0
    peak = values[0] if values else 0.0
    halted = False
    for time, value in zip(times, values, strict=True):
        if value > peak:
            peak = value
            halted = False
        elif not halted and value <= peak * (1 - DRAWDOWN_HALT):
            halted = True
            episodes += 1
            if first is None:
                first = time
    return first, episodes


@dataclass(frozen=True, slots=True)
class Fill:
    """One market order filled: the record of a trade's leg in the chart data."""

    side: Side
    time: int
    """Start time of the candle the order filled on, at its open."""
    price: float
    """That open moved by the slippage against the bot: the same under both models."""
    mark: int
    """Time of the latest mark when the strategy changed its mind: the mark that caused
    the order, always one in the scoring period."""
    costs: tuple[FillCost, ...]
    """The fill under each cost model, in `COST_MODELS` order."""

    def cost(self, cost_model: CostModel) -> FillCost:
        return next(c for c in self.costs if c.model == cost_model.name)


@dataclass(frozen=True, slots=True)
class Trade:
    """One round trip: a buy and the sale that closed it."""

    entry: Fill
    exit: Fill
    results: dict[str, float]
    """The trade's result under each cost model, by name: the account's value after the
    exit fill less its value after the entry fill, in percent of the latter."""
    opened_on_hit: bool
    """Whether the mark that opened the trade was a hit."""
    closed_on_hit: bool


@dataclass(frozen=True)
class TradeGroup:
    """The trades opened on a mark of one outcome and closed on a mark of another."""

    opened_on_hit: bool
    closed_on_hit: bool
    trades: int
    mean: float | None
    """Mean result in percent; None without trades."""
    median: float | None


GROUPS = ((True, True), (True, False), (False, True), (False, False))
"""The four groups, in the order the score lists them: opened on a hit and closed on a hit,
hit and false mark, false mark and hit, false mark and false mark."""


@dataclass(frozen=True)
class StrategyScore:
    """How a strategy did over a period under one cost model (ADR-0008)."""

    growth: float | None
    """The account's value at the period's last close over its value at the close before
    the period began; None for a period without closes."""
    benchmark_growth: float | None
    worst_drawdown: float | None
    """In percent of the peak; None for a period without closes."""
    benchmark_worst_drawdown: float | None
    trades: int
    """Round trips whose entry filled in the period."""
    fees: float
    """USD paid in fees on the fills of the period."""
    funding: float
    """USD paid in funding at the hourly closes of the period."""
    share_long: float
    """The share of the period's candles whose close found the account long."""
    groups: tuple[TradeGroup, ...]
    """The trades by the outcomes of the marks that opened and closed them: `GROUPS`."""
    halt_at: int | None
    """The first close at which a `DRAWDOWN_HALT` would have fired, or None."""
    halt_episodes: int
    eras: tuple[EraStrategyScore, ...] = ()


@dataclass(frozen=True)
class EraStrategyScore:
    era: Era
    score: StrategyScore


@dataclass(frozen=True)
class CostModelScore:
    model: str
    """The cost model's name."""
    score: StrategyScore


@dataclass(frozen=True)
class ValueSeries:
    """The account's value at a series of closes under each cost model, by name, and the
    benchmark's at the same closes. In the chart data: every hourly close of the scoring
    period, what a later chart draws."""

    times: list[int]
    benchmark: list[float]
    accounts: dict[str, list[float]]

    @classmethod
    def empty(cls) -> ValueSeries:
        return cls([], [], {model.name: [] for model in COST_MODELS})

    def record(
        self, time: int, price: float, accounts: Sequence[Account], benchmark: Account
    ) -> None:
        """Value every account at `price`, the close at `time`."""
        self.times.append(time)
        self.benchmark.append(benchmark.value(price))
        for account in accounts:
            self.accounts[account.model.name].append(account.value(price))


BAR_COST_MODEL = PERPETUAL
"""The cost model the bar of ADR-0008 reads: growth at least the benchmark's in every era."""


@dataclass(frozen=True)
class BacktestResult:
    detector: str
    strategy: str
    timeframe: Timeframe
    scored_from: int
    """The first candle of the scoring period: when the account starts."""
    cost_models: tuple[CostModel, ...]
    fills: list[Fill]
    values: ValueSeries
    scores: tuple[CostModelScore, ...]
    """The strategy score under each cost model, in `cost_models` order."""
    passes: bool
    """The bar of ADR-0008: growth at least the benchmark's in every era that has closes,
    under the perpetual cost model."""


def extremes_by_mark(
    marks: Sequence[MarkOutcome], extremes: Sequence[SwingExtreme]
) -> dict[int, float | None]:
    """The swing extreme each mark was measured against: the extreme of the mark's kind
    whose span of reading candles holds the mark's candle; None for a detector without
    swing extremes."""
    by_kind: dict[Kind, list[SwingExtreme]] = {kind: [] for kind in Kind}
    for extreme in extremes:
        by_kind[extreme.kind].append(extreme)
    starts = {kind: [e.active_from for e in spans] for kind, spans in by_kind.items()}
    found: dict[int, float | None] = {}
    for mark in marks:
        spans = by_kind[mark.kind]
        i = bisect_right(starts[mark.kind], mark.time) - 1
        until = spans[i].active_until if i >= 0 else None
        if i < 0 or (until is not None and mark.time > until):
            found[mark.time] = None
        else:
            found[mark.time] = spans[i].price
    return found


@dataclass(frozen=True, slots=True)
class Order:
    """A change of desired position, awaiting the next candle's open."""

    side: Side
    mark: int
    """Time of the latest mark when the strategy changed its mind: the mark that caused
    the order, always one in the scoring period."""


def fill(order: Order, candle: Candle, accounts: Sequence[Account]) -> Fill:
    """The order filled at the candle's open, under each cost model's account."""
    costs = tuple(
        account.buy(candle.open) if order.side is Side.BUY else account.sell(candle.open)
        for account in accounts
    )
    return Fill(order.side, candle.time, fill_price(order.side, candle.open), order.mark, costs)


@dataclass(frozen=True)
class Walked:
    """Everything the walk produced, before scoring."""

    closes: ValueSeries
    """The account at every candle close of the scoring period, under each cost model
    and for the benchmark."""
    long: list[bool]
    """Per close, whether the account was long."""
    hourly: ValueSeries
    """The same at every hourly close: the chart data."""
    fills: list[Fill]
    trades: list[Trade]
    funding: dict[str, list[tuple[int, float]]]
    """Per cost model, the funding paid at each hourly close, with the hour's start time."""


def walk(result: ReplayResult, strategy: Strategy) -> Walked:
    """Run the strategy over the replay from the first scored candle on, one account per
    cost model and one for the benchmark.

    A change of desired position is placed only while the latest mark lies in
    the scoring period: marks before it are history, never acted on.
    """
    candles, marks, points = result.candles, result.marks, result.turning_points
    account_from = result.scored_from if result.scored_from is not None else candles[0].time
    first = bisect_left(candles, account_from, key=lambda c: c.time)
    first_hour = period_start(account_from, Timeframe.H1)
    hit_of = {m.time: m.hit for m in marks if m.scored}
    extreme_of = extremes_by_mark(marks, result.swing_extremes)
    hours = HourBuilder(result.timeframe)
    accounts = [Account(model, STARTING_USD) for model in COST_MODELS]
    benchmark = Account(SPOT, STARTING_USD)
    closes, hourly = ValueSeries.empty(), ValueSeries.empty()
    long: list[bool] = []
    funding: dict[str, list[tuple[int, float]]] = {model.name: [] for model in COST_MODELS}
    seen: list[Candle] = []
    marks_seen: list[MarkWithExtreme] = []
    points_seen: list[TurningPoint] = []
    next_point = next_mark = 0
    position = Position.FLAT
    order: Order | None = None
    fills: list[Fill] = []

    def close_hour(hour: Candle) -> None:
        """Funding on the position standing at the hour's close, then the hourly values."""
        for account in accounts:
            cost = account.fund(hour.close)
            if cost:
                funding[account.model.name].append((hour.time, cost))
        hourly.record(hour.time, hour.close, accounts, benchmark)

    for i, candle in enumerate(candles):
        completed = hours.push(candle, last=i == len(candles) - 1)
        own_hour = period_start(candle.time, Timeframe.H1)
        # An hour left open by a missing candle closed before this candle opened; the
        # candle's own hour closes with the candle, after any fill at its open.
        earlier = [h for h in completed if first_hour <= h.time < own_hour]
        own = [h for h in completed if h.time == own_hour >= first_hour]
        for hour in earlier:
            close_hour(hour)
        if order is not None:
            fills.append(fill(order, candle, accounts))
            position = Position.LONG if order.side is Side.BUY else Position.FLAT
            order = None
        if i == first:
            benchmark.buy(candle.open)
        seen.append(candle)
        if completed:
            latest_hour = completed[-1].time
            while next_point < len(points) and points[next_point].confirmed_at <= latest_hour:
                points_seen.append(points[next_point])
                next_point += 1
        if next_mark < len(marks) and marks[next_mark].time == candle.time:
            mark = marks[next_mark]
            marks_seen.append(
                MarkWithExtreme(mark.kind, mark.time, mark.price, extreme_of[mark.time])
            )
            next_mark += 1
        for hour in own:
            close_hour(hour)
        if i >= first:
            closes.record(candle.time, candle.close, accounts, benchmark)
            long.append(position is Position.LONG)
            desired = strategy.desired(seen, marks_seen, points_seen, position)
            if desired is not position and marks_seen and marks_seen[-1].time >= account_from:
                side = Side.BUY if desired is Position.LONG else Side.SELL
                order = Order(side, marks_seen[-1].time)
    return Walked(closes, long, hourly, fills, pair_trades(fills, hit_of), funding)


def pair_trades(fills: Sequence[Fill], hit_of: dict[int, bool]) -> list[Trade]:
    """Every buy with the sale that closed it; a position still open at the end is no trade."""
    trades: list[Trade] = []
    for entry, exit_ in zip(fills, fills[1:], strict=False):
        if entry.side is not Side.BUY:
            continue
        results = {
            before.model: (after.after - before.after) / before.after * 100
            for before, after in zip(entry.costs, exit_.costs, strict=True)
        }
        trades.append(Trade(entry, exit_, results, hit_of[entry.mark], hit_of[exit_.mark]))
    return trades


def group_trades(trades: Sequence[Trade], cost_model: CostModel) -> tuple[TradeGroup, ...]:
    """The trades in the four groups of `GROUPS`, with the mean and median result under
    the cost model."""
    groups: list[TradeGroup] = []
    for opened, closed in GROUPS:
        results = [
            t.results[cost_model.name]
            for t in trades
            if t.opened_on_hit is opened and t.closed_on_hit is closed
        ]
        groups.append(
            TradeGroup(
                opened,
                closed,
                len(results),
                sum(results) / len(results) if results else None,
                median(results) if results else None,
            )
        )
    return tuple(groups)


def score_period(
    walked: Walked,
    cost_model: CostModel,
    start: int,
    end: int,
    before: float,
    before_benchmark: float,
) -> StrategyScore:
    """The score under the cost model over the closes with `start <= time < end`;
    `before` and `before_benchmark` are the values at the close before `start`."""
    times = walked.closes.times
    lo, hi = bisect_left(times, start), bisect_left(times, end)
    period = times[lo:hi]
    values = walked.closes.accounts[cost_model.name][lo:hi]
    benchmark = walked.closes.benchmark[lo:hi]
    long = walked.long[lo:hi]
    trades = [t for t in walked.trades if start <= t.entry.time < end]
    halt_at, episodes = halt(period, values)
    return StrategyScore(
        growth=growth(values, before),
        benchmark_growth=growth(benchmark, before_benchmark),
        worst_drawdown=worst_drawdown(values),
        benchmark_worst_drawdown=worst_drawdown(benchmark),
        trades=len(trades),
        fees=sum(f.cost(cost_model).fee for f in walked.fills if start <= f.time < end),
        funding=sum(cost for time, cost in walked.funding[cost_model.name] if start <= time < end),
        share_long=sum(long) / len(long) if long else 0.0,
        groups=group_trades(trades, cost_model),
        halt_at=halt_at,
        halt_episodes=episodes,
    )


def score_walked(walked: Walked, cost_model: CostModel, eras: Sequence[Era]) -> StrategyScore:
    """The score over the whole scoring period and per era under one cost model. The
    starting USD is the value before the whole period and before the first era; a later
    era starts from the last close before it."""
    times = walked.closes.times
    end = times[-1] + 1 if times else 0
    whole = score_period(walked, cost_model, 0, end, STARTING_USD, STARTING_USD)
    scored: list[EraStrategyScore] = []
    for era in eras:
        i = bisect_left(times, era.start)
        before = walked.closes.accounts[cost_model.name][i - 1] if i > 0 else STARTING_USD
        before_benchmark = walked.closes.benchmark[i - 1] if i > 0 else STARTING_USD
        period = score_period(walked, cost_model, era.start, era.end, before, before_benchmark)
        scored.append(EraStrategyScore(era, period))
    return replace(whole, eras=tuple(scored))


def bar_score(scores: Sequence[CostModelScore]) -> StrategyScore:
    """The score the bar of ADR-0008 reads: the one under `BAR_COST_MODEL`."""
    return next(s.score for s in scores if s.model == BAR_COST_MODEL.name)


def beats_benchmark_every_era(score: StrategyScore) -> bool:
    """The bar of ADR-0008: growth at least the benchmark's in every era that has closes."""
    judged = [e.score for e in score.eras if e.score.growth is not None]
    return bool(judged) and all(
        s.benchmark_growth is not None and s.growth is not None and s.growth >= s.benchmark_growth
        for s in judged
    )


def backtest(
    result: ReplayResult, strategy: Strategy, eras: Sequence[Era] = ERAS
) -> BacktestResult:
    """Run the strategy over the replay and score it under both cost models."""
    walked = walk(result, strategy)
    scores = tuple(
        CostModelScore(model.name, score_walked(walked, model, eras)) for model in COST_MODELS
    )
    return BacktestResult(
        result.detector,
        strategy.name,
        result.timeframe,
        result.scored_from if result.scored_from is not None else result.candles[0].time,
        COST_MODELS,
        walked.fills,
        walked.hourly,
        scores,
        beats_benchmark_every_era(bar_score(scores)),
    )


COST_MODELS_ADR = "ADR-0008"
"""The ADR that last fixed the cost models and the bar (ADR-0004): a re-scoring names it."""


def describe_growth(value: float | None) -> str:
    """A growth as the commands print it: three significant figures after a times sign."""
    if value is None:
        return "n/a (no candles)"
    if value >= 100:
        return f"×{value:.0f}"
    if value >= 10:
        return f"×{value:.1f}"
    if value >= 1:
        return f"×{value:.2f}"
    return f"×{value:.3g}"


def describe_percent(value: float | None) -> str:
    return "n/a (no candles)" if value is None else f"{value:.1f}%"


def describe_halt(score: StrategyScore) -> str:
    if score.halt_at is None:
        return "never"
    episodes = "episode" if score.halt_episodes == 1 else "episodes"
    return f"first {iso(score.halt_at)}, {score.halt_episodes} {episodes}"


def group_label(group: TradeGroup) -> str:
    """The group as the commands name it: the mark that opened the trade, then the one
    that closed it."""
    opened = "hit" if group.opened_on_hit else "false"
    closed = "hit" if group.closed_on_hit else "false"
    return f"{opened}→{closed}"


def describe_group(group: TradeGroup) -> str:
    trades = "trade" if group.trades == 1 else "trades"
    if group.mean is None or group.median is None:
        return f"{group.trades} {trades}"
    return f"{group.trades} {trades}, mean {group.mean:+.2f}%, median {group.median:+.2f}%"


def describe_era(score: StrategyScore) -> str:
    """An era on one line: the money numbers, then each group's count and mean."""
    if score.growth is None:
        return "no candles"
    groups = ", ".join(
        f"{group_label(g)} {g.trades}" + (f" ({g.mean:+.2f}%)" if g.mean is not None else "")
        for g in score.groups
    )
    trades = "trade" if score.trades == 1 else "trades"
    return (
        f"growth {describe_growth(score.growth)} (benchmark "
        f"{describe_growth(score.benchmark_growth)}), worst drawdown "
        f"{describe_percent(score.worst_drawdown)} (benchmark "
        f"{describe_percent(score.benchmark_worst_drawdown)}), {score.trades} {trades}, "
        f"fees {score.fees:,.2f} USD, funding {score.funding:,.2f} USD, "
        f"long {score.share_long:.1%}, {groups}, 20% halt {describe_halt(score)}"
    )


def describe_strategy_score(score: StrategyScore) -> list[tuple[str, str]]:
    """The strategy score as (label, value) pairs, in the order the commands print them:
    the period's numbers one per line, the four groups one per line, then one line per
    era. The same shape as `describe_score` for a detector."""
    none = "n/a (no candles)"
    lines = [
        (
            "growth",
            none
            if score.growth is None
            else f"{describe_growth(score.growth)}  (benchmark "
            f"{describe_growth(score.benchmark_growth)})",
        ),
        (
            "worst drawdown",
            none
            if score.worst_drawdown is None
            else f"{describe_percent(score.worst_drawdown)}  (benchmark "
            f"{describe_percent(score.benchmark_worst_drawdown)})",
        ),
        ("trades", str(score.trades)),
        ("fees", f"{score.fees:,.2f} USD"),
        ("funding", f"{score.funding:,.2f} USD"),
        ("time long", f"{score.share_long:.1%}"),
    ]
    lines.extend((group_label(g), describe_group(g)) for g in score.groups)
    lines.append(("20% halt", describe_halt(score)))
    lines.extend((scored.era.name, describe_era(scored.score)) for scored in score.eras)
    return lines


def describe_verdict(result: BacktestResult) -> tuple[str, str]:
    """The bar of ADR-0008 read out: pass or fail, with every judged era's growth against
    the benchmark's under the perpetual cost model."""
    bar = bar_score(result.scores)
    judged = ", ".join(
        f"{e.era.name} {describe_growth(e.score.growth)} vs "
        f"{describe_growth(e.score.benchmark_growth)}"
        for e in bar.eras
        if e.score.growth is not None
    )
    verdict = "pass" if result.passes else "fail"
    return (
        f"bar ({COST_MODELS_ADR})",
        f"growth at least the benchmark's in every era under the {BAR_COST_MODEL.name} cost "
        f"model: "
        f"{verdict} ({judged or 'no era has candles'})",
    )
