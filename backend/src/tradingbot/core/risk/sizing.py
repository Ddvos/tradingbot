"""Position sizing. Pure functions, money in Decimal.

Risk-based sizing answers: "how many units may I hold so that, if my stop is
hit, I lose exactly risk_pct of my balance?" The stop distance defines the
risk, so quantity = (balance * risk_pct) / (stop distance in price units).
"""

from decimal import ROUND_DOWN, Decimal

QUANTITY_QUANTUM = Decimal("0.00000001")

# Fraction of balance usable as notional; the rest stays as cash so slippage
# and fees (unknown until the fill) can never overdraw the account.
COST_BUFFER = Decimal("0.995")


def position_size(
    balance: Decimal,
    entry_price: Decimal,
    atr: Decimal,
    risk_pct: Decimal,
    stop_atr_multiple: Decimal,
) -> Decimal:
    """Quantity risking `risk_pct` of balance if the ATR-based stop is hit.

    Capped so notional never exceeds the balance (no leverage in v1).
    """
    if atr <= 0:
        raise ValueError(f"ATR must be positive, got {atr}")
    if balance <= 0 or entry_price <= 0:
        return Decimal(0)
    risk_amount = balance * risk_pct
    stop_distance = atr * stop_atr_multiple
    quantity = risk_amount / stop_distance
    max_quantity = balance * COST_BUFFER / entry_price
    return min(quantity, max_quantity).quantize(QUANTITY_QUANTUM, rounding=ROUND_DOWN)


def all_in_size(balance: Decimal, entry_price: Decimal) -> Decimal:
    """Quantity committing the whole balance (minus cost buffer). Buy-and-hold."""
    if balance <= 0 or entry_price <= 0:
        return Decimal(0)
    return (balance * COST_BUFFER / entry_price).quantize(QUANTITY_QUANTUM, rounding=ROUND_DOWN)
