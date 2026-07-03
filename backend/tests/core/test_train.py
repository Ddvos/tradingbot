import math
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from tradingbot.core.models.train import train_model


def synthetic_dataset(n: int = 400) -> pl.DataFrame:
    """Deterministic dataset where f1 fully determines the label and f2 is noise."""
    start = datetime(2024, 1, 1, tzinfo=UTC)
    f1 = [float((i % 10) - 5) for i in range(n)]
    f2 = [((i * 7) % 13) / 13 for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=i) for i in range(n)],
            "f1": f1,
            "f2": f2,
            "label": pl.Series([1 if v > 0 else 0 for v in f1], dtype=pl.Int8),
        }
    )


def test_learns_an_obvious_pattern() -> None:
    artifact = train_model(synthetic_dataset(), feature_columns=["f1", "f2"], n_estimators=20)

    assert artifact.metrics.auc > 0.95
    assert math.isfinite(artifact.metrics.ic)
    assert artifact.metrics.ic > 0
    assert artifact.feature_columns == ["f1", "f2"]


def test_split_is_chronological_and_purged() -> None:
    artifact = train_model(
        synthetic_dataset(400), feature_columns=["f1", "f2"], train_fraction=0.7, purge_rows=6
    )

    assert artifact.metrics.n_train == 280
    assert artifact.metrics.n_valid == 400 - 280 - 6


def test_too_small_dataset_raises() -> None:
    with pytest.raises(ValueError, match="rows"):
        train_model(synthetic_dataset(50), feature_columns=["f1", "f2"])
