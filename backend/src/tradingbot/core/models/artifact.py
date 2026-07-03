"""The trained-model artifact: everything inference needs, in one object."""

from dataclasses import dataclass
from datetime import datetime

from xgboost import XGBClassifier


@dataclass(frozen=True)
class TrainMetrics:
    """Validation metrics from the chronological split at training time."""

    auc: float
    ic: float
    """Information coefficient: Spearman rank correlation between predicted
    probability and realized label on the validation window."""
    base_rate: float
    """Fraction of positive labels in the training window."""
    n_train: int
    n_valid: int


@dataclass(frozen=True)
class ModelArtifact:
    model: XGBClassifier
    feature_columns: list[str]
    """Exact column order the model was fitted on; inference must match it."""
    trained_at: datetime
    metrics: TrainMetrics
