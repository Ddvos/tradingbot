"""Strategy driven by a trained model's predictions.

Long when the predicted probability of hitting the profit target (before the
stop, within the horizon) clears the threshold; flat otherwise. Long-only,
matching the binary label. The threshold is fixed a priori — tuning it
against a backtest is search-until-profitable.
"""

from dataclasses import dataclass
from decimal import Decimal

import polars as pl

from tradingbot.core.backtest.engine import TradeRules
from tradingbot.core.models.artifact import ModelArtifact
from tradingbot.core.models.dataset import feature_expressions
from tradingbot.core.models.inference import predict_probabilities
from tradingbot.core.signals.signal import Signal

ML_TRADE_RULES = TradeRules(take_profit_atr=Decimal("2.0"))
"""v1 risk rules with the take-profit aligned to the label's 2.0x ATR upper
barrier (see core.models.labeling) instead of the generic 3.0x default."""


@dataclass(frozen=True)
class MLStrategy:
    artifact: ModelArtifact
    threshold: float = 0.6

    def signals(self, ohlcv: pl.DataFrame) -> pl.Series:
        features = (
            ohlcv.with_columns(**feature_expressions())
            .select(self.artifact.feature_columns)
            .with_row_index()
        )
        complete = features.drop_nulls()

        values = [Signal.FLAT.value] * ohlcv.height
        if complete.height > 0:
            probabilities = predict_probabilities(self.artifact, complete.drop("index"))
            rows: list[int] = complete.get_column("index").to_list()
            for row, probability in zip(rows, probabilities.to_list(), strict=True):
                if probability >= self.threshold:
                    values[row] = Signal.LONG.value
        return pl.Series("signal", values)
