"""The development clamp: nothing reads past the holdout boundary."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from tradingbot.application.holdout import HOLDOUT_START, clamp_to_development


def frame_around(boundary: datetime, before: int, after: int) -> pl.DataFrame:
    """Hourly closes straddling `boundary`: `before` bars under it, `after` from it on."""
    start = boundary - timedelta(hours=before)
    n = before + after
    return pl.DataFrame(
        {
            "timestamp": pl.datetime_range(
                start, start + timedelta(hours=n - 1), interval="1h", time_unit="ms", eager=True
            ).dt.replace_time_zone("UTC"),
            "close": [100.0] * n,
        }
    )


def test_bars_at_and_after_the_boundary_are_dropped() -> None:
    clamped = clamp_to_development(frame_around(HOLDOUT_START, before=5, after=5))

    assert clamped.height == 5
    assert clamped[-1, "timestamp"] < HOLDOUT_START


def test_caller_supplied_end_cannot_cross_the_holdout() -> None:
    far_future = datetime(2030, 1, 1, tzinfo=UTC)

    clamped = clamp_to_development(frame_around(HOLDOUT_START, before=3, after=3), end=far_future)

    assert clamped.height == 3
    assert clamped[-1, "timestamp"] < HOLDOUT_START


def test_earlier_end_clamps_tighter_than_the_holdout() -> None:
    frame = frame_around(HOLDOUT_START, before=10, after=0)
    end = HOLDOUT_START - timedelta(hours=4)

    clamped = clamp_to_development(frame, end=end)

    assert clamped.height == 6
    assert clamped[-1, "timestamp"] < end


def test_nothing_left_raises_instead_of_returning_empty() -> None:
    frame = frame_around(HOLDOUT_START, before=0, after=5)

    with pytest.raises(ValueError, match="No data before development boundary"):
        clamp_to_development(frame)
