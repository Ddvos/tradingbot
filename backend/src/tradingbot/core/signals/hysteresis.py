"""Probability → signal mapping with hysteresis (HYPOTHESES.md → H2 iteration 2).

A single threshold flips the position every time the probability wobbles
across it — churn. Separate enter/exit bars make the regime sticky: enter
long on conviction (P ≥ enter_at), stay while the edge is above water
(P ≥ exit_at), leave only when the advantage is gone. The gap between the
bars is the turnover control a bare threshold lacks.
"""

from collections.abc import Sequence

from tradingbot.core.signals.signal import Signal


def hysteresis_signals(
    probabilities: Sequence[float], *, enter_at: float, exit_at: float
) -> list[str]:
    """One Signal value per probability: a sticky long/flat regime."""
    if not exit_at < enter_at:
        raise ValueError(f"exit_at ({exit_at}) must be below enter_at ({enter_at})")
    values: list[str] = []
    is_long = False
    for probability in probabilities:
        is_long = probability >= (exit_at if is_long else enter_at)
        values.append(Signal.LONG.value if is_long else Signal.FLAT.value)
    return values
