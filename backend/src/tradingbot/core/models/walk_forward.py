"""Purged, embargoed rolling walk-forward splits (López de Prado).

The splitter works on row indices of an already-built dataset (one row per
bar, chronological). Each fold trains on a fixed-size rolling window and
tests on the window that follows it, separated by a gap:

    |------- train (train_bars) -------|- purge -|- embargo -|--- test ---|

- **Purge** covers the label horizon: the last training rows carry
  triple-barrier labels that look up to `horizon` bars into the future, so
  without a gap those labels would peek into the test window.
- **Embargo** is an extra safety buffer on top of the purge, because hourly
  features are serially correlated — a training row 1 bar before the test
  window is nearly the same sample as the first test row.

Folds roll forward by `test_bars`, so the test windows are contiguous and
non-overlapping: concatenated they form one continuous out-of-sample
period. A truncated final fold is kept only if it has at least
`min_test_bars` rows — a 200-bar fold would contribute noise, not signal.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardConfig:
    """Split geometry in bars. Defaults assume 1h bars (CLAUDE.md → ML approach).

    purge_bars must be >= the label horizon; embargo_bars is judgment
    (default one day of hourly bars).
    """

    train_bars: int = 17_520  # ~2 years of 1h bars
    test_bars: int = 2_160  # ~90 days
    purge_bars: int = 6  # = triple-barrier horizon
    embargo_bars: int = 24
    min_test_bars: int = 720  # ~30 days

    def __post_init__(self) -> None:
        for name in ("train_bars", "test_bars", "min_test_bars"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1, got {getattr(self, name)}")
        for name in ("purge_bars", "embargo_bars"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0, got {getattr(self, name)}")
        if self.min_test_bars > self.test_bars:
            raise ValueError(
                f"min_test_bars ({self.min_test_bars}) cannot exceed test_bars ({self.test_bars})"
            )

    @property
    def gap_bars(self) -> int:
        return self.purge_bars + self.embargo_bars


@dataclass(frozen=True)
class Fold:
    """Half-open row ranges into the dataset: [start, end)."""

    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def walk_forward_folds(n_rows: int, config: WalkForwardConfig) -> list[Fold]:
    """Return the rolling folds that fit in `n_rows` dataset rows.

    Raises ValueError when the data cannot host even one fold — silently
    returning [] would let an eval "succeed" on nothing.
    """
    folds: list[Fold] = []
    index = 0
    while True:
        train_start = index * config.test_bars
        train_end = train_start + config.train_bars
        test_start = train_end + config.gap_bars
        test_end = min(test_start + config.test_bars, n_rows)
        if test_end - test_start < config.min_test_bars:
            break
        folds.append(Fold(index, train_start, train_end, test_start, test_end))
        if test_end == n_rows:
            break
        index += 1

    if not folds:
        needed = config.train_bars + config.gap_bars + config.min_test_bars
        raise ValueError(
            f"{n_rows} rows cannot host a single fold; need >= {needed} "
            f"(train {config.train_bars} + gap {config.gap_bars} + "
            f"min test {config.min_test_bars})"
        )
    return folds
