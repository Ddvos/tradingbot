"""The paper-trading bot process: an APScheduler loop around execute_tick.

The two-process design (ROADMAP.md, Slice 5): this bot and the API share
the database and nothing else. Commands (pause/resume/promote) arrive as
DB flags written by the API; every tick reads them fresh.

Ticks fire hourly at HH:00:45 — the grace period lets Kraken finalize the
just-closed candle (the provider drops the still-forming one, so an early
tick would simply see no new bar and no-op). v1 is 1h-only, matching the
primary timeframe.

Run (from backend/):

    uv run python -m tradingbot.live.runner
"""

import logging
from collections.abc import Callable
from datetime import UTC

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from tradingbot.adapters.kraken.provider import KrakenProvider
from tradingbot.adapters.simulated.executor import SimulatedExecutor
from tradingbot.application.execute_tick import execute_tick
from tradingbot.application.persistence import build_postgres_repositories
from tradingbot.application.run_backtest import SLIPPAGE_RATE, TAKER_FEE_RATE
from tradingbot.config.settings import Settings
from tradingbot.live.command_listener import CommandListener

logger = logging.getLogger(__name__)

TICK_SECOND = 45
"""Seconds past the hour to tick — Kraken needs a moment to close the candle."""

COMMAND_POLL_SECONDS = 30
MISFIRE_GRACE_SECONDS = 600
"""A tick that fires late (host asleep, clock jump) still runs within this
window; anything later is skipped — the next tick replays missed bars."""


def build_scheduler(tick: Callable[[], None], poll: Callable[[], object]) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=UTC)
    scheduler.add_job(
        tick,
        CronTrigger(minute=0, second=TICK_SECOND, timezone=UTC),
        id="tick",
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    scheduler.add_job(poll, "interval", seconds=COMMAND_POLL_SECONDS, id="commands")
    return scheduler


def make_tick(settings: Settings) -> Callable[[], None]:
    """Wire the paper tick: live Kraken data, simulated fills, Postgres state."""
    repos = build_postgres_repositories(settings.database_url)
    provider = KrakenProvider()
    executor = SimulatedExecutor(fee_rate=TAKER_FEE_RATE, slippage_rate=SLIPPAGE_RATE)

    def tick() -> None:
        try:
            report = execute_tick(
                provider,
                executor,
                repos,
                symbol=settings.paper_symbol,
                models_dir=settings.models_dir,
                initial_capital=settings.paper_initial_capital,
                set_market=executor.set_market,
            )
        except Exception:  # one bad tick must not take the scheduler down
            logger.exception("tick failed")
            return
        logger.info(
            "tick %s — bar %s, %d trade(s), equity %s",
            report.status,
            report.bar_time,
            report.n_trades,
            report.equity,
        )

    return tick


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings()
    listener = CommandListener(build_postgres_repositories(settings.database_url).bot_commands)
    scheduler = build_scheduler(make_tick(settings), listener.poll)
    logger.info(
        "paper runner up: %s 1h, tick at HH:00:%02d UTC", settings.paper_symbol, TICK_SECOND
    )
    scheduler.start()


if __name__ == "__main__":
    main()
