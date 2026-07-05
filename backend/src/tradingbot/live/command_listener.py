"""Polls the DB command flags between ticks and logs transitions.

The tick itself re-reads the flags — the database is the single source of
truth, so nothing here gates execution. The listener's job is visibility:
a pause or promotion issued mid-hour shows up in the bot's log within a
poll interval instead of silently an hour later.
"""

import logging

from tradingbot.core.ports.storage import BotCommandRepository, BotCommandsRecord

logger = logging.getLogger(__name__)


class CommandListener:
    def __init__(self, commands: BotCommandRepository) -> None:
        self._commands = commands
        self._last: BotCommandsRecord | None = None

    def poll(self) -> BotCommandsRecord | None:
        current = self._commands.get()
        if current is not None:
            self._log_transitions(self._last, current)
        self._last = current
        return current

    @staticmethod
    def _log_transitions(last: BotCommandsRecord | None, current: BotCommandsRecord) -> None:
        was_paused = last.is_paused if last is not None else False
        if current.is_paused != was_paused:
            logger.info("bot %s", "paused" if current.is_paused else "resumed")
        previous = last.promoted_strategy if last is not None else None
        if current.promoted_strategy != previous:
            if current.promoted_strategy is None:
                logger.info("strategy %r demoted — bot is idle", previous)
            else:
                logger.info("strategy %r promoted", current.promoted_strategy)
