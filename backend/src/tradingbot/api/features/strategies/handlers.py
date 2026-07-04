"""Strategies feature: config repository port → response schemas."""

from tradingbot.api.features.strategies.schemas import StrategyConfigSummary
from tradingbot.core.ports.storage import StrategyConfigRepository


def list_strategy_configs(configs: StrategyConfigRepository) -> list[StrategyConfigSummary]:
    return [StrategyConfigSummary.from_record(record) for record in configs.list_configs()]
