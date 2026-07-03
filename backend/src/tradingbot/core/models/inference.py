"""Prediction with a trained artifact."""

import polars as pl

from tradingbot.core.models.artifact import ModelArtifact


def predict_probabilities(artifact: ModelArtifact, features: pl.DataFrame) -> pl.Series:
    """Probability of the positive label (target hit before stop) per row.

    `features` must contain exactly the artifact's feature columns, in order,
    with no nulls — the caller filters incomplete (warmup) rows.
    """
    if features.columns != artifact.feature_columns:
        raise ValueError(
            f"Feature columns {features.columns} do not match "
            f"the artifact's {artifact.feature_columns}"
        )
    probabilities = artifact.model.predict_proba(features.to_numpy())[:, 1]
    return pl.Series("probability", probabilities, dtype=pl.Float64)
