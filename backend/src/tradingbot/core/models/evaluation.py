"""Model evaluation helpers. Grows into the full honest suite in Slice 3."""

from typing import cast

from scipy.stats import spearmanr


def information_coefficient(predictions: list[float], outcomes: list[float]) -> float:
    """Spearman rank correlation between predictions and realized outcomes.

    The core question of any signal: do higher predictions actually come with
    better outcomes? Returns nan when either side is constant — that nan is
    itself the sanity signal (a model predicting one value has no IC).
    """
    # cast: scipy's SignificanceResult is opaque to the type checker (scipy 1.18 ships
    # partial annotations); at runtime it is a (statistic, pvalue) named tuple.
    result = cast("tuple[float, float]", spearmanr(predictions, outcomes))
    return float(result[0])
