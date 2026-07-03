from decimal import Decimal

import pytest

from tradingbot.core.risk.sizing import all_in_size, position_size


def test_risk_based_quantity() -> None:
    # risk = 10000 * 1% = 100; stop distance = 500 * 1.5 = 750; qty = 100/750
    quantity = position_size(
        balance=Decimal(10000),
        entry_price=Decimal(50000),
        atr=Decimal(500),
        risk_pct=Decimal("0.01"),
        stop_atr_multiple=Decimal("1.5"),
    )
    assert quantity == Decimal("0.13333333")


def test_quantity_capped_at_balance_notional() -> None:
    # tiny ATR would suggest qty 666.66 -> notional 66k on a 10k account: capped
    quantity = position_size(
        balance=Decimal(10000),
        entry_price=Decimal(100),
        atr=Decimal("0.1"),
        risk_pct=Decimal("0.01"),
        stop_atr_multiple=Decimal("1.5"),
    )
    assert quantity == Decimal("99.5")  # 10000 * 0.995 / 100


def test_non_positive_atr_raises() -> None:
    with pytest.raises(ValueError, match="ATR"):
        position_size(Decimal(10000), Decimal(100), Decimal(0), Decimal("0.01"), Decimal("1.5"))


def test_zero_balance_gives_zero_quantity() -> None:
    assert position_size(
        Decimal(0), Decimal(100), Decimal(1), Decimal("0.01"), Decimal("1.5")
    ) == Decimal(0)


def test_all_in_size_applies_cost_buffer() -> None:
    assert all_in_size(Decimal(1000), Decimal(100)) == Decimal("9.95")
