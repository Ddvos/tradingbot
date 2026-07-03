"""Strategy driven by a trained model's predictions.

Long when the predicted probability of hitting the profit target (before the
stop, within the horizon) clears the threshold; flat otherwise. Long-only,
matching the binary label. The threshold is fixed a priori — tuning it
against a backtest is search-until-profitable.
"""

from dataclasses import dataclass

import polars as pl

from tradingbot.core.models.artifact import ModelArtifact
from tradingbot.core.models.dataset import feature_expressions
from tradingbot.core.models.inference import predict_probabilities
from tradingbot.core.signals.signal import Signal


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
