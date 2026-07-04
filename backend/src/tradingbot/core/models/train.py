"""XGBoost training on a chronological split. Procedural, no tuning.

Hyperparameters are fixed, sane defaults chosen a priori — tuning them
against the validation window before walk-forward exists (Slice 3) would be
search-until-profitable. The split is chronological (never random) and the
first `horizon` rows of the validation window are purged, because their
labels overlap the last training labels.
"""

from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt
import polars as pl
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

from tradingbot.core.models.artifact import ModelArtifact, TrainMetrics
from tradingbot.core.models.dataset import FEATURE_COLUMNS
from tradingbot.core.models.evaluation import information_coefficient

MIN_ROWS = 200


def fit_classifier(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.int8],
    *,
    n_estimators: int = 300,
    max_depth: int = 4,
    learning_rate: float = 0.05,
) -> XGBClassifier:
    """Fit the fixed-hyperparameter XGBoost. Single source of the params:
    the walk-forward (Slice 3) must train exactly the model train_model does."""
    model = XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(x, y)
    return model


def train_model(
    dataset: pl.DataFrame,
    *,
    feature_columns: list[str] | None = None,
    train_fraction: float = 0.7,
    purge_rows: int = 6,
    n_estimators: int = 300,
    max_depth: int = 4,
    learning_rate: float = 0.05,
) -> ModelArtifact:
    """Fit on the first train_fraction chronologically; validate on the rest."""
    features = feature_columns if feature_columns is not None else FEATURE_COLUMNS
    if dataset.height < MIN_ROWS:
        raise ValueError(f"Dataset has {dataset.height} rows; need >= {MIN_ROWS} to train")

    split = int(dataset.height * train_fraction)
    train = dataset.head(split)
    valid = dataset.slice(split + purge_rows)

    x_train = train.select(features).to_numpy()
    y_train = train.get_column("label").to_numpy()
    x_valid = valid.select(features).to_numpy()
    y_valid = valid.get_column("label").to_numpy()

    model = fit_classifier(
        x_train,
        y_train,
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
    )
    probabilities = model.predict_proba(x_valid)[:, 1]

    metrics = TrainMetrics(
        auc=float(roc_auc_score(y_valid, probabilities)),
        ic=information_coefficient(probabilities.tolist(), y_valid.tolist()),
        base_rate=float(y_train.mean()),
        n_train=train.height,
        n_valid=valid.height,
    )
    return ModelArtifact(
        model=model,
        feature_columns=list(features),
        trained_at=datetime.now(UTC),
        metrics=metrics,
    )
