"""Runner wiring and command-listener visibility, against fakes."""

import logging

import pytest

from tests.fakes import InMemoryBotCommandRepository
from tradingbot.live.command_listener import CommandListener
from tradingbot.live.runner import TICK_SECOND, build_scheduler


def test_scheduler_registers_tick_and_command_jobs() -> None:
    scheduler = build_scheduler(lambda: None, lambda: None)

    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert set(jobs) == {"tick", "commands"}
    tick_trigger = str(jobs["tick"].trigger)
    assert "minute='0'" in tick_trigger
    assert f"second='{TICK_SECOND}'" in tick_trigger


def test_listener_logs_pause_promote_and_demote(caplog: pytest.LogCaptureFixture) -> None:
    commands = InMemoryBotCommandRepository()
    listener = CommandListener(commands)
    assert listener.poll() is None  # nothing written yet

    with caplog.at_level(logging.INFO):
        commands.set_promoted("hold")
        listener.poll()
        commands.set_paused(True)
        listener.poll()
        commands.set_promoted(None)
        listener.poll()
        listener.poll()  # unchanged state -> no new log lines

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        "strategy 'hold' promoted",
        "bot paused",
        "strategy 'hold' demoted — bot is idle",
    ]
