"""The paper tick against fakes: gating, idempotence, catch-up, persistence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import polars as pl
import pytest

from tests.fakes import make_fake_repositories
from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.application.execute_tick import TickReport, execute_tick
from tradingbot.application.persistence import Repositories
from tradingbot.core.ports.market_data import Timeframe
from tradingbot.core.ports.storage import StrategyConfigId, StrategyConfigRecord
from tradingbot.core.strategies.ml_strategy import ML_TRADE_RULES

type OhlcvFactory = Callable[[list[float]], pl.DataFrame]

SYMBOL = "PF_XBTUSD"
T0 = datetime(2024, 1, 1, tzinfo=UTC)


@dataclass
class FrameProvider:
    """MarketDataProvider fake: serves a fixed frame of closed bars."""

    frame: pl.DataFrame

    def fetch_ohlcv(self, symbol: str, timeframe: Timeframe, since: datetime) -> pl.DataFrame:
        return self.frame


@pytest.fixture
def repos() -> Repositories:
    return make_fake_repositories()


def promote(repos: Repositories, name: str, params: dict[str, str | int | float | bool]) -> None:
    repos.strategy_configs.add(
        StrategyConfigRecord(id=StrategyConfigId(uuid4()), name=name, params=params, created_at=T0)
    )
    repos.bot_commands.set_promoted(name)


def tick(
    repos: Repositories,
    frame: pl.DataFrame,
    tmp_path: Path,
    hours_after_data: int = 1,
) -> TickReport:
    executor = SimulatedExecutor(fee_rate=Decimal(0), slippage_rate=Decimal(0))
    last_bar: datetime = frame[-1, "timestamp"]
    return execute_tick(
        FrameProvider(frame),
        executor,
        repos,
        symbol=SYMBOL,
        models_dir=tmp_path,
        set_market=executor.set_market,
        now=lambda: last_bar + timedelta(hours=hours_after_data),
    )


def test_paused_skips_everything(repos: Repositories, tmp_path: Path) -> None:
    promote(repos, "hold", {"kind": "hold"})
    repos.bot_commands.set_paused(True)

    report = execute_tick(
        FrameProvider(pl.DataFrame()),
        SimulatedExecutor(fee_rate=Decimal(0), slippage_rate=Decimal(0)),
        repos,
        symbol=SYMBOL,
        models_dir=tmp_path,
    )

    assert report.status == "paused"
    assert repos.paper_account.get() is None


def test_idle_without_promotion(repos: Repositories, tmp_path: Path) -> None:
    report = execute_tick(
        FrameProvider(pl.DataFrame()),
        SimulatedExecutor(fee_rate=Decimal(0), slippage_rate=Decimal(0)),
        repos,
        symbol=SYMBOL,
        models_dir=tmp_path,
    )

    assert report.status == "idle"


def test_promoted_without_config_raises(repos: Repositories, tmp_path: Path) -> None:
    repos.bot_commands.set_promoted("ghost")

    with pytest.raises(ValueError, match="no saved config"):
        execute_tick(
            FrameProvider(pl.DataFrame()),
            SimulatedExecutor(fee_rate=Decimal(0), slippage_rate=Decimal(0)),
            repos,
            symbol=SYMBOL,
            models_dir=tmp_path,
        )


def test_first_tick_opens_and_persists(
    repos: Repositories, tmp_path: Path, make_ohlcv: OhlcvFactory
) -> None:
    promote(repos, "hold", {"kind": "hold"})
    frame = make_ohlcv([100.0] * 60)

    report = tick(repos, frame, tmp_path)

    assert report.status == "executed"
    assert report.n_trades == 0
    position = repos.positions.get_open(SYMBOL)
    assert position is not None
    assert position.side.value == "buy"
    assert position.bars_held == 0
    account = repos.paper_account.get()
    assert account is not None
    assert account.last_bar_time == frame[-1, "timestamp"]
    # zero fees/slippage: all-in entry keeps equity exactly at capital
    assert account.equity == Decimal(10_000)


def test_second_tick_without_new_bar_is_a_noop(
    repos: Repositories, tmp_path: Path, make_ohlcv: OhlcvFactory
) -> None:
    promote(repos, "hold", {"kind": "hold"})
    frame = make_ohlcv([100.0] * 60)
    tick(repos, frame, tmp_path)
    account_before = repos.paper_account.get()

    report = tick(repos, frame, tmp_path, hours_after_data=2)

    assert report.status == "no_new_bar"
    assert repos.paper_account.get() == account_before


def test_catch_up_replays_every_missed_bar(
    repos: Repositories, tmp_path: Path, make_ohlcv: OhlcvFactory
) -> None:
    promote(repos, "hold", {"kind": "hold"})
    tick(repos, make_ohlcv([100.0] * 60), tmp_path)

    report = tick(repos, make_ohlcv([100.0] * 63), tmp_path)

    assert report.status == "executed"
    position = repos.positions.get_open(SYMBOL)
    assert position is not None
    assert position.bars_held == 3  # one per missed bar, exactly like the backtest
    account = repos.paper_account.get()
    assert account is not None
    assert account.cash < Decimal(10_000)  # three bars of funding were charged


def test_signal_exit_writes_the_trade_and_clears_the_position(
    repos: Repositories, tmp_path: Path, make_ohlcv: OhlcvFactory
) -> None:
    promote(repos, "ma", {"kind": "ma_cross", "fast": 2, "slow": 4})
    rising = [100.0 + i for i in range(10)]
    tick(repos, make_ohlcv(rising), tmp_path)
    assert repos.positions.get_open(SYMBOL) is not None

    falling = rising + [109.0 - 3.0 * i for i in range(1, 9)]
    report = tick(repos, make_ohlcv(falling), tmp_path)

    assert report.status == "executed"
    trades = repos.trades.list_trades()
    assert [t.exit_reason for t in trades] == ["signal"]
    assert trades[0].strategy == "ma"
    assert repos.positions.get_open(SYMBOL) is None


def test_ml_rules_keep_the_label_aligned_take_profit() -> None:
    assert ML_TRADE_RULES.take_profit_atr == Decimal("2.0")
